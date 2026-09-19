# Completion & Governance (Module 6)

Frontend: `/ginfina/ewp/completion-governance`.
API root: `/api/ewp/completion-governance`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/ewps` | Persisted EWP selector |
| GET | `/ewps/{ewp_id}/summary` | Current completion checks, blockers, obligations and governance history |
| POST | `/ewps/{ewp_id}/actions` | Record an outstanding action |
| POST | `/ewps/{ewp_id}/resolutions` | Close an obligation or formally accept a condition |
| POST | `/ewps/{ewp_id}/governance` | Verify the current summary |
| POST | `/ewps/{ewp_id}/submit` | Submit verified completion for closure review |
| POST | `/ewps/{ewp_id}/close` | Approve closure and persist an immutable snapshot |

Mutations require `version` from `summary.control.version`, `actor`, and a nonblank
`comment`. Governance additionally requires `summary_hash` from the latest summary.
Actions require `title`. Resolutions require `obligation_id`, `source_hash` and
`status` (`CLOSED`, or `ACCEPTED` for conditions only). A source change invalidates
its old resolution; no manual override exists for failed engineering checks.

## Gates and status

- Required engineering work must be `COMPLETED`; `READY_FOR_OUTPUT` is insufficient.
- Mandatory deliverables need released current document revisions. Deliverable
  preparation status is not used as a substitute for the controlled release.
- Current revision reviewers must have completed an accepting decision; all
  document review comments must be closed.
- Current document revisions must have their own approved release records.
  An older released revision does not satisfy a new draft revision.
- Every quantity register needs its current approved BOQ/EBOM with matching
  content and released source references.
- Every register's procurement handoff must be `COMPLETED`, with a reference
  to its current BOQ. `REFERENCED` or `SENT` is not sufficient for closure.
- Selected frozen SEB input links must still resolve to their released snapshot.
- SEB readiness conditions/blockers, document approval conditions and actions
  recorded in this module require explicit resolutions. Blockers/actions must
  close; conditions may be formally accepted with an accountable evidence note.

Work/deliverables are mandatory by default. Missing work, deliverables, documents,
quantity registers, procurement or frozen design basis block completion; missing
records never silently become 'not applicable'.

The live summary reports `BLOCKED` or `READY_FOR_CLOSURE`. Governance records the
source hash. Submission sets the completion record and EWP to `COMPLETION_REVIEW`.
Closure re-evaluates mandatory gates and the governance hash before atomically
storing `CLOSED` and the snapshot on the EWP. Changes after verification require
fresh governance verification and submission.

The existing pilot remains unauthenticated: actors are self-declared names,
recorded as `actor_mode = PROTOTYPE_PILOT`, not verified authorization identities.

## Storage and recovery

- `ewp_completion`: completion state, submission/approval/closure actors and dates.
- `ewp_completion_check`: most recently verified checklist, mandatory flags,
  statuses, counts and issue descriptions.
- `ewp_governance_check`: actor, evidence comment and timestamp for each event.
- `ewp_closure`: immutable checklist/obligation snapshot, source IDs, hash,
  governance summary hash, approver and closure timestamp.

The EWP's `completion_control` is the atomic source of truth; collections are
idempotent projections repaired on subsequent reads/retries. No startup seeding
or collection initialization was added. Closed summaries show the saved snapshot.
A retry after closure returns the original record rather than duplicating it.

A shared dependency on Module 1-5 routers rejects writes against closed EWPs,
including mutations addressed by activity, deliverable, document, reviewer,
comment, revision or register IDs. Read access remains available.

Version comparisons protect concurrent completion writes. Cross-collection
source reads are revalidated at each workflow action, but are not a MongoDB
multi-document transaction with all upstream writers.

## Validation

From `backend`: `python -B -m unittest discover -s tests -p "test_ewp*.py" -v`.
With frontend Vite on port 5173:
`python -B tests/completion_governance_ui_smoke.py`.
Both use isolated in-memory data; the browser intercepts API calls.
