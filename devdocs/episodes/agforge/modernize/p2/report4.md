# Step 4 — result delivery

## What was built

The `deliver_result` seam from Step 3 became the real sequence inside
`handle_runcreate` (`agforge/src/agforge/runcreate_topic.py`), each part its
own named `step`:

- **packaging** — `result_files()` scans `result/` recursively. Empty ⇒ the
  delivery is the generator's answer text ("a pure-text answer is a
  legitimate outcome", per the plan — `result/` non-empty is not the success
  signal; success is the run exiting zero, which `run_generator` already
  enforces by raising). Non-empty ⇒ `zip_result()` writes `result.zip` at
  the **workspace root** via `shutil.make_archive` — outside `result/`, so
  the archive can never contain itself — and `upload_result()` presigns it
  with the default 60-minute TTL (the "temporary" in "temporary download
  URL").
- **origin delivery** — `deliver_to_origin()` posts the delivery to the
  channel/topic from `Work.origin()` (the p1 `external_id`). Three shapes,
  none fatal: delivered; no origin recorded (hand-made Work) ⇒ the delivery
  goes into the runcreate summary instead; origin post raised ⇒ the error and
  the delivery both go into the summary. The summary post survives
  everything.
- **plane write-back** — Step 2's `report_work(project_id, issue_id, answer,
  True)`: the generator's answer becomes the issue comment (deliberately not
  the presigned URL — it expires and does not belong in a permanent record),
  and the Work moves to `completed` so it cannot be re-selected.

`generate.upload_and_presign` was generalized as the plan directed: the
hardcoded png/jpeg pair became a `CONTENT_TYPES` map (`.zip` ⇒
`application/zip`, unknown ⇒ `application/octet-stream`), and non-image
uploads land under a `files/` key prefix instead of `images/`. Its
`sys.exit` convention is right for the CLI and wrong inside a listener —
`upload_result` converts `SystemExit` into `ListenerError` so the
failed-during discipline still holds.

## Verification

Stub tests (`tests/test_runcreate_topic.py`, now also faking `report_work`
and `upload_result`):

- empty `result/` → the answer text is posted to `FreeForge/create-x`, no
  upload happens, Plane fake records `(comment=answer, success=True)`
- non-empty → a real `result.zip` is built, `zipfile` confirms it contains
  exactly the result files, and the URL is posted to the origin topic
- a re-trigger's second zip still contains only the result files (the
  self-containment guard, exercised twice over the same workspace)
- a Work without origin keeps the delivery in the runcreate summary
- an origin post that raises still reports to Plane and still posts the
  summary, naming the failed delivery

```
126 passed in 3.95s
```

Live: a scratch `result/` was zipped, uploaded through the generalized
`upload_and_presign` (5-minute TTL), downloaded back through the presigned
URL, and unzipped intact — the `application/zip` path works against the real
MinIO.

## Deviations from the plan

None. (The plan offered `transform.py`'s reuse pattern as a hint; the direct
`CONTENT_TYPES` generalization made it unnecessary.)
