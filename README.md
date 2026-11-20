# grok-bot-skills

Open skills for Grok Bot. A skill is a folder with a `SKILL.md` file the bot can follow. The first skill, `grok-bot-directory-router`, looks at the public directory when you start a new project, a new workstream, or ask for a new bot or teammate, and suggests bots that already exist. It only suggests. You decide whether to add anyone. Listing data comes from [grok-bot.directory](https://grok-bot.directory/).

## Skills

| Skill | When it triggers | What it does |
|---|---|---|
| [grok-bot-directory-router](skills/grok-bot-directory-router/SKILL.md) | You start a new project, a new workstream, or ask for a new bot or teammate for a job. | Runs `rank.py` on your one-sentence task and shows the top 3 listed bots, with a reason, an install count, and an `https://x.ai/bot/{shareId}` link. It does not add the bot. |

The bot decides when a skill applies by reading that skill's description. There is no guaranteed trigger.

## Install

Copy `skills/grok-bot-directory-router/` into the skills directory your Grok Bot reads.

Or create a new skill, paste `skills/grok-bot-directory-router/SKILL.md` as its text, and keep `rank.py` in the same folder. The skill runs `python3 rank.py` with its working directory set to that folder.

Python 3 is enough. The script uses the standard library only.

Before you rely on the "Found by" link, set `REPO_URL` at the top of `skills/grok-bot-directory-router/rank.py` to this repository's public URL. That is the only place the link is defined.

## How the router works

`rank.py` reads `https://grok-bot.directory/robots.txt` with `urllib.robotparser`. If the homepage is disallowed, or if robots.txt cannot be read, it does not fetch the homepage. When the homepage is allowed, it fetches `https://grok-bot.directory/` once, extracts the bot list from the embedded Next.js payload, and keeps rows with `status == "listed"`. It ranks those rows by keyword overlap with the name, description, and category (the name counts most), plus a small boost from `log(installs)`. A parsed copy is cached for 24 hours. Later runs inside that window do not contact the directory.

Safety rules for suggestions, untrusted listing text, and robots.txt are in [docs/safety.md](docs/safety.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/writing-a-skill.md](docs/writing-a-skill.md).

## License

[MIT](LICENSE). Copyright grok-bot-skills contributors.
