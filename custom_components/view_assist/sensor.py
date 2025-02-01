from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.config_validation import make_entity_service_schema
import voluptuous as vol
from .const import DOMAIN

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up sensors from a config entry."""
    sensors = [ViewAssistSensor(config_entry.data)]
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        name="set_state",
        schema=make_entity_service_schema({str: cv.match_all}, extra=vol.ALLOW_EXTRA),
        func="set_entity_state"
    )
    async_add_entities(sensors)

class ViewAssistSensor(SensorEntity):
    """Representation of a View Assist Sensor."""

    _attr_should_poll = False

    def __init__(self, config):
        """Initialize the sensor."""
        self._attr_name = config["name"]
        self._type = config["type"]
        self._attr_unique_id = f"{self._attr_name}_vasensor"
        self._mic_device = config["mic_device"]
        self._mediaplayer_device = config["mediaplayer_device"]
        self._musicplayer_device = config["musicplayer_device"]
        self._display_device = config.get("display_device")  # Optional for audio_only
        self._browser_id = config.get("browser_id", "")  # Optional for audio_only
        self._attr_native_value = ""
        self._attr_extra_state_attributes = {
            "type": self._type,
            "mic_device": self._mic_device,
            "mediaplayer_device": self._mediaplayer_device,
            "musicplayer_device": self._musicplayer_device,
        }

        # Only add these attributes if they exist
        if self._display_device:
            self._attr_extra_state_attributes["display_device"] = self._display_device
        if self._browser_id:
            self._attr_extra_state_attributes["browser_id"] = self._browser_id

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
            self._attr_extra_state_attributes[k] = v
        self.schedule_update_ha_state()

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return "mdi:glasses"