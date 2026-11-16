"""Install and update the MagicBand blueprint that ships with the integration.

The blueprint goes to blueprints/automation/magicband/. If the user already
imported it from GitHub (blueprints/automation/Legal-Copy7045/), that copy is
updated in place instead, so there's only ever one and existing automations
pick up fixes without a manual re-import.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import CoreState, HomeAssistant

_LOGGER = logging.getLogger(__name__)

BLUEPRINT_FILE = "magicband_notify.yaml"
SOURCE_MARKER = "github.com/Legal-Copy7045/Magic-bHAnds"
PRIMARY_DIR = ("blueprints", "automation", "magicband")
IMPORTED_DIR = ("blueprints", "automation", "Legal-Copy7045")


def _sync(config_dir: Path, bundled: Path) -> list[Path]:
    """Copy the bundled blueprint into place. Returns the files written."""
    content = bundled.read_text(encoding="utf-8")
    imported = config_dir.joinpath(*IMPORTED_DIR, BLUEPRINT_FILE)
    if imported.is_file() and SOURCE_MARKER in imported.read_text(encoding="utf-8"):
        target = imported
    else:
        target = config_dir.joinpath(*PRIMARY_DIR, BLUEPRINT_FILE)
    if target.is_file() and target.read_text(encoding="utf-8") == content:
        return []
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return [target]


async def async_install_blueprints(hass: HomeAssistant) -> list[Path]:
    """Install/update the blueprint; reload automations if it changed while running."""
    bundled = Path(__file__).parent / "blueprints" / BLUEPRINT_FILE
    try:
        written = await hass.async_add_executor_job(_sync, Path(hass.config.config_dir), bundled)
    except OSError:
        _LOGGER.warning("Couldn't install the MagicBand blueprint", exc_info=True)
        return []
    for path in written:
        _LOGGER.info("Installed MagicBand blueprint at %s", path)
    if written and hass.state is CoreState.running and hass.services.has_service("automation", "reload"):
        await hass.services.async_call("automation", "reload", blocking=False)
    return written
