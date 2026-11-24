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

Each commit's files are listed with `git diff-tree -r -z` (NUL-separated, so a
name is never quoted) and every added or changed file is read on its own (the
blob itself, and for a changed text file `git diff` of its two blobs), so no
byte inside a file (a control character, invalid UTF-8) can hide anything else.

The new commits are BASE..HEAD (the workflow passes them). When BASE isn't an
ancestor of HEAD (a force push) they are the commits since the merge base of
the two, or the whole history without one; when BASE isn't in the clone (and
can't be fetched by its SHA) the whole history. For a new branch or tag (BASE
all zeros) they are the commits since the merge base with origin/main, or the
whole history without one.

The private terms exist only in the secret, never in the repository, and a
match is reported only by commit, file, line and rule number, never by the text
that matched. Every path goes through shown_path(): one that itself matches a
private term is never printed (not in annotations, messages or the summary),
only its position in a git listing. Without the secret (e.g. a pull request
from a fork) check 3 is skipped with a warning.

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
RULES: list[re.Pattern] = []  # the private terms, for shown_path()


def git(*args: str) -> str:
    return subprocess.run(["git", "-c", "core.quotePath=false", *args],
                          capture_output=True, text=True, check=True, errors="replace").stdout


def git_bytes(*args: str) -> bytes:
    return subprocess.run(["git", "-c", "core.quotePath=false", *args], capture_output=True, check=True).stdout


def shown_path(path: str | None) -> str | None:
    """The one door for a path into the output: None when it matches a private term (then only its position,
    given in the message, locates it), else the path escaped as a GitHub annotation property."""
    if not path or matches(RULES, path):
        return None
    for ch, esc in (("%", "%25"), ("\r", "%0D"), ("\n", "%0A"), (":", "%3A"), (",", "%2C")):
        path = path.replace(ch, esc)
    return path


def error(msg: str, path: str | None = None, line: int | None = None) -> None:
    global problems
    hidden = path is not None and shown_path(path) is None
    path = shown_path(path)
    if hidden and line:
        msg += f" (line {line})"  # the annotation can't carry it without the path
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


def _has_commit(sha: str) -> bool:
    try:
        git("cat-file", "-e", sha + "^{commit}")
        return True
    except subprocess.CalledProcessError:
        return False


def commit_range() -> tuple[str, list[str]]:
    """(description, commits) of what this push or pull request adds."""
    base, head = os.environ.get("BASE", "").strip(), os.environ.get("HEAD", "").strip() or "HEAD"
    head = git("rev-parse", head).strip()
    if base and set(base) != {"0"}:
        if not _has_commit(base) and re.fullmatch(r"[0-9a-f]{40}", base):
            # After a force push the old tip isn't in the clone; GitHub usually still serves it by SHA.
            subprocess.run(["git", "fetch", "--quiet", "--no-tags", "origin", base],
                           capture_output=True, check=False, timeout=120)
        if _has_commit(base):
            try:
                git("merge-base", "--is-ancestor", base, head)
                return f"{base[:8]}..{head[:8]}", git("rev-list", f"{base}..{head}").split()
            except subprocess.CalledProcessError:
                pass
            # A force push (or a pull request whose base moved on): from where the old and new tips meet.
            try:
                mb = git("merge-base", base, head).strip()
                return f"{mb[:8]}..{head[:8]}", git("rev-list", f"{mb}..{head}").split()
            except subprocess.CalledProcessError:
                return f"all of {head[:8]}", git("rev-list", head).split()
        # The old tip can't be found: the merge base with main would be the new tip itself on a force push
        # to main, so check the whole history instead.
        return f"all of {head[:8]}", git("rev-list", head).split()
    # A new branch or tag: everything not already on main, or the whole history.
    for main in ("origin/main", "main"):
        try:
            mb = git("merge-base", head, main).strip()
        except subprocess.CalledProcessError:
            continue
        commits = git("rev-list", f"{mb}..{head}").split()
        return (f"{mb[:8]}..{head[:8]}", commits) if commits else (head[:8], [head])
    return f"all of {head[:8]}", git("rev-list", head).split()


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
    `path` is the annotation (error() withholds a path that itself matches a private term)."""
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


class Blobs:
    """Reads blobs through one `git cat-file --batch` process (bytes in, bytes out: nothing is parsed)."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, blob: str) -> bytes | None:
        """The blob's content, or None when it is missing or larger than MAX_BYTES."""
        self.proc.stdin.write(blob.encode() + b"\n")
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().split()
        if len(header) != 3:
            return None  # "<blob> missing"
        size = int(header[2])
        data = self.proc.stdout.read(size)
        self.proc.stdout.read(1)  # newline after the content
        return data if size <= MAX_BYTES else None

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait()


