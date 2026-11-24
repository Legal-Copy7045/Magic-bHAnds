"""pytest plugin for regression/integration/run.py: records each test's outcome, including known bugs (xfail).

JUnit XML can't tell an unexpected pass of a non-strict xfail from an ordinary pass, so this writes its own
JSON lines file (path in MB_REGRESSION_OUT) next to the JUnit report.
"""

from __future__ import annotations

import json
import os

import pytest

_OUT = os.environ.get("MB_REGRESSION_OUT")
_docs: dict[str, str] = {}


def pytest_collection_modifyitems(items):
    for item in items:
        doc = getattr(getattr(item, "function", None), "__doc__", None) or ""
        _docs[item.nodeid] = doc.strip().splitlines()[0] if doc.strip() else ""


@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report):
    if not _OUT:
        return
    if report.when != "call" and not (report.when == "setup" and (report.failed or report.skipped)) \
            and not (report.when == "teardown" and report.failed):
        return
    wasxfail = getattr(report, "wasxfail", None)
    if report.passed and wasxfail is not None:
        outcome = "xpassed"
    elif report.skipped and wasxfail is not None:
        outcome = "xfailed"
    else:
        outcome = report.outcome
    detail = ""
    if report.failed:
        crash = getattr(report.longrepr, "reprcrash", None)
        detail = f"{crash.path}:{crash.lineno}: {crash.message}" if crash else str(report.longrepr)[-2000:]
    elif report.skipped and wasxfail is None:
        detail = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
    with open(_OUT, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "nodeid": report.nodeid, "when": report.when, "outcome": outcome, "wasxfail": wasxfail,
            "detail": detail, "duration": round(report.duration, 3), "doc": _docs.get(report.nodeid, ""),
        }) + "\n")
