"""Integration services."""

from asyncio import TimerHandle
import logging

import voluptuous as vol

from homeassistant.const import (
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_PATH,
    CONF_TYPE,
)
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    config_validation as cv,
    entity_registry as er,
    selector,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .alarm_repeater import VAAlarmRepeater
from .const import (
    CONF_EXTRA,
    CONF_INCLUDE_EXPIRED,
    CONF_REMOVE_ALL,
    CONF_TIME,
    CONF_TIMER_ID,
    DOMAIN,
    VAConfigEntry,
)
from .dashboard import DashboardManager
from .helpers import get_mimic_entity_id, get_random_image
from .timers import VATimers, decode_time_sentence

_LOGGER = logging.getLogger(__name__)


NAVIGATE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE): selector.EntitySelector(
            selector.EntitySelectorConfig(integration=DOMAIN)
        ),
        vol.Required(CONF_PATH): str,
    }
)

SET_TIMER_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Exclusive(CONF_ENTITY_ID, "target"): cv.entity_id,
        vol.Exclusive(CONF_DEVICE_ID, "target"): vol.Any(cv.string, None),
        vol.Required(CONF_TYPE): str,
        vol.Optional(CONF_NAME): str,
        vol.Required(CONF_TIME): str,
        vol.Optional(CONF_EXTRA): vol.Schema({}, extra=vol.ALLOW_EXTRA),
    }
)


CANCEL_TIMER_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Exclusive(CONF_TIMER_ID, "target"): str,
        vol.Exclusive(CONF_ENTITY_ID, "target"): cv.entity_id,
        vol.Exclusive(CONF_DEVICE_ID, "target"): vol.Any(cv.string, None),
        vol.Exclusive(CONF_REMOVE_ALL, "target"): bool,
    }
)

SNOOZE_TIMER_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TIMER_ID): str,
        vol.Required(CONF_TIME): str,
    }
)

GET_TIMERS_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Exclusive(CONF_TIMER_ID, "target"): str,
        vol.Exclusive(CONF_ENTITY_ID, "target"): cv.entity_id,
        vol.Exclusive(CONF_DEVICE_ID, "target"): vol.Any(cv.string, None),
        vol.Optional(CONF_INCLUDE_EXPIRED, default=False): bool,
    }
)

ALARM_SOUND_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
            selector.EntitySelectorConfig(integration=DOMAIN)
        ),
        vol.Required("media_file"): str,
        vol.Optional("resume_media", default=True): bool,
        vol.Optional("max_repeats", default=0): int,
    }
)

STOP_ALARM_SOUND_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTITY_ID): selector.EntitySelector(
            selector.EntitySelectorConfig(integration=DOMAIN)
        ),
    }
)

BROADCAST_EVENT_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("event_name"): str,
        vol.Required("event_data"): dict,
    }
)

VIEW_SERVICE_SCHEMA = vol.Schema(
    {vol.Required("view_name"): str, vol.Optional("overwrite", default=False): bool}
)


