# pr-landing-rules

Rules for when an agent may squash-merge a pull request in this repository. The procedure is in [SKILL.md](SKILL.md). The same rules, plus the owner's checklist for turning landing on later, are in [docs/landing.md](../../docs/landing.md).

An agent may squash-merge only when a human has granted landing, a different agent has posted PASS for the exact commit, and the required `test` check is green on that commit. Until the repository owner approves agent landing, agents stop at merge-ready.

## Test

From the repository root:

```bash
python3 -m unittest discover -s skills/pr-landing-rules/tests -v
```

The test reads `SKILL.md`. It does not call GitHub and it does not merge anything.
