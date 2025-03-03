"""Manage views - download, apply, backup, restore."""

import base64
from dataclasses import dataclass
import datetime as dt
import logging
from pathlib import Path
from typing import Any
import urllib.parse

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
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.yaml import load_yaml_dict, save_yaml

from .const import (
    DASHBOARD_DIR,
    DASHBOARD_NAME,
    DEFAULT_VIEWS,
    DOMAIN,
    GITHUB_BRANCH,
    GITHUB_PATH,
    GITHUB_REPO,
    VIEWS_DIR,
    VAConfigEntry,
)

_LOGGER = logging.getLogger(__name__)

GITHUB_REPO_API = "https://api.github.com/repos"
MAX_DIR_DEPTH = 5
DASHBOARD_FILE = "dashboard.yaml"
DASHBOARD_MANAGER = "dashboard_manager"


@dataclass
class GithubFileDir:
    """A github dir or file object."""

    name: str
    type: str
    url: str


class DownloadManagerException(Exception):
    """A download manager exception."""


class DashboardManagerException(Exception):
    """A dashboard manager exception."""


class GitHubAPI:
    """Class to handle basic Github repo rest commands."""

    def __init__(self, hass: HomeAssistant, repo: str) -> None:
        """Initialise."""
        self.hass = hass
        self.repo = repo
        self.branch: str = GITHUB_BRANCH

    def _get_token(self):
        token_file = self.hass.config.path(f"{DOMAIN}/token.txt")
        if Path(token_file).exists():
            with Path(token_file).open("r", encoding="utf-8") as f:
                return f.read()
        return None

    async def _rest_request(self, url: str) -> str | dict | list | None:
        """Return rest request data."""
        session = async_get_clientsession(self.hass)

        kwargs = {}
        if token := await self.hass.async_add_executor_job(self._get_token):
            kwargs["headers"] = {"authorization": f"Bearer {token}"}

        async with session.get(url, **kwargs) as resp:
            if resp.status == 200:
                return await resp.json()
        return None

    async def get_dir_listing(self, dir_url: str) -> list[GithubFileDir]:
        """Get github repo dir listing."""
        dir_url = urllib.parse.quote(dir_url)
        url_path = f"{GITHUB_REPO_API}/{self.repo}/contents/{dir_url}?ref={self.branch}"

        if raw_data := await self._rest_request(url_path):
            return [GithubFileDir(e["name"], e["type"], e["url"]) for e in raw_data]
        return None

    async def get_file(self, file_url: str) -> bytes | None:
        """Get file contents from repo."""
        # Download and save file
        if file_data := await self._rest_request(file_url):
            if base64_string := str(file_data.get("content")):
                return base64.b64decode(base64_string)
        return None


