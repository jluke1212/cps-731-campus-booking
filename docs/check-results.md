# Recorded check results

Group 12, extension and handoff. Commands are run from the repository root in a
Python 3.14 virtual environment created as in the README.

## 1. Final checks on the implementation branch

Run by Ravi Kumar on Windows 11, Python 3.14.7, on branch `ext-resource-rules`
after `python -m booking.database reset --yes`. Output is copied from the
terminal with the `=====` separator lines removed.

```text
PS C:\Users\Home\projects\group12> .venv\Scripts\python.exe -m pytest
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\Home\projects\group12
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.12.1, cov-7.1.0
collected 96 items

tests\test_bookings.py ..............                                    [ 14%]
tests\test_cancellation.py .....                                         [ 19%]
tests\test_resource_rules.py ................                            [ 36%]
tests\test_resources.py ......                                           [ 42%]
tests\test_series.py ........................................            [ 84%]
tests\test_series_cancel.py ...............                              [100%]

96 passed in 18.42s

PS C:\Users\Home\projects\group12> .venv\Scripts\python.exe -m ruff check .
All checks passed!
PS C:\Users\Home\projects\group12> .venv\Scripts\python.exe -m ruff format --check .
14 files already formatted
PS C:\Users\Home\projects\group12> .venv\Scripts\python.exe -m mypy booking
Success: no issues found in 7 source files
```

GitHub Actions CI on the implementation pull request: https://github.com/jluke1212/cps-731-campus-booking/actions/runs/45776125682 (run #21 on commit `c6f1fa7`: lint, format, types, tests and coverage all passed).

**What this shows:** all 80 working-core tests still pass alongside the 16 new
extension tests, and lint, formatting and type checks are clean.

## 2. Failing run during implementation (recorded failure)

After adding the policy columns and the two seeded resources, but before
updating the seed assertions, the existing resource tests failed:

```text
FAILED tests/test_resources.py::test_student_can_browse_seeded_resources - As...
FAILED tests/test_resources.py::test_documented_init_command_is_repeatable - ...
FAILED tests/test_resources.py::test_databases_are_isolated_and_startup_does_not_seed
FAILED tests/test_resources.py::test_reset_requires_confirmation_and_restores_samples
4 failed, 76 passed in 6.74s
```

Each failure was a resource count or list (4 expected, 6 found), as predicted
in section 4 of the extension plan. The extension explicitly adds the Meeting
room and Projector to the seed data, so we updated those assertions (4 to 6,
5 to 7, and the ID list to `[1, 2, 3, 4, 5, 6]`). No other existing test needed
changes. This run was recorded during implementation in a Linux environment
(Python 3.12) used for development, not on the Windows machine above.

## 3. Do the new tests catch real mistakes?

During implementation, each mistake below was introduced on purpose into a copy
of the code, and only `tests/test_resource_rules.py` was run (same Linux
development environment):

| Deliberate mistake | Result |
| --- | --- |
| Old series cancel behaviour (skip and continue instead of all-or-nothing on notice) | 1 failed, 15 passed |
| Notice boundary off by one (`<=` instead of `<`, refusing exactly 24 hours) | 2 failed, 14 passed |
| Ignoring the per-resource limit (fixed 8 hours everywhere) | 2 failed, 14 passed |
| Cancelling each week before checking all of them | 1 failed, 15 passed |

Every mistake was caught, so the tests check the required behaviour rather than
just running the code.

## 4. What the extension tests cover

| Check | Requirement | Test |
| --- | --- | --- |
| E1 | Meeting room: exactly 2h allowed, 2h + 1s refused, nothing saved | `test_meeting_room_duration_boundary` |
| E2 | Limit applies to every series week; over-limit series saves nothing | `test_meeting_room_series_over_limit_saves_nothing` |
| E3 | Projector: exactly 8h allowed (overnight), 8h + 1s refused | `test_projector_duration_boundary` |
| E4 | Resources 1 to 4 keep the core 8h rule and message | `test_original_resources_keep_core_duration` |
| E5 | Meeting room cancel at exactly 24h allowed; 24h − 1s refused and booking stays active | `test_meeting_room_cancel_at_notice_boundary` |
| E6 | Projector cancel at exactly 1h allowed; 1h − 1s refused | `test_projector_cancel_at_notice_boundary` |
| E7, E8 | Requirements example: series cancel refused when the next week is 12h away, database unchanged; later week cancelled individually | `test_series_cancel_refused_if_any_week_lacks_notice` |
| E9 | Enough notice: all affected weeks cancelled, past and ongoing preserved | `test_series_cancel_with_enough_notice`, `test_meeting_room_series_cancel_with_enough_notice` |
| E10 | Repeating successful single and series cancels is harmless after the notice window | `test_repeat_cancellations_stay_harmless` |
| E11 | Core checks (403 ownership, 409 already started) still come first; resources 1 to 4 cancel until start | `test_core_cancel_checks_run_before_notice`, `test_original_resources_cancel_until_start` |
| E12 | Seeded policies stored correctly; repeat `init` keeps them; `GET /resources` shape unchanged | `test_seeded_policies` |

Rejection tests compare the full stored database state before and after the
request, not just the status code. Time is controlled by rebuilding the app on
the same database file with a fixed clock.

## 5. What remains unchecked

- **Simultaneous requests:** all checks are sequential. Two requests at the same
  instant could both pass the availability check.
- **Daylight-saving transitions:** no test uses transition dates.
- **Upgrading an old database:** tests always use fresh databases; the README
  says to reset instead of migrating.
- **Policies other than the seeded ones:** only the six seeded resources are
  tested, since there's no interface to change policies.
