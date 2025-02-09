"""Helper functions."""


def ensure_list(value: str | list[str]):
    """Ensure that a value is a list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return (value.replace("[", "").replace("]", "").replace('"', "")).split(",")
    return []
