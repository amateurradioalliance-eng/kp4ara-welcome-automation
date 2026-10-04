# KP4ARA Welcome automation

Independent FCC ULS processor for Welcome to New Puerto Rico Hams.
License Academy stays on Firebase Hosting Spark. Its source/build/banks are absent here.

## Controlled phase: manual dry-run only

Actions > FCC cold dry-run > Run workflow, on main. No schedule, secrets, Firebase credentials,
Firebase writes, deploys, persistent caches or artifacts. Standard public ubuntu-latest runner only.
Python >=3.11 standard library; requirements.lock intentionally has no external dependencies.
Tests use synthetic fixtures only. Real FCC input stays in RUNNER_TEMP and is removed on exit.
Logs and job summary expose only counts, class totals, dates, hashes and resource metrics.
The candidate contains only callsign, FCC name, license_class, grant_date and allowed metadata.
The candidate is temporary, not committed or uploaded as an artifact.

Cold rebuild discovers snapshot/delta coverage from FCC embedded manifests, validates schema/counts/CRC,
uses initial NE / granted G / APGRT / individual PR active Amateur with available prior-history controls,
and includes direct initial General/Extra. Both boundaries of today PR minus 30 days through today are included.
Coverage must reach yesterday PR; stale, corrupt or incomplete input fails the job with no publication.
Do not force the record count to 39: the real rolling window changes over time.

## Publisher status

publisher.py is a tested transport-injected JSON-only publication core; no real HTTP/auth adapter exists
in this phase and the workflow never invokes publication. production-reference.json is the audited
pre-Welcome reference, publication_enabled=false. Initial Welcome publication needs separate approval.
Before future publication: compare expected live version plus protected-manifest hash, copy all live
hashes/config and change only /new-pr-hams.json; upload only that gzip; recheck live before release.
Firebase has no documented atomic live-version CAS: coordinated exclusive publishing remains required.

## Future weekly operation (not enabled)

Sunday 12:37 America/Puerto_Rico (16:37 UTC), plus manual recovery. No scheduled trigger currently exists.
No SQLite/FCC ZIP artifact or cache. Reconstruct from scratch each time; retain last good JSON in Hosting.
Review schedule every six weeks: GitHub may disable public schedules after 60 inactive days.
Record legitimate successful release references; do not create artificial keepalive commits.
Recovery: enable workflow if disabled, manual dry-run, then separately authorized publish.

No billing, Blaze, Functions, Run, Scheduler or paid runners. No Firebase credential has been created.
