# TODO / Done

## TODO

- Give the autolab bot administer rights on the project channels it works in,
  so retiring a project does not need the Developer's realm-admin account.
  Zulip grants `can_administer_channel_group` to a channel's creator; the
  fourteen `pj-` channels had four different creators and one of them is a
  deactivated bot, leaving that group empty. Whoever opens a `pj-` channel
  should put the autolab bot in it. Then `project_archive` runs under the
  node's own credentials, and the natural next step — a `pj-` topic the
  autolab listener recognizes as "retire this project" — becomes possible.
  (Recorded 2026-08-17 from episodes/agautolab/archive_projects.)

- Separate the two consumption modes of cluster state from pj-clusterintent:
  snapshot use (state bundle + detail file, for handing state to AI/humans as
  one file) versus interactive use in agdevworld (visualization / conversational
  operations). For the interactive mode, prefer per-node on-demand queries
  (e.g. GraphQL) over ever-fatter bundles. If bundle files start growing to
  serve interactive needs, that is the signal to design the query path instead.
  (Recorded 2026-08-05 from pj-clusterintent fullstate_export discussion.)

- Resolve the SwarmUI access point from pj-clusterintent instead of a
  hand-set `.env` value (fits the `nctl relations` service-binding graph;
  would eliminate the swarmui-flow episode's problem.md #2 manual port
  probing). (Recorded 2026-08-06, scoped out of
  devdocs/ent-episodes/swarmui-flow/plan.md.)
- Fold the agforge bucket/policy/user creation into the declarative
  `minio-init` in `pj-clusterintent/devenv/nautobot/docker-compose.yml`,
  replacing the manual `mc` steps in agforge/README_DEV.md's MinIO-fallback
  agent instruction. (Recorded 2026-08-06, scoped out of
  devdocs/ent-episodes/swarmui-flow/plan.md.)

- Agent access point on agforge: put an agent behind the request-service
  seam (`POST /api/requests` stays the contract; the deterministic
  generate.sh backend becomes one tool among several). (Recorded 2026-08-06,
  scoped out of episodes/connect_world_and_forge/plan.md.)
- Artifact persistence: generated images currently live only behind
  presigned URLs that expire (60 min default); no catalogue, and the chat
  image bubble dies with the URL. Design storage/cataloguing when it hurts.
  (Recorded 2026-08-06, scoped out of episodes/connect_world_and_forge.)
- Voice-driven flow: ask for an image by voice, agdevworld's stated
  audio-in/out experience. (Recorded 2026-08-06, scoped out of
  episodes/connect_world_and_forge.)

## Done

- 2026-08-06 connect_world_and_forge: chat "draw a castle at sunset" in
  agdevworld → assistant emits generate_image action → agforge request
  service (intent-level HTTP API over generate.sh) → image bubble in the
  chat panel. See episodes/connect_world_and_forge/report[1-4].md.
