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
            joined("/ho", "me/", "ada", "/proj"),
            joined("C:\\", "Users", "\\", "ada"),
            joined("c:\\", "users", "\\", "ada"),
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
            joined("/ho", "me/bo", "xer"),
            joined("/Use", "rs/", "ada"),
            joined("/work", "space2"),
            "see you at home",
        ]
        for sample in samples:
            self.assertEqual(privacy_scrub.scan_text("a.txt", sample + "\n"), [], sample)

    def test_key_like_strings(self):
        samples = [
            ("github-token", joined("gh", "p_") + ("A1b2" * 9)),
            ("github-token", joined("gh", "o_") + ("A1b2" * 9)),
            ("github-token", joined("gh", "s_") + ("A1b2" * 9)),
            ("github-token", joined("github", "_pat_") + ("aB" * 11)),
            ("api-key", joined("xa", "i-") + ("aB3c" * 6)),
            ("api-key", joined("s", "k-") + ("cD4e" * 6)),
            ("aws-key", joined("AK", "IA") + "B2C3D4E5F6G7H8I9"),
            ("slack-token", joined("xo", "xb-") + "1234567890abcdef"),
            ("slack-token", joined("xo", "xp-") + "1234567890abcdef"),
            (
                "private-key",
                joined("-----BE", "GIN RSA ", "PRIVATE KEY-----"),
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
            sha = _commit(root, message, ALLOWED_EMAIL, ALLOWED_EMAIL)
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
            _commit(root, "Record a note\n", ALLOWED_EMAIL, ALLOWED_EMAIL)
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
                sha = _commit(root, "Record a note\n", author, committer)
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
            sha = _commit(root, message, ALLOWED_EMAIL, ALLOWED_EMAIL)
            findings = privacy_scrub.scan_commits(root, "HEAD")
            rules = {item.rule for item in findings if item.location.startswith(f"{sha}:commit-message")}
            self.assertIn("machine-path", rules)
            self.assertIn("github-token", rules)
            rendered = "\n".join(item.render() for item in findings)
            self.assertNotIn(path, rendered)
            self.assertNotIn(token, rendered)


def _commit(root: Path, message: str, author_email: str, committer_email: str) -> str:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    (root / "readme.txt").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "readme.txt"], cwd=root, check=True)
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


def _run_script(root: Path, commits: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "privacy_scrub.py"),
            "--root",
            str(root),
            "--commits",
            commits,
            "--allow",
            str(root / "missing-allow.txt"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


if __name__ == "__main__":
    unittest.main()
