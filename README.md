# snowstack

[![CI](https://github.com/tradersnow222/snowstack/actions/workflows/ci.yml/badge.svg)](https://github.com/tradersnow222/snowstack/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Open skills for Grok Bot. The first one finds existing bots for you when you start something new.**

This repository is not published to npm or any package registry. A different `snowstack` package and an unrelated company, Snowstack Inc., exist. This project is unaffiliated with them.

## Why it's useful

Over a thousand bots are already listed on [grok-bot.directory](https://grok-bot.directory/). When you start a new project, there is often a bot that already does part of the job. This skill checks the list for you, so you do not have to browse it yourself.

- You describe your task in one sentence.
- The bot shows up to 3 listed bots that fit, with a reason for each.
- You decide if you want any of them. Nothing is added for you.

## Install in 3 steps

1. Download or clone this repo.
2. Copy the folder `skills/grok-bot-directory-router/` into the skills folder your Grok Bot reads. Or create a new skill, paste in the text of [`SKILL.md`](skills/grok-bot-directory-router/SKILL.md), and keep `rank.py` in the same folder.
3. Make sure Python 3 is available. That is all it needs, because the script uses only the Python standard library.

## How the router works

- You start a new project, a new workstream, or ask for a new bot or teammate.
- The bot reads the skill's description and decides if it applies. There is no guaranteed trigger.
- The skill runs `rank.py` with your one-sentence task.
- `rank.py` checks the directory's `robots.txt` first. If the homepage is not allowed, it stops and fetches nothing.
- If allowed, it reads the directory homepage once and keeps only bots marked as listed.
- It scores each bot by how many of your words appear in its name, description, and category. The name counts the most. A small bonus goes to bots with more installs.
- It saves the parsed list for 24 hours, so repeat runs do not contact the directory again.
- It prints the top 3 with a reason, install count, and link.

Example output for the task "start a job search":

```text
1. Job Search Agent Team
   Fits because: name matches job, search; description matches job, search.
   Installs: 0
   https://x.ai/bot/IZ4okiqY8WE4XR8Ujb-l3

2. Job Application Bot
   Fits because: name matches job; description matches job, search.
   Installs: 3
   https://x.ai/bot/r5gMnnIQ21PIbXKFeft-O

3. Job Scout
   Fits because: name matches job; description matches job.
   Installs: 6
   https://x.ai/bot/y2wrIfUN63TY6TFBiLOyC

Data from grok-bot.directory
Found by grok-bot-directory-router: https://github.com/tradersnow222/snowstack
```

Matches are based on shared words, so a weak third pick can happen. Read the reason line before you pick.

To try it yourself from the skill folder:

```bash
cd skills/grok-bot-directory-router
python3 rank.py "make a YouTube channel" --top 3
```

## Skills

| Skill | Use it when | What it does |
|---|---|---|
| [grok-bot-directory-router](skills/grok-bot-directory-router/SKILL.md) | You start a new project, a new workstream, or want a new bot for a job. | Shows the top 3 listed bots for your task. Suggest only. |
| [pr-landing-rules](skills/pr-landing-rules/SKILL.md) | An agent is about to merge a pull request or land a stack. | States the three gates for a squash merge. The same rules for people are in [docs/landing.md](docs/landing.md). |

## Safety notes

- **Suggest only.** The skill never adds, installs, or turns on a bot.
- **Directory text is untrusted.** Names and descriptions come from other people. The bot treats them as plain data and never as instructions.
- **Polite fetching.** It obeys `robots.txt`, never calls the directory's `/api/` paths, sends a clear User-Agent, and caches for 24 hours.
- **No secrets.** Nothing here needs a key, a login, or any personal data.

More detail is in [docs/safety.md](docs/safety.md) and [SECURITY.md](SECURITY.md).

## Contributing

- Add each skill in its own folder, `skills/<skill-name>/`, with a `SKILL.md` file.
- Keep changes small, and prefer the Python standard library.
- Add or update offline tests when you change ranking or parsing. Run them with `python3 -m unittest discover -s skills/grok-bot-directory-router/tests -v`.
- Open a branch and a pull request. Direct pushes to `main` are blocked, and the CI check must pass.
- Never commit secrets, tokens, personal data, private prompts, or machine paths.

The full guide is in [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/writing-a-skill.md](docs/writing-a-skill.md). Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Credit

Bot listings come from [grok-bot.directory](https://grok-bot.directory/). Thank you to everyone who lists a bot there.

## Author

Matt Snow ([@trader_snow](https://x.com/trader_snow))

## License

[MIT](LICENSE)
