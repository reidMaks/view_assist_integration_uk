"""Manage views - download, apply, backup, restore."""

from dataclasses import dataclass
import datetime as dt
import logging
import operator
from pathlib import Path
from typing import Any
import urllib.parse

from aiohttp import ContentTypeError

from homeassistant.components.lovelace import (
    CONF_ICON,
    CONF_REQUIRE_ADMIN,
    CONF_SHOW_IN_SIDEBAR,
    CONF_TITLE,
    CONF_URL_PATH,
    LovelaceData,
    dashboard,
)
from homeassistant.const import (
    CONF_ID,
    CONF_MODE,
    CONF_TYPE,
    EVENT_LOVELACE_UPDATED,
    EVENT_PANELS_UPDATED,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.yaml import load_yaml_dict, save_yaml

from .const import (
    COMMUNITY_VIEWS_DIR,
    DASHBOARD_DIR,
    DASHBOARD_NAME,
    DEFAULT_VIEW,
    DEFAULT_VIEWS,
    DOMAIN,
    GITHUB_BRANCH,
    GITHUB_PATH,
    GITHUB_REPO,
    GITHUB_TOKEN_FILE,
    VIEWS_DIR,
    VAConfigEntry,
)
from .helpers import differ_to_json, json_to_dictdiffer
from .utils import dictdiff
from .websocket import MockWSConnection

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
    download_url: str | None = None


class GithubAPIException(Exception):
    """A github api exception."""


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
        self.api_base = f"{GITHUB_REPO_API}/{self.repo}/contents/"

    def _get_token(self):
        token_file = self.hass.config.path(f"{DOMAIN}/{GITHUB_TOKEN_FILE}")
        if Path(token_file).exists():
            with Path(token_file).open("r", encoding="utf-8") as f:
                return f.read()
        return None

    async def _rest_request(self, url: str) -> str | dict | list | None:
        """Return rest request data."""
        session = async_get_clientsession(self.hass)

        kwargs = {}
        if self.api_base in url:
            if token := await self.hass.async_add_executor_job(self._get_token):
                kwargs["headers"] = {"authorization": f"Bearer {token}"}
                _LOGGER.debug("Making api request with auth token - %s", url)
            else:
                _LOGGER.debug("Making api request without auth token - %s", url)

        async with session.get(url, **kwargs) as resp:
            if resp.status == 200:
                try:
                    return await resp.json()
                except ContentTypeError:
                    return await resp.read()
            elif resp.status == 403:
                # Rate limit
                raise GithubAPIException(
                    "Github api rate limit exceeded for this hour.  You may need to add a personal access token to authenticate and increase the limit"
                )
            elif resp.status == 404:
                raise GithubAPIException(f"Path not found on this repository.  {url}")
            else:
                raise GithubAPIException(await resp.json())
        return None

    async def get_dir_listing(self, dir_url: str) -> list[GithubFileDir]:
        """Get github repo dir listing."""
        # if dir passed is full url

        base_url = f"{GITHUB_REPO_API}/{self.repo}/contents/"
        if not dir_url.startswith(base_url):
            dir_url = urllib.parse.quote(dir_url)
            url_path = (
                f"{GITHUB_REPO_API}/{self.repo}/contents/{dir_url}?ref={self.branch}"
            )
        else:
            url_path = dir_url

        try:
            if raw_data := await self._rest_request(url_path):
                return [
                    GithubFileDir(e["name"], e["type"], e["url"], e["download_url"])
                    for e in raw_data
                ]
        except GithubAPIException as ex:
            _LOGGER.error(ex)
        return None

    async def download_file(self, download_url: str) -> bytes | None:
        """Download file."""
        if file_data := await self._rest_request(download_url):
            return file_data
        _LOGGER.debug("Failed to download file")
        return None


class DownloadManager:
    """Class to handle file downloads from github repo."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise."""
        self.hass = hass
        self.github = GitHubAPI(hass, GITHUB_REPO)

    def _save_binary_to_file(self, data: bytes, file_path: str, file_name: str):
        """Save binary data to file."""
        Path(file_path).mkdir(parents=True, exist_ok=True)
        Path.write_bytes(Path(file_path, file_name), data)

    async def _download_dir(self, dir_url: str, dir_path: str, depth: int = 1):
        """Download all files in a directory."""
        try:
            if dir_listing := await self.github.get_dir_listing(dir_url):
                _LOGGER.debug("Downloading %s", dir_url)
                # Recurse directories
                for entry in dir_listing:
                    if entry.type == "dir" and depth <= MAX_DIR_DEPTH:
                        await self._download_dir(
                            f"{dir_url}/{entry.name}",
                            f"{dir_path}/{entry.name}",
                            depth=depth + 1,
                        )
                    elif entry.type == "file":
                        _LOGGER.debug("Downloading file %s", f"{dir_url}/{entry.name}")
                        if file_data := await self.github.download_file(
                            entry.download_url
                        ):
                            await self.hass.async_add_executor_job(
                                self._save_binary_to_file,
                                file_data,
                                dir_path,
                                entry.name,
                            )
                        else:
                            raise DownloadManagerException(
                                f"Error downloading {entry.name} from the github repository."
                            )
        except GithubAPIException as ex:
            _LOGGER.error(ex)

    async def backup_file_or_folder(self, file_or_folder: str) -> bool:
        """Backup a file or folder."""
        try:
            await self.hass.async_add_executor_job(
                Path(file_or_folder).rename,
                f"{file_or_folder}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}",
            )
            _LOGGER.debug("Backed up %s", file_or_folder)
        except OSError as ex:
            _LOGGER.debug("Backup error: %s", ex)
            return False
        else:
            return True

    async def download_dashboard(
        self, overwrite: bool = False, backup_if_exists: bool = True
    ):
        """Download dashboard file."""
        # Ensure download to path exists
        base = self.hass.config.path(f"{DOMAIN}/{DASHBOARD_DIR}")
        exists = Path(base, DASHBOARD_FILE).exists()

        if exists and not overwrite:
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
        self,
        view_name: str,
        overwrite: bool = False,
        backup_if_exists: bool = True,
        community_view: bool = False,
    ):
        """Download files from a github repo directory."""

        # Ensure download to path exists
        base = self.hass.config.path(f"{DOMAIN}/{VIEWS_DIR}")
        if community_view:
            dir_url = f"{GITHUB_PATH}/{VIEWS_DIR}/{COMMUNITY_VIEWS_DIR}/{view_name}"
            msg_text = "Community view"
        else:
            dir_url = f"{GITHUB_PATH}/{VIEWS_DIR}/{view_name}"
            msg_text = "View"

        _LOGGER.debug("Downloading %s - %s", msg_text.lower(), view_name)
        exists = Path(base, view_name).exists()

        if exists and not overwrite:
            raise DownloadManagerException(
                f"Cannot download {msg_text.lower()} - {view_name}.  Directory already exists and overwrite set to false"
            )

        # Validate view dir on repo
        if await self.github.get_dir_listing(dir_url):
            # Rename existing dir
            if exists and backup_if_exists:
                if not await self.backup_file_or_folder(f"{base}/{view_name}"):
                    raise DownloadManagerException(
                        f"{msg_text} - {view_name} not downloaded. Failed backing up existing directory",
                    )

            # Create view directory
            Path(base, view_name).mkdir(parents=True, exist_ok=True)

            # Download view files
            await self._download_dir(dir_url, f"{base}/{view_name}")


