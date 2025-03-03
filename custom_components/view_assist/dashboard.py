"""Manage views - download, apply, backup, restore."""

import datetime as dt
import logging
from pathlib import Path
from typing import Any
import urllib
import urllib.parse

import requests

from homeassistant.components import frontend
from homeassistant.components.lovelace import (
    CONF_ICON,
    CONF_SHOW_IN_SIDEBAR,
    CONF_TITLE,
    CONF_URL_PATH,
    LovelaceData,
    dashboard,
)
from homeassistant.const import EVENT_PANELS_UPDATED
from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import load_yaml_dict, parse_yaml, save_yaml

from .const import (
    DASHBOARD_NAME,
    DASHBOARD_TITLE,
    DOMAIN,
    GITHUB_PATH,
    GITHUB_REPO,
    VAConfigEntry,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_CONFIG = "default_config"
DEFAULT_VIEWS = f"{DEFAULT_CONFIG}/views"


class DashboardManager:
    """Class to manage VA dashboard and views."""

    def __init__(self, hass: HomeAssistant, config: VAConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config = config

    def _get_files_in_dir(self, path: str) -> list[str]:
        """Get files in dir."""
        dir_path = Path(path)
        return [x.name for x in dir_path.iterdir() if x.is_file()]

    async def _save_to_yaml_file(
        self,
        file_path: str,
        data: dict[str, Any],
        overwrite: bool = False,
        backup_existing: bool = True,
    ) -> bool:
        """Save dict to yaml file, creating backup if required."""

        # Check if file exists
        if Path.is_file(Path(file_path)):
            if not overwrite:
                return False
            if overwrite and backup_existing:
                backup_file = Path(
                    f"{file_path}.backup_{dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
                )
                Path(file_path).rename(backup_file)

        await self.hass.async_add_executor_job(
            save_yaml,
            file_path,
            data,
        )

        return True

    async def setup_dashboard(self):
        """Config VA dashboard."""
        await self.add_dashboard()
        await self.load_default_views()
        await self.delete_view("home")

    async def load_default_views(self):
        """Load views from default config."""
        views = await self.hass.async_add_executor_job(
            self._get_files_in_dir, f"{Path(__file__).parent}/{DEFAULT_VIEWS}"
        )
        for view in views:
            await self.load_view(view, default_view=True)

    async def add_dashboard(self):
        """Create dashboard."""

        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]

        # Path to dashboard config file
        f = f"{Path(__file__).parent}/{DEFAULT_CONFIG}/dashboard.yaml"
        dashboard_config = await self.hass.async_add_executor_job(load_yaml_dict, f)
        dashboard_config["mode"] = "storage"

        dc = dashboard.DashboardsCollection(self.hass)
        await dc.async_load()
        dashboard_exists = any(
            e["url_path"] == DASHBOARD_NAME for e in dc.async_items()
        )

        if not dashboard_exists:
            # Create entry in dashboard collection
            await dc.async_create_item(
                {
                    CONF_ICON: "mdi:glasses",
                    CONF_TITLE: DASHBOARD_TITLE,
                    CONF_URL_PATH: DASHBOARD_NAME,
                    CONF_SHOW_IN_SIDEBAR: True,
                }
            )

            # Add dashboard entry to Lovelace storage
            lovelace.dashboards[DASHBOARD_NAME] = dashboard.LovelaceStorage(
                self.hass,
                {
                    "id": "view_assist",
                    CONF_ICON: "mdi:glasses",
                    CONF_TITLE: DASHBOARD_TITLE,
                    CONF_URL_PATH: DASHBOARD_NAME,
                },
            )
            await lovelace.dashboards[DASHBOARD_NAME].async_save(dashboard_config)

            # Register panel
            kwargs = {
                "frontend_url_path": DASHBOARD_NAME,
                "require_admin": False,
                "config": dashboard_config,
                "sidebar_title": DASHBOARD_NAME,
                "sidebar_icon": "mdi:glasses",
            }
            frontend.async_register_built_in_panel(
                self.hass, "lovelace", **kwargs, update=False
            )

            await dc.async_update_item("view_assist", {CONF_SHOW_IN_SIDEBAR: True})

            self.hass.bus.async_fire(EVENT_PANELS_UPDATED)

    async def load_view(
        self, view: str, overwrite: bool = False, default_view: bool = False
    ) -> bool:
        """Load a view file into the dashboard."""

        # Ensure file is valid
        # Load view config from file.
        view = view.replace(".yaml", "").lower()
        try:
            if default_view:
                f = f"{Path(__file__).parent}/{DEFAULT_VIEWS}/{view}.yaml"
            else:
                f = self.hass.config.path(f"{DOMAIN}/views/{view}.yaml")
            new_view_config = await self.hass.async_add_executor_job(load_yaml_dict, f)
        except OSError:
            _LOGGER.error("Unable to load view.  File not found or invalid format")
            return False

        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]
        # Get access to dashboard store
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
            DASHBOARD_NAME
        )
        # Load dashboard config data
        if dashboard_store:
            dashboard_config = await dashboard_store.async_load(False)

            for index, ex_view in enumerate(dashboard_config["views"]):
                if ex_view.get("path") == view:
                    if not overwrite:
                        if default_view:
                            _LOGGER.debug("Not loading view %s.  Already exists", view)
                        else:
                            _LOGGER.error("Unable to load view. View already exists")
                        return False
                    dashboard_config["views"].pop(index)
                    break

            _LOGGER.debug("Loading view %s", view)
            # Create new view and add it to dashboard
            new_view = {
                "type": "panel",
                "title": view.title(),
                "path": view,
                "cards": [new_view_config],
            }

            dashboard_config["views"].append(new_view)
            modified = True

            # Save dashboard config back to HA
            if modified:
                await dashboard_store.async_save(dashboard_config)
                self.hass.bus.async_fire(EVENT_PANELS_UPDATED)
        return True

    async def save_view(self, view_name: str, overwrite: bool = False) -> bool:
        """Backup a view to a file."""
        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]

        # Get access to dashboard store
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
            DASHBOARD_NAME
        )

        # Load dashboard config data
        if dashboard_store:
            dashboard_config = await dashboard_store.async_load(False)

            # Make list of existing view names for this dashboard
            for view in dashboard_config["views"]:
                if view.get("path") == view_name.lower():
                    file_path = self.hass.config.path(
                        f"{DOMAIN}/views/{view_name.lower()}.yaml"
                    )
                    return self._save_to_yaml_file(
                        file_path, view.get("cards", [])[0], overwrite
                    )
        return False

    async def delete_view(self, view: str):
        """Delete view."""
        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]

        # Get access to dashboard store
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
            DASHBOARD_NAME
        )

        # Load dashboard config data
        if dashboard_store:
            dashboard_config = await dashboard_store.async_load(True)

            # Remove view with title of home
            modified = False
            for index, ex_view in enumerate(dashboard_config["views"]):
                if ex_view.get("title", "").lower() == view.lower():
                    dashboard_config["views"].pop(index)
                    modified = True
                    break

            # Save dashboard config back to HA
            if modified:
                await dashboard_store.async_save(dashboard_config)

    async def download_view(self, view: str, overwrite: bool = False) -> bool:
        """Download view from github repository."""
        view_url = "https://raw.githubusercontent.com/" + urllib.parse.quote(
            f"{GITHUB_REPO}/{GITHUB_PATH}/{view}/{view}.yaml"
        )
        file_path = self.hass.config.path(f"{DOMAIN}/views/{view.lower()}.yaml")

        if Path.is_file(Path(file_path)) and not overwrite:
            _LOGGER.error(
                "Unable to download view %s.  File already exists and overwrite set to false",
                view,
            )
            return False

        try:
            r = await self.hass.async_add_executor_job(requests.get, view_url)
            r_yaml = parse_yaml(r.text)
            if await self._save_to_yaml_file(file_path, r_yaml, overwrite):
                if await self.load_view(view, overwrite=overwrite):
                    return True

        except Exception as ex:  # noqa: BLE001
            _LOGGER.error("Unable to load view from repo - %s", ex)
            return False
        return False
