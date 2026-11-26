# Extension plan: resource-specific booking and cancellation rules

Group 12. Written before implementation, against the working core at commit
`91903c4`. Changes made during implementation are recorded in the README
section "Changes from the extension plan", not by editing this file.

## 1. What the extension requires

Each resource gets a maximum duration per occurrence and a minimum
cancellation notice. Seed data must include:

| Resource | Max duration per occurrence | Min cancellation notice |
| --- | --- | --- |
| Meeting room | 2 hours | 24 hours |
| Projector | 8 hours | 1 hour |

- The duration limit applies to every occurrence (single bookings and each
  week of a series). Exactly the maximum is allowed.
- Cancellation is allowed at exactly the minimum notice.
- Series cancellation checks every future, uncancelled occurrence it would
  affect. If any one has too little notice, cancel none; otherwise cancel all
  of them. Past and ongoing occurrences are preserved, cancelled records are
  kept, and repeating a successful cancellation is harmless.
- No policy-management interface.

## 2. Affected requirements

| Core rule | Effect |
| --- | --- |
| C3 (max 8 hours) | Becomes per-resource. Stays 8 hours for the four existing resources |
| C7, C9 (cancel one booking strictly before start) | Adds a notice check after the existing "already started" check |
| C8 (series cancel skips started weeks, cancels the rest) | **Rule change:** if any affected future week lacks notice, cancel none |
| C10 (single and series share rules) | Preserved: both go through the same helpers |
| Seed data and `GET /resources` | Two new resources (IDs 5 and 6) |

## 3. Affected code, data and interfaces

| Area | Planned change |
| --- | --- |
| `booking/models.py` `Resource` | Add `max_duration_minutes: int = 480` and `min_cancel_notice_minutes: int = 0` |
| `booking/database.py` `initialize` | Seed Meeting room (120, 1440) and Projector (480, 60) |
| `booking/main.py` `validate_interval` | Take the resource's max duration instead of the fixed `MAX_DURATION` |
| `create_booking`, `create_series` | Pass the resource's limit into `validate_interval` |
| `cancel_booking` | After the start check, reject if `start - now` is less than the notice |
| `cancel_series` | Collect affected weeks (future, uncancelled), check notice on all first, then cancel all or none in one commit |
| `GET /resources` | Keep the response as `id`, `name`, `kind` (see decision D2) |
| Database files | Schema change: existing local databases need `python -m booking.database reset --yes` |

## 4. Dependencies

- Builds on T2's `validate_interval` and `find_conflict`, so single bookings
  and series automatically share the new duration rule.
- `cancel_series` (T5) must change from "skip and continue" to "check all,
  then cancel all or none".
- `test_resources.py` asserts exactly four resources; it must be updated
  because the extension explicitly changes the seed data.

## 5. Risks

| Risk | Mitigation |
| --- | --- |
| Breaking existing behaviour for the four original resources | Their defaults (8 hours, no extra notice) reproduce the core rules; all existing tests must pass, with only the seed-count assertions updated |
| Off-by-one at the boundaries | Explicit tests at exactly the max duration and exactly the notice, plus one second either side |
| Partial series cancellation | Check every affected week before changing any; one commit |
| Notice of 0 allowing cancellation at the start time | Keep the existing `start <= now` check first, so core C7 is unchanged |
| Old databases missing the new columns | Document the reset; tests always use fresh databases |

## 6. Decisions and alternatives

**D1. Where the policy lives.**
- Chosen: two columns on `Resource`, with defaults matching the core.
- Alternative A: a separate `ResourcePolicy` table. Cleaner separation, but an
  extra join everywhere for two numbers and no requirement for policy history.
- Alternative B: a hard-coded dictionary keyed by resource name. No schema
  change, but fragile (renaming a resource silently drops its policy) and not
  stored with the data.

**D2. Whether `GET /resources` exposes the policy.**
- Chosen: keep the response as `id`, `name`, `kind`, so existing clients and
  tests see the same shape. Policy is visible through the error messages.
- Alternative: add the two fields to the response. Useful to clients, but it
  changes a core contract the extension doesn't ask us to change.

**D3. Status code for too little notice.** 409, matching the core's
"Booking has already started" cancellation refusal. The requirements don't
specify a code.

**D4. Units.** Store minutes as integers, avoiding timedelta storage quirks
in SQLite.

## 7. Planned checks

| ID | Check | Expected |
| --- | --- | --- |
| E1 | Meeting room single booking of exactly 2h; 2h + 1s | 201; 422 |
| E2 | Meeting room series where each week is 2h + 1s | 422, nothing saved |
| E3 | Projector booking of exactly 8h; 8h + 1s | 201; 422 |
| E4 | Original resources still allow 8h, reject 8h + 1s | Unchanged |
| E5 | Cancel a Meeting room booking exactly 24h before start; 24h − 1s before | 200; 409, still active |
| E6 | Cancel a Projector booking exactly 1h before; 1h − 1s before | 200; 409 |
| E7 | Series cancel where the nearest future week has under 24h notice | 409, every week unchanged |
| E8 | Same series, cancel the later week individually | 200 (it meets notice) |
| E9 | Series cancel where all affected weeks have enough notice | All cancelled; past and ongoing weeks unchanged |
| E10 | Repeat a successful series cancel after time passes | 200, no changes, even if notice would now fail |
| E11 | Original resources: core cancel tests unchanged | Pass |
| E12 | Seed data includes both new resources with their policies; `init` stays repeatable | Pass |
| R | Full existing suite, `ruff check`, `ruff format --check`, `mypy booking` | All pass; any assertion changes listed and justified |

## 8. Work allocation

| Task | Owner | Reviewer |
| --- | --- | --- |
| This plan | Ravi | Team |
| Model, seed data, duration rule | Ravi | Jacob |
| Cancellation notice (single and series) | Ravi | Toneri |
| Tests E1 to E12 | Ravi | Sayeed |
| Recorded results, README sections, retrospective | Team | Team |
| Evidence index and ZIP | Team | Team |
