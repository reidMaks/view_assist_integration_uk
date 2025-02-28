"""Functions to configure Lovelace frontend with dashboard and views."""

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import (
    CONF_ICON,
    CONF_SHOW_IN_SIDEBAR,
    CONF_TITLE,
    CONF_URL_PATH,
    LovelaceData,
    dashboard,
)
from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import load_yaml_dict

from .const import DOMAIN, URL_BASE, VA_SUB_DIRS
from .helpers import create_dir_if_not_exist

_LOGGER = logging.getLogger(__name__)

DASHBOARD_NAME = "View Assist"

# This is path of dashboard files in integration directory.
# Ie the directory this file is in.
CONFIG_FILES_PATH = "default_config"


class FrontendConfig:
    """Class to configure front end for View Assist."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise."""
        self.hass = hass
        self.files_path = f"{self.hass.config.config_dir}/custom_components/{DOMAIN}/{CONFIG_FILES_PATH}"
        self.path = DASHBOARD_NAME.replace(" ", "-").lower()

    async def async_config(self):
        """Create the view assist dashboard and views if they dont exist already.

        It will not overwrite modifications made to views
        """
        await self._config_dashboard()
        views = await self.hass.async_add_executor_job(
            self.get_files_in_dir, f"{Path(__file__).parent}/default_config/views"
        )

        await self._config_views(views)
        await self._delete_home_view()

        await self.create_url_paths()

    def get_files_in_dir(self, path: str) -> list[str]:
        """Get files in dir."""
        dir_path = Path(path)
        return [x.name for x in dir_path.iterdir() if x.is_file()]

    async def _config_dashboard(self):
        """Create dashboard."""

        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]

        # Path to dashboard config file
        f = f"{self.files_path}/dashboard.yaml"
        dashboard_config = await self.hass.async_add_executor_job(load_yaml_dict, f)
        dashboard_config["mode"] = "storage"

        dc = dashboard.DashboardsCollection(self.hass)
        await dc.async_load()
        dashboard_exists = any(e["url_path"] == self.path for e in dc.async_items())

        if not dashboard_exists:
            # Create entry in dashboard collection
            await dc.async_create_item(
                {
                    CONF_ICON: "mdi:glasses",
                    CONF_TITLE: DASHBOARD_NAME,
                    CONF_URL_PATH: self.path,
                    CONF_SHOW_IN_SIDEBAR: True,
                }
            )

            # Add dashboard entry to Lovelace storage
            lovelace.dashboards[self.path] = dashboard.LovelaceStorage(
                self.hass,
                {
                    "id": "view_assist",
                    CONF_ICON: "mdi:glasses",
                    CONF_TITLE: DASHBOARD_NAME,
                    CONF_URL_PATH: self.path,
                },
            )
            await lovelace.dashboards[self.path].async_save(dashboard_config)

            # Register panel
            kwargs = {
                "frontend_url_path": self.path,
                "require_admin": False,
                "config": dashboard_config,
                "sidebar_title": DASHBOARD_NAME,
                "sidebar_icon": "mdi:glasses",
            }
            frontend.async_register_built_in_panel(
                self.hass, "lovelace", **kwargs, update=False
            )

            await dc.async_update_item("view_assist", {CONF_SHOW_IN_SIDEBAR: True})

            # TODO: Needs restart for lovelace to properly manage dashboard.  Must be some
            # event that needs raising.

    async def _config_views(self, views_to_load: list[str]):
        """Create views from config files if not exist."""
        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]

        # Get access to dashboard store
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(self.path)

        # Load dashboard config data
        if dashboard_store:
            dashboard_config = await dashboard_store.async_load(False)

            # Make list of existing view names for this dashboard
            existing_views = [
                view["path"] for view in dashboard_config["views"] if view.get("path")
            ]

            # Iterate list of views to add
            modified = False
            for view_file in views_to_load:
                # If view already exists, skip adding it
                view = view_file.replace(".yaml", "")
                if view in existing_views:
                    continue

                # Load view config from file.
                f = f"{self.files_path}/views/{view_file}"
                new_view_config = await self.hass.async_add_executor_job(
                    load_yaml_dict, f
                )

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

    async def _delete_home_view(self):
        # Get lovelace (frontend) config data
        lovelace = self.hass.data["lovelace"]

        # Get access to dashboard store
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(self.path)

        # Load dashboard config data
        if dashboard_store:
            dashboard_config = await dashboard_store.async_load(True)

            # Remove view with title of home
            modified = False
            for i, view in enumerate(dashboard_config["views"]):
                if view.get("title", "").lower() == "home":
                    del dashboard_config["views"][i]
                    modified = True
                    break

            # Save dashboard config back to HA
            if modified:
                await dashboard_store.async_save(dashboard_config)

    async def _async_register_path(self, url: str, path: str):
        """Register resource path if not already registered."""
        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(url, path, False)]
            )
            _LOGGER.debug("Registered resource path from %s", path)
        except RuntimeError:
            # Runtime error is likley this is already registered.
            _LOGGER.debug("Resource path already registered")

    async def create_url_paths(self):
        """Create viewassist url paths."""
        # Make viewassist config directory and url paths

        # Top level view_assist dir
        if await self.hass.async_add_executor_job(
            create_dir_if_not_exist, self.hass, DOMAIN
        ):
            for sub_dir in VA_SUB_DIRS:
                sub_dir = f"{DOMAIN}/{sub_dir}"
                await self.hass.async_add_executor_job(
                    create_dir_if_not_exist, self.hass, sub_dir
                )

        await self._async_register_path(
            f"{URL_BASE}/defaults", f"{Path(__file__).parent}/default_config"
        )
        va_dir = f"{self.hass.config.config_dir}/{DOMAIN}"
        await self._async_register_path(f"{URL_BASE}", va_dir)
