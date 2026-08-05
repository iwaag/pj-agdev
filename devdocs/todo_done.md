# TODO / Done

## TODO

- Separate the two consumption modes of cluster state from pj-clusterintent:
  snapshot use (state bundle + detail file, for handing state to AI/humans as
  one file) versus interactive use in agdevworld (visualization / conversational
  operations). For the interactive mode, prefer per-node on-demand queries
  (e.g. GraphQL) over ever-fatter bundles. If bundle files start growing to
  serve interactive needs, that is the signal to design the query path instead.
  (Recorded 2026-08-05 from pj-clusterintent fullstate_export discussion.)

## Done
