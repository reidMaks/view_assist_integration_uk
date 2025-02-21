"""Handlers alarm repeater."""

import asyncio
from dataclasses import dataclass
import logging
import time
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity, entity_registry as er
from homeassistant.helpers.entity_component import DATA_INSTANCES, EntityComponent
from homeassistant.helpers.network import get_url

from .const import BROWSERMOD_DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class PlayingMedia:
    """Class to hold paused media."""

    media_content_id: str
    media_type: str = "music"
    media_position: float = 0
    volume: int = 0
    player: Any | None = None
    queue: Any | None = None


class VAAlarmRepeater:
    """Class to handle announcing on media player with resume."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config = config

        self.alarm_tasks: dict[str, asyncio.Task] = {}

    def _get_entity_from_entity_id(self, entity_id: str):
        """Get entity object from entity_id."""
        domain = entity_id.partition(".")[0]
        entity_comp: EntityComponent[entity.Entity] | None
        entity_comp = self.hass.data.get(DATA_INSTANCES, {}).get(domain)
        if entity_comp:
            return entity_comp.get_entity(entity_id)
        return None

    def _get_integration_domain(self, entity_id: str) -> str | None:
        """Get integration of entity id."""

        entity_registry = er.async_get(self.hass)
        _entity = entity_registry.async_get(entity_id)
        if _entity:
            return _entity.platform
        return None

    def get_currently_playing_media(
        self, media_entity: MediaPlayerEntity
    ) -> PlayingMedia | None:
        """Try and get currently playing media."""

        # If not playing then return None
        if media_entity.state != MediaPlayerState.PLAYING:
            _LOGGER.debug(
                "%s is in %s state - will not attempt restore",
                media_entity.entity_id,
                media_entity.state,
            )
            return None

        data = None

        # Hook into integration data to get currently playing media
        media_integration = media_entity.platform.platform_name

        _LOGGER.debug("Media entity platform: %s", media_integration)
        # Browermod
        if media_integration == BROWSERMOD_DOMAIN:
            _data = media_entity._data  # noqa: SLF001
            data = PlayingMedia(
                media_content_id=_data["player"].get("src"),
                media_type="music",
                media_position=_data.get("player", {}).get("media_position", None),
                volume=_data.get("player", {}).get("volume", 0),
            )
        # HA Voice Satellite
        elif media_integration == "esphome":
            _LOGGER.debug("MUSIC ASSISTANT DATA: %s", media_entity._state)  # noqa: SLF001

        # An integration may populate these properties - most don't seem to
        elif content_id := media_entity.media_content_id:
            data = PlayingMedia(
                media_content_id=content_id,
                media_type=media_entity.media_content_type or "music",
                media_position=media_entity.media_position,
            )

        _LOGGER.debug("Current playing media: %s", data)
        return data

    async def wait_for_state(
        self,
        media_entity: MediaPlayerEntity,
        data_var: str,
        attribute: str,
        wanted_state: Any,
        timeout: float = 10.0,
    ) -> None:
        """Wait for an object attribute to reach the given state."""
        start_timestamp = time.time()
        _LOGGER.debug("Waiting for %s to reach state %s", attribute, wanted_state)
        try:
            async with asyncio.timeout(timeout):
                while (
                    getattr(getattr(media_entity, data_var), attribute) != wanted_state
                ):
                    await asyncio.sleep(0.2)

        except TimeoutError:
            _LOGGER.debug(
                "%s did not reach state %s within the timeout of %s seconds",
                attribute,
                wanted_state,
                timeout,
            )
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error("ERROR: %s", ex)

        elapsed_time = round(time.time() - start_timestamp, 2)
        _LOGGER.debug(
            "%s reached state %s within %s seconds",
            attribute,
            wanted_state,
            elapsed_time,
        )

    async def wait_for_idle(self, media_entity: MediaPlayerEntity, timeout: int = 30):
        """Wait for media player to be idle."""
        start_timestamp = time.time()
        _LOGGER.debug("Waiting for %s to be idle", media_entity.entity_id)
        try:
            async with asyncio.timeout(timeout):
                while media_entity.state != MediaPlayerState.IDLE:
                    await asyncio.sleep(0.2)

        except TimeoutError:
            _LOGGER.debug(
                "%s did not become idle within the timeout of %s seconds",
                media_entity.entity_id,
                timeout,
            )
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error("ERROR: %s", ex)

        elapsed_time = round(time.time() - start_timestamp, 2)
        _LOGGER.debug(
            "%s reached idle state within %s seconds",
            media_entity.entity_id,
            elapsed_time,
        )

    async def repeat_announce(
        self,
        integration: str,
        media_entity: MediaPlayerEntity,
        media_url: str,
        max_repeats: int = 0,
    ):
        """Repeat announcement using announce methods."""
        _LOGGER.debug("Using announce for alarm")

        if media_url.startswith("/"):
            media_url = media_url.removeprefix("/")
            media_url = f"{get_url(self.hass)}/{media_url}"

        if integration == "music_assistant":
            i = 1
            while i <= max_repeats or max_repeats == 0:
                try:
                    _LOGGER.debug("Announcing iteration %s", i)
                    await self.hass.services.async_call(
                        "music_assistant",
                        "play_announcement",
                        service_data={"url": media_url},
                        target={"entity_id": "media_player.snapweb_client"},
                    )
                    await asyncio.sleep(1)
                    await self.wait_for_state(
                        media_entity, "player", "announcement_in_progress", False
                    )
                    await asyncio.sleep(1)
                    i += 1
                except Exception as ex:  # noqa: BLE001
                    _LOGGER.error("ERROR: %s", ex)
                    return
            _LOGGER.debug("Announce ended")

    async def repeat_media(
        self,
        media_entity: MediaPlayerEntity,
        media_type: str,
        media_url: str,
        max_repeats: int = 0,
    ):
        """Repeat playing media file."""
        _LOGGER.debug("Using repeat media for alarm")

        if media_url.startswith("/"):
            media_url = media_url.removeprefix("/")
            media_url = f"{get_url(self.hass)}/{media_url}"

        i = 1
        try:
            while i <= max_repeats or not max_repeats:
                await self.hass.services.async_call(
                    "media_player",
                    "play_media",
                    {
                        "entity_id": media_entity.entity_id,
                        "media_content_type": "music",
                        "media_content_id": media_url,
                    },
                )
                await asyncio.sleep(0.5)
                await self.wait_for_idle(media_entity)
                i += 1
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error("ERROR: %s", ex)
            return
        _LOGGER.debug("Repeat media ended")

    async def cancel_alarm_sound(self, entity_id: str | None = None):
        """Cancel announcement."""
        if entity_id:
            entities = [entity_id]
        else:
            entities = list(self.alarm_tasks.keys())

        for mp_entity_id in entities:
            await self.hass.services.async_call(
                "media_player", "media_stop", {"entity_id": mp_entity_id}
            )
            if (
                self.alarm_tasks.get(mp_entity_id)
                and not self.alarm_tasks[mp_entity_id].done()
            ):
                self.alarm_tasks[mp_entity_id].cancel()

    async def alarm_sound(
        self,
        entity_id: str,
        media_url: str,
        media_type: MediaType = "music",
        resume: bool = True,
        max_repeats: int = 0,
    ):
        """Announce to media player and resume."""

        # Get instance of media player
        media_entity: MediaPlayerEntity
        if media_entity := self._get_entity_from_entity_id(entity_id):
            media_integration = media_entity.platform.platform_name

            if media_integration == "music_assistant":
                self.alarm_tasks[entity_id] = self.config.async_create_background_task(
                    self.hass,
                    self.repeat_announce(
                        media_integration, media_entity, media_url, max_repeats
                    ),
                    name=f"AnnounceRepeat-{entity_id}",
                )
            else:
                playing_media = self.get_currently_playing_media(media_entity)

                # Sound alarm
                self.alarm_tasks[entity_id] = self.config.async_create_background_task(
                    self.hass,
                    self.repeat_media(media_entity, media_type, media_url, max_repeats),
                    name=f"AlarmRepeat-{entity_id}",
                )

                # Wait for alarm media task to finish
                while not self.alarm_tasks[entity_id].done():
                    await asyncio.sleep(0.2)

                self.alarm_tasks.pop(entity_id)

                if resume and playing_media:
                    _LOGGER.debug("Resuming media: %s", playing_media)
                    await self.hass.services.async_call(
                        "media_player",
                        "play_media",
                        {
                            "entity_id": entity_id,
                            "media_content_type": playing_media.media_type,
                            "media_content_id": playing_media.media_content_id,
                        },
                    )

                    if playing_media.media_position:
                        await self.hass.services.async_call(
                            "media_player",
                            "media_seek",
                            {
                                "entity_id": entity_id,
                                "seek_position": playing_media.media_position,
                            },
                        )
        return {}
