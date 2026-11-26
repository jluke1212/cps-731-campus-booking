# Retrospective

Group 12: Hin Ki Jacob Luke, Ravi Kumar, Toneri He, Sayeed Jalil.

## What worked

- **Reviews caught real defects.** On PR #2, testing the series cancel against
  Appendix A showed it returned 409 when any week had started; it was fixed with
  new tests before merging. On PR #4, Sayeed noticed V17 injected its failure
  before any booking rows were written, so it never tested what it claimed. Both
  would have shipped without a reviewer actually running or reading the tests.
- **Shared helpers made the extension small.** Because single bookings and series
  already went through `validate_interval`, the per-resource duration limit was
  one change, not two.
- **Testing persisted state, not just status codes.** Comparing the whole
  database before and after a rejected request is what proves "nothing was
  saved", and it caught the partial-series case.

## What caused difficulty

- **Direct pushes to `main` broke the build.** A commit pushed straight to `main`
  left stray text in `models.py`, so nothing imported and every test failed until
  it was fixed in the next PR.
- **Parallel edits to `main.py`.** Three tasks changed the same file, which caused
  a merge conflict on the cancel PR on deadline day.
- **Repository setup.** Our repo was a fork of the starter, so CI was disabled
  until the owner enabled it, and new pull requests defaulted to the instructor's
  public repo as the base.
- **Documentation left to the end.** Our working-core submission lost marks for
  missing design trade-offs and recorded check output, even though the code and
  tests were complete.
- **Deadline crunch.** Most merges happened on the final day, leaving little time
  for review.

## What we would change next time

- Protect `main` from day one: pull requests only, one approving review, green CI.
- Use a private repository that isn't a fork, and enable CI before writing code.
- Write the design note and check results alongside each PR rather than at the end.
- Split work by file where possible, and merge small PRs early to reduce conflicts.
- Set an internal deadline a day before the real one.
