import inspect
import torch
import torch.nn.functional as F
import comfy.samplers
import comfy.utils
import nodes
from nodes import common_ksampler
from .utils import SUITE_CATEGORY

REFINER_CATEGORY = f"{SUITE_CATEGORY}/Refiners"


def _apply_differential_diffusion(model):
    model = model.clone()
    if "denoise_mask_function" not in model.model_options:
        def denoise_mask_function(sigma, denoise_mask, extra_options):
            return denoise_mask
        model.set_model_denoise_mask_function(denoise_mask_function)
    return model


def _gaussian_blur_2d(tensor_4d: torch.Tensor, radius: int, pad_mode: str = "reflect", pad_value: float = 0.0) -> torch.Tensor:
    if radius <= 0:
        return tensor_4d
    kernel_size = radius * 2 + 1
    sigma = radius * 0.5
    coords = torch.arange(kernel_size, dtype=torch.float32, device=tensor_4d.device) - (kernel_size // 2)
    g = torch.exp(-(coords ** 2) / (2 * sigma ** 2))
    g /= g.sum()
    channels = tensor_4d.shape[1]
    kernel = (g.view(1, 1, kernel_size, 1) * g.view(1, 1, 1, kernel_size)).repeat(channels, 1, 1, 1)
    pad = kernel_size // 2
    if pad_mode == "constant":
        padded = F.pad(tensor_4d, (pad, pad, pad, pad), mode="constant", value=pad_value)
    else:
        padded = F.pad(tensor_4d, (pad, pad, pad, pad), mode=pad_mode)
    return F.conv2d(padded, kernel, groups=channels)


def _unsharp_mask(image: torch.Tensor, amount: float = 1.0, kernel_size: int = 5, sigma: float = 1.0) -> torch.Tensor:
    img_tensor = image.permute(0, 3, 1, 2)
    coords = torch.arange(kernel_size, dtype=torch.float32, device=img_tensor.device) - (kernel_size // 2)
    g = torch.exp(-(coords ** 2) / (2 * sigma ** 2))
    g /= g.sum()
    kernel = (g.view(1, 1, kernel_size, 1) * g.view(1, 1, 1, kernel_size)).repeat(img_tensor.shape[1], 1, 1, 1)
    pad = kernel_size // 2
    padded = F.pad(img_tensor, (pad, pad, pad, pad), mode="reflect")
    blurred = F.conv2d(padded, kernel, groups=img_tensor.shape[1])
    sharpened = torch.clamp(img_tensor + amount * (img_tensor - blurred), 0.0, 1.0)
    return sharpened.permute(0, 2, 3, 1)


def _get_edge_mask(image_tensor: torch.Tensor, edge_strength: float = 1.0, edge_blur: int = 3) -> torch.Tensor:
    gray = (
        0.299 * image_tensor[:, :, :, 0]
        + 0.587 * image_tensor[:, :, :, 1]
        + 0.114 * image_tensor[:, :, :, 2]
    ).unsqueeze(1)

    sobel_x = torch.tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=torch.float32, device=gray.device).view(1, 1, 3, 3)
    sobel_y = torch.tensor([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=torch.float32, device=gray.device).view(1, 1, 3, 3)

    padded = F.pad(gray, (1, 1, 1, 1), mode="reflect")
    edge_x = F.conv2d(padded, sobel_x)
    edge_y = F.conv2d(padded, sobel_y)
    edges = torch.sqrt(edge_x ** 2 + edge_y ** 2)

    b = edges.shape[0]
    edges_flat = edges.view(b, -1)
    edges_min = edges_flat.min(dim=1, keepdim=True)[0].view(b, 1, 1, 1)
    edges_max = edges_flat.max(dim=1, keepdim=True)[0].view(b, 1, 1, 1)
    edges = (edges - edges_min) / (edges_max - edges_min + 1e-8)
    edges = torch.clamp(edges * edge_strength, 0.0, 1.0)

    if edge_blur > 0:
        edges = _gaussian_blur_2d(edges, edge_blur, pad_mode="reflect")

    return edges.squeeze(1)


def _get_smart_mask(
    image_tensor: torch.Tensor,
    edge_strength: float = 1.0,
    mask_dilation: int = 5,
    mask_blur: int = 5,
    base_mask_level: float = 0.1,
) -> torch.Tensor:
    gray = (
        0.299 * image_tensor[:, :, :, 0]
        + 0.587 * image_tensor[:, :, :, 1]
        + 0.114 * image_tensor[:, :, :, 2]
    ).unsqueeze(1)

    sobel_x = torch.tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=torch.float32, device=gray.device).view(1, 1, 3, 3)
    sobel_y = torch.tensor([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=torch.float32, device=gray.device).view(1, 1, 3, 3)

    padded = F.pad(gray, (1, 1, 1, 1), mode="reflect")
    edge_x = F.conv2d(padded, sobel_x)
    edge_y = F.conv2d(padded, sobel_y)
    edges = torch.sqrt(edge_x ** 2 + edge_y ** 2)

    b = edges.shape[0]
    edges_flat = edges.view(b, -1)
    edges_min = edges_flat.min(dim=1, keepdim=True)[0].view(b, 1, 1, 1)
    edges_max = edges_flat.max(dim=1, keepdim=True)[0].view(b, 1, 1, 1)
    edges = (edges - edges_min) / (edges_max - edges_min + 1e-8)
    edges = edges * edge_strength

    if mask_dilation > 0:
        k = mask_dilation * 2 + 1
        edges = F.max_pool2d(edges, kernel_size=k, stride=1, padding=k // 2)

    if base_mask_level > 0.0:
        edges = edges + base_mask_level

    edges = torch.clamp(edges, 0.0, 1.0)

    if mask_blur > 0:
        edges = _gaussian_blur_2d(edges, mask_blur, pad_mode="reflect")

    return edges.squeeze(1)


class WA_FullImageRefiner:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "denoise": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "noise_mask": ("BOOLEAN", {"default": True}),
                "noise_mask_feather": ("INT", {"default": 20, "min": 0, "max": 100, "step": 1}),
                "force_inpaint": ("BOOLEAN", {"default": True}),
                "cycle": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "do_refine"
    CATEGORY = REFINER_CATEGORY

    def do_refine(
        self, image, model, clip, vae, positive, negative, seed, steps, cfg,
        sampler_name, scheduler, denoise, noise_mask, noise_mask_feather, force_inpaint, cycle
    ):
        batch_size, h, w, _ = image.shape
        result_image = image

        for i in range(cycle):
            pixels = result_image[:, :, :, :3]
            t = vae.encode(pixels)
            latent = {"samples": t}

            mask = torch.ones((batch_size, h, w), dtype=torch.float32, device="cpu")
            if noise_mask:
                if noise_mask_feather > 0:
                    mask = _gaussian_blur_2d(mask.unsqueeze(1), noise_mask_feather, pad_mode="constant", pad_value=0.0).squeeze(1)
                latent_h, latent_w = t.shape[2], t.shape[3]
                mask_resized = F.interpolate(mask.unsqueeze(1), size=(latent_h, latent_w), mode="bilinear", align_corners=False).squeeze(1)
                if force_inpaint:
                    latent["noise_mask"] = mask_resized

            sampled = common_ksampler(
                model=model,
                seed=seed + i,
                steps=steps,
                cfg=cfg,
                sampler_name=sampler_name,
                scheduler=scheduler,
                positive=positive,
                negative=negative,
                latent=latent,
                denoise=denoise,
            )
            result_image = vae.decode(sampled[0]["samples"])

        return (result_image,)


class WA_FullImageRefinerPipe(WA_FullImageRefiner):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "basic_pipe": ("BASIC_PIPE",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "denoise": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "noise_mask": ("BOOLEAN", {"default": True}),
                "noise_mask_feather": ("INT", {"default": 20, "min": 0, "max": 100, "step": 1}),
                "force_inpaint": ("BOOLEAN", {"default": True}),
                "cycle": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "BASIC_PIPE")
    FUNCTION = "do_refine_pipe"
    CATEGORY = REFINER_CATEGORY

    def do_refine_pipe(
        self, image, basic_pipe, seed, steps, cfg, sampler_name, scheduler,
        denoise, noise_mask, noise_mask_feather, force_inpaint, cycle
    ):
        model, clip, vae, positive, negative = basic_pipe
        (result_image,) = self.do_refine(
            image, model, clip, vae, positive, negative, seed, steps, cfg,
            sampler_name, scheduler, denoise, noise_mask, noise_mask_feather, force_inpaint, cycle
        )
        return (result_image, basic_pipe)


class WA_AdvancedFullImageRefiner:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "denoise": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "noise_mask": ("BOOLEAN", {"default": True}),
                "noise_mask_feather": ("INT", {"default": 20, "min": 0, "max": 100, "step": 1}),
                "force_inpaint": ("BOOLEAN", {"default": True}),
                "cycle": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
                "upscale_factor": ("FLOAT", {"default": 1.0, "min": 1.0, "max": 4.0, "step": 0.05}),
                "pre_sharpen": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 5.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "do_refine"
    CATEGORY = REFINER_CATEGORY

    def do_refine(
        self, image, model, clip, vae, positive, negative, seed, steps, cfg,
        sampler_name, scheduler, denoise, noise_mask, noise_mask_feather,
        force_inpaint, cycle, upscale_factor, pre_sharpen
    ):
        batch_size, h, w, _ = image.shape
        result_image = image

        if pre_sharpen > 0.0:
            result_image = _unsharp_mask(result_image, amount=pre_sharpen)

        if upscale_factor > 1.0:
            new_h = int(h * upscale_factor)
            new_w = int(w * upscale_factor)
            img_tensor = result_image.permute(0, 3, 1, 2)
            img_tensor = F.interpolate(img_tensor, size=(new_h, new_w), mode="bicubic", align_corners=False)
            result_image = img_tensor.permute(0, 2, 3, 1)

        _, cur_h, cur_w, _ = result_image.shape

        for i in range(cycle):
            pixels = result_image[:, :, :, :3]
            t = vae.encode(pixels)
            latent = {"samples": t}

            mask = torch.ones((batch_size, cur_h, cur_w), dtype=torch.float32, device="cpu")
            if noise_mask:
                if noise_mask_feather > 0:
                    mask = _gaussian_blur_2d(mask.unsqueeze(1), noise_mask_feather, pad_mode="constant", pad_value=0.0).squeeze(1)
                latent_h, latent_w = t.shape[2], t.shape[3]
                mask_resized = F.interpolate(mask.unsqueeze(1), size=(latent_h, latent_w), mode="bilinear", align_corners=False).squeeze(1)
                if force_inpaint:
                    latent["noise_mask"] = mask_resized

            sampled = common_ksampler(
                model=model,
                seed=seed + i,
                steps=steps,
                cfg=cfg,
                sampler_name=sampler_name,
                scheduler=scheduler,
                positive=positive,
                negative=negative,
                latent=latent,
                denoise=denoise,
            )
            result_image = vae.decode(sampled[0]["samples"])

        if upscale_factor > 1.0:
            img_tensor = result_image.permute(0, 3, 1, 2)
            img_tensor = F.interpolate(img_tensor, size=(h, w), mode="bicubic", align_corners=False)
            result_image = img_tensor.permute(0, 2, 3, 1)

        return (result_image,)


class WA_AdvancedFullImageRefinerPipe(WA_AdvancedFullImageRefiner):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "basic_pipe": ("BASIC_PIPE",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "denoise": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "noise_mask": ("BOOLEAN", {"default": True}),
                "noise_mask_feather": ("INT", {"default": 20, "min": 0, "max": 100, "step": 1}),
                "force_inpaint": ("BOOLEAN", {"default": True}),
                "cycle": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
                "upscale_factor": ("FLOAT", {"default": 1.0, "min": 1.0, "max": 4.0, "step": 0.05}),
                "pre_sharpen": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 5.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "BASIC_PIPE")
    FUNCTION = "do_refine_pipe"
    CATEGORY = REFINER_CATEGORY

    def do_refine_pipe(
        self, image, basic_pipe, seed, steps, cfg, sampler_name, scheduler,
        denoise, noise_mask, noise_mask_feather, force_inpaint, cycle, upscale_factor, pre_sharpen
    ):
        model, clip, vae, positive, negative = basic_pipe
        (result_image,) = self.do_refine(
            image, model, clip, vae, positive, negative, seed, steps, cfg,
            sampler_name, scheduler, denoise, noise_mask, noise_mask_feather,
            force_inpaint, cycle, upscale_factor, pre_sharpen
        )
        return (result_image, basic_pipe)


class WA_ExactImpactRefiner:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "denoise": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "noise_mask": ("BOOLEAN", {"default": True}),
                "noise_mask_feather": ("INT", {"default": 20, "min": 0, "max": 100, "step": 1}),
                "force_inpaint": ("BOOLEAN", {"default": True}),
                "inpaint_model": ("BOOLEAN", {"default": False, "label_on": "enabled", "label_off": "disabled"}),
                "cycle": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "do_refine"
    CATEGORY = REFINER_CATEGORY

    def do_refine(
        self, image, model, clip, vae, positive, negative, seed, steps, cfg,
        sampler_name, scheduler, denoise, noise_mask, noise_mask_feather,
        force_inpaint, inpaint_model, cycle
    ):
        batch_size, h, w, _ = image.shape
        result_image = image

        if noise_mask and noise_mask_feather > 0:
            model = _apply_differential_diffusion(model)

        for i in range(cycle):
            current_image = result_image
            mask = torch.ones((batch_size, h, w), dtype=torch.float32, device="cpu")

            if noise_mask and noise_mask_feather > 0:
                mask = _gaussian_blur_2d(mask.unsqueeze(1), noise_mask_feather, pad_mode="reflect").squeeze(1)

            if noise_mask and inpaint_model:
                imc_encode = nodes.InpaintModelConditioning().encode
                if "noise_mask" in inspect.signature(imc_encode).parameters:
                    pos, neg, latent_image = imc_encode(positive, negative, current_image, vae, mask=mask, noise_mask=True)
                else:
                    pos, neg, latent_image = imc_encode(positive, negative, current_image, vae, mask)
            else:
                pixels = current_image[:, :, :, :3]
                t = vae.encode(pixels)
                latent_image = {"samples": t}
                if noise_mask:
                    latent_image["noise_mask"] = mask
                pos, neg = positive, negative

            sampled = common_ksampler(
                model=model,
                seed=seed + i,
                steps=steps,
                cfg=cfg,
                sampler_name=sampler_name,
                scheduler=scheduler,
                positive=pos,
                negative=neg,
                latent=latent_image,
                denoise=denoise,
            )
            result_image = vae.decode(sampled[0]["samples"])

        return (result_image,)


class WA_ExactImpactRefinerPipe(WA_ExactImpactRefiner):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "basic_pipe": ("BASIC_PIPE",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "denoise": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01}),
                "noise_mask": ("BOOLEAN", {"default": True}),
                "noise_mask_feather": ("INT", {"default": 20, "min": 0, "max": 100, "step": 1}),
                "force_inpaint": ("BOOLEAN", {"default": True}),
                "inpaint_model": ("BOOLEAN", {"default": False, "label_on": "enabled", "label_off": "disabled"}),
                "cycle": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "BASIC_PIPE")
    FUNCTION = "do_refine_pipe"
    CATEGORY = REFINER_CATEGORY

    def do_refine_pipe(
        self, image, basic_pipe, seed, steps, cfg, sampler_name, scheduler,
        denoise, noise_mask, noise_mask_feather, force_inpaint, inpaint_model, cycle
    ):
        model, clip, vae, positive, negative = basic_pipe
        (result_image,) = self.do_refine(
            image, model, clip, vae, positive, negative, seed, steps, cfg,
            sampler_name, scheduler, denoise, noise_mask, noise_mask_feather,
            force_inpaint, inpaint_model, cycle
        )
        return (result_image, basic_pipe)


class WA_EdgeTargetedRefiner:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "denoise": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01}),
                "edge_strength": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 10.0, "step": 0.1}),
                "edge_blur": ("INT", {"default": 3, "min": 0, "max": 20, "step": 1}),
                "noise_mask_feather": ("INT", {"default": 20, "min": 0, "max": 100, "step": 1}),
                "inpaint_model": ("BOOLEAN", {"default": False, "label_on": "enabled", "label_off": "disabled"}),
                "cycle": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("IMAGE", "EDGE_MASK")
    FUNCTION = "do_refine"
    CATEGORY = REFINER_CATEGORY

    def do_refine(
        self, image, model, clip, vae, positive, negative, seed, steps, cfg,
        sampler_name, scheduler, denoise, edge_strength, edge_blur,
        noise_mask_feather, inpaint_model, cycle
    ):
        result_image = image
        model = _apply_differential_diffusion(model)

        for i in range(cycle):
            current_image = result_image
            mask = _get_edge_mask(current_image, edge_strength, edge_blur)
            generated_edge_mask = mask.clone()

            if noise_mask_feather > 0:
                mask = _gaussian_blur_2d(mask.unsqueeze(1), noise_mask_feather, pad_mode="reflect").squeeze(1)

            if inpaint_model:
                imc_encode = nodes.InpaintModelConditioning().encode
                if "noise_mask" in inspect.signature(imc_encode).parameters:
                    pos, neg, latent_image = imc_encode(positive, negative, current_image, vae, mask=mask, noise_mask=True)
                else:
                    pos, neg, latent_image = imc_encode(positive, negative, current_image, vae, mask)
            else:
                pixels = current_image[:, :, :, :3]
                t = vae.encode(pixels)
                latent_image = {"samples": t, "noise_mask": mask}
                pos, neg = positive, negative

            sampled = common_ksampler(
                model=model,
                seed=seed + i,
                steps=steps,
                cfg=cfg,
                sampler_name=sampler_name,
                scheduler=scheduler,
                positive=pos,
                negative=neg,
                latent=latent_image,
                denoise=denoise,
            )
            result_image = vae.decode(sampled[0]["samples"])

        return (result_image, generated_edge_mask)


