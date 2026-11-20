# Writing a skill

A skill is one folder under `skills/`. The folder name matches the `name` in `SKILL.md`.

## SKILL.md

Start with frontmatter:

```yaml
---
name: example-skill
description: >
  Use when ... Say what the user is doing, in one or two sentences.
  Say what the skill will and will not do.
---
```

The bot decides when a skill applies by reading `description`. There is no separate trigger switch and no guarantee the skill runs. Put the "when" in the first sentence.

The rest of the file is the procedure: what to ask, what to run, what to show, and what to do when a step fails. Tell the bot to show script output when a fact must be exact, instead of filling gaps from memory.

## Optional files

- A helper script next to `SKILL.md`, if the task is parsing, ranking, or anything else that should not be improvised.
- A short `README.md` for people installing or running that skill by hand.
- Tests that run offline. Keep fixtures small and invented. Do not paste live listings into the repository.

Shared notes live in `docs/`, not inside a skill, when more than one skill would need them.

## What not to put in a skill

No secrets, no access tokens, no personal data, and no private prompts. If the skill reads third-party text, say that the text is data and not instructions. Read [safety.md](safety.md) before adding a skill that recommends another bot.
