import logging

from config.custom_components.view_assist.timers import Timer, TimerClass, VATimers
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, RuntimeData, VAConfigEntry
from .entity_listeners import EntityListeners
from .frontend import FrontendConfig
from .helpers import ensure_list
from .services import setup_services
from .websocket import async_register_websockets
import datetime as dt

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: VAConfigEntry):
    """Set up View Assist from a config entry."""

    # Add runtime data to config entry to have place to store data and
    # make accessible throughout integration
    entry.runtime_data = RuntimeData()
    set_runtime_data_from_config(entry)

    # Request platform setup
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Add config change listener
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Run first display instance only functions
    await run_if_first_display_instance(hass, entry)

    # Load entity listeners
    EntityListeners(hass, entry)

    # Inisitialise service
    await setup_services(hass, entry)

    # Load websockets
    await async_register_websockets(hass)

    return True


async def run_if_first_display_instance(hass: HomeAssistant, entry: VAConfigEntry):
    """Things to run only one when multiple instances exist."""
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data["type"] == "view_audio" and not entry.disabled_by
    ]

    # If not first instance, return
    if not entries or entries[0].entry_id != entry.entry_id:
        return

    # Things to run on first instance setup only go below here

    # Run dashboard and view setup
    async def setup_frontend(*args):
        fc = FrontendConfig(hass)
        await fc.async_config()

    if hass.is_running:
        await setup_frontend()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, setup_frontend)

    # Timers
    # TODO: Implement a first config item setup to put this in.
    timers = VATimers(hass, entry)
    await timers.load()
    entry.runtime_data._timers = timers  # noqa: SLF001


def set_runtime_data_from_config(config_entry: VAConfigEntry):
    """Set config.runtime_data attributes from matching config values."""

    config_sources = [config_entry.data, config_entry.options]
    for source in config_sources:
        for k, v in source.items():
            if hasattr(config_entry.runtime_data, k):
                # This is a fix for config lists being a string
                if isinstance(getattr(config_entry.runtime_data, k), list):
                    setattr(config_entry.runtime_data, k, ensure_list(v))
                else:
                    setattr(config_entry.runtime_data, k, v)


async def _async_update_listener(hass: HomeAssistant, config_entry: VAConfigEntry):
    """Handle config options update."""
    # Reload the integration when the options change.
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: VAConfigEntry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
