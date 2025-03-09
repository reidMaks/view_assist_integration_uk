"""View Assist websocket handlers."""

from dataclasses import dataclass
import logging
import time
from typing import Any

import voluptuous as vol

from homeassistant.components.websocket_api import (
    ActiveConnection,
    async_register_command,
    async_response,
    websocket_command,
)
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .helpers import get_entity_id_by_browser_id, get_mimic_entity_id

_LOGGER = logging.getLogger(__name__)


@dataclass
class MockAdminUser:
    """Mock admin user for use in MockWSConnection."""

    is_admin = True


class MockWSConnection:
    """Mock a websocket connection to be able to call websocket handler functions.

    This is here for creating the View Assist dashboard
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initilise."""
        self.hass = hass
        self.user = MockAdminUser()

        self.failed_request: bool = False

    def send_result(self, id, item):
        """Receive result."""
        self.failed_request = False

    def send_error(self, id, code, msg):
        """Receive error."""
        self.failed_request = True

    def execute_ws_func(self, ws_type: str, msg: dict[str, Any]) -> bool:
        """Execute ws function."""
        if self.hass.data["websocket_api"].get(ws_type):
            try:
                handler, schema = self.hass.data["websocket_api"][ws_type]
                if schema is False:
                    handler(self.hass, self, msg)
                else:
                    handler(self.hass, self, schema(msg))
            except Exception as ex:  # noqa: BLE001
                _LOGGER.error("Error calling %s.  Error is %s", ws_type, ex)
                return False
            else:
                return True
        return False


async def async_register_websockets(hass: HomeAssistant):
    """Register websocket functions."""

    # Get sensor entity by browser id
    @websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/get_entity_id",
            vol.Required("browser_id"): str,
        }
    )
    @async_response
    async def websocket_get_entity_by_browser_id(
        hass: HomeAssistant, connection: ActiveConnection, msg: dict
    ) -> None:
        """Get entity id by browser id."""
        output = get_entity_id_by_browser_id(hass, msg["browser_id"])
        if not output:
            output = get_mimic_entity_id(hass)

        connection.send_result(msg["id"], output)

    # Get server datetime
    @websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/get_server_time_delta",
            vol.Required("epoch"): int,
        }
    )
    @async_response
    async def websocket_get_server_time(
        hass: HomeAssistant, connection: ActiveConnection, msg: dict
    ) -> None:
        """Get entity id by browser id."""

        delta = round(time.time() * 1000) - msg["epoch"]
        connection.send_result(msg["id"], delta)

    async_register_command(hass, websocket_get_entity_by_browser_id)
    async_register_command(hass, websocket_get_server_time)