def changes(sha: str) -> tuple[str, list[tuple[str, str, str, str, str]]]:
    """(listing command, [(status, old mode, old blob, new blob, path)]) of one commit against its first parent,
    from NUL-separated `git diff-tree -z` output: paths are never quoted and no byte in a file can split it."""
    parents = git("rev-list", "--parents", "-n", "1", sha).split()[1:]
    rng = [parents[0], sha] if parents else ["--root", sha]
    listing = "`git diff-tree -r --no-renames --name-only " + " ".join(r[:8] if r != "--root" else r for r in rng) + "`"
    fields = git_bytes("diff-tree", "-r", "-z", "--no-renames", "--no-abbrev", "--no-commit-id", *rng).split(b"\0")
    out = []
    i = 0
    while i + 1 < len(fields):
        meta, name = fields[i], fields[i + 1]
        i += 2
        parts = meta.lstrip(b":").split()
        if len(parts) < 5:
            continue
        out.append((parts[4].decode()[:1], parts[1].decode(), parts[2].decode(), parts[3].decode(),
                    name.decode("utf-8", "replace")))
    return listing, out


def added_lines(old_blob: str, new_blob: str, new: bytes) -> list[tuple[int, bytes]] | None:
    """(line number, text) of the lines `new` adds to the old blob, from `git diff` of the two blobs alone
    (one file, no path, so nothing to quote and no other file's bytes in the stream). None when git treats
    the pair as binary: then the caller scans the whole new file."""
    if set(old_blob) == {"0"}:
        return list(enumerate(new.split(b"\n"), 1))
    out = git_bytes("diff", "--no-color", "--no-ext-diff", "--no-textconv", "--unified=0", old_blob, new_blob)
    lines, n, in_hunk = [], 0, False
    for raw in out.split(b"\n"):
        if raw.startswith(b"@@"):
            in_hunk = True
            m = re.match(rb"@@ -\S+ \+(\d+)", raw)
            n = int(m.group(1)) if m else 0
        elif not in_hunk:
            if raw.startswith(b"Binary files ") or raw.startswith(b"GIT binary patch"):
                return None
        elif raw.startswith(b"+"):
            lines.append((n, raw[1:]))
            n += 1
    return lines


def check_commits(rules: list[re.Pattern]) -> int:
    rng, commits = commit_range()
    print(f"privacy guard: checking {len(commits)} commit(s) ({rng})")
    # 1, and 2/3 on commit messages and names
    for sha in commits:
        fields = git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", sha).split("\x00")
        fields += [""] * (5 - len(fields))
        an, ae, cn, ce, body = fields[0], fields[1], fields[2], fields[3], "\x00".join(fields[4:])
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

    # 2 and 3 on what each commit adds: file names, added lines, added or changed binary files. Each commit's
    # file list and each file's content are read separately (never one combined patch stream to split).
    blobs = Blobs()
    seen_binary: set[str] = set()
    try:
        for sha in commits:
            listing, files = changes(sha)
            for order, (status, _old_mode, old_blob, new_blob, path) in enumerate(files, 1):
                if status == "D":
                    continue
                ref = f"Commit {sha[:8]}, path #{order} in {listing}"
                who = f"Commit {sha[:8]}" if path_ref(rules, path, ref) else f"Commit {sha[:8]} (path #{order})"
                if SECRET_FILES.search(path):
                    error(f"{who} adds a secrets file: remove it from the history and add it to "
                          ".gitignore", path)
                if new_blob == "0" * len(new_blob) or len(new_blob) not in (40, 64):
                    continue
                data = blobs.read(new_blob)  # a submodule (gitlink) or an oversized file reads as None
                if data is None:
                    continue
                if data[:4] == b"PK\x03\x04" or is_binary(data):
                    if rules and new_blob not in seen_binary:
                        seen_binary.add(new_blob)
                        scan_blob(rules, data, f"{who}, an added binary file", path, credentials=False)
                    continue
                added = added_lines(old_blob, new_blob, data)
                if added is None:  # git saw the old version as binary: the whole new file is new text
                    added = list(enumerate(data.split(b"\n"), 1))
                for n, raw in added:
                    line = raw.decode("utf-8", "replace")
                    if path != SELF and CREDENTIALS.search(line):
                        error(f"{who} adds a line that looks like a credential", path, n)
                    for i in matches(rules, line):
                        error(f"{who} adds a line matching private term #{i}: remove it from the "
                              "history (not only from the latest version)", path, n)
    finally:
        blobs.close()
    return len(commits)


def check_tree(rules: list[re.Pattern]) -> None:
    for n, path in enumerate(git("ls-files", "-z").split("\0"), 1):
        if not path or not os.path.isfile(path):
            continue
        shown = path_ref(rules, path, f"Tracked file #{n} (`git ls-files | sed -n {n}p`)")
        if SECRET_FILES.search(path):
            error("A secrets file is tracked: remove it and add it to .gitignore", path)
            continue
        if os.path.getsize(path) > MAX_BYTES:
            continue
        with open(path, "rb") as fh:
            data = fh.read()
        scan_blob(rules, data, "" if shown else f"Tracked file #{n}", path, credentials=path != SELF)


def main() -> int:
    rules = denylist()
    RULES[:] = rules
    if not rules:
        print("::warning::PRIVACY_DENYLIST secret isn't set (or a fork PR): private terms not checked")
    count = check_commits(rules)
    check_tree(rules)
    print(f"privacy guard: {count} commit(s) and {len([p for p in git('ls-files', '-z').split(chr(0)) if p])} file(s) checked, "
          f"{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