class VAServices:
    """Class to manage services."""

    def __init__(self, hass: HomeAssistant, config: VAConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config = config

        self.navigate_task: dict[str, TimerHandle] = {}

    async def async_setup_services(self):
        """Initialise VA services."""

        self.hass.services.async_register(
            DOMAIN,
            "get_target_satellite",
            self.async_handle_get_target_satellite,
            supports_response=SupportsResponse.ONLY,
        )

        self.hass.services.async_register(
            DOMAIN,
            "navigate",
            self.async_handle_navigate,
            schema=NAVIGATE_SERVICE_SCHEMA,
        )

        self.hass.services.async_register(
            DOMAIN,
            "set_timer",
            self.async_handle_set_timer,
            schema=SET_TIMER_SERVICE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

        self.hass.services.async_register(
            DOMAIN,
            "snooze_timer",
            self.async_handle_snooze_timer,
            schema=SNOOZE_TIMER_SERVICE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

        self.hass.services.async_register(
            DOMAIN,
            "cancel_timer",
            self.async_handle_cancel_timer,
            schema=CANCEL_TIMER_SERVICE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

        self.hass.services.async_register(
            DOMAIN,
            "get_timers",
            self.async_handle_get_timers,
            schema=GET_TIMERS_SERVICE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

        self.hass.services.async_register(
            DOMAIN,
            "get_random_image",
            self.async_handle_get_random_image,
            supports_response=SupportsResponse.ONLY,
        )

        self.hass.services.async_register(
            DOMAIN,
            "sound_alarm",
            self.async_handle_alarm_sound,
            schema=ALARM_SOUND_SERVICE_SCHEMA,
        )

        self.hass.services.async_register(
            DOMAIN,
            "cancel_sound_alarm",
            self.async_handle_stop_alarm_sound,
            schema=STOP_ALARM_SOUND_SERVICE_SCHEMA,
        )

        self.hass.services.async_register(
            DOMAIN,
            "broadcast_event",
            self.async_handle_broadcast_event,
            schema=BROADCAST_EVENT_SERVICE_SCHEMA,
        )

        self.hass.services.async_register(
            DOMAIN,
            "load_view",
            self.async_handle_load_view,
            schema=VIEW_SERVICE_SCHEMA,
        )

        self.hass.services.async_register(
            DOMAIN,
            "download_view",
            self.async_handle_download_view,
            schema=VIEW_SERVICE_SCHEMA,
        )

        self.hass.services.async_register(
            DOMAIN,
            "save_view",
            self.async_handle_save_view,
            schema=VIEW_SERVICE_SCHEMA,
        )

    # -----------------------------------------------------------------------
    # Get Target Satellite
    # Used to determine which VA satellite is being used based on its microphone device
    #
    # Sample usage
    # action: view_assist.get_target_satellite
    # data:
    #   device_id: 4385828338e48103f63c9f91756321df
    # -----------------------------------------------------------------------

    async def async_handle_broadcast_event(self, call: ServiceCall):
        """Fire an event with the provided name and data.

        name: View Assist Broadcast Event
        description: Immediately fires an event with the provided name and data
        """
        event_name = call.data.get("event_name")
        event_data = call.data.get("event_data", {})
        # Fire the event
        self.hass.bus.fire(event_name, event_data)

    async def async_handle_alarm_sound(self, call: ServiceCall) -> ServiceResponse:
        """Handle alarm sound."""
        alarms: VAAlarmRepeater = self.hass.data[DOMAIN]["alarms"]
        entity_id = call.data.get(CONF_ENTITY_ID)
        media_file = call.data.get("media_file")
        resume_media = call.data.get("resume_media")
        max_repeats = call.data.get("max_repeats")

        return await alarms.alarm_sound(
            entity_id, media_file, "music", resume_media, max_repeats
        )

    async def async_handle_stop_alarm_sound(self, call: ServiceCall):
        """Handle stop alarm sound."""
        alarms: VAAlarmRepeater = self.hass.data[DOMAIN]["alarms"]
        entity_id = call.data.get(CONF_ENTITY_ID)
        await alarms.cancel_alarm_sound(entity_id)

    async def async_handle_get_target_satellite(
        self, call: ServiceCall
    ) -> ServiceResponse:
        """Handle a get target satellite lookup call."""
        device_id = call.data.get(CONF_DEVICE_ID)
        entity_registry = er.async_get(self.hass)

        entities = []

        entry_ids = [
            entry.entry_id for entry in self.hass.config_entries.async_entries(DOMAIN)
        ]

        for entry_id in entry_ids:
            integration_entities = er.async_entries_for_config_entry(
                entity_registry, entry_id
            )
            entity_ids = [entity.entity_id for entity in integration_entities]
            entities.extend(entity_ids)

        # Fetch the 'mic_device' attribute for each entity
        # compare the device_id of mic_device to the value passed in to the service
        # return the match for the satellite that contains that mic_device
        target_satellite_devices = []
        for entity_id in entities:
            if state := self.hass.states.get(entity_id):
                if mic_entity_id := state.attributes.get("mic_device"):
                    if mic_entity := entity_registry.async_get(mic_entity_id):
                        if mic_entity.device_id == device_id:
                            target_satellite_devices.append(entity_id)

        # Return the list of target_satellite_devices
        # This should match only one VA device
        return {"target_satellite": target_satellite_devices}

    # -----------------------------------------------------------------------
    # Handle Navigation
    # Used to determine how to change the view on the VA device
    #
    # action: view_assist.navigate
    # data:
    #   target_display_device: sensor.viewassist_office_browser_path
    #   path: /dashboard-viewassist/weather
    # ------------------------------------------------------------------------
    async def async_handle_navigate(self, call: ServiceCall):
        """Handle a navigate to view call."""

        va_entity_id = call.data.get(CONF_DEVICE)
        path = call.data.get(CONF_PATH)

        # get config entry from entity id to allow access to browser_id parameter
        entity_registry = er.async_get(self.hass)
        if va_entity := entity_registry.async_get(va_entity_id):
            entity_config_entry: VAConfigEntry = (
                self.hass.config_entries.async_get_entry(va_entity.config_entry_id)
            )

            async_dispatcher_send(
                self.hass,
                f"{DOMAIN}_{entity_config_entry.entry_id}_browser_navigate",
                {"path": path},
            )

    # ----------------------------------------------------------------
    # TIMERS
    # ----------------------------------------------------------------
    async def async_handle_set_timer(self, call: ServiceCall) -> ServiceResponse:
        """Handle a set timer service call."""
        entity_id = call.data.get(CONF_ENTITY_ID)
        device_id = call.data.get(CONF_DEVICE_ID)
        timer_type = call.data.get(CONF_TYPE)
        name = call.data.get(CONF_NAME)
        timer_time = call.data.get(CONF_TIME)
        extra_data = call.data.get(CONF_EXTRA)

        sentence, timer_info = decode_time_sentence(timer_time)
        if entity_id is None and device_id is None:
            mimic_device = get_mimic_entity_id(self.hass)
            if mimic_device:
                entity_id = mimic_device
                _LOGGER.warning(
                    "Using the set mimic entity %s to set timer as no entity or device id provided to the set timer service",
                    mimic_device,
                )
            else:
                raise vol.InInvalid("entity_id or device_id is required")

        extra_info = {"sentence": sentence}
        if extra_data:
            extra_info.update(extra_data)

        if timer_info:
            t: VATimers = self.hass.data[DOMAIN]["timers"]
            timer_id, timer, response = await t.add_timer(
                timer_class=timer_type,
                device_or_entity_id=entity_id if entity_id else device_id,
                timer_info=timer_info,
                name=name,
                extra_info=extra_info,
            )

            return {"timer_id": timer_id, "timer": timer, "response": response}
        return {"error": "unable to decode time or interval information"}

    async def async_handle_snooze_timer(self, call: ServiceCall) -> ServiceResponse:
        """Handle a set timer service call."""
        timer_id = call.data.get(CONF_TIMER_ID)
        timer_time = call.data.get(CONF_TIME)

        _, timer_info = decode_time_sentence(timer_time)

        if timer_info:
            t: VATimers = self.hass.data[DOMAIN]["timers"]
            timer_id, timer, response = await t.snooze_timer(
                timer_id,
                timer_info,
            )

            return {"timer_id": timer_id, "timer": timer, "response": response}
        return {"error": "unable to decode time or interval information"}

    async def async_handle_cancel_timer(self, call: ServiceCall) -> ServiceResponse:
        """Handle a cancel timer service call."""
        timer_id = call.data.get(CONF_TIMER_ID)
        entity_id = call.data.get(CONF_ENTITY_ID)
        device_id = call.data.get(CONF_DEVICE_ID)
        cancel_all = call.data.get(CONF_REMOVE_ALL, False)
        if any([timer_id, device_id, cancel_all]):
            t: VATimers = self.hass.data[DOMAIN]["timers"]
            result = await t.cancel_timer(
                timer_id=timer_id,
                device_or_entity_id=entity_id if entity_id else device_id,
                cancel_all=cancel_all,
            )
            return {"result": result}
        return {"error": "no timer id supplied"}

    async def async_handle_get_timers(self, call: ServiceCall) -> ServiceResponse:
        """Handle a cancel timer service call."""
        entity_id = call.data.get(CONF_ENTITY_ID)
        device_id = call.data.get(CONF_DEVICE_ID)
        timer_id = call.data.get(CONF_TIMER_ID)
        include_expired = call.data.get(CONF_INCLUDE_EXPIRED, False)

        t: VATimers = self.hass.data[DOMAIN]["timers"]
        result = t.get_timers(
            timer_id=timer_id,
            device_or_entity_id=entity_id if entity_id else device_id,
            include_expired=include_expired,
        )
        return {"result": result}

    async def async_handle_get_random_image(self, call: ServiceCall) -> ServiceResponse:
        """Handle random image selection.

        name: View Assist Select Random Image
        description: Selects a random image from the specified directory or downloads a new image
        """
        directory: str = call.data.get("directory")
        source: str = call.data.get(
            "source", "local"
        )  # Default to "local" if source is not provided

        return await self.hass.async_add_executor_job(
            get_random_image, self.hass, directory, source
        )

    async def async_handle_download_view(self, call: ServiceCall):
        """Handle download view."""

        view_name = call.data.get("view_name")
        overwrite = call.data.get("overwrite")
        dm: DashboardManager = self.hass.data[DOMAIN]["dashboard_manager"]
        result = await dm.download_view(view_name, overwrite)
        if not result:
            raise HomeAssistantError("Unable to download view")

    async def async_handle_load_view(self, call: ServiceCall):
        """Handle load of a view from view_assist dir."""

        view_name = call.data.get("view_name")
        overwrite = call.data.get("overwrite")
        dm: DashboardManager = self.hass.data[DOMAIN]["dashboard_manager"]
        result = await dm.load_view(view_name, overwrite=overwrite)
        if not result:
            raise HomeAssistantError("Unable to load view")

    async def async_handle_save_view(self, call: ServiceCall):
        """Handle saving view to view_assit dir."""

        view_name = call.data.get("view_name")
        overwrite = call.data.get("overwrite")
        dm: DashboardManager = self.hass.data[DOMAIN]["dashboard_manager"]
        result = await dm.save_view(view_name, overwrite)
        if not result:
            raise HomeAssistantError("Unable to save view")
