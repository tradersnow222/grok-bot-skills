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
import os
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

_BINARY_EXTS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
    }
)

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
    r"|ghu_[A-Za-z0-9]{36}|ghr_[A-Za-z0-9]{36}"
    r"|github_pat_[A-Za-z0-9_]{22,}"
)
_API_RE = re.compile(
    r"(?:xai|sk)-[A-Za-z0-9][A-Za-z0-9_\-]{19,}"
    r"|(?:sk|rk)_live_[A-Za-z0-9]{16,}"
)
_AWS_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_GOOGLE_API_RE = re.compile(r"AIza[0-9A-Za-z_\-]{20,}")
_SLACK_RE = re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_BEARER_RE = re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+(\S{8,})")
_JWT_RE = re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_ASSIGN_RE = re.compile(
    r"(?i)"
    r"(?P<name>[A-Za-z0-9_.\"']*(?:"
    r"key|secret|token|password|credential|bearer|authorization|authentication"
    r"|(?<![A-Za-z])auth(?![A-Za-z])"
    r")[A-Za-z0-9_.\"']*)"
    r"\s*[=:]\s*"
    r"(?:(?P<q>['\"])(?P<quoted>[^'\"\n]*)(?P=q)"
    r"|(?P<bare>[A-Za-z0-9+/=_\-.]{8,}))"
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
        # Match the allowlist against the raw git path, not a slash-normalized
        # form, so a backslash in a file name is not treated as a separator.
        if rel in allow.files:
            continue
        path = root / rel
        if not path.is_file():
            continue
        text = _read_text(path)
        if text is None:
            continue
        skip = {number for name, number in allow.lines if name == rel}
        findings.extend(scan_text(rel, text, skip))
    return findings


def scan_tracked_files(root: Path, allow: Allowlist | None = None) -> list[Finding]:
    if allow is None:
        allow = load_allowlist(root / "scripts" / "privacy_scrub_allow.txt")
    return scan_files(root, _tracked_paths(root), allow)


def scan_commits(root: Path, expr: str, allow: Allowlist | None = None) -> list[Finding]:
    findings: list[Finding] = []
    expr = normalize_range(expr)
    for sha in _rev_list(root, expr):
        meta = _commit_meta(root, sha)
        message = meta.pop("message")
        findings.extend(scan_text(f"{sha}:commit-message", message))
        for field, value in meta.items():
            findings.extend(scan_text(f"{sha}:{field}", value))
    findings.extend(_scan_added_lines(root, expr, allow))
    return findings


def scan_env_texts(names: list[str]) -> list[Finding]:
    """Scan environment values (for example a pull request title or body)."""
    findings: list[Finding] = []
    for name in names:
        value = os.environ.get(name, "")
        if not value:
            continue
        findings.extend(scan_text(f"env:{name}", value))
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
    parser.add_argument(
        "--text-env",
        action="append",
        default=[],
        metavar="NAME",
        help="Scan the value of this environment variable, such as PR_TITLE",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    allow_path = Path(args.allow) if args.allow else root / "scripts" / "privacy_scrub_allow.txt"
    try:
        allow = load_allowlist(allow_path)
        findings = scan_tracked_files(root, allow)
        if args.commits:
            findings.extend(scan_commits(root, args.commits, allow))
        findings.extend(scan_env_texts(args.text_env))
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
            if rule == "bearer-token":
                preview = "Authorization: Bearer ***"
            elif rule == "jwt":
                preview = "***.***.***"
            else:
                preview = _preview_known(match.group(0), prefixes)
            hits.append((rule, preview))
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
        ("github-token", _GITHUB_RE, ("github_pat_", "ghp_", "gho_", "ghs_", "ghu_", "ghr_")),
        ("api-key", _API_RE, ("xai-", "sk_live_", "rk_live_", "sk-")),
        ("aws-key", _AWS_RE, ("AKIA", "ASIA")),
        ("api-key", _GOOGLE_API_RE, ("AIza",)),
        ("slack-token", _SLACK_RE, ("xoxb-", "xoxa-", "xoxp-", "xoxr-", "xoxs-")),
        ("private-key", _PRIVATE_KEY_RE, ("-----BEGIN ",)),
        ("bearer-token", _BEARER_RE, ()),
        ("jwt", _JWT_RE, ()),
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
    root_home = re.escape("/ro" + "ot")
    mnt_users = re.escape("/mnt/c/" + "Users")
    stores = re.escape("/cur" + "sor/stores")
    windows = r"C:\\+Use" + r"rs\\+"
    name = r"[A-Za-z0-9._-]+"
    boundary = r"(?![A-Za-z0-9._-])"
    return (
        re.compile(home_box + boundary),
        re.compile(home + name + boundary),
        re.compile(users + name + boundary),
        re.compile(workspace + boundary),
        re.compile(root_home + boundary),
        re.compile(mnt_users + boundary, re.IGNORECASE),
        re.compile(stores + boundary),
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
    win = "c:" + "\\" + "users"
    win_json = "c:" + "\\\\" + "users"
    if win in lowered or win_json in lowered:
        return "C:\\" + "Users" + "\\***"
    if lowered.startswith("/mnt/c/" + "users"):
        return "/m***"
    if raw.startswith("/Use" + "rs/"):
        return "/Use" + "rs/***"
    if raw.startswith("/ho" + "me/"):
        return "/ho" + "me/***"
    if raw.startswith("/work" + "space"):
        return "/w***"
    if raw.startswith("/ro" + "ot"):
        return "/r***"
    if raw.startswith("/cur" + "sor/stores"):
        return "/c***"
    return "***"


def _preview_known(raw: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if raw.startswith(prefix):
            preview = prefix + "***"
            if raw not in preview:
                return preview
    return "***"


def _is_skipped_binary(path: Path) -> bool:
    return path.suffix.lower() in _BINARY_EXTS


def _looks_like_utf16(data: bytes) -> bool:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return True
    if len(data) < 4 or len(data) % 2 != 0:
        return False
    pairs = len(data) // 2
    even_nuls = data[0::2].count(0)
    odd_nuls = data[1::2].count(0)
    return even_nuls * 2 >= pairs or odd_nuls * 2 >= pairs


def _read_text(path: Path) -> str | None:
    if _is_skipped_binary(path):
        return None
    data = path.read_bytes()
    if _looks_like_utf16(data):
        if data.startswith(b"\xfe\xff"):
            encoding = "utf-16-be"
        elif data.startswith(b"\xff\xfe"):
            encoding = "utf-16-le"
        else:
            odd_nuls = data[1::2].count(0)
            even_nuls = data[0::2].count(0)
            encoding = "utf-16-le" if odd_nuls >= even_nuls else "utf-16-be"
        return data.decode(encoding, errors="replace")
    return data.decode("utf-8", errors="replace")


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


def _scan_added_lines(root: Path, expr: str, allow: Allowlist | None = None) -> list[Finding]:
    """Scan lines added in git log -p over expr, including later-removed secrets."""
    result = subprocess.run(
        ["git", "log", "-p", "--text", "--format=%x00%H", expr],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError("git log failed")
    findings: list[Finding] = []
    for record in result.stdout.split(b"\0"):
        if not record.strip():
            continue
        header, sep, rest = record.partition(b"\n")
        sha = _decode_field(header.strip())
        if not sha:
            continue
        path = "unknown"
        text = _decode_field(rest) if sep else ""
        for line in text.splitlines():
            if line.startswith("+++ b/"):
                path = line[6:]
            elif line.startswith("+") and not line.startswith("+++"):
                if allow and path in allow.files:
                    continue
                for rule, preview in _scan_line(line[1:]):
                    findings.append(Finding(f"{sha}:added:{path}", rule, preview))
    return findings


def _decode_field(blob: bytes) -> str:
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob.decode("latin-1")


if __name__ == "__main__":
    sys.exit(main())
