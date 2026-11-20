#!/usr/bin/env python3
"""Scan tracked files and commits for emails, machine paths, and key-like strings.

The CI test job runs this script. A finding prints a file:line or a commit
SHA, the rule name, and a redacted preview. The matched value is not printed.

Applied rules: stdlib only; keep this check inside the test job; redact
previews; do not add behavior beyond the privacy scrub.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Minimum length for a generic assigned secret. Specific key rules below
# set their own lengths and do not use this cutoff.
_MIN_SECRET_LENGTH = 20
_MIN_ENTROPY = 3.5
_MIN_UNIQUE = 8

_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"([A-Za-z0-9_%+\-]+(?:\.[A-Za-z0-9_%+\-]+)*)"
    r"@"
    r"((?:[A-Za-z0-9\-]+\.)+[A-Za-z]{2,})"
    r"(?![A-Za-z0-9\-])"
)

_ALLOWED_EMAILS = frozenset(
    {
        "noreply@github.com",
        "cursoragent@cursor.com",
    }
)

_GITHUB_RE = re.compile(
    r"ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}"
    r"|github_pat_[A-Za-z0-9_]{22,}"
)
_API_RE = re.compile(r"(?:xai|sk)-[A-Za-z0-9][A-Za-z0-9_\-]{19,}")
_AWS_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_SLACK_RE = re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_ASSIGN_RE = re.compile(
    r"(?i)"
    r"(?P<name>[A-Za-z0-9_.\"']*(?:key|secret|token|password)[A-Za-z0-9_.\"']*)"
    r"\s*[=:]\s*"
    r"(?:(?P<q>['\"])(?P<quoted>[^'\"\n]*)(?P=q)"
    r"|(?P<bare>[A-Za-z0-9+/=_\-]{20,}))"
)


@dataclass(frozen=True)
class Finding:
    location: str
    rule: str
    preview: str

    def render(self) -> str:
        return f"{self.location}: {self.rule}: {self.preview}"


@dataclass(frozen=True)
class Allowlist:
    files: frozenset[str]
    lines: frozenset[tuple[str, int]]


def load_allowlist(path: Path) -> Allowlist:
    """Read path and path:line entries. Blank lines and # comments are ignored."""
    files: set[str] = set()
    lines: set[tuple[str, int]] = set()
    if not path.is_file():
        return Allowlist(frozenset(), frozenset())
    for raw in path.read_text(encoding="utf-8").splitlines():
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        rel, sep, maybe_line = entry.rpartition(":")
        if sep and maybe_line.isdigit() and rel:
            lines.add((rel.strip(), int(maybe_line)))
        else:
            files.add(entry)
    return Allowlist(frozenset(files), frozenset(lines))


def email_allowed(address: str) -> bool:
    """True for the documented noreply and cursor agent exceptions."""
    value = address.lower()
    if value in _ALLOWED_EMAILS:
        return True
    local, sep, domain = value.partition("@")
    if not sep or domain != "users.noreply.github.com" or not local:
        return False
    if "+" in local:
        digits, plus, user = local.partition("+")
        return bool(plus) and digits.isdigit() and bool(user) and "+" not in user
    return True


def normalize_range(expr: str) -> str:
    """Turn an all-zero push base into the reachable tip, otherwise keep expr."""
    if ".." not in expr:
        return expr
    left, right = expr.split("..", 1)
    if left and set(left) <= {"0"}:
        return right or "HEAD"
    return expr


