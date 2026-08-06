# TODO / Done

## TODO

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

## Done
