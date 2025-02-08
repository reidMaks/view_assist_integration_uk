from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry

DOMAIN = "view_assist"

type VAConfigEntry = ConfigEntry[RuntimeData]


@dataclass
class RuntimeData:
    """Class to hold your data."""

    mode: str = "normal"
    do_not_disturb: bool = False
    status_icons: list[str] = field(default_factory=list)
    extra_data: dict[str, Any] = field(default_factory=dict)
