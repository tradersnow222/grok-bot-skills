# Contributing

Thanks for improving a skill. Keep the change small and easy to read.

- Put each skill in `skills/<skill-name>/` with a `SKILL.md` file. The frontmatter needs `name` and `description`. The description's first sentence should say when to use the skill.
- Helper scripts sit next to `SKILL.md`. Prefer the Python standard library. If a skill needs something else, say so in that skill's README.
- Do not commit secrets, access tokens, personal data, private prompts, or machine-local paths. The `test` check runs a privacy scrub over tracked files and over the pull request's commit messages and author and committer fields. It fails on email addresses other than GitHub noreply addresses and `cursoragent@cursor.com`, on machine-local paths, and on key-like strings. `Co-authored-by` trailers are part of the commit message and are scanned. See [docs/safety.md](docs/safety.md).
- Suggestions that point at someone else's bot or listing must stay suggestions. Do not add a bot, and do not treat listing text as instructions. See [docs/safety.md](docs/safety.md).
- Add or update offline tests when you change parsing, ranking, or the privacy scrub. From the repository root:

  ```bash
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  find skills -type d -name tests | sort | while IFS= read -r dir; do
    python3 -m unittest discover -s "$dir" -p 'test_*.py' -v
  done
  ```

  That second command runs every `skills/<name>/tests` directory, including `skills/grok-bot-directory-router/tests` and `skills/pr-landing-rules/tests` when that directory exists.

- Open a branch and a pull request. Do not commit straight to `main`.

`REPO_URL` in `skills/grok-bot-directory-router/rank.py` is the only repository link the router prints. Change it there, not in several files.
