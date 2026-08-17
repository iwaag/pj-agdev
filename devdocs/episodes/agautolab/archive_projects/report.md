# agautolab — archive_projects episode report

## Braindump

The Plane/Zulip agent system accumulated verification projects. `pj-` is the
project-channel prefix, and by 2026-08-17 there were fourteen of them. The
desire: archive the ones that had served their purpose.

## What a project actually is — 2026-08-17

`init_project` creates three surfaces (one Plane project, three Gitea
repositories, one local clone set), and a fourth — the `pj-<slug>` Zulip
channel — is created beside them by whoever starts the experiment. So a
project that is "done" keeps costing attention in four separate listings, and
retiring it by hand means four different APIs. That is the pain this episode
answers, and it is a recurring one: the count only grows.

Measured before the work:

| surface | count |
|---|---|
| Zulip `pj-` channels | 14 |
| Plane projects | 17 (14 verification + FreeForge, ClusterAdmin, Assetpipe1-class) |
| Gitea `autodev` repositories | 50 |
| local clone sets in `.local/projects/` | 12 |

Last-activity was useless as a liveness signal: an autolab sweep had posted to
every `pj-` channel that same morning (04:19–04:22), so every channel looked
equally fresh. The developer decided the set instead — all fourteen.

## What was built

`agautolab.project_archive`, the inverse of `project_init`. Four probes first,
each against a throwaway object that was deleted afterwards, because none of
these APIs were documented in this repo:

| surface | mechanism | verified |
|---|---|---|
| Zulip 12.2 | `DELETE streams/<id>` (archives, does not delete) | channel created + archived by a non-admin bot |
| Plane CE 1.4.1 | `POST .../projects/<id>/archive/` → 204 | archived row stays listed with `archived_at`; repeat call is a no-op |
| Gitea | `PATCH /repos/<org>/<repo>` `{"archived": true}` | repository stays readable |
| local | `rename` into `.local/projects-archived/<slug>` | — |

Nothing deletes. Plane keeps its issues, Gitea keeps the history readable,
Zulip keeps an archived channel's messages, and the clone set is moved rather
than removed because it is the only copy of whatever a run left uncommitted.
Each step reports `archived` / `already-archived` / `absent`, so a
half-archived project runs through again cleanly and the report says which
surfaces were already done.

`pyagag` gained `ZulipClient.archive_channel` (commit `ab166e1`); agautolab
picked it up in the lock and added the module (commit `9354cf6`).

### The principal problem

Archiving a Zulip channel needs the right to administer it, which Zulip grants
to the channel's creator and to organization administrators. The fourteen
channels had four different creators — Developer (8), Omni Agent (9), the now
deactivated Devworld Assistant (10, leaving `can_administer_channel_group`
empty), and Autolab Agstudio (11) — so **no bot could archive all of them**.
The Developer account is the only principal that could, being the realm
administrator.

`AUTOLAB_ZULIP_ENV` therefore overrides the node's own bot credentials. The
bulk run used the Developer credentials. This is worth fixing at the source
rather than at the archive end: if project channels were created with the
autolab bot in `can_administer_channel_group`, the agent could retire its own
projects without borrowing a human's account.

## Result — 2026-08-17

```sh
AUTOLAB_ZULIP_ENV=../.local/zulip/developer.env \
  uv run python -m agautolab.project_archive <slug> [...]
```

All fourteen archived, exit 0. Verified independently afterwards:

- Zulip: no `pj-` channel remains.
- Plane: 12 archived; 5 active projects remain.
- Gitea: 30 of 50 repositories archived.
- Local: 10 clone sets in `.local/projects-archived/`.

The counts differ per surface because the older channels never had the full
set — `members-20260813` and `phase1-subscribe-20260813` were channel-only,
and the pre-devlog projects have two repositories rather than three. The tool
reported those as `absent` rather than failing.

## Left behind

Three project-shaped leftovers have **no** `pj-` channel and were therefore
outside the requested set: `phase1-smoke-20260813`, `phase2omni`,
`three-choice-quiz` (Plane projects, Gitea repositories, and for the first two
a local clone set). They are archivable with the same command whenever the
developer wants them gone.

Also untouched: the standing `create-*` channels and `zz-allpublic-20260813`.

## Notes

- Deus Ex Machina: the Omni Agent built and ran the archive path for the
  autolab agent — handoff candidate. The natural next step is a `pj-` topic
  the autolab listener recognizes, so retiring a project becomes a request
  rather than a shell command.
- Backend: Claude Opus 5 (1M context), via the Omni Agent's own harness.
