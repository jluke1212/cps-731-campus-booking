# Design decisions and changes from our plans

Group 12. This file explains the main design decisions for the working core and
the extension, the alternatives we considered, and where the final code differs
from our plans. The extension plan itself is kept unchanged in
[`extension-plan.md`](extension-plan.md), committed before implementation.

## Responsibilities in the code

| Part | Responsibility |
| --- | --- |
| `booking/models.py` | Stored records: `User`, `Resource` (now with `max_duration_minutes` and `min_cancel_notice_minutes`), `Booking` (with optional `series_id`) and `Series` |
| `booking/database.py` | Table creation and seed data, including the Meeting room and Projector policies |
| `booking/schemas.py` | Request and response shapes; `ResourceRead` keeps `GET /resources` at `id`, `name`, `kind` |
| `booking/main.py` `validate_interval` | Time rules shared by single bookings and every week of a series, using the resource's maximum duration |
| `booking/main.py` `find_conflict` | Overlap check shared by single bookings and series |
| `booking/main.py` `check_cancel_notice` | Notice rule shared by single and series cancellation |
| Endpoint functions | Look up user, resource and records, call the helpers, then write in one commit |

## Key decisions

**1. Shared helpers instead of duplicated checks (core, T2).**
The first `create_series` copied the time and overlap checks from
`create_booking`. We moved them into `validate_interval` and `find_conflict` so
single and series bookings can't drift apart (C3, C4, C10). Alternative: keep two
copies, which avoids touching baseline code but means every rule change has to be
made twice. This decision paid off in the extension: the per-resource duration
limit only had to be added in one place.

**2. One real `Booking` row per week, linked by `series_id` (core).**
Alternatives were storing only the recurrence rule and generating weeks on read,
or having the client book each week separately. Storing real rows reuses the
existing conflict, read and cancel logic; the client-side approach would break
all-or-nothing because each booking would commit on its own.

**3. All-or-nothing through "check everything, then one commit" (core and extension).**
Series creation validates every week before adding anything to the session, then
commits once. The extension applies the same pattern to series cancellation:
check notice on every affected week first, then cancel all of them in one commit.
Test V17 forces a failure after booking rows are flushed and confirms nothing is
saved.

**4. Policy as two columns on `Resource` (extension).**
Alternatives: a separate `ResourcePolicy` table (cleaner separation, but an extra
join for two numbers and no need for policy history), or a dictionary keyed by
resource name (no schema change, but renaming a resource would silently lose its
policy). Defaults of 480 minutes and 0 notice reproduce the core rules for
resources 1 to 4, so core behaviour is unchanged for them.

**5. Keep `GET /resources` unchanged (extension).**
Adding the policy fields to the response would help clients but changes a core
contract that the extension doesn't ask us to change. A `ResourceRead` response
model keeps the starter's shape.

**6. 409 for too little notice (extension).**
The requirements don't specify a status. 409 matches the core's existing
cancellation refusal ("Booking has already started"). Ownership (403) and
"already started" (409) are checked first, so the order of core errors is kept.

**7. Duration messages in words (extension).**
The core message is "Duration must be at most eight hours". To keep it identical
for 8-hour resources, messages are built from the limit in words ("two hours"
for the Meeting room) rather than a new numeric format.

## Changes from the change plan (working core)

| Planned | What happened | Why |
| --- | --- | --- |
| T2 helpers merged before T3 creation | `create_series` was already on `main` with duplicated checks when T2 was ready, so T2 also switched it to the helpers (PR #1) | Work happened in parallel; refactoring both at once avoided a second change |
| One test file `tests/test_series.py` | Split into `test_series.py` (creation) and `test_series_cancel.py` (reads and cancellation) | The two halves were written on different branches |
| V17 injects failure with a monkeypatch on `commit()` | Uses an SQLAlchemy `after_flush` listener that fails on the flush writing `Booking` rows | Sayeed's review on PR #4 showed the first version failed on the earlier `Series` flush and never reached the bookings |
| Series cancel skips started weeks | First implementation returned 409 if any week had started; fixed during review on PR #2 | It didn't match C8 or Appendix A |

## Changes from the extension plan

| Planned | What happened | Why |
| --- | --- | --- |
| Error messages not specified | Added `describe_hours` so messages read "two hours", "eight hours", "twenty-four hours" | Keeps the core 8-hour message unchanged |
| Notice check inside each cancel endpoint | Shared `check_cancel_notice` helper used by both | Same reasoning as decision 1 |
| Checks E1 to E12 | Implemented as 16 test cases: E4 covers all four original resources, E9 adds a Meeting room case, E11 adds a core-resource case | Wider boundary coverage for little extra cost |
| `test_resources.py` seed assertions updated | Done as planned (4 to 6 resources); see `check-results.md` for the failing run before the update | The extension explicitly changes the seed data |

Otherwise the implementation follows the plan's affected-code list.
