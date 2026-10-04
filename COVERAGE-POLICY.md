# FCC coverage policy v1

## Evidence and limits

FCC's ULS public-access guide (updated 2014) documents complete exports early Sunday,
daily exports early Tuesday-Saturday, containing the preceding day's transactions:
https://wireless.fcc.gov/uls/documentation/pa_intro24.pdf

FCC's Amateur-specific notice documents nightly business-day processing, with weekend
and holiday applications processed on the next business day:
https://docs.fcc.gov/public/attachments/DA-00-270A1.pdf

These are primary sources, but historic descriptions, not a current guaranteed SLA.
Actual validated 2026-09/10 Amateur manifests include Sunday and Monday daily exports,
generation at 04:00, 08:00 and 09:00 Eastern, and application/license snapshots at
different times. Never substitute the historic schedule for actual discovery/ingestion.
Public FCC download pages returned HTTP 403 in this investigation; raw data access works.

National holidays and weekend observance come from OPM:
https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/

There is no verified FCC guarantee here about maximum normal delay or automatic exports
on holidays. Absence of a scheduled export does not prove there were zero transactions.

## Deterministic conservative operational rule

1. Evaluate current date/time in UTC-4 Puerto Rico, independent of runner timezone/DST.
2. For each earlier national federal business day, define its availability deadline as
   12:00 Puerto Rico on the NEXT CALENDAR DAY. This bounded margin is OUR policy,
   not a claim FCC guarantees this hour.
3. Require coverage at least the latest business day whose deadline has passed.
   Permit ZERO missed overdue business days. No extra whole business day of grace.
4. Also abort if actual closed-day coverage is older than FOUR calendar days, future,
   unparseable, corrupt, missing either source, or otherwise invalid.
5. National OPM holidays only; Saturday holidays observed Friday, Sunday holidays Monday.
   New Year's observance crossing Dec/Jan is included. Calendar supported 2026-2030.
   Inauguration-local days, exceptional executive closures, shutdowns and extended outages
   NEVER automatically extend tolerance; abort and review with Emilio.
6. Always ingest ALL available valid exports, including weekend/holiday exports. No change
   to ZIP schema/CRC/count validation, delta replay protection or contiguous chain rules.
   A gap requires a full reconciliation, not pretending missing days had no changes.

Sunday after an ordinary Friday requires Friday (age two), including 2026-10-04 ->
2026-10-02. Sunday after an observed Friday holiday requires Thursday (age three).
Monday ordinarily still requires Friday. Tuesday after a Monday holiday may require
Friday (age four); an older date aborts. Before noon, an export not yet due may be
temporarily unavailable without stale; the absolute four-day cap still applies.
The long-closure cap can intentionally abort even if a calendar deadline has not passed.
After noon, missing the required business day is stale, regardless of an FCC outage notice.

## Honest metadata

source_through_date = min(actual application coverage, actual license coverage), derived
from validated FCC manifests as closed previous creation date. It is NEVER changed to
the expected business day or the last observed grant date. The business-day threshold is
an acceptance floor, not a statement that nonbusiness days were fully covered.

last_updated = time the complete valid batch is accepted, not time of a failed attempt
or a newly observed HTTP header. Rejected rebuilds preserve the accepted base/pointer and
last_updated. With no accepted base, reject without manufacturing a timestamp/feed.
generated_at = when the candidate or failure fallback is computed.
stale = failed attempt OR actual coverage outside this policy. False means current relative
to the documented policy, not coverage through today. Source date remains visible.

The rolling grant window always remains [today PR - 30 calendar days, today PR], inclusive.
It is never anchored to source_through_date, a business calendar or the weekly run day.
Fallback candidates recalculate expiration but stay stale; the future publisher rejects
them and preserves the last valid live JSON. Website stale/expiry presentation remains
part of a separately authorized production integration, not changed in this dry-run phase.

## Controlled execution

Manual workflow_dispatch only; no Firebase identity, secrets, writes or deployment.
Synthetic tests cover weekends, national/observed holidays, deadline, bounded delay,
genuine stale, calendar rollover, future coverage, 30-day window and transactional rollback.
Do not relax this rule again if the real dry-run fails; report the actual reason.
