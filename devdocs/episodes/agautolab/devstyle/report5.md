# Step 5 report — acceptance

Date: 2026-08-08.

## Environment and regression tests

Before using the local mediator environment, `nctl status --json` reported
`ok: true`: Nautobot was reachable and authenticated, and both the intent
catalog and intent GraphQL endpoint were available. The acceptance runs used
isolated temporary checkouts and did not modify the existing mediator state,
gateway service, or cluster desired state.

`uv run pytest -q` in agautolab passed all 41 tests.

## Dry read-through

The first fresh-session probe selected Instant Ramen and recorded its reason,
but read both style specifications before choosing. That failed the folder
isolation criterion and exposed a real ambiguity: the common README had no
selection hints, so comparison required opening both specifications.

The README now gives one-line, non-binding fit hints and says to choose before
opening either `STYLE.md` (agautolab commit `80fc61d`). A second completely
fresh mediator session then completed in 6 turns, 20.468 seconds, and
$0.1544796. Its NOTES and session result recorded:

- `STYLE: instant-ramen` with a one-line reason;
- `styles/README.md` and `styles/instant-ramen/STYLE.md` as the only
  style-related files read;
- explicit confirmation that `styles/slow-brew/STYLE.md` was not opened;
- the required three-line hindsight report.

This satisfies selection, durable recording, and selected-folder-only loading
for a mission that named no style.

## Small real mission

A separate fresh checkout received a small, style-unspecified mission: build
an offline browser gallery with three local SVGs and three labeled controls
that switch the featured image. The mediator chose Instant Ramen, placed six
smoke gates directly in `job.yaml`, and ran `autolab run-once` in the
foreground.

The mission completed in one mediator session and one coding iteration:

| measure | devstyle run | ex1 baseline |
|---|---:|---:|
| mediator sessions | 1 | 6 |
| mediator turns | 23 | 303 |
| coding-agent turns | 27 | 94 |
| elapsed mission time | 219.966 s | about 2,336 s |
| mediator cost | $0.6064716 | $7.3324366 |
| coding-agent cost | $0.5260427 | $2.0515236 |
| known total LLM cost | $1.1325143 | $9.8078737 |

This is an 83.3% session reduction, an 88.5% known-cost reduction, and about
a 90.6% elapsed-time reduction. It is a scale comparison rather than a strict
same-work benchmark: this acceptance used locally authored SVGs and therefore
did not invoke the baseline's director or agforge asset pipeline.

The job reached `converged` at iteration 1 with all six gates passing. The
delivered repository contained one HTML file and three SVGs, no package
manifest, and no HTTP(S) references. An independent fresh HTTP probe returned
200 for the HTML and all three SVGs. Manual source inspection confirmed three
labeled radio controls point to distinct local images and the change handler
assigns the selected value to the featured image's `src`.

## Hindsight

- Style chosen: Instant Ramen
- Why: the acceptance product was a tiny, reversible, dependency-free offline
  app with no shared contracts or infrastructure.
- Was it right in hindsight: yes; one lightweight iteration and six smoke
  gates delivered and verified the mission without a plan/review round trip.

