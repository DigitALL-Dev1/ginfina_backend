# EWP Approval & Release

Module 4 reuses `ewp_document` and `ewp_document_revision`. The frontend is
`frontend/src/layouts/EWPApprovalReleaseLayout.jsx`.

All endpoints below use `/api/ewp/approval-release`. For the prototype pilot,
this module does not require a login token or enforce account-based approval
and release permissions. Other modules' authentication is unchanged.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/ewps` | Select an EWP. |
| GET | `/approvers` | Active users available for approver assignment. |
| GET | `/documents?ewp_id=...` | Reviewed revisions, saved decisions, and release history for that EWP. |
| GET | `/revisions/{revision_id}/package` | Exact approval package, package hash, approval, release, and current status. |
| PUT | `/revisions/{revision_id}/approver` | Assign with `{"approver_id": "user-id"}`. |
| POST | `/revisions/{revision_id}/approval` | Record a decision for the selected approver. |
| POST | `/revisions/{revision_id}/release` | Release with `{"comment": "Controlled issue"}`. |

Approval request:

```json
{
  "decision": "APPROVE",
  "comment": "Approved for controlled release.",
  "condition": null,
  "package_reviewed": true,
  "package_hash": "<package_hash returned by GET package>"
}
```

Decisions: `APPROVE`, `APPROVE_WITH_CONDITION`, `CHANGE_REQUIRED`, `REJECT`.
All except `APPROVE` require a comment. Conditional approval also requires a
condition. A stale package hash requires the user to refresh and review again.

## Lifecycle

- Approval requires the current `REVIEW_COMPLETED` revision, its uploaded file,
  at least one reviewer, acceptance from every reviewer, and no open comments.
- Successful approval records `APPROVED` on the approval and moves the revision
  and current document to `READY_FOR_RELEASE`.
- `CHANGE_REQUIRED` and `REJECT` move the revision to `CHANGE_REQUIRED` and
  `REJECTED`, respectively. Further engineering changes require a new revision.
- Release is a separate action available without signing in during the pilot.
  It verifies that the file and package still match the approved package and
  moves the revision and current document to `RELEASED`.
- Reviewed/approved/released review material is locked. Creating D04 updates
  the document's current pointer; D03, its comments, approval and release stay
  intact. Released-file downloads check the saved SHA-256 hash.

## Stored records

`ewp_document_approval`: document/revision/EWP IDs, assigned approver ID/name,
assigned-by ID and timestamp, decision, comment, condition, decision timestamp,
approval status, reviewed package and package hash.

`ewp_document_release`: document/revision/EWP IDs, exact revision number,
approval ID and decision details, release code, release actor ID/name,
release timestamp/comment, `RELEASED` status, frozen package and release hash.

The frozen package includes the EWP/deliverable/document references, revision,
file metadata/hash, responsible engineer, reviewers and decisions, comment
responses and closure, exact frozen SEB revision, selected release items and
their readiness/conditions/source references, and activity input confirmations.
Document file bytes remain in the existing revision upload location.

Each revision atomically stores its decision and release record. The two
collections are projections keyed by revision ID, so retries do not create
multiple releases. Package reads/retries repair projections after interrupted
multi-collection writes. This works with standalone MongoDB; no startup seeding
or collection initialization is added.

The current user directory supplies approver choices. Selecting an approver
does not verify the caller's identity in the pilot. New decisions and releases
record `actor_mode: PROTOTYPE_PILOT` and the actor ID `prototype-pilot` separately
from the selected approver. Lifecycle validation and revision locks still apply.

## Verification

From `backend`, run `python -B -m unittest discover -s tests -v`.
Tests use an isolated in-memory collection adapter and never access application
MongoDB. For browser coverage, start Vite on `127.0.0.1:5173` and run
`python -B tests/approval_release_ui_smoke.py`. That test routes API requests to
the isolated backend and exercises conditional approval, release and refresh.