class DownloadManager:
    """Class to handle file downloads from github repo."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise."""
        self.hass = hass
        self.github = GitHubAPI(hass, GITHUB_REPO)

    def _save_binary_to_file(self, data: bytes, file_path: str, file_name: str):
        """Save binary data to file."""
        if not Path(file_path):
            Path.mkdir(file_path)

        with open(f"{file_path}/{file_name}", "xb") as f:  # noqa: PTH123
            f.write(data)

    async def _download_dir(self, dir_url: str, dir_path: str, depth: int = 1):
        """Download all files in a directory."""
        dir_listing = await self.github.get_dir_listing(dir_url)
        _LOGGER.debug("Downloading %s", dir_path)
        # Recurse directories
        if dir_listing:
            for entry in dir_listing:
                if entry.type == "dir" and depth <= MAX_DIR_DEPTH:
                    await self._download_dir(
                        entry.url, f"{dir_path}/{entry.name}", depth=depth + 1
                    )
                elif entry.type == "file":
                    file_bytes = await self.github.get_file(entry.url)
                    await self.hass.async_add_executor_job(
                        self._save_binary_to_file, file_bytes, dir_path, entry.name
                    )
        else:
            raise DownloadManagerException(
                "Unable to find a directory called {dir_url} on the github repository"
            )

    async def backup_file_or_folder(self, file_or_folder: str) -> bool:
        """Backup a file or folder."""
        try:
            await self.hass.async_add_executor_job(
                Path(file_or_folder).rename,
                f"{file_or_folder}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}",
            )
        except OSError:
            return False
        else:
            return True

    async def download_dashboard(
        self, overwrite: bool = False, backup_if_exists: bool = True
    ):
        """Download dashboard file."""
        # Ensure download to path exists
        exists = False
        base = self.hass.config.path(f"{DOMAIN}/{DASHBOARD_DIR}")

        if not Path(base).exists():
            Path(base).mkdir()

        if Path(base, DASHBOARD_FILE).exists():
            exists = True

        if exists and overwrite:
            raise DownloadManagerException(
                "Cannot download dashboard.  Dashboard file already exists and overwrite set to false"
            )

        # Validate view dir on repo
        dir_url = f"{GITHUB_PATH}/{DASHBOARD_DIR}"
        if await self.github.get_dir_listing(dir_url):
            # Rename existing dir
            if exists and backup_if_exists:
                if not await self.backup_file_or_folder(f"{base}/{DASHBOARD_FILE}"):
                    raise DownloadManagerException(
                        f"{base}/{DASHBOARD_FILE} not downloaded. Failed backing up existing file",
                    )
            # Download view files
            await self._download_dir(dir_url, base)

    async def download_view(
        self, view_name: str, overwrite: bool = False, backup_if_exists: bool = True
    ):
        """Downlaod files from a github repo directory."""

        # Ensure download to path exists
        exists = False
        base = self.hass.config.path(f"{DOMAIN}/views")

        if not Path(base).exists():
            Path(base).mkdir()

        if Path(base, view_name).exists():
            exists = True

        if exists and not overwrite:
            raise DownloadManagerException(
                f"Cannot download {view_name}.  Directory already exists and overwrite set to false"
            )

        # Validate view dir on repo
        dir_url = f"{GITHUB_PATH}/{VIEWS_DIR}/{view_name}"
        if await self.github.get_dir_listing(dir_url):
            # Rename existing dir
            if exists and backup_if_exists:
                if not await self.backup_file_or_folder(f"{base}/{DASHBOARD_FILE}"):
                    raise DownloadManagerException(
                        f"{view_name} not downloaded. Failed backing up existing directory",
                    )

            # Create view directory
            Path(base, view_name).mkdir()

            # Download view files
            await self._download_dir(dir_url, f"{base}/{view_name}")


