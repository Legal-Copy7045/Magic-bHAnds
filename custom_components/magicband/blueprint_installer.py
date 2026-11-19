"""Install and update the blueprints that ship with the integration.

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
    """Copy one bundled blueprint into place. Returns the files written."""
    content = bundled.read_text(encoding="utf-8")
    imported = config_dir.joinpath(*IMPORTED_DIR, bundled.name)
    if imported.is_file() and SOURCE_MARKER in imported.read_text(encoding="utf-8"):
        target = imported
    else:
        target = config_dir.joinpath(*PRIMARY_DIR, bundled.name)
    if target.is_file() and target.read_text(encoding="utf-8") == content:
        return []
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return [target]


async def async_install_blueprints(hass: HomeAssistant) -> list[Path]:
    """Install/update the blueprints; reload automations if one changed while running."""
    folder = Path(__file__).parent / "blueprints"

    def _sync_all() -> list[Path]:
        return [p for bundled in sorted(folder.glob("*.yaml")) for p in _sync(Path(hass.config.config_dir), bundled)]

    try:
        written = await hass.async_add_executor_job(_sync_all)
    except OSError:
        _LOGGER.warning("Couldn't install the MagicbHAnds blueprint", exc_info=True)
        return []
    for path in written:
        _LOGGER.info("Installed MagicbHAnds blueprint at %s", path)
    if written and hass.state is CoreState.running and hass.services.has_service("automation", "reload"):
        await hass.services.async_call("automation", "reload", blocking=False)
    return written
