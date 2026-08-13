# Phase 1, step 1 — Python foundation

Done. `uv sync` and `uv run pytest` both succeed from `agdevworld/assistant/`.

## What was created

| File | Note |
|---|---|
| `assistant/pyproject.toml` | `agdevworld-assistant`, `requires-python >=3.11`, hatchling, `dev = ["pytest>=8.0"]` |
| `assistant/agdevworld_assistant/__init__.py` | flat package, no `src/` layer |
| `assistant/tests_py/test_foundation.py` | the one trivial test |
| `assistant/uv.lock` | committed, as in `agautolab/` |

`.gitignore` gained `__pycache__/`, `.venv/`, `.pytest_cache/`. The existing
`*.local` rule already covers the generated overlay, so nothing was added for it.

Decisions taken where the plan left them open:

- Location `agdevworld/assistant/`, as recommended — `assistant/Dockerfile`
  already does `COPY assistant/ ./assistant/`, so the Python tree arrives in the
  image with no Dockerfile change.
- Tests in `tests_py/` beside the `.mjs` `tests/`, with
  `[tool.pytest.ini_options] testpaths = ["tests_py"]` so `uv run pytest` needs
  no argument and never wanders into `node_modules`.
- `uv.lock` is tracked, matching `agautolab`.

## The phase-2 risk this retires

`pyagag` is already a dependency although nothing imports it yet, and the git
source resolves:

```
+ pyagag==0.1.0 (from git+https://github.com/iwaag/pyagag.git@7cf02a44)
```

Resolution inside the image is still unproven — that is step 4's business.

## Evidence

```
$ uv sync
Using CPython 3.14.2 interpreter
Resolved 8 packages in 515ms
Installed 7 packages in 13ms
$ uv run pytest -q
1 passed
```

Local CPython is 3.14.2, above the declared floor of 3.11; the floor is what the
Alpine image will have to satisfy in step 4.

Nothing outside `agdevworld/assistant/` and `.gitignore` was touched. The JS
server and `npm test` are untouched and still the live path.
