"""Handles entity listeners."""

import logging

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, VAConfigEntry

_LOGGER = logging.getLogger(__name__)


class EntityListeners:
    """Class to manage entity monitors."""

    def __init__(self, hass: HomeAssistant, config_entry: VAConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config_entry = config_entry

        # Add microphone mute switch listener
        mic_device = config_entry.runtime_data.mic_device
        mic_type = config_entry.runtime_data.mic_type
        mute_switch = self.get_mute_switch(mic_device, mic_type)

        config_entry.async_on_unload(
            async_track_state_change_event(hass, mute_switch, self._async_on_mic_change)
        )

        # Add media player mute listener
        mediaplayer_device = self.config_entry.data["mediaplayer_device"]

        config_entry.async_on_unload(
            async_track_state_change_event(
                hass, mediaplayer_device, self._async_on_mediaplayer_device_mute_change
            )
        )

        # Add do not disturb listener
        dnd_device = "sensor." + config_entry.runtime_data.name

        # config_entry.async_on_unload(
        #    async_track_state_change_event(
        #        hass, dnd_device, self._async_on_dnd_device_state_change
        #    )
        # )

    def update_entity(self):
        """Dispatch message that entity is listening for to update."""
        async_dispatcher_send(
            self.hass, f"{DOMAIN}_{self.config_entry.entry_id}_update"
        )

    @callback
    def _async_on_mic_change(self, event: Event[EventStateChangedData]) -> None:
        mic_mute_new_state = event.data["new_state"].state

        # If not change to mic mute state, exit function
        if (
            not event.data.get("old_state")
            or event.data["old_state"].state == mic_mute_new_state
        ):
            return

        _LOGGER.info("MIC MUTE: %s", mic_mute_new_state)
        status_icons = self.config_entry.runtime_data.status_icons.copy()

        if mic_mute_new_state == "on" and "mic" not in status_icons:
            status_icons.append("mic")
        elif mic_mute_new_state == "off" and "mic" in status_icons:
            status_icons.remove("mic")

        self.config_entry.runtime_data.status_icons = status_icons
        self.update_entity()

    @callback
    def _async_on_mediaplayer_device_mute_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        mp_mute_new_state = event.data["new_state"].attributes.get(
            "is_volume_muted", False
        )

        # If not change to mute state, exit function
        if (
            not event.data.get("old_state")
            or event.data["old_state"].attributes.get("is_volume_muted")
            == mp_mute_new_state
        ):
            return

        _LOGGER.info("MP MUTE: %s", mp_mute_new_state)
        status_icons = (
            self.config_entry.runtime_data.status_icons.copy()
            if self.config_entry.runtime_data.status_icons
            else []
        )

        if mp_mute_new_state and "mediaplayer" not in status_icons:
            status_icons.append("mediaplayer")
        elif not mp_mute_new_state and "mediaplayer" in status_icons:
            status_icons.remove("mediaplayer")

        self.config_entry.runtime_data.status_icons = status_icons
        self.update_entity()

    @callback
    def _async_on_dnd_device_state_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        dnd_new_state = event.data["new_state"].attributes.get("do_not_disturb", False)

        # If not change to dnd state, exit function
        if (
            not event.data.get("old_state")
            or event.data["old_state"].attributes.get("do_not_disturb") == dnd_new_state
        ):
            return

        _LOGGER.info("DND STATE: %s", dnd_new_state)
        status_icons = self.config_entry.runtime_data.status_icons.copy()

        if dnd_new_state and "dnd" not in status_icons:
            status_icons.append("dnd")
        elif not dnd_new_state and "dnd" in status_icons:
            status_icons.remove("dnd")

        self.config_entry.runtime_data.status_icons = status_icons
        self.update_entity()

    def get_mute_switch(self, target_device: str, mic_type: str):
        """Get mute switch."""

        if mic_type == "Stream Assist":
            return target_device.replace("sensor", "switch").replace("_stt", "_mic")
        if mic_type == "HassMic":
            return target_device.replace("sensor", "switch").replace(
                "simple_state", "microphone"
            )
        if mic_type == "Home Assistant Voice Satellite":
            return target_device.replace("assist_satellite", "switch") + "_mute"

        return None
