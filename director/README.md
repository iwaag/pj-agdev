# director

`director.py` is a deliberately small, one-question runner for creative asset
direction. It starts one headless `claude-sonnet-5` call for either:

- `compose`: turn `brief.md` plus one manifest entry into an agforge desire;
- `review`: inspect the one delivered file named by that manifest entry and
  return a lenient accepted/rejected verdict.

The backend's working directory is the direction workspace. The runner reads
only `brief.md` there and, from the game repository, the explicitly supplied
manifest plus the exact asset path declared by it. This is context placement,
not a security sandbox.

```sh
DIRECTOR_CLAUDE_CMD=/path/to/claude python3 director/director.py compose \
  --direction .local/asset-reconcile/othello-direction \
  --manifest .local/asset-reconcile/othello-web/assets/manifest.json \
  --request-id background
```

The command prints a JSON envelope containing the validated answer and any
cost/timing metadata returned by Claude Code.
