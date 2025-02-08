"""Handles entity listeners."""

import logging

from .const import VAConfigEntry
from homeassistant.components.websocket_api.http import async_dispatcher_send
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class EntityListeners:
    """Class to manage entity monitors."""

    def __init__(self, hass: HomeAssistant, config_entry: VAConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config_entry = config_entry

        mic_device = self.config_entry.data["mic_device"]
        mic_type = self.config_entry.options.get("mic_type")
        mute_switch = get_mute_switch(mic_device, mic_type)


        mediaplayer_device = self.config_entry.data["mediaplayer_device"]
    

        # Add microphone mute switch listener
        config_entry.async_on_unload(
            async_track_state_change_event(hass, mute_switch, self._async_on_mic_change)
        )

        # Add media player mute listener
        config_entry.async_on_unload(
            async_track_state_change_event(
                hass, mediaplayer_device, self._async_on_mediaplayer_device_mute_change
            )
        )

    def update_entity(self):
        """Dispatch message that entity is listening for to update."""
        async_dispatcher_send(
            self.hass, f"{DOMAIN}_{self.config_entry.entry_id}_update"
        )

    # @callback
    # def _async_on_mic_change(self, event: Event[EventStateChangedData]) -> None:
    #     old_state = event.data["old_state"]
    #     new_state = event.data["new_state"]
    #     _LOGGER.info("OLD STATE: %s", old_state.state)
    #     _LOGGER.info("NEW STATE: %s", new_state.state)
    #     self.config_entry.runtime_data.do_not_disturb = new_state.state == "on"
    #     if new_state.state == "on":
    #         if "mic" not in self.config_entry.runtime_data.status_icons:
    #             self.config_entry.runtime_data.status_icons.append("mic")
    #     self.update_entity()


    @callback
    def _async_on_mic_change(self, event: Event[EventStateChangedData]) -> None:
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        _LOGGER.info("OLD STATE: %s", old_state.state)
        _LOGGER.info("NEW STATE: %s", new_state.state)



    @callback
    def _async_on_mediaplayer_device_mute_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        new_state = event.data["new_state"]
        mp_mute_new_state = new_state.attributes.get("is_volume_muted", False)
        _LOGGER.info("MP MUTE: %s", mp_mute_new_state)
        if mp_mute_new_state is True:
            self.config_entry.runtime_data.status_icons.append("mediaplayer")
        elif mp_mute_new_state is False:
            self.config_entry.runtime_data.status_icons.remove("mediaplayer")            
        self.update_entity()            




    def get_mute_switch(target_device, mic_type):
        if mic_type == "Stream Assist":
            target_device = target_device.replace("sensor", "switch").replace(
                "_stt", "_mic"
            )
        elif mic_type == "HassMic":
            target_device = target_device.replace("sensor", "switch").replace(
                "simple_state", "microphone"
            )
        elif mic_type == "Home Assistant Voice Satellite":
            target_device = (
                target_device.replace("assist_satellite", "switch") + "_mute"
            )

        return target_device
