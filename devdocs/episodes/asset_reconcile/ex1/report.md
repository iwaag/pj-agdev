# asset_reconcile ex1 — final report

Date: 2026-08-08. Outcome: **completed end to end**.

The agforge ↔ autolab integration survived the current remote-development
architecture without an autolab code change. One gateway mission created a
plan-phase job, reviewed its self-authored plan and seven gates, generated and
reviewed three assets during the approval window, let the coding agent commit
and implement the delivered bytes, converged, installed the audited revision,
and served it as a working three-button browser gallery.

## What ran

1. Nautobot/`nctl` reported `agautolab1` compute and node converged. The normal
   setup playbook completed with `ok=12 changed=0`, the gateway was healthy and
   idle, and Ansible proved node reachability to both agforge `:8092` and a
   fresh presigned MinIO `agstudio.local:9100` object.
2. The separate Gitea repositories were established: `gallery-direction`
   holds the brief, tools, and durable reviews; `gallery-web` was left empty
   for the coding agent.
3. Gateway run 3 used six mediator sessions. The coding job produced a
   technical-only three-entry 1024×1024 PNG manifest, a requirement-to-gate
   plan, and seven deterministic gates. The approved implement iteration
   committed the delivered assets and complete static app as `07085cc`.
4. The director/reconcile tools made one agforge attempt per image, accepted
   all three, copied exact bytes without conversion, and pushed complete
   evidence as direction revision `31a4240`.
5. Independent operator verification re-ran 7/7 gates (10/10 subtests), checked
   all PNG signatures/dimensions, confirmed no external references or
   direction material in the game repository, and byte-compared all eight
   served HTTP responses to `07085cc`. Chromium rendered the actual gateway
   endpoint; evidence is in [gallery-served.png](gallery-served.png).

## Costs and timing

| Layer | Calls/sessions | Turns | Measured duration | Cost |
|---|---:|---:|---:|---:|
| Gateway mediator | 6 sessions | 303 | 2,269 s | $7.3324366 |
| Coding agent | 3 iterations | 94 | 453.581 s | $2.0515236 |
| Director | 6 one-shot calls | 9 | 26.790 s | $0.4239135 |
| **Known LLM total** |  | **406** | not additive | **$9.8078737** |

The gateway duration includes time spent waiting on child work, so durations
must not be added as wall-clock time. Run 3 took roughly 39 minutes including
driver gaps. Agforge generation cost and timing are not exposed by its API and
are omitted rather than estimated.

The mediator overhead was much larger than coding/director spend. Much of it
came from repeatedly re-reading state across sessions and, in the final
session, reconstructing progress after NOTES lagged the durable job state.

## Agforge attempts

| Image | Attempts | Request ID | Result |
|---|---:|---|---|
| `gallery-image-1` | 1 | `4ee79387f40d4a56b7659c470e64cb4e` | valid 1024×1024 PNG, accepted |
| `gallery-image-2` | 1 | `d97cf30bcaa04d718c11865763e2c558` | valid 1024×1024 PNG, accepted |
| `gallery-image-3` | 1 | `c69770aa13214b36a55c7fbd457ca08f` | valid 1024×1024 PNG, accepted |

There were no rejected candidates, second attempts, timeouts, conversions, or
hidden producer-contract relaxations. The three creative results are distinct
and coherent with the brief: a candlelit vaulted corridor, a warm medieval
portrait, and a painterly village scene.

## Boundaries and evidence

The technical/creative split held. The coding repo contains only IDs, local
paths, PNG format, dimensions, and delivery status. Creative direction,
desires, verdicts, costs, and request IDs exist only in the direction repo.
The coding agent had no direction workspace; director calls ran from the
direction workspace with one manifest entry and one candidate.

Every successful compose/review envelope was persisted this time, closing the
parent episode's evidence gap. The coding-agent iteration diff proves the
worker—not the mediator—committed the three asset bytes and status flips. The
served-file hashes prove the deployed product is the audited revision, closing
the parent episode's wrong-serving-location gap.

## What broke and recovered

No product, agforge request, or mission failed. Recovered friction was:

- one Ansible probe launched from the wrong working directory;
- 13 coding-agent permission denials plus related mediator command-shape
  friction, all handled through allowed alternatives;
- NOTES narration lagging several sessions behind durable state, recovered by
  re-reading job/git/evidence truth;
- one operator zsh scalar-loop mistake during checksums.

Details and future mitigations are in [problem.md](problem.md).

## Future judgments

**Keep the awaiting-approval delivery window as the standard short-term
pattern.** It prevented the implement loop from idling, preserved coding-agent
ownership of commits, and all three assets arrived before approval without a
new autolab state. A real `awaiting_assets` state is not yet justified solely
by this successful three-image run. Add it when asset work needs independent
queueing, human review, concurrency, long pauses, or resumable per-asset
status; the NOTES lag shows why such durable visibility will eventually help.

**Keep one top-level user mission, but make asset reconcile a durable service
sub-boundary.** One user request remains the right experience and preserves
end-to-end accountability. Internally, however, the six mediator sessions and
$7.33 overhead show that ad hoc session-by-session orchestration is expensive.
The next evolution should expose a resumable reconcile operation with explicit
per-entry state and evidence, callable by the mediator during approval. It does
not need to become a second user-submitted mission.

Step evidence is in `report1.md` through `report5.md`; operational friction is
consolidated in `problem.md`.
