import logging
import os
import random
import requests
from datetime import datetime
import voluptuous as vol

from homeassistant.const import CONF_DEVICE, CONF_PATH
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.helpers import entity_registry as er, selector
from homeassistant.helpers.event import partial

from .const import DOMAIN, CONF_BROWSER_ID, CONF_DISPLAY_TYPE
_LOGGER = logging.getLogger(__name__)

NAVIGATE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE): selector.EntitySelector(
            selector.EntitySelectorConfig(integration=DOMAIN)
        ),
        vol.Required(CONF_PATH): str,
        vol.Required(CONF_DISPLAY_TYPE): str,
    }
)


async def setup_services(hass: HomeAssistant):
    """Initialise VA services."""
    ##################
    # Get Target Satellite
    # Used to determine which VA satellite is being used based on its microphone device
    #
    # Sample usage
    # action: view_assist.get_target_satellite
    # data:
    #   device_id: 4385828338e48103f63c9f91756321df

    async def handle_get_target_satellite(call: ServiceCall) -> ServiceResponse:
        """Handle a get target satellite lookup call."""
        device_id = call.data.get("device_id")
        entity_registry = er.async_get(hass)

        entities = []

        entry_ids = [
            entry.entry_id for entry in hass.config_entries.async_entries(DOMAIN)
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
            if state := hass.states.get(entity_id):
                if mic_entity_id := state.attributes.get("mic_device"):
                    if mic_entity := entity_registry.async_get(mic_entity_id):
                        if mic_entity.device_id == device_id:
                            target_satellite_devices.append(entity_id)

        # Return the list of target_satellite_devices
        # This should match only one VA device
        return {"target_satellite": target_satellite_devices}

    hass.services.async_register(
        DOMAIN,
        "get_target_satellite",
        handle_get_target_satellite,
        supports_response=SupportsResponse.ONLY,
    )

    #########

    #########
    # Handle Navigation
    # Used to determine how to change the view on the VA device
    #
    # action: view_assist.navigate
    # data:
    #   target_display_device: sensor.viewassist_office_browser_path
    #   target_display_type: browsermod
    #   path: /dashboard-viewassist/weather
    #
    async def handle_navigate(call: ServiceCall):
        """Handle a navigate to view call."""
        va_entity_id = call.data.get("device")
        path = call.data.get("path")
        display_type = call.data.get("display_type")

        # get config entry from entity id to allow access to browser_id parameter
        entity_registry = er.async_get(hass)
        if entity := entity_registry.async_get(va_entity_id):
            entity_config_entry = hass.config_entries.async_get_entry(
                entity.config_entry_id
            )
            browser_id = entity_config_entry.runtime_data.browser_id

            if browser_id:
                await browser_navigate(browser_id, path, display_type, "/view-assist/clock")

    hass.services.async_register(
        DOMAIN, "navigate", handle_navigate, schema=NAVIGATE_SERVICE_SCHEMA
    )

    async def browser_navigate(
        browser_id: str,
        path: str,
        display_type: str,
        revert_path: str | None = None,
        timeout: int = 10,
    ):
        """Navigate browser to defined view.

        Optionally revert to another view after timeout.
        """
        _LOGGER.info("Navigating: browser_id: %s, path: %s, display_type: %s", browser_id, path, display_type)

        if display_type == "BrowserMod":
            await hass.services.async_call(
                "browser_mod",
                "navigate",
                {"browser_id": browser_id, "path": path},
            )
        elif display_type == "Remote Assist Display":
            await hass.services.async_call(
                "remote_assist_display",
                "navigate",
                {"target": browser_id, "path": path},
            )            

        if revert_path and timeout:
            _LOGGER.info("Adding revert to %s in %ss", revert_path, timeout)
            hass.loop.call_later(
                10,
                partial(
                    hass.create_task,
                    browser_navigate(browser_id, revert_path, display_type),
                    f"Revert browser {browser_id}",
                ),
            )

    async def handle_get_random_image(call: ServiceCall) -> ServiceResponse:
        """yaml
        name: View Assist Select Random Image
        description: Selects a random image from the specified directory or downloads a new image
        """
        directory = call.data.get("directory")
        source = call.data.get("source", "local")  # Default to "local" if source is not provided
        
        valid_extensions = ('.jpeg', '.jpg', '.tif', '.png')

        if source == "local":
            # Translate /local/ to /config/www/ for directory validation
            if directory.startswith("/local/"):
                filesystem_directory = directory.replace("/local/", "/config/www/", 1)
            else:
                filesystem_directory = directory

            # Verify the directory exists
            if not os.path.isdir(filesystem_directory):
                return {"error": f"The directory '{filesystem_directory}' does not exist."}

            # List only image files with the valid extensions
            images = [f for f in os.listdir(filesystem_directory) if f.lower().endswith(valid_extensions)]

            # Check if any images were found
            if not images:
                return {"error": f"No images found in the directory '{filesystem_directory}'."}

            # Select a random image
            selected_image = random.choice(images)

            # Replace /config/www/ with /local/ for constructing the relative path
            if filesystem_directory.startswith("/config/www/"):
                relative_path = filesystem_directory.replace("/config/www/", "/local/")
            else:
                relative_path = directory

            # Ensure trailing slash in the relative path
            if not relative_path.endswith('/'):
                relative_path += '/'

            # Construct the image path
            image_path = f"{relative_path}{selected_image}"

        elif source == "download":
            url = "https://unsplash.it/640/425?random"
            response = requests.get(url)

            if response.status_code == 200:
                current_time = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"random_{current_time}.jpg"
                full_path = os.path.join(directory, filename)

                with open(full_path, "wb") as file:
                    file.write(response.content)

                # Remove previous background image
                for file in os.listdir(directory):
                    if file.startswith("random_") and file != filename:
                        os.remove(os.path.join(directory, file))

                image_path = full_path
            else:
                # Return existing image if the download fails
                existing_files = [os.path.join(directory, file) for file in os.listdir(directory) if file.startswith("random_")]
                image_path = existing_files[0] if existing_files else None

            if not image_path:
                return {"error": "Failed to download a new image and no existing images found."}

        else:
            return {"error": "Invalid source specified. Use 'local' or 'download'."}

        # Return the image path in a dictionary
        return {"image_path": image_path}

    hass.services.async_register(
        DOMAIN,
        "get_random_image",
        handle_get_random_image,
        supports_response=SupportsResponse.ONLY,
    )