"""Handles entity listeners."""

import logging
from typing import Any

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import CONF_MODE

from .const import CONF_DO_NOT_DISTURB, DOMAIN, VA_ATTRIBUTE_UPDATE_EVENT, VAConfigEntry

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

        # Add listener to set_state service to call sensor_attribute_changed
        hass.bus.async_listen(
            VA_ATTRIBUTE_UPDATE_EVENT.format(config_entry.entry_id),
            self.set_state_changed_attribute,
        )

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

    def update_entity(self):
        """Dispatch message that entity is listening for to update."""
        async_dispatcher_send(
            self.hass, f"{DOMAIN}_{self.config_entry.entry_id}_update"
        )

    # ---------------------------------------------------------------------------------------
    # Actions for monitoring changes to external entities
    # ---------------------------------------------------------------------------------------

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

    # ---------------------------------------------------------------------------------------
    # Actions for attributes changed via the set_state service
    # ---------------------------------------------------------------------------------------

    @callback
    def set_state_changed_attribute(self, event: Event):
        """Call when a sensor attribute is changed by the set_state service."""

        # This function is only called if the new_value != old_value so no need to test
        # for that.  If you are here, an attribute has changed.
        attribute = event.data.get("attribute")
        old_value = event.data.get("old_value")
        new_value = event.data.get("new_value")

        _LOGGER.info(
            "ATTR CHANGED: %s - old value: %s, new value: %s",
            attribute,
            old_value,
            new_value,
        )

        if attribute == CONF_DO_NOT_DISTURB:
            self._async_on_dnd_device_state_change(event)

        if attribute == CONF_MODE:
            self._async_on_mode_state_change(event)

    @callback
    def _async_on_dnd_device_state_change(self, event: Event) -> None:
        """Set dnd status icon."""

        # This is called from our set_service event listener and therefore event data is
        # slightly different.  See set_state_changed_attribute above
        dnd_new_state = event.data["new_value"]

        _LOGGER.info("DND STATE: %s", dnd_new_state)
        status_icons = self.config_entry.runtime_data.status_icons.copy()
        if dnd_new_state and "dnd" not in status_icons:
            status_icons.append("dnd")
        elif not dnd_new_state and "dnd" in status_icons:
            status_icons.remove("dnd")

        self.config_entry.runtime_data.status_icons = status_icons
        self.update_entity()
    
    @callback
    def _async_on_mode_state_change(self, event: Event) -> None:
        """Set mode status icon."""

        mode_new_state = event.data["new_value"]
        mode_old_state = event.data["old_value"]

        _LOGGER.info("MODE STATE: %s", mode_new_state)
        status_icons = self.config_entry.runtime_data.status_icons.copy()

        modes = ["hold","cycle"]

        # Remove all mode icons
        for mode in modes:
            if mode in status_icons:
                status_icons.remove(mode)

        # Now add back any you want
        if mode_new_state in modes and mode_new_state not in status_icons:
            status_icons.append(mode_new_state)

        self.config_entry.runtime_data.status_icons = status_icons
        self.update_entity() 

        if mode_new_state == "normal" and mode_old_state != "normal":
            # Add navigate to default view
            _LOGGER.info("NAVIGATE TO: %s", mode_new_state)
        elif mode_new_state == "music" and mode_old_state != "music":
            # Add navigate to music view
            _LOGGER.info("NAVIGATE TO: %s", mode_new_state)
        elif mode_new_state == "cycle" and mode_old_state != "cycle":
            # Add start cycle mode
            # Pull cycle_mode attribute
            _LOGGER.info("START MODE: %s", mode_new_state)                                    