class WA_EdgeTargetedRefinerPipe(WA_EdgeTargetedRefiner):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "basic_pipe": ("BASIC_PIPE",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "denoise": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01}),
                "edge_strength": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 10.0, "step": 0.1}),
                "edge_blur": ("INT", {"default": 3, "min": 0, "max": 20, "step": 1}),
                "noise_mask_feather": ("INT", {"default": 20, "min": 0, "max": 100, "step": 1}),
                "inpaint_model": ("BOOLEAN", {"default": False, "label_on": "enabled", "label_off": "disabled"}),
                "cycle": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "BASIC_PIPE")
    RETURN_NAMES = ("IMAGE", "EDGE_MASK", "BASIC_PIPE")
    FUNCTION = "do_refine_pipe"
    CATEGORY = REFINER_CATEGORY

    def do_refine_pipe(
        self, image, basic_pipe, seed, steps, cfg, sampler_name, scheduler,
        denoise, edge_strength, edge_blur, noise_mask_feather, inpaint_model, cycle
    ):
        model, clip, vae, positive, negative = basic_pipe
        result_image, generated_mask = self.do_refine(
            image, model, clip, vae, positive, negative, seed, steps, cfg,
            sampler_name, scheduler, denoise, edge_strength, edge_blur,
            noise_mask_feather, inpaint_model, cycle
        )
        return (result_image, generated_mask, basic_pipe)


