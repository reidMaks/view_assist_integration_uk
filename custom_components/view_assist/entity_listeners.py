"""Handles entity listeners."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)


class EntityListeners:
    """Class to manage entity monitors."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config_entry = config_entry

        mic_device = self.config_entry.data["mic_device"]

        # Add mic listener
        config_entry.async_on_unload(
            async_track_state_change_event(hass, mic_device, self._async_on_mic_change)
        )

    @callback
    def _async_on_mic_change(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        _LOGGER.info("STATE CHANGE: %s", new_state)
