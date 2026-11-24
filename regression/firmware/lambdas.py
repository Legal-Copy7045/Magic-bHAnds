"""Pull lambdas out of the reader's resolved config into host C++.

`esphome config` prints the reader config with substitutions applied; the
lambdas named in WANTED are written as plain C++ functions into
lambdas_gen.h, with every `id(x)` they use declared as a host stand-in
(host/lambda_mocks.h) of the right kind. host/test_lambdas.cpp then runs them.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml


class _Loader(yaml.SafeLoader):
    pass


def _tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return {"!" + suffix: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {"!" + suffix: loader.construct_sequence(node, deep=True)}
    return {"!" + suffix: loader.construct_mapping(node, deep=True)}


_Loader.add_multi_constructor("!", _tag)


def load_resolved(text: str) -> dict:
    body = "".join(l for l in text.splitlines(True) if not l.startswith(("INFO", "WARNING", "ERROR")))
    # `esphome config` wraps text it takes for a secret (anything after "key: ") in terminal
    # "concealed" codes; they aren't part of the config.
    for code in ("\x1b[8m", "\x1b[28m", "\\033[8m", "\\033[28m"):
        body = body.replace(code, "")
    return yaml.load(body, Loader=_Loader)


def lam(x) -> str | None:
    return x.get("!lambda") if isinstance(x, dict) and "!lambda" in x else None


def walk(x):
    """Yield every lambda body under x."""
    if isinstance(x, dict):
        b = lam(x)
        if b is not None:
            yield b
            return
        for v in x.values():
            yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)


def as_list(x):
    return x if isinstance(x, list) else [x] if x else []


KIND_TYPES = {"number": "mock::Number", "sensor": "mock::Number", "select": "mock::Select", "switch": "mock::Switch",
              "binary_sensor": "mock::BinarySensor", "text_sensor": "mock::TextSensor", "text": "mock::TextSensor",
              "script": "mock::Script", "time": "mock::Clock", "media_player": "mock::Speaker"}
PARAM_TYPES = {"string": "std::string", "bool": "bool", "int": "int", "float": "float"}


def id_types(cfg: dict) -> dict[str, str]:
    types = {}
    for g in as_list(cfg.get("globals")):
        types[g["id"]] = g["type"]
    for kind, t in KIND_TYPES.items():
        for e in as_list(cfg.get(kind)):
            if isinstance(e, dict) and e.get("id"):
                types[e["id"]] = t
    return types


def find(cfg: dict) -> dict[str, tuple[str, str, str]]:
    """name -> (signature, body, where) for every lambda the host tests use."""
    out = {}
    ring = next(l for l in as_list(cfg.get("light")) if l.get("id") == "ring")
    for eff in ring.get("effects", []):
        a = eff.get("addressable_lambda")
        if a and a["name"] in ("Warm glow", "Chase", "Idle circle", "Pulse", "Welcome", "Spin", "Breathe"):
            fn = "fx_" + re.sub(r"\W+", "_", a["name"].lower())
            out[fn] = ("void %s(hosttest::MockRing &it, esphome::Color current_color, bool initial_run)", lam(a["lambda"]),
                       f"light ring effect {a['name']}")
    scripts = {s["id"]: s for s in as_list(cfg.get("script"))}
    for sid in ("note_refusal", "end_lockout", "apply_quiet", "update_night", "sun_time"):
        s = scripts[sid]
        params = ", ".join(f"{PARAM_TYPES[t]} {n}" for n, t in (s.get("parameters") or {}).items())
        out["script_" + sid] = ("void %s(" + params + ")", next(walk(s["then"])), f"script {sid}")
    # band_tapped: the "Known bands only" decision
    body = next(b for b in walk(scripts["band_tapped"]["then"]) if "known_list" in b and "decision" in b)
    out["known_decision"] = ("void %s(std::string uid)", body, "script band_tapped (Known bands only decision)")
    # interval: the lockout's end
    body = next(b for b in walk(cfg.get("interval")) if "lockout_until" in b and "millis()" in b)
    out["lockout_over"] = ("bool %s()", body, "interval (end of lockout)")
    # on_tag: the lockout check and the pairing confirmation
    tag = as_list(cfg.get("pn532_i2c"))[0]["on_tag"]
    for b in walk(tag):
        if "lockout_until" in b:
            out["tag_locked"] = ("bool %s()", b, "pn532 on_tag (lockout check)")
        if "reader_confirm_pair" in b:
            out["tag_confirms_pair"] = ("bool %s()", b, "pn532 on_tag (pairing confirmation)")
    btn = next(b for b in as_list(cfg.get("button")) if b.get("name") == "Allow last band")
    out["allow_last_band"] = ("void %s()", next(walk(btn["on_press"])), "button Allow last band")
    for name in ("Forget last band", "Forget all bands"):
        btn = next(b for b in as_list(cfg.get("button")) if b.get("name") == name)
        out[re.sub(r"\W+", "_", name.lower())] = ("void %s()", next(walk(btn["on_press"])), f"button {name}")
    # band_tapped: whether this tap is sent to Home Assistant as a tag scan (unknown-band limit)
    body = next(b for b in walk(scripts["band_tapped"]["then"]) if "unknown_tags" in b)
    out["tag_report"] = ("bool %s(std::string uid)", body, "script band_tapped (unknown-band limit)")
    # set_known_bands: applies the list (and remembers its bands in listed_bands)
    act = next(a for a in as_list((cfg.get("api") or {}).get("actions")) if a.get("action") == "set_known_bands")
    body = next(b for b in walk(act["then"]) if "known_list" in b)
    out["set_known_bands"] = ("void %s(std::string bands, std::string key)", body, "api action set_known_bands")
    # the play_show action's rate limit
    act = next(a for a in as_list((cfg.get("api") or {}).get("actions")) if a.get("action") == "play_show")
    body = next(b for b in walk(act["then"]) if "show_calls" in b)
    out["play_show_allowed"] = ("bool %s()", body, "api action play_show (rate limit)")
    # on_boot: whether the start-up sound plays
    boot = as_list((cfg.get("esphome") or {}).get("on_boot"))
    body = next(b for b in walk(boot) if "sound_at_night" in b)
    out["boot_sound"] = ("bool %s()", body, "esphome on_boot (start-up sound)")
    return out


def generate(cfg: dict, dest: Path) -> dict[str, str]:
    lambdas = find(cfg)
    types = id_types(cfg)
    used = sorted({m for _, body, _ in lambdas.values() for m in re.findall(r"\bid\((\w+)\)", body)})
    decls, missing = [], []
    for name in used:
        t = types.get(name)
        if t is None:
            missing.append(name)
            continue
        decls.append(f"inline {t} {name}{{}};")
    if missing:
        raise SystemExit(f"lambdas use ids with no known kind: {missing}")
    parts = [
        "#pragma once",
        "// Generated by regression/firmware/lambdas.py from esphome/magicband-reader.yaml. Do not edit.",
        "#include <algorithm>\n#include <array>\n#include <cctype>\n#include <cmath>\n#include <cstdio>\n#include <cstdlib>\n#include <string>",
        '#include "test_common.h"',
        '#include "esphome/components/magicband/shows.h"',
        '#include "esphome/components/magicband/reader_key.h"',
        '#include "esphome/components/magicband/time_zone.h"',
        '#include "esphome/components/magicband/guards.h"',
        '#include "lambda_mocks.h"',
        "using namespace esphome;",
        "namespace mock {\nusing namespace esphome;",
        *decls,
        "}  // namespace mock",
        "#define id(x) (::mock::x)",
        "using mock::millis;",
        "namespace gen {",
    ]
    where = {}
    for fn, (sig, body, loc) in lambdas.items():
        where[fn] = loc
        parts.append(f"// {loc}\n" + (sig % fn) + " {\n" + body + "\n}")
    parts += ["}  // namespace gen", "#undef id"]
    dest.write_text("\n".join(parts) + "\n")
    return where
