# grok-bot-directory-router

Suggests up to three listed bots from [grok-bot.directory](https://grok-bot.directory/) for a one-sentence task. It does not install a bot. You decide.

The behavior a Grok Bot should follow is in [SKILL.md](SKILL.md). Ranking is in `rank.py` (Python 3 standard library only).

## Run

From this folder:

```bash
python3 rank.py "draft a weekly meal plan"
```

| Flag | Effect |
|---|---|
| `--top N` | How many matches to print. Default 3. |
| `--json` | Machine-readable output. |
| `--refresh` | Read the directory again even if the local cache is still inside its 24 hour window. |

The script checks `robots.txt`, then fetches only the homepage, and only when the cache is older than 24 hours or you pass `--refresh`. It stores the parsed listing in `.cache/listing.json` next to this file. That file is not part of the repository. On a failed read it prints a stale cache if one exists and exits non-zero. It does not retry in a loop.

Set `REPO_URL` at the top of `rank.py` to this repository's public URL. That constant is the only copy. It is sent in the User-Agent and printed on every result.

## Tests

From the repository root:

```bash
python3 -m unittest discover -s skills/grok-bot-directory-router/tests -v
```

Tests use a saved fixture and do not touch the network.
