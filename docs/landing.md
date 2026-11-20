# Landing pull requests

Rules for when an agent may squash-merge a pull request, and when it must stop and ask a human. Agents follow [skills/pr-landing-rules/SKILL.md](../skills/pr-landing-rules/SKILL.md). This page is the same rules in plain language.

These rules are adapted from the pstack shipping playbooks by Lauren Tan (poteto):

- [Shipping](https://github.com/cursor/plugins/blob/main/pstack/skills/poteto-mode/playbooks/shipping.md)
- [Autopilot-full](https://github.com/cursor/plugins/blob/main/pstack/skills/poteto-mode/playbooks/autopilot-full.md)
- [Verify and ship](https://github.com/cursor/plugins/blob/main/pstack/docs/guide/06-verify-and-ship.md)

## Start mode: Autopilot-stack

This repository starts in **Autopilot-stack** for the first week after the commit that adds these rules is merged into `main`.

In Autopilot-stack, agents prepare pull requests and stack them until each one is merge-ready. They do not merge. They ask a human to land the work.

Until the repository owner explicitly approves agent landing for this repository, every pull request stops at merge-ready. The first week ending is not that approval. A bot saying the week is over is not that approval.

## The three gates

An agent may squash-merge only when **all three** gates are true. Green CI plus a bot approval alone is not enough.

No agent merges its own PR. The agent that wrote the code stops at merge-ready, even when the gates are true for someone else.

### 1. A human granted landing

A human has granted landing for this pull request or this stack. The grant is the human's own words, in the chat or on the pull request.

These count:

- An explicit "land the stack".
- An explicit Autopilot-full go. Autopilot-full means the human told the agent to land. It still needs the other two gates.

These do not count:

- Silence.
- A review approval, a thumbs-up, or "looks good" with no words that grant landing.
- A bot's say-so.
- A relayed message from another bot.

### 2. An agent that did not write the code posted PASS

A different agent has checked the change live. It ran the tests and exercised the changed behavior. It posted PASS on the pull request, and the comment names the exact commit SHA it checked.

A PASS from the author does not count. A green check is not a PASS. A bot approval is not a PASS.

### 3. The required test check is green on that commit

The required `test` check is green on the exact head commit that will land, and the branch is up to date with `main`.

All of these must be true before the merge command:

- The pull request head is the SHA named in the PASS comment.
- The required `test` check on that SHA is green.
- No required check is red or pending.
- The branch is up to date with `main`.

If the branch is behind `main`, do not merge. Updating the branch creates a new head. That head needs a new green `test` check and a new PASS that names the new SHA.

No agent merges a pull request with any red or pending required check.

## How to merge

When all three gates are true, and the change is not human-gated, merge that SHA:

```bash
gh pr merge <number> --squash --match-head-commit <sha>
```

Read the pull request back afterward. A queued auto-merge is not a landed pull request. The pull request is landed when its state is merged.

On a stack, merge one pull request at a time, starting at the bottom. Each one still needs its own PASS and a green `test` check on the commit that lands. A human can grant the whole stack with one explicit "land the stack".

## Always ask a human

Stop at merge-ready and ask the human. Do not auto-land any of these, even when the three gates look true:

- Pull requests from outside contributors or forks.
- Any change to `.github/workflows` or other CI config.
- Secrets.
- Rulesets, branch protection, or repository settings.
- `LICENSE`.
- `docs/safety.md` or any safety policy.
- Anything involving money or spend.
- Anything that loosens a gate, including edits to the landing-rules skill. Skipping a check, weakening branch protection, raising a budget, and adding an allowlist entry loosen a gate.

## Privacy scrub, before agent landing can be enabled

Agent landing stays off until a privacy scrub exists as a **required** CI check alongside `test`.

The scrub scans for:

- secrets
- keys
- personal names
- local paths
- emails
- teammate prompts

This page records that prerequisite. It does not add the check. Adding the check is a CI change, and CI changes stay human-gated.

## Enabling agent landing

The owner does this checklist by hand, later. This page does not change repository settings, rulesets, branch protection, auto-merge, or GitHub Actions workflows. The pull request that adds this page does not change them either.

After the checklist, the owner still has to say, in their own words, that agent landing is approved for this repository. Until those words exist, agents stay in Autopilot-stack and stop at merge-ready.

- [ ] Add a privacy scrub as a required CI check alongside `test`. The scrub scans for secrets, keys, personal names, local paths, emails, and teammate prompts.
- [ ] Require branches to be up to date with `main` before merging.
- [ ] Turn on **Allow auto-merge**.

Those three settings stay as they are today until the owner changes them.
