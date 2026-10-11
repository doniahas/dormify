# Allocation rules

What the automatic allocation may and may not do. The rules below are the ones encoded in `backend/allocation/solver.py` and normalised by `backend/api/domains/allocation/config.py`; the solver scenario suite (`api.tests.allocation`) and the controlled cases in `backend/canada_algorithm_tests/` pin them. Manual assignment, transfers and swaps performed by staff do not go through these gates: authorised staff may place a student by hand where the solver would not.

## Hard constraints

Hard constraints define a legal placement. They are always active, carry no weight and cannot be relaxed from the UI.

| Rule | Effect |
|---|---|
| Housing type and apartment category | A single male or female student is placed only in a single-type apartment of the matching category. |
| Building-level gender restriction | When a building carries a gender restriction (shared-facility buildings), every room in it is limited to that gender and the restriction overrides any conflicting apartment category. A restricted building that already holds a conflicting occupant is frozen for new automatic assignments until staff resolve it. |
| Exclusive household types | Couple, family and single-occupant-in-a-couple-layout applications occupy an entire apartment of the matching type; no other application shares it, and a mutual roommate request never groups two exclusive applications. One student record is one complete application. |
| Religious placement | Students who requested religious placement are placed only with compatible occupants; an existing religious occupant restricts who may join. For shared-facility apartments the restriction applies apartment-wide, because the rooms share a kitchen and common space. |
| Accepted dormitory type | A student is placed only within the dormitory type they were accepted into. Generic-priority students keep a long-standing bypass of this rule; students carrying the reserved-population marker never do. |
| Reserved apartments and the reserved building | Reserved inventory is usable only by the students it is reserved for. The reserved building inside one specific dormitory type is never consumed automatically by a student outside its eligible population; eligible students are preferred there by a soft reward but may legally be placed elsewhere in their dormitory type. |
| Existing occupants | Active assignments are counted as occupied capacity and are never modified by a later run. Unassigned students can be re-solved against the remaining inventory only. |
| Inactive housing | Inactive buildings, apartments and rooms are not candidates. |
| Accessibility cases | Students flagged for accessibility are excluded from the automatic solve and left to the assisted-allocation workbench. |
| Mutual roommate requests (when configured as hard) | Honoured only when both students requested each other; requests are reconciled across the different import-field generations so the same student is recognised regardless of how they were referenced. |

## Soft preferences

Soft preferences are weighted objective terms. Each run receives its own configuration; a preference can be disabled, and its weight is clamped to 0..10. Defaults:

| Key | Preference | Default weight |
|---|---|---|
| `sameReligion` | place students of the same religion together | 6 |
| `roommateMatch` | satisfy roommate requests (positive and negative) | 8 |
| `sectorMatching` | place students of the same sector together | 7 |
| `avoidYearMix_1_with_3_4` | avoid mixing first-year students with third- and fourth-year students | 4 |
| `avoidAtudaimWithHasmaha` | avoid mixing two specific programme populations | 4 |

The keys `sameGender`, `priorityFirst`, `roommatePositiveOnly` and `ReligiousTogether` are accepted in the same configuration object for compatibility but are always treated as hard: enabled, strict and weightless, whatever the request says.

## Search and results

- The operator chooses the maximum search time per run. The solver returns the best solution found within it and records whether it was proven optimal or is best-effort.
- The best solution so far is mirrored into the run row during the search; the preview endpoint reads that snapshot.
- Cancel discards the search; stop-and-save keeps the best feasible solution found so far.
- Shared-facility apartments are evaluated room by room for roommate and same-religion preferences, so a pairing is scored against the room it would actually occupy.
- Assignments of a completed run are written in one short transaction, tagged with the run, and read back from the database for the results page.
- Students who could not be placed are reported with a reason and appear in the assisted-allocation queue.
