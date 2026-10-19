from .utils import SUITE_CATEGORY, any_type

NUM_INPUTS = 100
START_INDEX = 0  # Change to 1 if you prefer 1-100 instead of 0-99


class WA_OmniSwitch100:
    """
    WA OmniSwitch 100: A 100-input wildcard Index Switch for ComfyUI.
    Uses ComfyUI's lazy evaluation so ONLY the upstream branch connected
    to the active index is executed. All other 99 branches are completely ignored.
    """

    @classmethod
    def INPUT_TYPES(cls):
        optional_inputs = {
            f"input_{i}": (any_type, {"lazy": True})
            for i in range(START_INDEX, START_INDEX + NUM_INPUTS)
        }
        return {
            "required": {
                "index": (
                    "INT",
                    {
                        "default": START_INDEX,
                        "min": START_INDEX,
                        "max": START_INDEX + NUM_INPUTS - 1,
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


NODE_CLASS_MAPPINGS = {
    "WA_OmniSwitch100": WA_OmniSwitch100,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WA_OmniSwitch100": "WA Index Switch 100 ⚡ (WA Suite)",
}
