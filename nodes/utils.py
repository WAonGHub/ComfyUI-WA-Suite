SUITE_CATEGORY = "WFA Node Suite"


class AnyType(str):
    """Wildcard type that matches any input/output type in ComfyUI."""
    def __ne__(self, __value: object) -> bool:
        return False

    def __eq__(self, __value: object) -> bool:
        return True


any_type = AnyType("*")
