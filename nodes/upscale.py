import logging
import os
import torch
import comfy.model_management as model_management
import comfy.utils

try:
    import comfy.model_patcher as model_patcher
except ImportError:
    model_patcher = None

try:
    import folder_paths
except ImportError:
    folder_paths = None

try:
    from server import PromptServer
except ImportError:
    PromptServer = None

from spandrel import ImageModelDescriptor, ModelLoader

try:
    from spandrel import MAIN_REGISTRY
    from spandrel_extra_arches import EXTRA_REGISTRY

    MAIN_REGISTRY.add(*EXTRA_REGISTRY)
except Exception:
    pass

from .utils import SUITE_CATEGORY

UPSCALE_CATEGORY = f"{SUITE_CATEGORY}/Upscaling"
RESCALE_METHODS = ["bicubic", "lanczos", "area", "bilinear", "nearest-exact"]

# Bounded RAM cache keyed by (model_path, mtime) so batch loops don't reload .pth/.safetensors every iteration
_UPSCALE_MODEL_CACHE: dict[tuple[str, float], ImageModelDescriptor] = {}


def _list_upscale_models() -> list[str]:
    if folder_paths is not None:
        try:
            models = list(folder_paths.get_filename_list("upscale_models"))
            if models:
                return models
        except Exception:
            pass
    return ["<no upscale models found>"]


def _get_cached_upscale_model(model_name: str) -> ImageModelDescriptor:
    if folder_paths is None:
        raise RuntimeError("ComfyUI folder_paths is unavailable.")

    if hasattr(folder_paths, "get_full_path_or_raise"):
        model_path = folder_paths.get_full_path_or_raise("upscale_models", model_name)
    else:
        model_path = folder_paths.get_full_path("upscale_models", model_name)
        if not model_path or not os.path.isfile(model_path):
            raise FileNotFoundError(f"Upscale model not found: {model_name}")

    try:
        mtime = os.path.getmtime(model_path)
    except Exception:
        mtime = 0.0

    cache_key = (model_path, mtime)
    cached = _UPSCALE_MODEL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    # Evict older cached models cleanly to keep CPU RAM usage low
    if len(_UPSCALE_MODEL_CACHE) >= 2:
        for old_desc in _UPSCALE_MODEL_CACHE.values():
            try:
                old_desc.to("cpu")
            except Exception:
                pass
        _UPSCALE_MODEL_CACHE.clear()

    sd = comfy.utils.load_torch_file(model_path, safe_load=True)
    if "module.layers.0.residual_group.blocks.0.norm1.weight" in sd:
        sd = comfy.utils.state_dict_prefix_replace(sd, {"module.": ""})

    out = ModelLoader().load_from_state_dict(sd).eval()
    if not isinstance(out, ImageModelDescriptor):
        raise ValueError(f"Upscale model '{model_name}' must be a single-image model.")

    if model_patcher is not None and hasattr(model_patcher, "CoreModelPatcher"):
        out.patcher = model_patcher.CoreModelPatcher(
            out.model,
            load_device=model_management.get_torch_device(),
            offload_device=model_management.unet_offload_device(),
        )
    else:
        out.patcher = None

    _UPSCALE_MODEL_CACHE[cache_key] = out
    return out


