"""Class to handle persistent storage."""

from collections.abc import Callable
from dataclasses import dataclass
import datetime as dt
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HassJob, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORE_NAME = DOMAIN


@dataclass
class Timer:
    """Class to hold timer."""

    id: int
    expires: dt.datetime
    name: str | None = None
    callback: Callable | None = None
    cancel: Callable | None = None


class VATimers:
    """Class to handle VA timers."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry):
        """Initialise."""
        self.hass = hass
        self.config = config

        self._store = Store[list[Timer]](hass, 1, STORE_NAME)
        self.timers: list[Timer] = []

    async def load(self):
        """Load data store."""
        self.timers = await self._store.async_load()

    async def add_timer(self, timer: Timer):
        """Add timer to store."""
        timer_cancel = async_track_point_in_time(
            self.hass,
            HassJob(
                self._timer_expired_callback,
                f"Timer{timer.id}",
                cancel_on_shutdown=False,
            ),
            timer.expires,
        )
        # timer.cancel = timer_cancel
        self.timers.append(timer)
        await self._store.async_save(self.timers)

        _LOGGER.warning("TIMERS: %s", self.timers)

    @callback
    def _timer_expired_callback(self, *args):
        _LOGGER.info("TIMER EXPIRED: %s", args)
