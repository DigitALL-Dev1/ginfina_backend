# Module 5 — Quantities & Procurement

Pilot API prefix: `/api/ewp/quantities-procurement`. No sign-in is required.
Actor names are entered by the operator and recorded as `PROTOTYPE_PILOT`.
No collections, sample records, or indexes are initialized at startup.

## Workflow

Select EWP → released document revisions → create QTO → add quantities →
validate → generate BOQ or EBOM → review → approve → PROCUREMENT_READY →
record procurement reference → track reported status.

Only revisions with `status = RELEASED` and an immutable release record are
eligible. Historical releases remain valid sources. A newer release never
silently replaces a quantity's selected source.

BOQ and EBOM share `ewp_boq`, distinguished by `type: BOQ | EBOM`. Generated
sets contain quantity snapshots with their own `R01`, `R02`, etc. within a QTO.
Review/approval changes return the QTO to draft; the previous generated snapshot
is retained and a subsequent generation creates a new version. Approved sets
cannot be edited. Create another QTO for later engineering changes.

## Collections

- `ewp_quantity_register`: EWP/project, name, workflow status, version counter,
  canonical quantity items, validation, generated sets, handoff, activity history.
- `ewp_quantity_item`: each quantity, unit, specification, description, source
  sheet/reference and derivation notes. Removed draft items retain `REMOVED` status.
- `ewp_boq`: BOQ/EBOM type, version, content hash, validator, reviewer and approver
  decisions/comments, timestamps, and workflow status.
- `ewp_boq_item`: immutable quantity snapshot for each generated BOQ/EBOM version.
- `ewp_procurement_handoff`: approved set ID/hash, item IDs, engineering release
  IDs, external system/reference/URL, tracking status, actor, note and timestamps.

Every quantity source stores exact document/revision/release IDs, document and
release hashes, deliverable reference, and the original frozen SEB basis.

The register is the atomic source of truth. Other collections are projections
keyed by stable IDs and protected by register versions. Reads repair projections
after interrupted writes. All updates require the returned `version` to reject
stale concurrent edits. This works with standalone MongoDB.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/ewps` | Available EWPs |
| GET | `/released-outputs?ewp_id=...` | Exact released engineering sources |
| GET | `/registers?ewp_id=...` | Saved QTO registers |
| POST | `/registers` | Create using `ewp_id`, `name` |
| GET | `/registers/{id}` | Full saved workflow |
| POST | `/registers/{id}/items` | Add quantity |
| PUT | `/registers/{id}/items/{item_id}` | Edit a draft quantity |
| DELETE | `/registers/{id}/items/{item_id}` | Remove draft quantity; JSON body contains `version` |
| POST | `/registers/{id}/validate` | Record engineering validation |
| POST | `/registers/{id}/reopen` | Return validated QTO to draft |
| POST | `/registers/{id}/generate` | Generate `type: BOQ | EBOM` |
| POST | `/registers/{id}/review` | `decision: ACCEPT | CHANGE_REQUIRED` |
| POST | `/registers/{id}/approve` | `decision: APPROVE | CHANGE_REQUIRED | REJECT` |
| POST | `/registers/{id}/procurement-ready` | Mark approved quantities ready |
| POST | `/registers/{id}/handoff` | Record external procurement reference |
| PATCH | `/registers/{id}/handoff` | Record reported procurement status |

Quantity write example:

```json
{
  "version": 1,
  "item": "DC Cable 6 mm²",
  "description": "PV DC cable",
  "specification": "1.5 kV DC",
  "quantity": 4200,
  "unit": "m",
  "source_revision_id": "<released-document-revision-id>",
  "source_reference": "Sheet 2, cable schedule rows 10–18",
  "derivation": "42 runs × 100 m"
}
```

Workflow actions take `version`, `actor`, and optional `comment`, plus the
fields indicated above. Nonaccepting decisions require a comment. Quantities
must be finite and positive. The UI totals quantities separately by unit.

Handoff creation also takes `system`, `reference`, and optional HTTP(S) `url`.
It starts at `REFERENCED`. Tracking follows `SENT → ACKNOWLEDGED → IN_PROGRESS
→ COMPLETED`, or `CANCELLED` from any nonterminal state, and requires a note.
These are manually reported states: no external procurement integration or
automatic sending/acknowledgement is claimed. The approved package can be
downloaded from the frontend for use outside the application.

## Checks

From `backend`: `python -B -m unittest discover -s tests -v`.
With Vite on port 5173: `python -B tests/quantities_procurement_ui_smoke.py`.
Both use isolated data; application MongoDB is not modified by tests.