class DashboardManager:
    """Class to manage VA dashboard and views."""

    def __init__(self, hass: HomeAssistant, config: VAConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config = config
        self.dl = DownloadManager(hass)

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
                if await DownloadManager(self.hass).backup_file_or_folder(file_path):
                    await self.hass.async_add_executor_job(
                        save_yaml,
                        file_path,
                        data,
                    )
                    return True
        raise DashboardManagerException(f"Unable to save {file_path}")

    async def setup_dashboard(self):
        """Config VA dashboard."""

        if not await self.dashboard_exists(DASHBOARD_NAME):
            dashboard_path = self.hass.config.path(f"{DOMAIN}/dashboard/dashboard.yaml")
            if not Path(dashboard_path).exists():
                await self.dl.download_dashboard()

            await self.add_dashboard(DASHBOARD_NAME, dashboard_path)
            await self.load_default_views()
            await self.delete_view("home")

    async def load_default_views(self):
        """Load views from default config."""
        for view in DEFAULT_VIEWS:
            try:
                await self.add_view(view)
            except DashboardManagerException as ex:
                _LOGGER.error(ex)

    def dashboard_path(self, dashboard_name: str) -> str:
        """Return path for dashboard name."""
        return dashboard_name.replace(" ", "-").lower()

    async def dashboard_exists(self, dashboard_name: str) -> bool:
        """Return if dashboard exists."""
        lovelace: LovelaceData = self.hass.data["lovelace"]
        url_path = self.dashboard_path(dashboard_name)
        return url_path in lovelace.dashboards

    async def view_exists(self, view: str) -> int:
        """Return if view exists."""
        dashboard_url_path = self.dashboard_path(DASHBOARD_NAME)
        lovelace: LovelaceData = self.hass.data["lovelace"]
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
            dashboard_url_path
        )
        # Load dashboard config data
        if dashboard_store:
            dashboard_config = await dashboard_store.async_load(False)

            for index, ex_view in enumerate(dashboard_config["views"]):
                if ex_view.get("path") == view:
                    return index + 1
        return 0

    async def add_dashboard(self, dashboard_name: str, dashboard_path: str):
        """Create dashboard."""

        if not await self.dashboard_exists(dashboard_name):
            # Get lovelace (frontend) config data
            lovelace: LovelaceData = self.hass.data["lovelace"]

            # Load dashboard config file from path
            dashboard_config = await self.hass.async_add_executor_job(
                load_yaml_dict, dashboard_path
            )
            dashboard_config["mode"] = "storage"
            url_path = self.dashboard_path(dashboard_name)

            # Create entry in dashboard collection
            dc = dashboard.DashboardsCollection(self.hass)
            await dc.async_load()
            dash = await dc.async_create_item(
                {
                    CONF_ICON: "mdi:glasses",
                    CONF_TITLE: DASHBOARD_NAME,
                    CONF_URL_PATH: url_path,
                    CONF_SHOW_IN_SIDEBAR: True,
                }
            )

            # Add dashboard entry to Lovelace storage
            lovelace.dashboards[url_path] = dashboard.LovelaceStorage(
                self.hass,
                {
                    "id": dash["id"],
                    CONF_ICON: "mdi:glasses",
                    CONF_TITLE: DASHBOARD_NAME,
                    CONF_URL_PATH: url_path,
                },
            )
            await lovelace.dashboards[url_path].async_save(dashboard_config)

            # Register panel
            kwargs = {
                "frontend_url_path": url_path,
                "require_admin": False,
                "config": dashboard_config,
                "sidebar_title": DASHBOARD_NAME,
                "sidebar_icon": "mdi:glasses",
            }
            frontend.async_register_built_in_panel(
                self.hass, "lovelace", **kwargs, update=False
            )

            await dc.async_update_item(dash["id"], {CONF_SHOW_IN_SIDEBAR: True})

    async def add_view(
        self,
        name: str,
        download_if_missing: bool = True,
        force_download: bool = False,
        overwrite: bool = False,
    ) -> bool:
        """Load a view file into the dashboard from the view_assist view folder."""

        # Return 1 based view index.  If 0, view doesn't exist
        view_index = await self.view_exists(name)

        if view_index:
            if not overwrite:
                raise DashboardManagerException(
                    f"Unable to load view. A view with the name {name} already exists on the View Assist dashboard and overwrite is set to false"
                )

        # Validate file actions
        f = self.hass.config.path(f"{DOMAIN}/views/{name}/{name}.yaml")
        if not Path(f).exists():
            if not download_if_missing and not force_download:
                raise DashboardManagerException(
                    f"Unable to load view. A yaml file for the view {name} cannot be found and download if missing is set to false"
                )

        if force_download or not Path(f).exists():
            await self.dl.download_view(name, overwrite)

        # Install view from file.
        try:
            new_view_config = await self.hass.async_add_executor_job(load_yaml_dict, f)
        except OSError as ex:
            raise DashboardManagerException(
                f"Unable to load view {name}.  Error is {ex}"
            ) from ex

        dashboard_url_path = self.dashboard_path(DASHBOARD_NAME)
        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]
        # Get access to dashboard store
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
            dashboard_url_path
        )

        # Load dashboard config data
        if new_view_config and dashboard_store:
            dashboard_config = await dashboard_store.async_load(False)

            _LOGGER.debug("Loading view %s", name)
            # Create new view and add it to dashboard
            new_view = {
                "type": "panel",
                "title": name.title(),
                "path": name,
                "cards": [new_view_config],
            }

            if view_index:
                dashboard_config["views"][view_index - 1] = new_view
            else:
                dashboard_config["views"].append(new_view)
            modified = True

            # Save dashboard config back to HA
            if modified:
                await dashboard_store.async_save(dashboard_config)
                self.hass.bus.async_fire(EVENT_PANELS_UPDATED)
            return True
        return False

    async def save_view(self, view_name: str, overwrite: bool = False) -> bool:
        """Backup a view to a file."""
        url_path = self.dashboard_path(DASHBOARD_NAME)
        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]

        # Get access to dashboard store
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(url_path)

        # Load dashboard config data
        if dashboard_store:
            dashboard_config = await dashboard_store.async_load(False)

            # Make list of existing view names for this dashboard
            for view in dashboard_config["views"]:
                if view.get("path") == view_name.lower():
                    file_path = self.hass.config.path(
                        f"{DOMAIN}/views/{view_name.lower()}/{view_name.lower()}.yaml"
                    )
                    return await self._save_to_yaml_file(
                        file_path, view.get("cards", [])[0], overwrite
                    )
        return False

    async def delete_view(self, view: str):
        """Delete view."""
        url_path = self.dashboard_path(DASHBOARD_NAME)
        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]

        # Get access to dashboard store
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(url_path)

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