class WA_SmartMaskRefiner:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "denoise": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01}),
                "edge_strength": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 10.0, "step": 0.1}),
                "mask_dilation": ("INT", {"default": 10, "min": 0, "max": 64, "step": 1}),
                "mask_blur": ("INT", {"default": 5, "min": 0, "max": 32, "step": 1}),
                "mask_base_level": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.01}),
                "noise_mask_feather": ("INT", {"default": 20, "min": 0, "max": 100, "step": 1}),
                "inpaint_model": ("BOOLEAN", {"default": False, "label_on": "enabled", "label_off": "disabled"}),
                "cycle": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("IMAGE", "SMART_MASK")
    FUNCTION = "do_refine"
    CATEGORY = REFINER_CATEGORY

    def do_refine(
        self, image, model, clip, vae, positive, negative, seed, steps, cfg,
        sampler_name, scheduler, denoise, edge_strength, mask_dilation,
        mask_blur, mask_base_level, noise_mask_feather, inpaint_model, cycle
    ):
        result_image = image
        model = _apply_differential_diffusion(model)

        for i in range(cycle):
            current_image = result_image
            mask = _get_smart_mask(current_image, edge_strength, mask_dilation, mask_blur, mask_base_level)
            generated_mask = mask.clone()

            if noise_mask_feather > 0:
                mask = _gaussian_blur_2d(mask.unsqueeze(1), noise_mask_feather, pad_mode="reflect").squeeze(1)

            if inpaint_model:
                imc_encode = nodes.InpaintModelConditioning().encode
                if "noise_mask" in inspect.signature(imc_encode).parameters:
                    pos, neg, latent_image = imc_encode(positive, negative, current_image, vae, mask=mask, noise_mask=True)
                else:
                    pos, neg, latent_image = imc_encode(positive, negative, current_image, vae, mask)
            else:
                pixels = current_image[:, :, :, :3]
                t = vae.encode(pixels)
                latent_image = {"samples": t, "noise_mask": mask}
                pos, neg = positive, negative

            sampled = common_ksampler(
                model=model,
                seed=seed + i,
                steps=steps,
                cfg=cfg,
                sampler_name=sampler_name,
                scheduler=scheduler,
                positive=pos,
                negative=neg,
                latent=latent_image,
                denoise=denoise,
            )
            result_image = vae.decode(sampled[0]["samples"])

        return (result_image, generated_mask)


