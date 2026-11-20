# grok-bot-directory-router

Suggests a teammate you already have, or up to three listed bots from [grok-bot.directory](https://grok-bot.directory/), for a one-sentence task. It does not install a bot. You decide. Teammate names and descriptions stay on this machine.

The behavior a Grok Bot should follow is in [SKILL.md](SKILL.md). Ranking is in `rank.py` (Python 3 standard library only).

## Run

From this folder:

```bash
python3 rank.py "draft a weekly meal plan"
```

| Flag | Effect |
|---|---|
| `--top N` | How many directory matches to print. Default 3. |
| `--json` | Machine-readable output. With `--team`, the JSON includes `path`. |
| `--refresh` | Read the directory again even if the local cache is still inside its 24 hour window. Ignored when a teammate is a strong fit. |
| `--team FILE` | Local JSON list of `{name, description}`. If the best score is at least `TEAM_SCORE_THRESHOLD` (5, one shared name word), print `Path: team` and do not contact the directory. Otherwise print `Path: directory` and run the directory flow. An empty list or an empty file takes the directory path. |

On the directory path the script checks `robots.txt`, then fetches only the homepage, and only when the cache is older than 24 hours or you pass `--refresh`. A teammate at or above the threshold skips that read. The parsed directory listing is stored in `.cache/listing.json` next to this file. That file is not part of the repository, and it does not contain teammates. On a failed read it prints a stale cache if one exists and exits non-zero. It does not retry in a loop.

Set `REPO_URL` at the top of `rank.py` to this repository's public URL. That constant is the only copy. It is sent in the User-Agent and printed on directory results. Do not add teammate names, descriptions, or prompts to it.

## Tests

From the repository root:

```bash
python3 -m unittest discover -s skills/grok-bot-directory-router/tests -v
```

Tests use a saved fixture and do not touch the network.