def scan_text(rel: str, text: str, skip_lines: set[int] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if skip_lines and number in skip_lines:
            continue
        for rule, preview in _scan_line(line):
            findings.append(Finding(f"{rel}:{number}", rule, preview))
    return findings


def scan_files(root: Path, rel_paths: list[str], allow: Allowlist) -> list[Finding]:
    findings: list[Finding] = []
    for rel in rel_paths:
        posix = rel.replace("\\", "/")
        if posix in allow.files:
            continue
        path = root / rel
        if not path.is_file():
            continue
        text = _read_text(path)
        if text is None:
            continue
        skip = {number for name, number in allow.lines if name == posix}
        findings.extend(scan_text(posix, text, skip))
    return findings


def scan_tracked_files(root: Path, allow: Allowlist | None = None) -> list[Finding]:
    if allow is None:
        allow = load_allowlist(root / "scripts" / "privacy_scrub_allow.txt")
    return scan_files(root, _tracked_paths(root), allow)


def scan_commits(root: Path, expr: str) -> list[Finding]:
    findings: list[Finding] = []
    for sha in _rev_list(root, normalize_range(expr)):
        meta = _commit_meta(root, sha)
        message = meta.pop("message")
        findings.extend(scan_text(f"{sha}:commit-message", message))
        for field, value in meta.items():
            findings.extend(scan_text(f"{sha}:{field}", value))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to scan")
    parser.add_argument(
        "--commits",
        default="",
        help="Git revision range to scan, for example origin/main..HEAD",
    )
    parser.add_argument(
        "--allow",
        default="",
        help="Allowlist file. Default: scripts/privacy_scrub_allow.txt",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    allow_path = Path(args.allow) if args.allow else root / "scripts" / "privacy_scrub_allow.txt"
    try:
        findings = scan_tracked_files(root, load_allowlist(allow_path))
        if args.commits:
            findings.extend(scan_commits(root, args.commits))
    except RuntimeError as exc:
        print(f"privacy scrub: {exc}", file=sys.stderr)
        return 2
    if findings:
        for finding in findings:
            print(finding.render())
        print(f"privacy scrub: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    print("privacy scrub: ok")
    return 0


def _scan_line(line: str) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    covered: list[tuple[int, int]] = []

    for match in _EMAIL_RE.finditer(line):
        address = match.group(0)
        if email_allowed(address):
            continue
        hits.append(("email", _preview_email(address)))
        covered.append(match.span())

    for start, end, raw in _path_spans(line):
        hits.append(("machine-path", _preview_path(raw)))
        covered.append((start, end))

    for rule, regex, prefixes in _key_specs():
        for match in regex.finditer(line):
            hits.append((rule, _preview_known(match.group(0), prefixes)))
            covered.append(match.span())

    for match in _ASSIGN_RE.finditer(line):
        value = match.group("quoted") if match.group("quoted") is not None else match.group("bare")
        if value is None or not _high_entropy(value):
            continue
        span = match.span("quoted") if match.group("quoted") is not None else match.span("bare")
        if any(start < span[1] and span[0] < end for start, end in covered):
            continue
        hits.append(("assigned-secret", "***"))
        covered.append(span)
    return hits


def _key_specs() -> tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...]:
    return (
        ("github-token", _GITHUB_RE, ("github_pat_", "ghp_", "gho_", "ghs_")),
        ("api-key", _API_RE, ("xai-", "sk-")),
        ("aws-key", _AWS_RE, ("AKIA",)),
        ("slack-token", _SLACK_RE, ("xoxb-", "xoxa-", "xoxp-", "xoxr-", "xoxs-")),
        ("private-key", _PRIVATE_KEY_RE, ("-----BEGIN ",)),
    )


def _path_spans(text: str) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    for regex in _path_regexes():
        for match in regex.finditer(text):
            found.append((match.start(), match.end(), match.group(0)))
    found.sort(key=lambda item: (item[0], item[0] - item[1]))
    kept: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, raw in found:
        if start < last_end:
            continue
        kept.append((start, end, raw))
        last_end = end
    return kept


def _path_regexes() -> tuple[re.Pattern[str], ...]:
    # Pieces are joined so this file does not contain the literal paths.
    home_box = re.escape("/ho" + "me/bo" + "x")
    home = re.escape("/ho" + "me/")
    users = re.escape("/Use" + "rs/")
    workspace = re.escape("/work" + "space")
    windows = re.escape("C:\\" + "Users" + "\\")
    name = r"[A-Za-z0-9._-]+/"
    boundary = r"(?![A-Za-z0-9._-])"
    return (
        re.compile(home_box + boundary),
        re.compile(home + name),
        re.compile(users + name),
        re.compile(workspace + boundary),
        re.compile(windows, re.IGNORECASE),
    )


def _high_entropy(value: str) -> bool:
    if len(value) < _MIN_SECRET_LENGTH or any(char.isspace() for char in value):
        return False
    classes = (
        any(char.islower() for char in value),
        any(char.isupper() for char in value),
        any(char.isdigit() for char in value),
        any(not char.isalnum() for char in value),
    )
    if sum(classes) < 2 or len(set(value)) < _MIN_UNIQUE:
        return False
    counts = Counter(value)
    total = len(value)
    entropy = -sum((count / total) * math.log2(count / total) for count in counts.values())
    return entropy >= _MIN_ENTROPY


def _preview_email(address: str) -> str:
    local, _, domain = address.partition("@")
    host, dot, tld = domain.rpartition(".")
    if not local or not dot or not tld:
        return "***"
    return f"{local[:1]}***@{host[:1]}***.{tld}"


def _preview_path(raw: str) -> str:
    lowered = raw.lower()
    windows = "c:\\" + "users" + "\\"
    if windows in lowered:
        return "C:\\" + "Users" + "\\***"
    if raw.startswith("/Use" + "rs/"):
        return "/Use" + "rs/***"
    if raw.startswith("/ho" + "me/"):
        return "/ho" + "me/***"
    if raw.startswith("/work" + "space"):
        return "/w***"
    return "***"


def _preview_known(raw: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if raw.startswith(prefix):
            preview = prefix + "***"
            if raw not in preview:
                return preview
    return "***"


def _read_text(path: Path) -> str | None:
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError("git ls-files failed")
    return [rel.decode("utf-8", "surrogateescape") for rel in result.stdout.split(b"\0") if rel]


def _rev_list(root: Path, expr: str) -> list[str]:
    result = subprocess.run(
        ["git", "rev-list", expr],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("git rev-list failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _commit_meta(root: Path, sha: str) -> dict[str, str]:
    # NUL cannot appear in git names or messages, so it is a safe field split.
    fmt = "%x00".join(("%an", "%ae", "%cn", "%ce", "%B"))
    result = subprocess.run(
        ["git", "log", "-1", f"--format={fmt}", sha],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError("git log failed")
    parts = result.stdout.split(b"\0", 4)
    if len(parts) != 5:
        raise RuntimeError("git log returned an unexpected record")
    author_name, author_email, committer_name, committer_email, message = (
        _decode_field(part) for part in parts
    )
    return {
        "author-name": author_name,
        "author-email": author_email,
        "committer-name": committer_name,
        "committer-email": committer_email,
        "message": message,
    }


def _decode_field(blob: bytes) -> str:
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob.decode("latin-1")


if __name__ == "__main__":
    sys.exit(main())