class WA_SmartMaskRefinerPipe(WA_SmartMaskRefiner):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "basic_pipe": ("BASIC_PIPE",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                "denoise": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01}),
                "edge_strength": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 10.0, "step": 0.1}),
                "mask_dilation": ("INT", {"default": 10, "min": 0, "max": 64, "step": 1}),
                "mask_blur": ("INT", {"default": 5, "min": 0, "max": 32, "step": 1}),
                "mask_base_level": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.01}),
                "noise_mask_feather": ("INT", {"default": 20, "min": 0, "max": 100, "step": 1}),
                "inpaint_model": ("BOOLEAN", {"default": False, "label_on": "enabled", "label_off": "disabled"}),
                "cycle": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "BASIC_PIPE")
    RETURN_NAMES = ("IMAGE", "SMART_MASK", "BASIC_PIPE")
    FUNCTION = "do_refine_pipe"
    CATEGORY = REFINER_CATEGORY

    def do_refine_pipe(
        self, image, basic_pipe, seed, steps, cfg, sampler_name, scheduler,
        denoise, edge_strength, mask_dilation, mask_blur, mask_base_level,
        noise_mask_feather, inpaint_model, cycle
    ):
        model, clip, vae, positive, negative = basic_pipe
        result_image, generated_mask = self.do_refine(
            image, model, clip, vae, positive, negative, seed, steps, cfg,
            sampler_name, scheduler, denoise, edge_strength, mask_dilation,
            mask_blur, mask_base_level, noise_mask_feather, inpaint_model, cycle
        )
        return (result_image, generated_mask, basic_pipe)


