from .utils import SUITE_CATEGORY, any_type

START_INDEX = 0  # Change to 1 if you prefer 1-N instead of 0-(N-1)
SWITCH_SIZES = (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)


class _WFAIndexSwitchBase:
    """
    Base class for WFA Lazy Wildcard Index Switches (10 to 100 inputs).
    Uses ComfyUI's lazy evaluation so ONLY the upstream branch connected
    to the active index is executed. All other branches are completely ignored.
    """

    NUM_INPUTS = 100

    @classmethod
    def INPUT_TYPES(cls):
        optional_inputs = {
            f"input_{i}": (any_type, {"lazy": True})
            for i in range(START_INDEX, START_INDEX + cls.NUM_INPUTS)
        }
        return {
            "required": {
                "index": (
                    "INT",
                    {
                        "default": START_INDEX,
                        "min": START_INDEX,
                        "max": START_INDEX + cls.NUM_INPUTS - 1,
                        "step": 1,
                    },
                ),
            },
            "optional": optional_inputs,
        }

    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("output",)
    FUNCTION = "switch"
    CATEGORY = f"{SUITE_CATEGORY}/Switches"

    def check_lazy_status(self, index: int, **kwargs):
        """
        Tells ComfyUI which single input is needed before running `switch`.
        Only this input's upstream nodes will be executed.
        """
        target_key = f"input_{index}"
        if kwargs.get(target_key, None) is None:
            return [target_key]
        return []

    def switch(self, index: int, **kwargs):
        target_key = f"input_{index}"
        return (kwargs.get(target_key, None),)


NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

for _size in SWITCH_SIZES:
    _cls_name = f"WFA_IndexSwitch{_size}"
    _cls = type(
        _cls_name,
        (_WFAIndexSwitchBase,),
        {
            "__doc__": f"WFA Index Switch {_size}: {_size}-input lazy wildcard Index Switch for ComfyUI.",
            "NUM_INPUTS": _size,
        },
    )
    globals()[_cls_name] = _cls
    NODE_CLASS_MAPPINGS[_cls_name] = _cls
    NODE_DISPLAY_NAME_MAPPINGS[_cls_name] = f"WFA Index Switch {_size} ⚡ (WFA Suite)"


class WFA_IntIndexSwitch:
    """
    WFA INT Index Switch: 100-row visual index selector UI with editable row notes/labels,
    clickable row numbers, and alternating dark/light grey row shading.
    Outputs only the selected INT index (no text output or comment stripping needed).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
                "select": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 9999,
                        "step": 1,
                    },
                ),
            }
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("selected_index",)
    FUNCTION = "select_index"
    CATEGORY = f"{SUITE_CATEGORY}/Switches"

    def select_index(self, text: str = "", select: int = 0):
        return (select,)


NODE_CLASS_MAPPINGS["WFA_IntIndexSwitch"] = WFA_IntIndexSwitch
NODE_DISPLAY_NAME_MAPPINGS["WFA_IntIndexSwitch"] = "WFA INT Index Switch ⚡ (WFA Suite)"

