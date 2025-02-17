"""Handles entity listeners."""

import logging

from homeassistant.const import CONF_DEVICE, CONF_MODE, CONF_PATH
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, partial
from homeassistant.util import slugify

from .const import (
    CONF_DO_NOT_DISTURB,
    DOMAIN,
    VA_ATTRIBUTE_UPDATE_EVENT,
    VAConfigEntry,
    VADisplayType,
    VAMode,
    VAType,
)
from .helpers import get_random_image

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
            self.async_set_state_changed_attribute,
        )

        # Add listener for browsermod or remote assist display
        if config_entry.runtime_data.type == VAType.VIEW_AUDIO:
            if config_entry.runtime_data.display_type == VADisplayType.BROWSERMOD:
                view_entity = f"sensor.{slugify(config_entry.runtime_data.browser_id)}_browser_path"
            elif (
                config_entry.runtime_data.display_type
                == VADisplayType.REMOTE_ASSIST_DISPLAY
            ):
                # TODO: Change this to be correct sensor for RAD
                view_entity = f"sensor.{slugify(config_entry.runtime_data.browser_id)}_browser_path"

            config_entry.async_on_unload(
                async_track_state_change_event(
                    hass, view_entity, self._async_on_view_change
                )
            )

        # Add mic mute switch listener
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

    async def browser_navigate(self, path: str):
        """Call browser navigate option."""

        # Get entity id of VA entity
        entity_id = f"sensor.{slugify(self.config_entry.runtime_data.name)}"

        # Call our navigate service
        await self.hass.services.async_call(
            DOMAIN,
            "navigate",
            {
                CONF_DEVICE: entity_id,
                CONF_PATH: path,
            },
        )

    async def cycle_display(self, views: list[str]):
        """Cycle display."""

        async def _interval_timer_expiry(view_index: int):
            if self.config_entry.runtime_data.mode == VAMode.CYCLE:
                # still in cycle mode
                if view_index > (len(views) - 1):
                    view_index = 0

                # Navigate browser
                await self.browser_navigate(
                    f"{self.config_entry.runtime_data.dashboard}/{views[view_index]}",
                )

                # Set next timeout
                self.hass.loop.call_later(
                    timeout,
                    partial(
                        self.hass.create_task, _interval_timer_expiry(view_index + 1)
                    ),
                )
            else:
                _LOGGER.info("Cycle display terminated")

        timeout = self.config_entry.runtime_data.view_timeout
        await _interval_timer_expiry(0)
        _LOGGER.info("Cycle display started")

    # ---------------------------------------------------------------------------------------
    # Actions for monitoring changes to external entities
    # ---------------------------------------------------------------------------------------

    @callback
    def _async_on_view_change(self, event: Event[EventStateChangedData]) -> None:
        current_view = event.data["new_state"].state
        previous_view = (
            event.data["old_state"].state if event.data["old_state"] else None
        )

        # TODO: Decide when to save values to runtime_data._current_view and _previous_view for hold mode
        # And then utilise these if navigate in that mode.

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

    async def async_set_state_changed_attribute(self, event: Event):
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
            await self._async_on_dnd_device_state_change(event)

        if attribute == CONF_MODE:
            await self._async_on_mode_state_change(event)

    async def _async_on_dnd_device_state_change(self, event: Event) -> None:
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

    async def _async_on_mode_state_change(self, event: Event) -> None:
        """Set mode status icon."""

        new_mode = event.data["new_value"]

        _LOGGER.info("MODE STATE: %s", new_mode)
        status_icons = self.config_entry.runtime_data.status_icons.copy()

        modes = [VAMode.HOLD, VAMode.CYCLE]

        # Remove all mode icons
        for mode in modes:
            if mode in status_icons:
                status_icons.remove(mode)

        # Now add back any you want
        if new_mode in modes and new_mode not in status_icons:
            status_icons.append(new_mode)

        self.config_entry.runtime_data.status_icons = status_icons
        self.update_entity()

        if new_mode == VAMode.NORMAL:
            # Add navigate to default view
            await self.browser_navigate(self.config_entry.runtime_data.home)
            _LOGGER.info("NAVIGATE TO: %s", new_mode)

        elif new_mode == VAMode.MUSIC:
            # Add navigate to music view
            await self.browser_navigate(self.config_entry.runtime_data.music)

            # --------------------------------------------
            # Service call option
            # --------------------------------------------
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {
                    "entity_id": "switch.android_satellite_viewassist_office_wyoming_mute"
                },
            )

            _LOGGER.info("NAVIGATE TO: %s", new_mode)

        elif new_mode == VAMode.CYCLE:
            # Add start cycle mode
            # Pull cycle_mode attribute
            await self.cycle_display(
                views=["music", "info", "weather", "clock"],
            )
            _LOGGER.info("START MODE: %s", new_mode)
        elif new_mode == VAMode.ROTATE:
            #
            # Test image rotate service
            #
            image_path = await self.hass.async_add_executor_job(
                get_random_image,
                self.hass,
                "/config/www/viewassist/backgrounds",
                "local",
            )
            _LOGGER.info("START MODE: %s %s", new_mode, image_path)
