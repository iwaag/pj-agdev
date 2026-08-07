# asset_reconcile — Step 4 report

Date: 2026-08-08. Outcome: **verified**.

## Gates

Ran bare `node --test` in the delivered game checkout at `6ff9d87`:

- 12 tests passed, 0 failed, 0 skipped;
- the original 10 acceptance tests remained green;
- the manifest-presence test passed;
- the delivered branch decoded and validated
  `assets/bg/background.png` against the declared 1024×1024 PNG contract.

The director implementation's eight unit tests also passed independently.

## Live browser verification

The initial 1280×800 screenshot was mistakenly taken from a temporary server
on agstudio before the existing VM job target had pulled the delivery commit.
At that point `http://agautolab1.local:8080` still served `61c65d7`: its
manifest said `requested` and the background path returned HTTP 404. That
local screenshot did not prove live deployment.

After confirming the VM target was clean, it was fast-forwarded to `6ff9d87`.
The VM then passed the same 12/12 tests, served the PNG with HTTP 200 and
1,473,342 bytes, and returned a `delivered` manifest. A new 1280×800 browser
screenshot was captured from the VM's actual port 8080 through an SSH local
forward. The received image SHA-256 matched the committed asset:
`ea81829cbc0c2210d9deace6c52c6c4c7ec89206b9d64df3c89fb0f5a00d242b`.

Visual inspection confirmed that the candlelit medieval room fills the page,
the Othello board and status text remain readable over the dark translucent
panel, the initial four discs and legal-move hints are visible, and the New
game control is unobstructed. The screenshot was a temporary local
verification artifact and was not committed.

The VM job target and local delivery clone both remained clean and synchronized
with Gitea `main` after verification. The HTTP server did not require a
restart because it serves the updated files directly from the target checkout.