class DashboardManager:
    """Class to manage VA dashboard and views."""

    def __init__(self, hass: HomeAssistant, config: VAConfigEntry) -> None:
        """Initialise."""
        self.hass = hass
        self.config = config
        self.download_manager = DownloadManager(hass)
        self.build_mode: bool = False

        # Experimental - listen for dashboard change and write out changes
        config.async_on_unload(
            hass.bus.async_listen(EVENT_LOVELACE_UPDATED, self._dashboard_changed)
        )

    async def _save_to_yaml_file(
        self,
        file_path: str,
        data: dict[str, Any],
        overwrite: bool = False,
        backup_existing: bool = True,
    ) -> bool:
        """Save dict to yaml file, creating backup if required."""

        # Check if file exists
        if Path(file_path).exists():
            if not overwrite:
                raise DashboardManagerException(
                    f"Unable to save {file_path}.  File exists and overwrite set to false"
                )
            if overwrite and backup_existing:
                await DownloadManager(self.hass).backup_file_or_folder(file_path)

        await self.hass.async_add_executor_job(
            save_yaml,
            file_path,
            data,
        )
        return True

    @property
    def dashboard_key(self) -> str:
        """Return path for dashboard name."""
        return DASHBOARD_NAME.replace(" ", "-").lower()

    @property
    def dashboard_exists(self) -> bool:
        """Return if dashboard exists."""
        lovelace: LovelaceData = self.hass.data["lovelace"]
        return self.dashboard_key in lovelace.dashboards

    async def setup_dashboard(self):
        """Config VA dashboard."""
        if not self.dashboard_exists:
            _LOGGER.debug("Initialising View Assist dashboard")
            self.build_mode = True

            # Download dashboard
            base = self.hass.config.path(DOMAIN)
            dashboard_file_path = f"{base}/{DASHBOARD_DIR}/{DASHBOARD_DIR}.yaml"
            view_base = f"{base}/{VIEWS_DIR}"

            if not Path(dashboard_file_path).exists():
                await self.download_manager.download_dashboard()

            # Download initial views
            _LOGGER.debug("Downloading default views")
            for view in DEFAULT_VIEWS:
                if not Path(view_base, view).exists():
                    await self.download_manager.download_view(view)

            # Load dashboard
            _LOGGER.debug("Adding dashboard")
            await self.add_dashboard(DASHBOARD_NAME, dashboard_file_path)
            await self._apply_user_dashboard_changes()

            # Load views that have successfully downloaded plus others already in directory
            _LOGGER.debug("Adding views")
            for view in await self.hass.async_add_executor_job(Path(view_base).iterdir):
                try:
                    await self.add_view(
                        view.name,
                        download_if_missing=False,
                        force_download=False,
                        overwrite=False,
                    )
                except DashboardManagerException as ex:
                    _LOGGER.warning(ex)

            # Remove home view
            await self.delete_view("home")

            # Finish
            self.build_mode = False

        else:
            _LOGGER.debug(
                "View Assist dashboard already exists, skipping initialisation"
            )

    async def view_exists(self, view: str) -> int:
        """Return index of view if view exists."""
        lovelace: LovelaceData = self.hass.data["lovelace"]
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
            self.dashboard_key
        )
        # Load dashboard config data
        if dashboard_store:
            dashboard_config = await dashboard_store.async_load(False)
            if not dashboard_config["views"]:
                return 0

            for index, ex_view in enumerate(dashboard_config["views"]):
                if ex_view.get("path") == view:
                    return index + 1
        return 0

    async def add_dashboard(self, dashboard_name: str, dashboard_path: str):
        """Create dashboard."""

        if not self.dashboard_exists:
            mock_connection = MockWSConnection(self.hass)
            if mock_connection.execute_ws_func(
                "lovelace/dashboards/create",
                {
                    CONF_ID: 1,
                    CONF_TYPE: "lovelace/dashboards/create",
                    CONF_ICON: "mdi:glasses",
                    CONF_TITLE: DASHBOARD_NAME,
                    CONF_URL_PATH: self.dashboard_key,
                    CONF_MODE: "storage",
                    CONF_SHOW_IN_SIDEBAR: True,
                    CONF_REQUIRE_ADMIN: False,
                },
            ):
                # Get lovelace (frontend) config data
                lovelace: LovelaceData = self.hass.data["lovelace"]

                # Load dashboard config file from path
                if dashboard_config := await self.hass.async_add_executor_job(
                    load_yaml_dict, dashboard_path
                ):
                    await lovelace.dashboards[self.dashboard_key].async_save(
                        dashboard_config
                    )

    async def update_dashboard(
        self,
    ):
        """Download latest dashboard from github repository and apply."""

        # download dashboard - no backup
        await self.download_manager.download_dashboard(
            overwrite=True, backup_if_exists=False
        )

        # Apply new dashboard to HA
        base = self.hass.config.path(DOMAIN)
        dashboard_file_path = f"{base}/{DASHBOARD_DIR}/{DASHBOARD_DIR}.yaml"

        if not Path(dashboard_file_path).exists():
            # No master dashboard
            return

        # Load dashboard config file from path
        if updated_dashboard_config := await self.hass.async_add_executor_job(
            load_yaml_dict, dashboard_file_path
        ):
            lovelace: LovelaceData = self.hass.data["lovelace"]
            dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
                self.dashboard_key
            )
            # Load dashboard config data
            if dashboard_store:
                dashboard_config = await dashboard_store.async_load(False)

                # Copy views to updated dashboard
                updated_dashboard_config["views"] = dashboard_config.get("views")

                # Apply
                self.build_mode = True
                await dashboard_store.async_save(updated_dashboard_config)
                await self._apply_user_dashboard_changes()
                self.build_mode = False

    async def add_update_view(
        self,
        name: str,
        download_if_missing: bool = True,
        force_download: bool = False,
        overwrite: bool = False,
        backup_existing_dir: bool = True,
        community_view: bool = False,
    ) -> bool:
        """Load a view file into the dashboard from the view_assist view folder."""

        # Block trying to download the community contributions folder
        if name == COMMUNITY_VIEWS_DIR:
            raise DashboardManagerException(
                f"{name} is not not a valid view name.  Please select a view from within that folder"  # noqa: S608
            )

        # Return 1 based view index.  If 0, view doesn't exist
        view_index = await self.view_exists(name)

        if view_index:
            if not overwrite:
                raise DashboardManagerException(
                    f"Unable to load view. A view with the name {name} already exists on the View Assist dashboard and overwrite is set to false"
                )

        # Validate file actions
        f = self.hass.config.path(f"{DOMAIN}/{VIEWS_DIR}/{name}/{name}.yaml")
        if not Path(f).exists():
            if not download_if_missing and not force_download:
                raise DashboardManagerException(
                    f"Unable to load view. A yaml file for the view {name} cannot be found and download if missing is set to false"
                )

        if force_download or not Path(f).exists():
            await self.download_manager.download_view(
                name,
                overwrite=overwrite,
                backup_if_exists=backup_existing_dir,
                community_view=community_view,
            )

        # Install view from file.
        try:
            new_view_config = await self.hass.async_add_executor_job(load_yaml_dict, f)
        except OSError as ex:
            raise DashboardManagerException(
                f"Unable to load view {name}.  Error is {ex}"
            ) from ex

        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]
        # Get access to dashboard store
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
            self.dashboard_key
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

            if not dashboard_config["views"]:
                dashboard_config["views"] = [new_view]
            elif view_index:
                dashboard_config["views"][view_index - 1] = new_view
            elif name == DEFAULT_VIEW:
                # Insert default view as first view in list
                dashboard_config["views"].insert(0, new_view)
            else:
                dashboard_config["views"].append(new_view)
            modified = True

            # Save dashboard config back to HA
            if modified:
                await dashboard_store.async_save(dashboard_config)
                self.hass.bus.async_fire(EVENT_PANELS_UPDATED)
            return True
        return False

    async def save_view(
        self, view_name: str, overwrite: bool = False, backup_if_exists: bool = False
    ) -> bool:
        """Backup a view to a file."""

        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]

        # Get access to dashboard store
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
            self.dashboard_key
        )

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
                        file_path,
                        view.get("cards", [])[0],
                        overwrite=overwrite,
                        backup_existing=backup_if_exists,
                    )
        return False

    async def delete_view(self, view: str):
        """Delete view."""

        # Get lovelace (frontend) config data
        lovelace: LovelaceData = self.hass.data["lovelace"]

        # Get access to dashboard store
        dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
            self.dashboard_key
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

    async def _dashboard_changed(self, event: Event):
        # If in dashboard build mode, ignore changes
        if self.build_mode:
            return

        if event.data["url_path"] == self.dashboard_key:
            try:
                lovelace: LovelaceData = self.hass.data["lovelace"]
                dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
                    self.dashboard_key
                )
                # Load dashboard config data
                if dashboard_store:
                    dashboard_config = await dashboard_store.async_load(False)

                    # Remove views from dashboard config for saving
                    dashboard_only = dashboard_config.copy()
                    dashboard_only["views"] = [{"title": "Home"}]

                    file_path = Path(self.hass.config.config_dir, DOMAIN, DASHBOARD_DIR)
                    file_path.mkdir(parents=True, exist_ok=True)

                    if diffs := await self._compare_dashboard_to_master(dashboard_only):
                        await self._save_to_yaml_file(
                            Path(file_path, "user_dashboard.yaml"),
                            diffs,
                            overwrite=True,
                            backup_existing=False,
                        )
            except Exception as ex:  # noqa: BLE001
                _LOGGER.error("Error saving dashboard. Error is %s", ex)

    async def _compare_dashboard_to_master(
        self, comp_dash: dict[str, Any]
    ) -> dict[str, Any]:
        """Compare dashboard dict to master and return differences."""
        # Get master dashboard
        base = self.hass.config.path(DOMAIN)
        dashboard_file_path = f"{base}/{DASHBOARD_DIR}/{DASHBOARD_DIR}.yaml"

        if not Path(dashboard_file_path).exists():
            # No master dashboard
            return None

        # Load dashboard config file from path
        if master_dashboard := await self.hass.async_add_executor_job(
            load_yaml_dict, dashboard_file_path
        ):
            if operator.eq(master_dashboard, comp_dash):
                _LOGGER.debug("They are the same!")
            else:
                diffs = dictdiff.diff(master_dashboard, comp_dash, expand=True)
                return differ_to_json(diffs)
        return None

    async def _apply_user_dashboard_changes(self):
        """Apply a user_dashboard changes file to master dashboard."""

        # Get master dashboard
        base = self.hass.config.path(DOMAIN)
        user_dashboard_file_path = f"{base}/{DASHBOARD_DIR}/user_dashboard.yaml"

        if not Path(user_dashboard_file_path).exists():
            # No master dashboard
            return

        # Load dashboard config file from path
        _LOGGER.debug("Applying user changes to dashboard")
        if user_dashboard := await self.hass.async_add_executor_job(
            load_yaml_dict, user_dashboard_file_path
        ):
            lovelace: LovelaceData = self.hass.data["lovelace"]
            dashboard_store: dashboard.LovelaceStorage = lovelace.dashboards.get(
                self.dashboard_key
            )
            # Load dashboard config data
            if dashboard_store:
                dashboard_config = await dashboard_store.async_load(False)

                # Apply
                user_changes = json_to_dictdiffer(user_dashboard)
                updated_dashboard = dictdiff.patch(user_changes, dashboard_config)
                await dashboard_store.async_save(updated_dashboard)
