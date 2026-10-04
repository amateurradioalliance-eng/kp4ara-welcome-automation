# KP4ARA Welcome weekly automation

Independent automation for **Welcome to New Puerto Rico Hams**. License Academy remains on Firebase Hosting Spark (`kp4ara-license-academy`). This repository contains neither Academy source/build nor question banks.

## Active workflow

`.github/workflows/welcome-json-only-manual.yml` — **Welcome weekly JSON-only update**.

Sunday **12:37 PM America/Puerto_Rico**, equivalent to **16:37 UTC** throughout the year: `37 16 * * 0`. `workflow_dispatch` remains available. GitHub schedules run from the default branch and can be delayed; this is an expected trigger time, not a delivery SLA.

Standard `ubuntu-latest`, public repository only; `contents: read`; concurrency group `kp4ara-hosting-publication`, `cancel-in-progress: false`. No larger runner, cache, artifact, persistent private storage, or keepalive commit.

## Processing and privacy

Every run reconstructs from scratch in private `RUNNER_TEMP`: discover FCC full snapshots/deltas by real embedded coverage; validate ZIP, CRC, schema and continuity; apply the validated initial NE / granted G / APGRT / individual / PR state / active Amateur / prior-history rules. Direct initial General or Extra is permitted. Exclude noninitial operations, clubs/trustees and disallowed prior/vanity cases. Both endpoints of the rolling PR date window `today-30 days` through `today` are inclusive.

Policy **fcc-business-day-noon-pr-v1** remains unchanged. No missing overdue business day is accepted; maximum absolute coverage age is four calendar days. Weekend/holiday handling uses actual processed coverage, never invented dates. Corrupt, incomplete, stale or failed FCC input aborts before Hosting writes and preserves the last good live JSON. Source coverage and last-update metadata remain factual. Private ZIP/SQLite/log scratch is erased even when processing fails.

Public JSON permits only `callsign`, FCC `name`, `license_class`, `grant_date` per person and approved general metadata. Never upload FRN/USI, contacts, addresses, application numbers, ZIP, SQLite, credentials, private backups or temporary input. Logs expose aggregate counts/dates/hashes/resource metrics only. The JSON candidate is temporary, not an artifact or repository commit.

## Safe advancing reference

`production-reference.json` records the initially approved version **adcfcc2c9dae26fe** and immutable protected fingerprint **e467e94874729e83b93e43f0fe7ab4e89a0de909623f68c7b247649c3133387a**. That fingerprint covers the exact 30 non-JSON manifest entries plus Hosting configuration. The version field is an initial audit anchor, not a permanent required live version.

At each run the publisher reads the current live release and verifies exactly 31 paths and that fixed fingerprint. This validated current live version becomes the operational baseline for this run. A successful JSON-only release advances the operational reference in Hosting itself; its version is recorded in the Action summary and becomes the next run's baseline only if the protected fingerprint remains identical. No mutable GitHub reference, write-enabled GitHub token, cache, artifact or artificial commit is required. Manual changes to Academy/configuration are never automatically adopted: fingerprint mismatch aborts and requires Emilio's explicit review.

Before creating a version and immediately before activating a release, reread live and compare the complete baseline snapshot. Concurrent change aborts. Firebase has no documented atomic live compare-and-swap; anyone publishing manually must coordinate through this same concurrency group or pause the workflow. A very small check-to-release race remains an API limitation.

Byte-identical candidate/live JSON yields **NO-OP PASS**, zero versions/releases/writes. A real valid difference reuses all 30 protected hashes and exact live configuration, changes only `/new-pr-hams.json`, rejects any other requested upload, validates the prepared version, then activates the release. No React build or full `firebase deploy` is performed. Metadata timestamps can legitimately make JSON bytes differ even when the operator list is unchanged.

After publication verify 31 manifest entries, all 30 protected hashes/configuration, public SHA-256 bytes of all 30 resources, and exact public candidate JSON bytes. Unexpected verification failure rolls back to this run's baseline when live is still the release created by this run; never overwrite a concurrent third-party release.

## Identity and $0 conditions

Existing identity only: `kp4ara-welcome-publisher@kp4ara-license-academy.iam.gserviceaccount.com`.
Existing Secret only: `FIREBASE_HOSTING_SERVICE_ACCOUNT_JSON`, exposed solely to the two authentication/Hosting steps. It is parsed in memory, never written to disk or printed. No new credentials or IAM changes.

Public standard runners are free: https://docs.github.com/en/actions/concepts/billing-and-usage . Repository-private jobs are skipped. No artifacts/cache are uploaded. Firebase must remain **Spark with billing disabled**, with no paid Google services.

Billing remains the explicitly accepted **external administrative precondition**. The dedicated operational role has no Cloud Billing read permission and cannot independently detect a future administrator linking billing. Before any plan, billing, visibility, runner or service change, disable this workflow and obtain Emilio's review; do not resume unless the $0 conditions are audited. This workflow cannot enable billing, change IAM or provision APIs/services. Do not interpret a passing Hosting read as a billing audit. The initial administrative audit confirmed billing disabled on 2026-10-04.

## Failure and recovery

FCC/validation/concurrency failures preserve the previous live data. Check the failed Action and the visible stale/update status; never weaken freshness or privacy guards to recover. Actions > **Welcome weekly JSON-only update** > **Run workflow** on `main` retries through the same tests, validations and publication protections. PASS or NO-OP PASS is required.

GitHub may disable public scheduled workflows after **60 days without repository activity**: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule . Successful workflow runs should not be assumed to prevent this policy. No fake activity/keepalive commits are implemented.

Review Actions periodically (suggested every six weeks):

1. Open the workflow and check that it is enabled and recent Sunday runs exist.
2. If disabled by GitHub, click **Enable workflow** (or the equivalent enable action in its menu).
3. Run **Run workflow** manually on `main` before relying on the schedule again.
4. Verify all tests and end-to-end PASS/NO-OP PASS, protected hashes/configuration and freshness.
5. Confirm the next Sunday run appears; if absent, inspect the enabled state/default branch and retry manually.

GitHub failure notifications go to the responsible account according to its existing notification settings; this automation does not change notification preferences. Recovery uses no paid service.
