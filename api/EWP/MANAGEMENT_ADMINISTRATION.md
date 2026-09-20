# Management & Administration (pilot)

Base route: `/api/ewp/management-administration`.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/projects` | Project selector with EWP counts |
| GET | `/ewps?project_id=...` | Project's EWPs |
| GET | `/users` | Active user IDs and display names |
| GET | `/ewps/{ewp_id}/overview` | Records, progress, attention items and recorded history |
| POST | `/ewps/{ewp_id}/records/{kind}` | Create management record |
| PATCH | `/ewps/{ewp_id}/records/{kind}/{record_id}` | Update record in selected EWP |
| PATCH | `/ewps/{ewp_id}/settings` | Discipline, planned dates and operational status |

Record `kind`: `team`, `milestones`, `issues`, `risks`, `actions`, `access`.
Writes require the overview's current `version`, a self-declared `actor`, and a
`comment`. Record writes additionally require `data` (full editable record).
Settings fields are at the top level. Every successful write returns the updated
overview. Stale writes return 409; refresh before retrying an interrupted save.

Example action creation:

```json
{
  "version": 0,
  "actor": "Engineering Manager",
  "comment": "Raised during coordination review",
  "data": {
    "title": "Verify roof loading",
    "owner": "Structural Lead",
    "due_date": "2026-10-15",
    "priority": "HIGH",
    "status": "OPEN"
  }
}
```

## Storage and controls

`ewp.management_control` is the atomic, versioned source for management records
and before/after audit events. Changes also update these reporting collections:

- `ewp_team_member`
- `ewp_milestone`
- `ewp_issue`
- `ewp_risk`
- `ewp_action`
- `ewp_access`
- `ewp_activity_log`

Records carry their ID, EWP ID, created/updated timestamps and management version.
Audit events contain actor, timestamp, action, comment, before/after and
`actor_mode: PROTOTYPE_PILOT`. Reporting writes are idempotent and repaired by
overview reads after an interrupted save. There is no startup initialization or
seed data. Disable assignments or close records instead of deleting history.

Only one active lead and one team/access record per user per EWP are allowed.
Assigning a managed lead updates `ewp.lead_engineer` and `lead_engineer_id`.
Actions always block closure while open; issues and risks do so when marked
blocking. Closing a control record requires resolution/evidence text. Completion
reads the canonical management obligations and cannot independently resolve them.
Management changes invalidate prior governance verification. Concurrent management
and completion commits check each other's version. Closed EWPs are read-only.
Only Completion & Governance can set `COMPLETION_REVIEW` / `CLOSED`; engineering
activity states are checked before administrative READY_FOR_OUTPUT / COMPLETED.

The existing unauthenticated pilot is retained: access assignments are recorded
administrative intent, not enforced authorization. Actor names are self-declared.

## Dashboard

Progress is derived from saved engineering work, deliverables, current document
reviews/releases, and procurement handoffs. Empty modules display no percentage;
overall progress averages modules with records, and does not imply closure readiness.
Attention includes overdue work, pending reviews/approvals and deliverables due
within 30 days. Management audit history is combined with existing recorded
document approval/release, quantity and governance events; it is not a claim of
full auditing of older modules that do not record events.

Run isolated tests from `backend`:
`python -B -m unittest discover -s tests -p test_ewp*.py -v`.