NODE_CLASS_MAPPINGS = {
    "WFA_FullImageRefiner": WA_FullImageRefiner,
    "WFA_FullImageRefinerPipe": WA_FullImageRefinerPipe,
    "WFA_AdvancedFullImageRefiner": WA_AdvancedFullImageRefiner,
    "WFA_AdvancedFullImageRefinerPipe": WA_AdvancedFullImageRefinerPipe,
    "WFA_ExactImpactRefiner": WA_ExactImpactRefiner,
    "WFA_ExactImpactRefinerPipe": WA_ExactImpactRefinerPipe,
    "WFA_EdgeTargetedRefiner": WA_EdgeTargetedRefiner,
    "WFA_EdgeTargetedRefinerPipe": WA_EdgeTargetedRefinerPipe,
    "WFA_SmartMaskRefiner": WA_SmartMaskRefiner,
    "WFA_SmartMaskRefinerPipe": WA_SmartMaskRefinerPipe,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WFA_FullImageRefiner": "WFA Full Image Refiner ⚡ (WFA Suite)",
    "WFA_FullImageRefinerPipe": "WFA Full Image Refiner (Pipe) ⚡ (WFA Suite)",
    "WFA_AdvancedFullImageRefiner": "WFA Advanced Full Image Refiner ⚡ (WFA Suite)",
    "WFA_AdvancedFullImageRefinerPipe": "WFA Advanced Full Image Refiner (Pipe) ⚡ (WFA Suite)",
    "WFA_ExactImpactRefiner": "WFA Exact Impact Refiner ⚡ (WFA Suite)",
    "WFA_ExactImpactRefinerPipe": "WFA Exact Impact Refiner (Pipe) ⚡ (WFA Suite)",
    "WFA_EdgeTargetedRefiner": "WFA Edge-Targeted Refiner ⚡ (WFA Suite)",
    "WFA_EdgeTargetedRefinerPipe": "WFA Edge-Targeted Refiner (Pipe) ⚡ (WFA Suite)",
    "WFA_SmartMaskRefiner": "WFA Smart Mask Refiner ⚡ (WFA Suite)",
    "WFA_SmartMaskRefinerPipe": "WFA Smart Mask Refiner (Pipe) ⚡ (WFA Suite)",
}
