"""The MagicbHAnds management page, served as a Home Assistant sidebar panel.

frontend/page.html is the page (also used by the home-dashboards project, which
wraps it in its own site menu). Here it gets frontend/common.js (shared
helpers), frontend/shim.js (window.hdHA: live states and a small set of
controls), and the fonts and styles, and is served to logged-in users at
/api/magicband/page. frontend/panel.js is the sidebar panel that loads it into
a frame and hands it the user's live `hass` object.

The sidebar entry is on by default and can be turned off under
Configure -> Settings (for example when the page is shown inside another set
of dashboards instead).
"""

from __future__ import annotations

from pathlib import Path

from aiohttp import web

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant

FRONTEND = Path(__file__).parent / "frontend"
PANEL_PATH = "magicbhands"
STATIC = "/magicbhands_static"
CONF_SIDEBAR = "show_in_sidebar"
_SETUP = "magicband_panel_http"


def build_page() -> str:
    """The page with its helpers, shim, fonts and styles (blocking: run in the executor)."""
    read = lambda name: (FRONTEND / name).read_text(encoding="utf-8")  # noqa: E731
    html = read("page.html").replace("/*COMMON*/", read("common.js"))
    head = "<script>" + read("shim.js") + "</script>\n"
    style = read("fonts.html") + "<style>" + read("style.css") + "</style>\n"
    html = html.replace("<head>", "<head>" + head, 1)
    i = html.find("</head>")
    return html[:i] + style + html[i:] if i >= 0 else style + html


class PageView(HomeAssistantView):
    """GET /api/magicband/page: the management page, for logged-in users only."""

    url = "/api/magicband/page"
    name = "api:magicband:page"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        html = await request.app["hass"].async_add_executor_job(build_page)
        return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "private, no-cache"})


async def async_setup_panel(hass: HomeAssistant, show: bool) -> None:
    """Serve the page, and add the sidebar entry if `show`."""
    if not hass.data.get(_SETUP):
        hass.http.register_view(PageView())
        await hass.http.async_register_static_paths([StaticPathConfig(STATIC, str(FRONTEND), False)])
        hass.data[_SETUP] = True
    if not show or "frontend" not in hass.config.components:
        return
    if PANEL_PATH in hass.data.get(frontend.DATA_PANELS, {}):
        return
    version = int(await hass.async_add_executor_job(lambda: (FRONTEND / "panel.js").stat().st_mtime))
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name="magicbhands-panel",
        sidebar_title="MagicbHAnds",
        sidebar_icon="mdi:watch-variant",
        module_url=f"{STATIC}/panel.js?v={version}",
        require_admin=False,
        config={},
    )


def async_remove_panel(hass: HomeAssistant) -> None:
    """Take the sidebar entry away (on unload, or when turned off)."""
    if PANEL_PATH in hass.data.get(frontend.DATA_PANELS, {}):
        frontend.async_remove_panel(hass, PANEL_PATH)
