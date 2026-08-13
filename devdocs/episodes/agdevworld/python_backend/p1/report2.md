# Phase 1, step 2 — `tool-service.mjs` ported to Python

Done. `agdevworld_assistant/tool_service.py` (stdlib only) reproduces the four
tools, and `uv run pytest` is 17 green. The `.mjs` service is still the one the
harnesses launch; repointing is step 3.

## Equality with the JS catalog, checked rather than assumed

The `tools/list` reply of the two services was diffed as parsed JSON:

```sh
printf '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n' \
  | python3 assistant/agdevworld_assistant/tool_service.py > py.json
printf '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n' \
  | node assistant/tool-service.mjs > js.json
# → identical
```

Names, descriptions, input schemas and order are the same object, so neither the
model's reading of them nor `assistant/GUIDE.md` changes.

`initialize` returns `protocolVersion 2025-03-26` and
`serverInfo.name agdevworld-tools`, unchanged.

## The traps, and what was done about each

| Trap | Resolution |
|---|---|
| `urllib` raises on 4xx/5xx, `fetch()` does not | `HTTPError` is caught and read as an ordinary response; only `URLError`/socket failures become `isError`. Covered by `test_fetch_passes_a_404_through_as_a_normal_response` |
| binary bodies | `decode("utf-8", errors="replace")`, matching `TextDecoder` |
| `//example.com/x` | both guards kept — the literal `//` prefix check and the post-`urljoin` origin comparison |
| notifications | messages with no `id` are skipped silently; unknown methods give `-32601` |
| framing | one JSON object per line, `flush()` after every write |
| import form | no package-relative imports, so `python3 …/tool_service.py` and `python3 -m agdevworld_assistant.tool_service` both work — step 3 needs the file form |

One divergence was found that the plan did not list, and it mattered:

- **`urllib` stamps `content-type: application/x-www-form-urlencoded` on any
  non-`None` body.** A `POST` with no `body` argument would therefore have grown
  a content type the JS never sends, since `fetch()` only sets one when a body
  was supplied. Sending `data=None` with an explicit `content-length: 0` instead
  keeps the header absent. The test asserts the server-observed content type in
  both directions.

JavaScript's argument coercion (`String(x ?? '')`, `Number(x)`) is reproduced by
small `_as_text` / `_as_number` helpers, so `wait` with `"nope"`, `-3` or `120`
answers exactly as before, the `"(N was requested)"` suffix included.

## Tests

`tests_py/test_tool_service.py`, 17 cases. The `.mjs` test's four are all there —
catalog, `//` refusal, a fetch returning status/content-type/body, and the
end-to-end stdio exchange that ends in a written actions line. The stub is a real
`http.server` on `127.0.0.1:0` rather than a monkeypatched `fetch`, so the wire
behaviour (request method, sent headers, status) is what gets asserted.

Added beyond the port: the 404 passthrough, the 1 MB clip, the content-type rule
above, a refused method, a transport failure, the `wait` clamp, the missing
action channel, an unknown view, an empty `show_image` URL, an unknown tool, and
`ping` plus a silent notification inside the stdio exchange.

## Evidence

```
$ uv run pytest -q
17 passed in 2.65s

$ npm test
ℹ pass 48   ℹ fail 0        # the JS side is untouched and still green

$ printf … initialize, tools/list … | python3 assistant/agdevworld_assistant/tool_service.py
{'name': 'agdevworld-tools', 'version': '1.0.0'}
['fetch', 'wait', 'switch_view', 'show_image']
```

Prohibitions held: stdlib only, stdout carries JSON-RPC lines and nothing else,
no credentials or local absolute paths in the committed files, `agents.toml`
untouched, and no fallback path exists — the Python service does not know the
`.mjs` one exists.
