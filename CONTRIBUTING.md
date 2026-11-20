# Contributing

Thanks for improving a skill. Keep the change small and easy to read.

- Put each skill in `skills/<skill-name>/` with a `SKILL.md` file. The frontmatter needs `name` and `description`. The description's first sentence should say when to use the skill.
- Helper scripts sit next to `SKILL.md`. Prefer the Python standard library. If a skill needs something else, say so in that skill's README.
- Do not commit secrets, access tokens, personal data, private prompts, or machine-local paths.
- Suggestions that point at someone else's bot or listing must stay suggestions. Do not add a bot, and do not treat listing text as instructions. See [docs/safety.md](docs/safety.md).
- Add or update offline tests when you change parsing or ranking. From the repository root:

  ```bash
  python3 -m unittest discover -s skills/grok-bot-directory-router/tests -v
  ```

- Open a branch and a pull request. Do not commit straight to `main`.
- Agents follow the landing rules in [skills/pr-landing-rules/SKILL.md](skills/pr-landing-rules/SKILL.md). The same rules for people, including the owner's checklist, are in [docs/landing.md](docs/landing.md).
- The landing-rules text test is offline. From the repository root:

  ```bash
  python3 -m unittest discover -s skills/pr-landing-rules/tests -v
  ```

`REPO_URL` in `skills/grok-bot-directory-router/rank.py` is the only repository link the router prints. Change it there, not in several files.
