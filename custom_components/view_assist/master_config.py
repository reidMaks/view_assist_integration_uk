"""Holds master config for View Assist."""

from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import DOMAIN, VAConfigEntry, VAEvent

MASTER_CONFIG = "master_config"


@dataclass
class MasterConfig:
    """Class to hold master config."""

    show_date: bool = False


class MasterConfigManager:
    """Class to manager master config."""

    def __init__(self, hass: HomeAssistant, config: VAConfigEntry) -> None:
        """Initialise."""
        self._hass = hass
        self._config = config
        self._store = Store(hass, 1, f"{DOMAIN}.master_config")
        self.config: MasterConfig

        hass.services.async_register(
            DOMAIN,
            "set_master_config",
            self._async_handle_set_master_config,
        )

    async def load(self):
        """Load tiers from store."""
        stored: dict[str, Any] = await self._store.async_load()
        if stored:
            self.config = MasterConfig(**stored)
        else:
            self.config = MasterConfig()

    async def save(self):
        """Save store."""
        await self._store.async_save(self.config)

    async def _async_handle_set_master_config(self, call: ServiceCall):
        """Handle set master config service call."""
        invalid_attrs = []

        # Check for invalid attributes
        if invalid_attrs := [
            attr for attr in call.data if not hasattr(self.config, attr)
        ]:
            raise HomeAssistantError(f"Invalid attributes - {invalid_attrs}")

        # Set values now we know all valid
        for attr, value in call.data.items():
            setattr(self.config, attr, value)

        await self.save()
        async_dispatcher_send(
            self._hass, f"{DOMAIN}_event", VAEvent("master_config_update")
        )
