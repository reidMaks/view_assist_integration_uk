"""Update entities for HACS."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant, HomeAssistantError, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    GITHUB_BRANCH,
    GITHUB_PATH,
    GITHUB_REPO,
    VA_VIEW_DOWNLOAD_PROGRESS,
    VIEWS_DIR,
)
from .dashboard import DASHBOARD_MANAGER, DashboardManager
from .typed import VAConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: VAConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up update platform."""
    update_sensors = []
    dm = hass.data[DOMAIN][DASHBOARD_MANAGER]
    data = await dm.store.load()

    # Wait upto 5s for view data to be created on first run
    for _ in range(5):
        if data.get("views") is not None:
            break
        data = await dm.store.load()
        await asyncio.sleep(1)

    if data.get("views"):
        update_sensors = [
            VAUpdateEntity(
                dm=dm,
                view=view,
            )
            for view in data["views"]
        ]
    else:
        _LOGGER.error("Unable to load view version information")

    if data.get("dashboard"):
        update_sensors.append(
            VAUpdateEntity(
                dm=dm,
                view="dashboard",
            )
        )
    else:
        _LOGGER.error("Unable to load dashboard version information")

    async_add_entities(update_sensors)


class VAUpdateEntity(UpdateEntity):
    """Update entities for repositories downloaded with HACS."""

    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.PROGRESS
        | UpdateEntityFeature.RELEASE_NOTES
    )

    def __init__(self, dm: DashboardManager, view: str) -> None:
        """Initialize."""
        self.dm = dm
        self.view = view

        self._attr_supported_features = (
            (self._attr_supported_features | UpdateEntityFeature.BACKUP)
            if view != "dashboard"
            else self._attr_supported_features
        )

    @property
    def name(self) -> str | None:
        """Return the name."""
        if self.view == "dashboard":
            return f"View Assist - {self.view}"
        return f"View Assist - {self.view} view"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        if self.view == "dashboard":
            return f"{DOMAIN}_{self.view}"
        return f"{DOMAIN}_{self.view}_view"

    @property
    def latest_version(self) -> str:
        """Return latest version of the entity."""
        if self.view == "dashboard":
            return self.dm.store.data["dashboard"]["latest"]
        return self.dm.store.data["views"][self.view]["latest"]

    @property
    def release_url(self) -> str:
        """Return the URL of the release page."""
        return f"https://github.com/{GITHUB_REPO}/tree/{GITHUB_BRANCH}/{GITHUB_PATH}/{VIEWS_DIR}/{self.view}"

    @property
    def installed_version(self) -> str:
        """Return downloaded version of the entity."""
        if self.view == "dashboard":
            return self.dm.store.data["dashboard"]["installed"]
        return self.dm.store.data["views"][self.view]["installed"]

    @property
    def release_summary(self) -> str | None:
        """Return the release summary."""
        if self.view == "dashboard":
            return "<ha-alert alert-type='info'>Updating the dashboard will attempt to keep any changes you have made to it</ha-alert>"
        return "<ha-alert alert-type='warning'>Updating this view will overwrite any changes you have made to it</ha-alert>"

    @property
    def entity_picture(self) -> str | None:
        """Return the entity picture to use in the frontend."""
        return f"https://brands.home-assistant.io/_/{DOMAIN}/icon.png"

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install an update."""
        try:
            if self.view == "dashboard":
                # Install dashboard
                await self.dm.update_dashboard(download_from_repo=True)
            else:
                # Install view
                await self.dm.add_update_view(
                    self.view, download_from_repo=True, backup_current_view=backup
                )
        except Exception as exception:
            raise HomeAssistantError(exception) from exception

    async def async_release_notes(self) -> str | None:
        """Return the release notes."""
        # TODO: Get release notes from markdown readme
        return self.release_summary

    async def async_added_to_hass(self) -> None:
        """Register for status events."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                VA_VIEW_DOWNLOAD_PROGRESS,
                self._update_download_progress,
            )
        )

    @callback
    def _update_download_progress(self, data: dict) -> None:
        """Update the download progress."""
        if data["view"] != self.view:
            return
        self._attr_in_progress = data["progress"]
        self.async_write_ha_state()