class WFA_ModelUpscaleResize:
    """
    WFA Model Upscale & Scale: Combines `Load Upscale Model` + `Upscale using Model` + `Upscale Image By`
    into a single fast, VRAM-safe node with RAM model caching, fused NCHW post-scaling (zero extra 4K tensor
    transposes), and a 1-click / wireable `enabled` bypass switch.
    """

    @classmethod
    def INPUT_TYPES(cls):
        models = _list_upscale_models()
        return {
            "required": {
                "image": ("IMAGE",),
                "enabled": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Enabled",
                        "label_off": "Bypass",
                        "tooltip": "When Enabled, upscales with the selected model and scales by `scale_by`. When Bypass, passes `image` straight through in 0ms.",
                    },
                ),
                "model_name": (
                    models,
                    {
                        "default": models[0],
                        "tooltip": "Upscale model from `ComfyUI/models/upscale_models` (cached in RAM across batch loops).",
                    },
                ),
                "method": (
                    RESCALE_METHODS,
                    {
                        "default": "bicubic",
                        "tooltip": "Post-upscale resize interpolation (`bicubic` or `lanczos` give crisp supersampled detail when downscaling e.g. 0.50 after a 4x model).",
                    },
                ),
                "scale_by": (
                    "FLOAT",
                    {
                        "default": 0.50,
                        "min": 0.05,
                        "max": 8.00,
                        "step": 0.01,
                        "tooltip": "Post-model scale multiplier (e.g. `0.50` after a `4x` upscale model = crisp `2x` net supersampled upscale; `1.00` = keep full model size).",
                    },
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT")
    RETURN_NAMES = ("image", "width", "height")
    FUNCTION = "upscale_and_resize"
    CATEGORY = UPSCALE_CATEGORY

    def upscale_and_resize(
        self,
        image: torch.Tensor,
        enabled: bool = True,
        model_name: str = "",
        method: str = "bicubic",
        scale_by: float = 0.50,
        unique_id=None,
    ):
        in_h = int(image.shape[1])
        in_w = int(image.shape[2])

        if not bool(enabled):
            if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and unique_id is not None:
                uid = unique_id[0] if isinstance(unique_id, list) else unique_id
                PromptServer.instance.send_sync(
                    "wfa-upscale-feedback",
                    {
                        "node_id": str(uid),
                        "text": f"Bypassed • {in_w}×{in_h}",
                        "done": False,
                    },
                )
            return (image, in_w, in_h)

        upscale_model = _get_cached_upscale_model(model_name)
        model_scale = float(getattr(upscale_model, "scale", 1.0))

        memory_required = (512 * 512 * 3) * image.element_size() * max(model_scale, 1.0) * 384.0
        memory_required += image.nelement() * image.element_size()

        use_patcher = getattr(upscale_model, "patcher", None) is not None
        if use_patcher:
            device = upscale_model.patcher.load_device
            model_management.load_models_gpu(
                [upscale_model.patcher],
                memory_required=memory_required,
                force_full_load=True,
            )
        else:
            device = model_management.get_torch_device()
            model_management.free_memory(memory_required, device)
            upscale_model.to(device)

        in_img = image.movedim(-1, -3).to(device)
        tile = 512
        overlap = 32
        output_device = (
            model_management.intermediate_device()
            if hasattr(model_management, "intermediate_device")
            else torch.device("cpu")
        )

        try:
            oom = True
            while oom:
                try:
                    steps = in_img.shape[0] * comfy.utils.get_tiled_scale_steps(
                        in_img.shape[3],
                        in_img.shape[2],
                        tile_x=tile,
                        tile_y=tile,
                        overlap=overlap,
                    )
                    pbar = comfy.utils.ProgressBar(steps)
                    s = comfy.utils.tiled_scale(
                        in_img,
                        lambda a: upscale_model(a.float()),
                        tile_x=tile,
                        tile_y=tile,
                        overlap=overlap,
                        upscale_amount=upscale_model.scale,
                        pbar=pbar,
                        output_device=output_device,
                    )
                    oom = False
                except Exception as e:
                    if hasattr(model_management, "raise_non_oom"):
                        model_management.raise_non_oom(e)
                    elif not isinstance(e, model_management.OOM_EXCEPTION):
                        raise
                    tile //= 2
                    if tile < 128:
                        raise
        finally:
            del in_img
            if not use_patcher:
                upscale_model.to("cpu")

        # `s` is already in NCHW layout: (B, C, raw_h, raw_w)
        s = torch.clamp(s, min=0.0, max=1.0)
        raw_h = int(s.shape[2])
        raw_w = int(s.shape[3])

        out_w = max(1, round(raw_w * float(scale_by)))
        out_h = max(1, round(raw_h * float(scale_by)))

        if (out_w, out_h) != (raw_w, raw_h):
            s = comfy.utils.common_upscale(s, out_w, out_h, method, "disabled")
            s = torch.clamp(s, min=0.0, max=1.0)

        out_dtype = (
            model_management.intermediate_dtype()
            if hasattr(model_management, "intermediate_dtype")
            else torch.float32
        )
        out_image = s.movedim(1, -1).to(out_dtype)
        del s

        if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and unique_id is not None:
            uid = unique_id[0] if isinstance(unique_id, list) else unique_id
            scale_tag = f"{int(model_scale)}x" if model_scale.is_integer() else f"{model_scale:g}x"
            PromptServer.instance.send_sync(
                "wfa-upscale-feedback",
                {
                    "node_id": str(uid),
                    "text": f"✓ {in_w}×{in_h} → {out_w}×{out_h} ({scale_tag} × {float(scale_by):.2f})",
                    "done": True,
                },
            )

        return (out_image, out_w, out_h)


NODE_CLASS_MAPPINGS = {
    "WFA_ModelUpscaleResize": WFA_ModelUpscaleResize,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WFA_ModelUpscaleResize": "WFA Model Upscale & Scale ⚡ (WFA Suite)",
}
