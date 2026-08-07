# director

`director.py` is a deliberately small, one-question runner for creative asset
direction. It starts one headless `claude-sonnet-5` call for either:

- `compose`: turn `brief.md` plus one manifest entry into an agforge desire;
- `review`: inspect one explicit candidate (or, by default, the delivered file
  named by that manifest entry) and return a lenient accepted/rejected verdict.

The backend's working directory is the direction workspace. The runner reads
only `brief.md` there and the explicitly supplied manifest. Review candidates
are staged inside the direction workspace; after delivery, review can instead
read the exact asset path declared by the manifest. This is context placement,
not a security sandbox.

```sh
DIRECTOR_CLAUDE_CMD=/path/to/claude python3 director/director.py compose \
  --direction .local/asset-reconcile/othello-direction \
  --manifest .local/asset-reconcile/othello-web/assets/manifest.json \
  --request-id background
```

The command prints a JSON envelope containing the validated answer and any
cost/timing metadata returned by Claude Code.

`reconcile.py` drives the bounded delivery flow: compose, POST/poll agforge,
download into the direction workspace, mechanically decode and verify the
manifest format/dimensions, ask the director for a lenient review, and on
acceptance copy to the manifest path and flip only that entry to `delivered`.
It makes at most two generation attempts and never resizes or converts an
artifact to hide an agforge contract mismatch.

```sh
DIRECTOR_CLAUDE_CMD=/path/to/claude python3 director/reconcile.py \
  --direction .local/asset-reconcile/othello-direction \
  --manifest .local/asset-reconcile/othello-web/assets/manifest.json \
  --request-id background \
  --agforge-url http://localhost:8092
```
