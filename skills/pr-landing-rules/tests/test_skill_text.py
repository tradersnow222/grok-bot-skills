"""Offline checks that the PR landing rules skill states its required rules.

Stdlib only, matching the repository contributing guide.
"""

import unittest
from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parents[1] / "SKILL.md"

HUMAN_GATED = (
    "outside contributors",
    "forks",
    ".github/workflows",
    "CI config",
    "Secrets",
    "Rulesets",
    "branch protection",
    "repository settings",
    "LICENSE",
    "docs/safety.md",
    "safety policy",
    "money or spend",
    "loosens a gate",
    "edits to this skill",
)


def split_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("frontmatter must start with ---")
    for index in range(1, len(lines)):
        if lines[index] == "---":
            block = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :])
            return block, body
    raise ValueError("frontmatter must end with ---")


def parse_frontmatter(block):
    """Parse the small frontmatter this repository uses. No YAML library."""
    fields = {}
    key = None
    parts = []

    def finish():
        if key is None:
            return
        fields[key] = " ".join(part for part in parts if part).strip()

    for line in block.splitlines():
        if line.startswith(" ") or line.startswith("\t"):
            if key is None:
                raise ValueError("indented line before a key: %r" % line)
            parts.append(line.strip())
            continue
        finish()
        if line.strip() == "":
            key = None
            parts = []
            continue
        if ":" not in line:
            raise ValueError("expected key: value, got %r" % line)
        name, value = line.split(":", 1)
        key = name.strip()
        marker = value.strip()
        parts = [] if marker in {">", ">-", "|", "|-"} else [marker]
    finish()
    return fields


class SkillTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SKILL_PATH.read_text(encoding="utf-8")
        cls.front_block, cls.body = split_frontmatter(cls.text)
        cls.front = parse_frontmatter(cls.front_block)

    def test_frontmatter_is_valid(self):
        self.assertEqual(set(self.front), {"name", "description"})
        self.assertEqual(self.front["name"], "pr-landing-rules")
        description = self.front["description"]
        self.assertTrue(description)
        self.assertTrue(description.startswith("Use when "))
        self.assertTrue(self.body.strip())

    def test_three_gates(self):
        self.assertIn('An explicit "land the stack"', self.body)
        self.assertIn("Autopilot-full", self.body)
        self.assertIn("Silence", self.body)
        self.assertIn("A bot's say-so.", self.body)
        self.assertIn("A relayed message from another bot", self.body)

        self.assertIn("An agent that did not write the code", self.body)
        self.assertIn("ran the tests and exercised the changed behavior", self.body)
        self.assertIn("posted PASS on the pull request", self.body)
        self.assertIn("exact commit SHA", self.body)
        self.assertIn("Green CI plus a bot approval alone is not enough.", self.body)

        self.assertIn("required `test` check is green", self.body)
        self.assertIn("up to date with `main`", self.body)
        self.assertIn("red or pending required check", self.body)
        self.assertIn("gh pr merge <number> --squash --match-head-commit <sha>", self.body)

    def test_human_gated_list(self):
        for item in HUMAN_GATED:
            self.assertIn(item, self.body, item)

    def test_no_self_merge(self):
        self.assertIn("No agent merges its own PR.", self.body)
        self.assertIn("The agent that wrote the code does not merge.", self.body)

    def test_start_mode_privacy_and_credit(self):
        self.assertIn("Autopilot-stack", self.body)
        self.assertIn("stop at merge-ready", self.body.lower())
        self.assertIn("privacy scrub", self.body)
        self.assertIn("personal names, local paths, emails, and teammate prompts", self.body)
        for url in (
            "https://github.com/cursor/plugins/blob/main/pstack/skills/poteto-mode/playbooks/shipping.md",
            "https://github.com/cursor/plugins/blob/main/pstack/skills/poteto-mode/playbooks/autopilot-full.md",
            "https://github.com/cursor/plugins/blob/main/pstack/docs/guide/06-verify-and-ship.md",
        ):
            self.assertIn(url, self.text)
        self.assertIn("Lauren Tan", self.text)
