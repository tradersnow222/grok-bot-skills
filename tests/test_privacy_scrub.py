"""Privacy scrub tests. Sensitive samples are joined at runtime."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import privacy_scrub  # noqa: E402

ALLOWED_EMAIL = "cursoragent@cursor.com"


def joined(*parts: str) -> str:
    return "".join(parts)


class RuleTests(unittest.TestCase):
    def test_email_in_a_file_is_redacted(self):
        email = joined("someone", "@", "example.com")
        findings = privacy_scrub.scan_text("notes.txt", f"contact {email}\n")
        self.assertEqual([item.rule for item in findings], ["email"])
        self.assertEqual(findings[0].location, "notes.txt:1")
        self.assertNotIn(email, findings[0].render())
        self.assertNotIn("someone", findings[0].render())

    def test_allowed_emails_are_ignored(self):
        samples = [
            "noreply@github.com",
            ALLOWED_EMAIL,
            joined("496351", "+", "octocat", "@users.noreply.github.com"),
            joined("octocat", "@users.noreply.github.com"),
            "CursorAgent@Cursor.com",
        ]
        for address in samples:
            self.assertEqual(privacy_scrub.scan_text("a.txt", address + "\n"), [], address)

    def test_noreply_lookalikes_fail(self):
        samples = [
            joined("notdigits", "+", "user", "@users.noreply.github.com"),
            joined("123", "+", "@users.noreply.github.com"),
            joined("user", "@users.noreply.github.example"),
            joined("person", "@", "example.com"),
        ]
        for address in samples:
            findings = privacy_scrub.scan_text("a.txt", address + "\n")
            self.assertTrue(findings, address)
            self.assertEqual(findings[0].rule, "email")
            self.assertNotIn(address, findings[0].render())

    def test_machine_paths(self):
        samples = [
            joined("/ho", "me/bo", "x"),
            joined("/ho", "me/bo", "x", "/src"),
            joined("/work", "space"),
            joined("/work", "space", "/proj"),
            joined("/Use", "rs/", "ada", "/proj"),
            joined("/Use", "rs/", "ada"),
            joined("/ho", "me/", "ada", "/proj"),
            joined("/ho", "me/", "ada"),
            joined("C:\\", "Users", "\\", "ada"),
            joined("c:\\", "users", "\\", "ada"),
            joined("C:\\\\", "Users", "\\\\", "ada"),
            joined("/ro", "ot"),
            joined("/ro", "ot", "/src"),
            joined("/mnt/c/", "Users"),
            joined("/mnt/c/", "Users", "/ada"),
            joined("/cur", "sor/stores"),
            joined("/cur", "sor/stores", "/id"),
        ]
        for sample in samples:
            findings = privacy_scrub.scan_text("a.txt", f"path {sample}\n")
            self.assertTrue(findings, sample)
            self.assertTrue(all(item.rule == "machine-path" for item in findings), sample)
            rendered = "\n".join(item.render() for item in findings)
            self.assertNotIn(sample, rendered)

    def test_path_lookalikes_are_ignored(self):
        samples = [
            joined("/ho", "mework", "/notes"),
            joined("/work", "space2"),
            "see you at home",
            joined("/ro", "oter"),
            joined("/ro", "ots"),
            joined("/cur", "sor/store"),
            joined("/mnt/c/", "User"),
        ]
        for sample in samples:
            self.assertEqual(privacy_scrub.scan_text("a.txt", sample + "\n"), [], sample)

    def test_key_like_strings(self):
        samples = [
            ("github-token", joined("gh", "p_") + ("A1b2" * 9)),
            ("github-token", joined("gh", "o_") + ("A1b2" * 9)),
            ("github-token", joined("gh", "s_") + ("A1b2" * 9)),
            ("github-token", joined("gh", "u_") + ("A1b2" * 9)),
            ("github-token", joined("gh", "r_") + ("A1b2" * 9)),
            ("github-token", joined("github", "_pat_") + ("aB" * 11)),
            ("api-key", joined("xa", "i-") + ("aB3c" * 6)),
            ("api-key", joined("s", "k-") + ("cD4e" * 6)),
            ("api-key", joined("sk", "_live_") + ("cD4e" * 6)),
            ("api-key", joined("rk", "_live_") + ("cD4e" * 6)),
            ("api-key", joined("AI", "za") + ("A1b2C3d4" * 3)),
            ("aws-key", joined("AK", "IA") + "B2C3D4E5F6G7H8I9"),
            ("aws-key", joined("AS", "IA") + "B2C3D4E5F6G7H8I9"),
            ("slack-token", joined("xo", "xb-") + "1234567890abcdef"),
            ("slack-token", joined("xo", "xp-") + "1234567890abcdef"),
            (
                "private-key",
                joined("-----BE", "GIN RSA ", "PRIVATE KEY-----"),
            ),
            (
                "bearer-token",
                joined("Author", "ization: Bearer ", "abcdef12", "34567890xyz"),
            ),
            (
                "jwt",
                joined(
                    "eyJhbGciOi",
                    "JIUzI1NiJ9",
                    ".",
                    "eyJzdWIiOi",
                    "IxMjM0NTY3In0",
                    ".",
                    "dGVzdHNpZ",
                    "25hdHVyZQ",
                ),
            ),
        ]
        for rule, sample in samples:
            findings = privacy_scrub.scan_text("a.txt", sample + "\n")
            self.assertTrue(any(item.rule == rule for item in findings), (rule, findings))
            rendered = "\n".join(item.render() for item in findings)
            self.assertNotIn(sample, rendered)

    def test_assigned_high_entropy_secret(self):
        value = joined("abC1", "deF2", "ghI3", "jkL4", "mnO5")
        lines = [
            f'api_key = "{value}"',
            f"token={value}",
            f'"access_token": "{value}"',
            f"db_password: '{value}'",
        ]
        for line in lines:
            findings = privacy_scrub.scan_text("a.txt", line + "\n")
            self.assertTrue(any(item.rule == "assigned-secret" for item in findings), line)
            self.assertNotIn(value, "\n".join(item.render() for item in findings))

    def test_assigned_secret_keeps_dotted_value(self):
        # Two dotted segments so this is not also classified as a JWT.
        value = joined("abC1deF2", ".", "ghI3jkL4mnO5pqR6")
        line = f"token={value}"
        findings = privacy_scrub.scan_text("a.txt", line + "\n")
        self.assertTrue(any(item.rule == "assigned-secret" for item in findings), findings)
        self.assertNotIn(value, "\n".join(item.render() for item in findings))

    def test_assigned_secret_auth_credential_bearer_names(self):
        value = joined("abC1", "deF2", "ghI3", "jkL4", "mnO5")
        lines = [
            f'auth = "{value}"',
            f'credential = "{value}"',
            f'bearer = "{value}"',
        ]
        for line in lines:
            findings = privacy_scrub.scan_text("a.txt", line + "\n")
            self.assertTrue(any(item.rule == "assigned-secret" for item in findings), line)
            self.assertNotIn(value, "\n".join(item.render() for item in findings))
        author = f'author = "{value}"'
        rules = [item.rule for item in privacy_scrub.scan_text("a.txt", author + "\n")]
        self.assertNotIn("assigned-secret", rules, author)

    def test_low_entropy_or_unrelated_assignment_is_ignored(self):
        value = joined("abC1", "deF2", "ghI3", "jkL4", "mnO5")
        samples = [
            'api_key = "short"',
            'password = "' + ("ab" * 15) + '"',
            'secret = "this is a normal sentence about nothing"',
            f'description = "{value}"',
            "TOKEN_RE = re.compile(r\"[a-z0-9]+\")",
        ]
        for sample in samples:
            rules = [item.rule for item in privacy_scrub.scan_text("a.py", sample + "\n")]
            self.assertNotIn("assigned-secret", rules, sample)

    def test_specific_key_is_not_also_an_assigned_secret(self):
        token = joined("gh", "p_") + ("A1b2" * 9)
        findings = privacy_scrub.scan_text("a.py", f'api_key = "{token}"\n')
        self.assertIn("github-token", [item.rule for item in findings])
        self.assertNotIn("assigned-secret", [item.rule for item in findings])

    def test_allowlist_skips_a_file_or_one_line(self):
        email = joined("someone", "@", "example.com")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "fixture.txt").write_text(f"ok\n{email}\n", encoding="utf-8")
            empty = privacy_scrub.Allowlist(frozenset(), frozenset())
            self.assertTrue(privacy_scrub.scan_files(root, ["fixture.txt"], empty))
            whole = privacy_scrub.Allowlist(frozenset({"fixture.txt"}), frozenset())
            self.assertEqual(privacy_scrub.scan_files(root, ["fixture.txt"], whole), [])
            one_line = privacy_scrub.Allowlist(frozenset(), frozenset({("fixture.txt", 2)}))
            self.assertEqual(privacy_scrub.scan_files(root, ["fixture.txt"], one_line), [])
            other = privacy_scrub.Allowlist(frozenset(), frozenset({("fixture.txt", 1)}))
            self.assertTrue(privacy_scrub.scan_files(root, ["fixture.txt"], other))

    def test_allowlist_uses_raw_git_path(self):
        email = joined("someone", "@", "example.com")
        raw = "tests" + "\\" + "fixtures" + "\\" + "privacy_scrub_sample.txt"
        slash = "tests/fixtures/privacy_scrub_sample.txt"
        allow = privacy_scrub.Allowlist(frozenset({slash}), frozenset())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / raw).write_text(f"contact {email}\n", encoding="utf-8")
            findings = privacy_scrub.scan_files(root, [raw], allow)
            self.assertTrue(any(item.rule == "email" for item in findings), findings)
            self.assertNotIn(email, "\n".join(item.render() for item in findings))
            (root / "tests" / "fixtures").mkdir(parents=True)
            (root / slash).write_text(f"contact {email}\n", encoding="utf-8")
            self.assertEqual(privacy_scrub.scan_files(root, [slash], allow), [])

    def test_nul_byte_does_not_hide_a_file(self):
        email = joined("someone", "@", "example.com")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "notes.txt").write_bytes(
                f"contact {email}\n".encode("utf-8") + b"\x00more\n"
            )
            findings = privacy_scrub.scan_files(
                root, ["notes.txt"], privacy_scrub.Allowlist(frozenset(), frozenset())
            )
            self.assertTrue(any(item.rule == "email" for item in findings), findings)
            self.assertNotIn(email, "\n".join(item.render() for item in findings))

    def test_utf16_file_is_scanned(self):
        email = joined("someone", "@", "example.com")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "notes.txt").write_bytes(("contact " + email + "\n").encode("utf-16"))
            findings = privacy_scrub.scan_files(
                root, ["notes.txt"], privacy_scrub.Allowlist(frozenset(), frozenset())
            )
            self.assertTrue(any(item.rule == "email" for item in findings), findings)
            self.assertNotIn(email, "\n".join(item.render() for item in findings))

    def test_binary_extension_is_skipped(self):
        email = joined("someone", "@", "example.com")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "icon.png").write_bytes(f"contact {email}\n".encode("utf-8"))
            findings = privacy_scrub.scan_files(
                root, ["icon.png"], privacy_scrub.Allowlist(frozenset(), frozenset())
            )
            self.assertEqual(findings, [])

    def test_committed_fixture_is_skipped_by_the_default_allowlist(self):
        allow = privacy_scrub.load_allowlist(ROOT / "scripts" / "privacy_scrub_allow.txt")
        self.assertIn("tests/fixtures/privacy_scrub_sample.txt", allow.files)
        others = subprocess.check_output(
            ["git", "ls-files", "-z", "--others", "--exclude-standard"],
            cwd=ROOT,
        )
        rels = privacy_scrub._tracked_paths(ROOT)
        rels += [rel.decode("utf-8") for rel in others.split(b"\0") if rel]
        self.assertEqual(privacy_scrub.scan_files(ROOT, rels, allow), [])
        fixture = (ROOT / "tests" / "fixtures" / "privacy_scrub_sample.txt").read_text(
            encoding="utf-8"
        )
        direct = privacy_scrub.scan_text("fixture.txt", fixture)
        rules = {item.rule for item in direct}
        self.assertIn("email", rules)
        self.assertIn("machine-path", rules)
        rendered = "\n".join(item.render() for item in direct)
        self.assertNotIn(joined("someone", "@", "example.com"), rendered)
        self.assertNotIn(joined("/ho", "me/bo", "x"), rendered)

    def test_zero_before_range_scans_the_tip(self):
        zeros = "0" * 40
        self.assertEqual(privacy_scrub.normalize_range(f"{zeros}..abc123"), "abc123")
        self.assertEqual(
            privacy_scrub.normalize_range("origin/main..HEAD"),
            "origin/main..HEAD",
        )


class CommitScanTests(unittest.TestCase):
    def test_coauthored_by_trailer_in_a_commit_message(self):
        email = joined("someone", "@", "example.com")
        message = "Record a note\n\nCo-authored-by: Someone <" + email + ">\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha = _commit(root, "readme.txt", "clean\n", message, ALLOWED_EMAIL, ALLOWED_EMAIL)
            findings = privacy_scrub.scan_commits(root, "HEAD")
            rendered = "\n".join(item.render() for item in findings)
            self.assertTrue(
                any(
                    item.location == f"{sha}:commit-message:3" and item.rule == "email"
                    for item in findings
                ),
                rendered,
            )
            self.assertNotIn(email, rendered)
            completed = _run_script(root, "HEAD")
            self.assertNotEqual(completed.returncode, 0)
            self.assertNotIn(email, completed.stdout)
            self.assertNotIn(email, completed.stderr)
            self.assertIn(sha, completed.stdout)
            self.assertIn("email", completed.stdout)

    def test_clean_commit_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _commit(root, "readme.txt", "clean\n", "Record a note\n", ALLOWED_EMAIL, ALLOWED_EMAIL)
            self.assertEqual(privacy_scrub.scan_commits(root, "HEAD"), [])
            completed = _run_script(root, "HEAD")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("privacy scrub: ok", completed.stdout)

    def test_author_and_committer_emails_are_scanned(self):
        bad = joined("person", "@", "example.com")
        cases = (
            ("author-email", bad, ALLOWED_EMAIL),
            ("committer-email", ALLOWED_EMAIL, bad),
        )
        for field, author, committer in cases:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                sha = _commit(root, "readme.txt", "clean\n", "Record a note\n", author, committer)
                findings = privacy_scrub.scan_commits(root, "HEAD")
                rendered = "\n".join(item.render() for item in findings)
                self.assertTrue(
                    any(item.location.startswith(f"{sha}:{field}") and item.rule == "email" for item in findings),
                    (field, rendered),
                )
                self.assertNotIn(bad, rendered)

    def test_commit_message_path_and_token(self):
        path = joined("/Use", "rs/", "ada", "/proj")
        token = joined("gh", "p_") + ("A1b2" * 9)
        message = "note " + path + " " + token + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha = _commit(root, "readme.txt", "clean\n", message, ALLOWED_EMAIL, ALLOWED_EMAIL)
            findings = privacy_scrub.scan_commits(root, "HEAD")
            rules = {item.rule for item in findings if item.location.startswith(f"{sha}:commit-message")}
            self.assertIn("machine-path", rules)
            self.assertIn("github-token", rules)
            rendered = "\n".join(item.render() for item in findings)
            self.assertNotIn(path, rendered)
            self.assertNotIn(token, rendered)

    def test_secret_added_then_removed_in_range_is_found(self):
        email = joined("someone", "@", "example.com")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = _commit(
                root, "readme.txt", "clean\n", "Start\n", ALLOWED_EMAIL, ALLOWED_EMAIL
            )
            _commit_existing(root, "note.txt", f"contact {email}\n", "Add note\n")
            _commit_existing(root, "note.txt", "contact none\n", "Remove note\n")
            findings = privacy_scrub.scan_commits(root, f"{first}..HEAD")
            rendered = "\n".join(item.render() for item in findings)
            self.assertTrue(
                any(item.rule == "email" and ":added:" in item.location for item in findings),
                rendered,
            )
            self.assertNotIn(email, rendered)
            completed = _run_script(root, f"{first}..HEAD")
            self.assertNotEqual(completed.returncode, 0)
            self.assertNotIn(email, completed.stdout)
            self.assertNotIn(email, completed.stderr)
            self.assertIn("email", completed.stdout)

    def test_text_env_scans_values(self):
        email = joined("someone", "@", "example.com")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _commit(root, "readme.txt", "clean\n", "Record a note\n", ALLOWED_EMAIL, ALLOWED_EMAIL)
            completed = _run_script(
                root,
                "HEAD",
                extra=["--text-env", "PR_TITLE", "--text-env", "PR_BODY"],
                env_updates={"PR_TITLE": "Add " + email, "PR_BODY": "clean description"},
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertNotIn(email, completed.stdout)
            self.assertNotIn(email, completed.stderr)
            self.assertIn("env:PR_TITLE", completed.stdout)
            self.assertIn("email", completed.stdout)

    def test_text_env_empty_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _commit(root, "readme.txt", "clean\n", "Record a note\n", ALLOWED_EMAIL, ALLOWED_EMAIL)
            completed = _run_script(
                root,
                "HEAD",
                extra=["--text-env", "PR_TITLE", "--text-env", "PR_BODY"],
                env_updates={"PR_TITLE": "", "PR_BODY": ""},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("privacy scrub: ok", completed.stdout)


def _git_commit(root: Path, message: str, author_email: str, committer_email: str) -> str:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Test Author",
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_COMMITTER_NAME": "Test Author",
            "GIT_COMMITTER_EMAIL": committer_email,
        }
    )
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "-m", message],
        cwd=root,
        check=True,
        env=env,
    )
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def _commit(
    root: Path,
    filename: str,
    content: str,
    message: str,
    author_email: str,
    committer_email: str,
) -> str:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    (root / filename).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", filename], cwd=root, check=True)
    return _git_commit(root, message, author_email, committer_email)


def _commit_existing(root: Path, filename: str, content: str, message: str) -> str:
    (root / filename).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", filename], cwd=root, check=True)
    return _git_commit(root, message, ALLOWED_EMAIL, ALLOWED_EMAIL)


def _run_script(
    root: Path,
    commits: str,
    extra: list[str] | None = None,
    env_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_updates:
        env.update(env_updates)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "privacy_scrub.py"),
        "--root",
        str(root),
        "--commits",
        commits,
        "--allow",
        str(root / "missing-allow.txt"),
    ]
    if extra:
        command.extend(extra)
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


if __name__ == "__main__":
    unittest.main()
