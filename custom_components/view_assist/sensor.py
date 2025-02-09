import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.config_validation import make_entity_service_schema
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, VAConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: VAConfigEntry, async_add_entities
):
    """Set up sensors from a config entry."""
    sensors = [ViewAssistSensor(config_entry)]
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

    def __init__(self, config: VAConfigEntry):
        """Initialize the sensor."""

        self.config = config

        self._attr_name = config.data["name"]
        self._type = config.data["type"]
        self._attr_unique_id = f"{self._attr_name}_vasensor"
        self._mic_device = config.data["mic_device"]
        self._mediaplayer_device = config.data["mediaplayer_device"]
        self._musicplayer_device = config.data["musicplayer_device"]
        self._mode = config.options.get("mode", "normal")
        self._view_timeout = config.options.get("view_timeout", "20")
        self._do_not_disturb = config.options.get("do_not_disturb", False)
        self._status_icons = config.options.get("status_icons", "[]")
        self._status_icons_size = config.options.get("status_icons_size", "8vw")
        self._status_assist_prompt = config.options.get("assist_prompt", "blur pop up")
        self._font_style = config.options.get("font_style", "Roboto")
        self._use_24_hour_time = config.options.get("use_24_hour_time", False)
        self._use_announce = config.options.get("use_announce", True)
        self._background = config.options.get(
            "background", "/local/viewassist/backgrounds/mybackground.jpg"
        )
        self._weather_entity = config.options.get("weather_entity", "weather.home")
        self._mic_type = config.options.get(
            "mic_type", "Home Assistant Voice Satellite"
        )
        self._display_type = config.options.get("display_type", "BrowserMod")
        self._display_device = config.data.get(
            "display_device"
        )  # Optional for audio_only
        self._browser_id = config.data.get("browser_id")  # Optional for audio_only
        self._attr_native_value = ""

    async def async_added_to_hass(self) -> None:
        """Run when entity is about to be added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self.config.entry_id}_update",
                self.update,
            )
        )

    @callback
    def update(self, *args):
        """Update entity."""
        self.schedule_update_ha_state(True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity attributes."""
        attrs = {
            "type": self._type,
            "mic_device": self._mic_device,
            "mediaplayer_device": self._mediaplayer_device,
            "musicplayer_device": self._musicplayer_device,
            # "mode": self._mode,
            "view_timeout": self._view_timeout,
            # "do_not_disturb": self._do_not_disturb,
            # "status_icons": self._status_icons,
            "status_icons_size": self._status_icons_size,
            "status_assist_prompt": self._status_assist_prompt,
            "font_style": self._font_style,
            "use_24_hour_time": self._use_24_hour_time,
            "use_announce": self._use_announce,
            "background": self._background,
            "weather_entity": self._weather_entity,
            "mic_type": self._mic_type,
            "display_type": self._display_type,
        }

        # Only add these attributes if they exist
        if self._display_device:
            attrs["display_device"] = self._display_device
        if self._browser_id:
            attrs["browser_id"] = self._browser_id

        # Add named attributes from runtime data
        for k in self.config.runtime_data.__dict__:
            if not k.startswith(("_", "__")) and k != "extra_data":
                attrs[k] = getattr(self.config.runtime_data, k)

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
                continue

            # Set the value of named vartiables or add/update to extra_data dict
            if hasattr(self.config.runtime_data, k):
                setattr(self.config.runtime_data, k, v)
            else:
                self.config.runtime_data.extra_data[k] = v

        self.schedule_update_ha_state()

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return "mdi:glasses"
