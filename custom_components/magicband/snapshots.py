"""Camera snapshots of each tap (optional).

A reader can be linked to a camera (``magicband.set_reader_camera``, or the
reader card on the MagicbHAnds page). Each tap on that reader then saves a
picture from the camera and attaches it to the tap in the history. Readers
without a camera work as before: nothing is captured.

Pictures are kept in ``<config>/magicbhands_snapshots/<YYYYMMDD>/<id>.jpg``
(not ``www``, which is public), served by an authenticated view through
short-lived signed links that only the admin-only history action hands out,
and deleted after ``snapshot_days`` (default 30) or past MAX_SNAPSHOTS.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from pathlib import Path
import re
import shutil
import uuid

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .sounds import admin_or_signed

_LOGGER = logging.getLogger(__name__)

FOLDER = "magicbhands_snapshots"
URL = "/api/magicband/snapshot"
DEFAULT_DAYS = 30
MAX_SNAPSHOTS = 3000
SIGNED_FOR = timedelta(hours=1)
SNAPSHOT_TIMEOUT = 15  # seconds; Ring live view can take a few
_ID = re.compile(r"^(\d{8})/([0-9a-f]{32})$")


def _root(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(FOLDER))


def _path(hass: HomeAssistant, snap_id: str) -> Path | None:
    m = _ID.match(snap_id or "")
    return _root(hass) / m.group(1) / f"{m.group(2)}.jpg" if m else None


async def async_capture(hass: HomeAssistant, camera: str) -> str | None:
    """Save a picture from `camera`; returns its id ("YYYYMMDD/hex"), or None if it failed."""
    from homeassistant.components.camera import async_get_image  # noqa: PLC0415 - only when a camera is set

    try:
        image = await async_get_image(hass, camera, timeout=SNAPSHOT_TIMEOUT)
    except Exception as err:  # noqa: BLE001 - a missing picture mustn't affect the tap
        _LOGGER.warning("No snapshot from %s: %s", camera, err)
        return None
    snap_id = f"{dt_util.now().strftime('%Y%m%d')}/{uuid.uuid4().hex}"
    path = _path(hass, snap_id)

    def _write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image.content)

    await hass.async_add_executor_job(_write)
    return snap_id


def signed_url(hass: HomeAssistant, snap_id: str | None) -> str | None:
    """A link to the picture, valid for an hour (only handed out by admin-only actions)."""
    if not snap_id or _path(hass, snap_id) is None:
        return None
    return async_sign_path(hass, f"{URL}/{snap_id}", SIGNED_FOR, use_content_user=True)


def prune(hass: HomeAssistant, days: int) -> int:
    """Delete pictures older than `days` and the oldest past MAX_SNAPSHOTS (blocking). Returns how many."""
    root = _root(hass)
    if not root.is_dir():
        return 0
    cutoff = (dt_util.now() - timedelta(days=max(1, days))).strftime("%Y%m%d")
    removed = 0
    for folder in sorted(root.iterdir()):
        if folder.is_dir() and re.fullmatch(r"\d{8}", folder.name) and folder.name < cutoff:
            removed += sum(1 for _ in folder.glob("*.jpg"))
            shutil.rmtree(folder, ignore_errors=True)
    files = sorted(root.glob("*/*.jpg"), key=lambda p: p.stat().st_mtime)
    for old in files[: max(0, len(files) - MAX_SNAPSHOTS)]:
        old.unlink(missing_ok=True)
        removed += 1
    return removed


class SnapshotView(HomeAssistantView):
    """GET /api/magicband/snapshot/<YYYYMMDD>/<id>: a tap's picture (signed link or logged-in admin)."""

    url = URL + "/{day}/{snap}"
    name = "api:magicband:snapshot"
    requires_auth = True

    async def get(self, request: web.Request, day: str, snap: str) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        if not admin_or_signed(request):
            raise web.HTTPForbidden
        path = _path(hass, f"{day}/{snap}")
        if path is None or not await hass.async_add_executor_job(path.is_file):
            raise web.HTTPNotFound
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@callback
def async_register_view(hass: HomeAssistant) -> None:
    key = f"{FOLDER}_view"
    if not hass.data.get(key):
        hass.http.register_view(SnapshotView())
        hass.data[key] = True
