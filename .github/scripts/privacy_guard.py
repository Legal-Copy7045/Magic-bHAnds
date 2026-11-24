#!/usr/bin/env python3
"""Privacy guard: keeps personal details out of this public repository.

Runs on every push and pull request (.github/workflows/privacy.yml) and fails if:

1. a new commit's author or committer isn't a no-reply address
   (<id>+<user>@users.noreply.github.com, noreply@github.com, noreply@anthropic.com);
2. any tracked file, line added by a new commit, or new commit message contains
   something that looks like a credential (GitHub/AWS/Google/Anthropic/OpenAI/Slack
   tokens, JWTs such as Home Assistant tokens, private keys), or a secrets file
   (secrets.yaml, *.pem other than *.pub.pem, ...) is tracked or added;
3. anything matches a private term from the PRIVACY_DENYLIST Actions secret: one
   Python regular expression per line (case-insensitive; lines starting with #
   are ignored), e.g. real names, places, home coordinates, band or device IDs.
   Checked against commit messages and names, file names and paths, every
   tracked file as it is now, and every line or file ADDED by each commit in the
   pushed range (so a value added and removed again within one push is still
   caught: it stays in the public history). Binary files are checked by their
   printable ASCII and UTF-16 runs (6 characters or more), and .zip files by
   their members' names and contents.

The new commits are BASE..HEAD (the workflow passes them). For a new branch or
tag (BASE all zeros or missing, e.g. after a force push) they are the commits
since the merge base with origin/main, or the whole history without one.

The private terms exist only in the secret, never in the repository, and a
match is reported only by commit, file, line and rule number, never by the text
that matched (and a path that itself matches is shown by its position in a git
listing, not by name). Without the secret (e.g. a pull request from a fork)
check 3 is skipped with a warning.

Run it locally: PRIVACY_DENYLIST="$(cat my-terms.txt)" python3 .github/scripts/privacy_guard.py
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import zipfile

SELF = ".github/scripts/privacy_guard.py"
ALLOWED_EMAIL = re.compile(r"(^[^@\s]+@users\.noreply\.github\.com$)|(^noreply@github\.com$)|(^noreply@anthropic\.com$)", re.I)
CREDENTIALS = re.compile(
    r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"  # JWT (e.g. a Home Assistant token)
    r"|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}"  # GitHub
    r"|\bAKIA[0-9A-Z]{16}\b"  # AWS
    r"|\bAIza[0-9A-Za-z_-]{35}\b"  # Google
    r"|\bsk-(?:ant-)?[A-Za-z0-9_-]{32,}"  # Anthropic / OpenAI
    r"|\bxox[abpors]-[A-Za-z0-9-]{10,}"  # Slack
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
# Public keys (*.pub.pem, e.g. the firmware signing key) may be tracked; a private key in one
# still fails the "BEGIN ... PRIVATE KEY" check in CREDENTIALS below.
SECRET_FILES = re.compile(r"(^|/)(secrets\.yaml|ha_token\.txt|geoapify_key\.txt|\.env|[^/]*(?<!\.pub)\.pem)$", re.I)
MAX_BYTES = 20_000_000  # larger files (and zip members) aren't read
ZIP_MAX_TOTAL = 50_000_000  # stop reading a zip's members after this much uncompressed data
ASCII_RUN = re.compile(rb"[\x20-\x7e]{6,}")
UTF16LE_RUN = re.compile(rb"(?:[\x20-\x7e]\x00){6,}")
UTF16BE_RUN = re.compile(rb"(?:\x00[\x20-\x7e]){6,}")
ZERO = "0" * 40

problems = 0


def git(*args: str) -> str:
    return subprocess.run(["git", "-c", "core.quotePath=false", *args],
                          capture_output=True, text=True, check=True, errors="replace").stdout


def error(msg: str, path: str | None = None, line: int | None = None) -> None:
    global problems
    loc = f" file={path}" + (f",line={line}" if line else "") if path else ""
    print(f"::error{loc}::{msg}")
    problems += 1


def denylist() -> list[re.Pattern]:
    raw = os.environ.get("PRIVACY_DENYLIST", "")
    rules = []
    for n, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rules.append(re.compile(line, re.I))
        except re.error:
            print(f"::error::PRIVACY_DENYLIST line {n} isn't a valid regular expression")
            rules.append(re.compile(r"(?!)"))
    return rules


def matches(rules: list[re.Pattern], text: str) -> list[int]:
    return [i for i, rule in enumerate(rules, 1) if rule.search(text)]


def commit_range() -> tuple[str, list[str]]:
    """(git revision range, commits) of what this push or pull request adds."""
    base, head = os.environ.get("BASE", "").strip(), os.environ.get("HEAD", "").strip() or "HEAD"
    head = git("rev-parse", head).strip()
    if base and set(base) != {"0"}:
        try:
            git("cat-file", "-e", base + "^{commit}")
            return f"{base}..{head}", git("rev-list", f"{base}..{head}").split()
        except subprocess.CalledProcessError:
            pass  # e.g. after a force push the old base isn't in the clone
    # A new branch or tag: everything not already on main, or the whole history.
    for main in ("origin/main", "main"):
        try:
            mb = git("merge-base", head, main).strip()
        except subprocess.CalledProcessError:
            continue
        commits = git("rev-list", f"{mb}..{head}").split()
        return (f"{mb}..{head}", commits) if commits else (head, [head])
    return head, git("rev-list", head).split()


def is_binary(data: bytes) -> bool:
    return b"\0" in data[:8000]


def binary_text(data: bytes) -> str:
    """Printable runs (ASCII, UTF-16LE/BE, at least 6 characters), one per line."""
    runs = [m.group().decode("ascii") for m in ASCII_RUN.finditer(data)]
    runs += [m.group().decode("utf-16-le") for m in UTF16LE_RUN.finditer(data)]
    runs += [m.group().decode("utf-16-be") for m in UTF16BE_RUN.finditer(data)]
    return "\n".join(runs)


def label(where: str, msg: str) -> str:
    return f"{where}: {msg[0].lower()}{msg[1:]}" if where else msg


def scan_blob(rules: list[re.Pattern], data: bytes, where: str, path: str | None, credentials: bool,
              depth: int = 0) -> None:
    """Check one file's content. `where` prefixes the messages ("" for a tracked file shown by its path);
    `path` is the annotation (None hides a path that itself matches a private term)."""
    if data[:4] == b"PK\x03\x04" and depth < 3:
        scan_zip(rules, data, where, path, depth)
        return
    if is_binary(data):
        if rules:
            for i in matches(rules, binary_text(data)):
                error(label(where, f"Binary content (a text run) matches private term #{i}: replace it with a "
                                   "made-up value or strip the file's metadata"), path)
        return
    for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        # Inside a zip the line is the member's, so it goes in the message, not on the zip's annotation.
        at, ln = (f" (line {n})", None) if depth else ("", n)
        if credentials and CREDENTIALS.search(line):
            error(label(where, "Looks like a credential") + at, path, ln)
        for i in matches(rules, line):
            error(label(where, f"Matches private term #{i}") + at + ": replace it with a made-up value", path, ln)


def scan_zip(rules: list[re.Pattern], data: bytes, where: str, path: str | None, depth: int) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except (zipfile.BadZipFile, OSError, ValueError):
        if rules:
            for i in matches(rules, binary_text(data)):
                error(label(where, f"Binary content (a text run) matches private term #{i}"), path)
        return
    total = 0
    for k, info in enumerate(infos, 1):
        member = (f"{where}, zip" if where else "Zip") + f" member #{k} (list them with unzip -Z1)"
        for i in matches(rules, info.filename):
            error(f"{member}: its name matches private term #{i}: rename it", path)
        if info.is_dir() or info.file_size > MAX_BYTES or total + info.file_size > ZIP_MAX_TOTAL:
            continue
        total += info.file_size
        try:
            body = zf.read(info)
        except Exception:  # noqa: BLE001 - encrypted or broken member: nothing readable to check
            continue
        scan_blob(rules, body, member, path, credentials=False, depth=depth + 1)


def path_ref(rules: list[re.Pattern], path: str, ref: str) -> str | None:
    """The path itself, or None when the path matches a private term (then only `ref` locates it)."""
    hits = matches(rules, path)
    for i in hits:
        error(f"{ref}: the file name or path matches private term #{i}: rename it")
    return None if hits else path


def check_commits(rules: list[re.Pattern]) -> int:
    rev, commits = commit_range()
    # 1, and 2/3 on commit messages and names
    for sha in commits:
        fields = git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", sha).split("\x00")
        an, ae, cn, ce, body = fields[0], fields[1], fields[2], fields[3], fields[4]
        for who, email in (("author", ae), ("committer", ce)):
            if not ALLOWED_EMAIL.match(email.strip()):
                error(f"Commit {sha[:8]}: {who} email isn't a no-reply address. Use "
                      "<id>+<user>@users.noreply.github.com (git config user.email) and turn on "
                      "GitHub's 'Keep my email addresses private'.")
        text = f"{an}\n{cn}\n{body}"
        if CREDENTIALS.search(text):
            error(f"Commit {sha[:8]}: the commit message looks like it contains a credential")
        for i in matches(rules, text):
            error(f"Commit {sha[:8]}: the commit message or name matches private term #{i}")

    # 2 and 3 on what each commit adds: file names, added lines, added binary files
    log_args = ["show", commits[0]] if ".." not in rev and len(commits) == 1 else ["log", rev]
    out = subprocess.run(
        ["git", "-c", "core.quotePath=false", *log_args, "--format=%x01%H", "--no-renames", "--diff-merges=first-parent",
         "--raw", "--no-abbrev", "-p", "--unified=0", "--no-color", "--no-ext-diff", "--no-textconv"],
        capture_output=True, check=True).stdout
    binaries: list[tuple[str, str, str]] = []  # (commit, path, blob)
    for chunk in out.split(b"\x01")[1:]:
        lines = chunk.split(b"\n")
        sha = lines[0].decode().strip()
        listing = f"`git show --no-renames --diff-merges=first-parent --name-only --format= {sha[:8]}`"
        blobs, refs, order = {}, {}, 0
        path, new_line, in_hunk = None, 0, False
        for raw in lines[1:]:
            if raw.startswith(b":") and not in_hunk and b"\t" in raw:
                meta, name = raw.split(b"\t", 1)
                parts = meta.split()
                name_s = name.decode("utf-8", "replace")
                order += 1
                if parts[4].startswith(b"D"):
                    continue
                blobs[name_s] = parts[3].decode()
                shown = path_ref(rules, name_s, f"Commit {sha[:8]}, path #{order} in {listing}")
                refs[name_s] = shown
                if SECRET_FILES.search(name_s):
                    error(f"Commit {sha[:8]} adds a secrets file: remove it from the history and add it to "
                          ".gitignore", shown)
                continue
            if raw.startswith(b"diff --git "):
                path, in_hunk = None, False
                continue
            if raw.startswith(b"+++ ") and not in_hunk:
                p = raw[4:].decode("utf-8", "replace")
                path = None if p == "/dev/null" else (p[2:] if p.startswith("b/") else p)
                continue
            if raw.startswith(b"Binary files ") and not in_hunk:
                m = re.search(rb" and (?:b/)?(.*) differ$", raw)
                p = m.group(1).decode("utf-8", "replace") if m else None
                if p and p in blobs:
                    binaries.append((sha, p, blobs[p]))
                continue
            if raw.startswith(b"@@"):
                in_hunk = True
                m = re.match(rb"@@ -\S+ \+(\d+)", raw)
                new_line = int(m.group(1)) if m else 0
                continue
            if in_hunk and raw.startswith(b"+") and path:
                text = raw[1:].decode("utf-8", "replace")
                shown = refs.get(path, path)
                if path != SELF and CREDENTIALS.search(text):
                    error(f"Commit {sha[:8]} adds a line that looks like a credential", shown, new_line)
                for i in matches(rules, text):
                    error(f"Commit {sha[:8]} adds a line matching private term #{i}: remove it from the history "
                          "(not only from the latest version)", shown, new_line)
                new_line += 1
    if rules and binaries:
        cat = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        seen = set()
        for sha, p, blob in binaries:
            if blob in seen:
                continue
            seen.add(blob)
            cat.stdin.write(blob.encode() + b"\n")
            cat.stdin.flush()
            header = cat.stdout.readline().split()
            size = int(header[2]) if len(header) == 3 else 0
            data = cat.stdout.read(size) if size else b""
            cat.stdout.read(1)  # newline after the content
            if size > MAX_BYTES:
                continue
            shown = None if matches(rules, p) else p
            scan_blob(rules, data, f"Commit {sha[:8]}, an added binary file", shown, credentials=False)
        cat.stdin.close()
        cat.wait()
    return len(commits)


def check_tree(rules: list[re.Pattern]) -> None:
    for n, path in enumerate(git("ls-files", "-z").split("\0"), 1):
        if not path or not os.path.isfile(path):
            continue
        shown = path_ref(rules, path, f"Tracked file #{n} (`git ls-files | sed -n {n}p`)")
        if SECRET_FILES.search(path):
            error("A secrets file is tracked: remove it and add it to .gitignore", shown)
            continue
        if os.path.getsize(path) > MAX_BYTES:
            continue
        with open(path, "rb") as fh:
            data = fh.read()
        scan_blob(rules, data, "" if shown else f"Tracked file #{n}", shown, credentials=path != SELF)


def main() -> int:
    rules = denylist()
    if not rules:
        print("::warning::PRIVACY_DENYLIST secret isn't set (or a fork PR): private terms not checked")
    count = check_commits(rules)
    check_tree(rules)
    print(f"privacy guard: {count} commit(s) and {len(git('ls-files').splitlines())} file(s) checked, "
          f"{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
