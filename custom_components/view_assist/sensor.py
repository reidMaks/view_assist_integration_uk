"""VA Sensors."""

from collections.abc import Callable
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.config_validation import make_entity_service_schema
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    OPTION_KEY_MIGRATIONS,
    VA_ATTRIBUTE_UPDATE_EVENT,
    VA_BACKGROUND_UPDATE_EVENT,
)
from .helpers import get_device_id_from_entity_id, get_mute_switch_entity_id
from .timers import VATimers
from .typed import VAConfigEntry, VATimeFormat

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: VAConfigEntry, async_add_entities
):
    """Set up sensors from a config entry."""
    sensors = [ViewAssistSensor(hass, config_entry)]
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        name="set_state",
        schema=make_entity_service_schema({str: cv.match_all}, extra=vol.ALLOW_EXTRA),
        func="set_entity_state",
    )

    async_add_entities(sensors)


class ViewAssistSensor(SensorEntity):
    """Representation of a View Assist Sensor."""

    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, config: VAConfigEntry) -> None:
        """Initialise the sensor."""

        self.hass = hass
        self.config = config

        self._attr_name = config.runtime_data.core.name
        self._type = config.runtime_data.core.type
        self._attr_unique_id = f"{self._attr_name}_vasensor"
        self._attr_native_value = ""
        self._attribute_listeners: dict[str, Callable] = {}

        self._voice_device_id = get_device_id_from_entity_id(
            self.hass, self.config.runtime_data.core.mic_device
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity is about to be added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self.config.entry_id}_update",
                self.va_update,
            )
        )

        # Add listener to timer changes
        timers: VATimers = self.hass.data[DOMAIN]["timers"]
        timers.store.add_listener(self.entity_id, self.va_update)

    @callback
    def va_update(self, *args):
        """Update entity."""
        _LOGGER.debug("Updating: %s", self.entity_id)
        self.schedule_update_ha_state(True)

    # TODO: Remove this when BPs/Views migrated
    def get_option_key_migration_value(self, value: str) -> str:
        """Get the original option key for a given new option key."""
        for key, key_value in OPTION_KEY_MIGRATIONS.items():
            if key_value == value:
                return key
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity attributes."""
        r = self.config.runtime_data

        attrs = {
            # Core settings
            "type": r.core.type,
            "mic_device": r.core.mic_device,
            "mic_device_id": get_device_id_from_entity_id(self.hass, r.core.mic_device),
            "mute_switch": get_mute_switch_entity_id(self.hass, r.core.mic_device),
            "mediaplayer_device": r.core.mediaplayer_device,
            "musicplayer_device": r.core.musicplayer_device,
            "voice_device_id": self._voice_device_id,
            # Dashboard settings
            "status_icons": r.dashboard.display_settings.status_icons,
            "status_icons_size": r.dashboard.display_settings.status_icons_size,
            "menu_config": r.dashboard.display_settings.menu_config,
            "menu_items": r.dashboard.display_settings.menu_items,
            "menu_active": self._get_menu_active_state(),
            "assist_prompt": self.get_option_key_migration_value(
                r.dashboard.display_settings.assist_prompt
            ),
            "font_style": r.dashboard.display_settings.font_style,
            "use_24_hour_time": r.dashboard.display_settings.time_format
            == VATimeFormat.HOUR_24,
            "background": r.dashboard.background_settings.background,
            # Default settings
            "mode": r.default.mode,
            "view_timeout": r.default.view_timeout,
            "do_not_disturb": r.default.do_not_disturb,
            "use_announce": r.default.use_announce,
            "weather_entity": r.default.weather_entity,
        }

        # Only add these attributes if they exist
        if r.core.display_device:
            attrs["display_device"] = r.core.display_device
        if r.core.intent_device:
            attrs["intent_device"] = r.core.intent_device

        # Add extra_data attributes from runtime data
        attrs.update(self.config.runtime_data.extra_data)

        return attrs

    def set_entity_state(self, **kwargs):
        """Set the state of the entity."""
        for k, v in kwargs.items():
            if k == "entity_id":
                continue
            if k == "allow_create":
                continue
            if k == "state":
                self._attr_native_value = v

            # Fire event if value changes to entity listener
            if hasattr(self.config.runtime_data.default, k):
                old_val = getattr(self.config.runtime_data.default, k)
            elif self.config.runtime_data.extra_data.get(k) is not None:
                old_val = self.config.runtime_data.extra_data[k]
            else:
                old_val = None
            if v != old_val:
                kwargs = {"attribute": k, "old_value": old_val, "new_value": v}
                self.hass.bus.fire(
                    VA_ATTRIBUTE_UPDATE_EVENT.format(self.config.entry_id), kwargs
                )

                # Fire background changed event to support linking device backgrounds
                if k == "background":
                    self.hass.bus.fire(
                        VA_BACKGROUND_UPDATE_EVENT.format(self.entity_id), kwargs
                    )

            # Set the value of named vartiables or add/update to extra_data dict
            if hasattr(self.config.runtime_data.default, k):
                setattr(self.config.runtime_data.default, k, v)
            else:
                self.config.runtime_data.extra_data[k] = v

        self.schedule_update_ha_state(True)

    def _get_menu_active_state(self) -> bool:
        """Get the menu active state from menu manager."""
        menu_manager = self.hass.data[DOMAIN].get("menu_manager")
        if not menu_manager:
            return False
            
        if hasattr(menu_manager, "_menu_states") and self.entity_id in menu_manager._menu_states:
            return menu_manager._menu_states[self.entity_id].active
            
        return False

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return "mdi:glasses"
