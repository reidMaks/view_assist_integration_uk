import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, URL_BASE, VA_SUB_DIRS, VAConfigEntry
from .helpers import create_dir_if_not_exist

_LOGGER = logging.getLogger(__name__)


class HTTPManager:
    """Manage HTTP paths."""

    def __init__(self, hass: HomeAssistant, config: VAConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config = config

    async def _async_register_path(self, url: str, path: str):
        """Register resource path if not already registered."""
        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(url, path, False)]
            )
            _LOGGER.debug("Registered resource path from %s", path)
        except RuntimeError:
            # Runtime error - likley this is already registered.
            _LOGGER.debug("Resource path already registered")

    async def create_url_paths(self):
        """Create viewassist url paths."""

        if await self.hass.async_add_executor_job(
            create_dir_if_not_exist, self.hass, DOMAIN
        ):
            for sub_dir in VA_SUB_DIRS:
                sub_dir = f"{DOMAIN}/{sub_dir}"
                await self.hass.async_add_executor_job(
                    create_dir_if_not_exist, self.hass, sub_dir
                )

        await self._async_register_path(
            f"{URL_BASE}/defaults", f"{Path(__file__).parent}/default_config"
        )
        va_dir = f"{self.hass.config.config_dir}/{DOMAIN}"
        await self._async_register_path(f"{URL_BASE}", va_dir)
