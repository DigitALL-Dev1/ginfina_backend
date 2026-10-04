# Team Assignment Implementation Summary

## Overview
Implemented team assignment functionality for SIA cases at the Start Case / Case Control stage. Team members (consultants or internal users) can now be assigned to cases with specific roles, disciplines, and lead designation.

## Changes Made

### 1. Backend API - SIA Case Module (`backend/api/SIA/sia_case.py`)

#### New Models Added:
- **`CaseTeamMemberCreate`**: Input model for creating team assignments
  - `sia_case_id`: Reference to the SIA case
  - `consultant_id`: Reference to external consultant (optional)
  - `user_id`: Reference to internal user (optional)
  - `team_role`: Role in the team (e.g., "Lead Engineer", "Designer")
  - `discipline`: Engineering discipline (e.g., "Civil Engineering")
  - `is_lead`: Boolean flag for team lead
  - `assigned_by`: User who made the assignment

- **`CaseTeamMemberResponse`**: Output model for team member data

#### New Endpoints Added:

1. **POST** `/api/sia/case-team`
   - Assigns a team member to an SIA case
   - Validates case existence
   - Ensures either consultant_id or user_id is provided
   - Returns created team member data

2. **GET** `/api/sia/cases/{case_id}/team`
   - Retrieves all team members for a specific case
   - Validates case existence
   - Returns sorted list of team members

3. **PATCH** `/api/sia/case-team/{member_id}`
   - Updates team member's role, discipline, or lead status
   - Allows partial updates (only specified fields are updated)
   - Returns updated team member data

4. **DELETE** `/api/sia/case-team/{member_id}`
   - Removes a team member assignment
   - Returns 204 No Content on success

#### Database Changes:
- Added `case_team_collection` reference to `sia_case_team` collection
- Added serialization function `serialize_case_team_member()`
- Updated initialization function to create indexes:
  - `sia_case_id` (for case lookups)
  - `consultant_id` (for consultant lookups)
  - `user_id` (for user lookups)
  - `is_lead` (for filtering team leads)

### 2. Initialization Script (`backend/initialize_core_collections.py`)

Updated `seed_assessment_packs()` function to:
- Create indexes for `sia_case_team` collection
- Initialize the team collection on first run

### 3. Documentation

#### Created `backend/api/SIA/TEAM_ASSIGNMENT.md`:
- Comprehensive API documentation
- Request/response examples
- Usage flow guidelines
- Database schema reference
- Error handling documentation
- Testing instructions

#### Created `backend/api/SIA/test_team_assignment_example.py`:
- Example Python script demonstrating API usage
- Shows complete workflow from consultant fetch to team management
- Includes helper functions for all endpoints
- Ready-to-use code snippets

## Database Schema

### Collection: `sia_case_team`

```javascript
{
  _id: UUID,                      // Primary key
  sia_case_id: UUID,              // FK → sia_case._id
  consultant_id: UUID,            // FK → ginfina_consultant._id (nullable)
  user_id: UUID,                  // FK → users._id (nullable)
  team_role: String(100),         // e.g., "Lead Engineer", "Designer"
  discipline: String(100),        // e.g., "Civil Engineering"
  is_lead: Boolean,               // default: false
  assigned_by: UUID,              // FK → users._id (nullable)
  created_at: ISODate             // Timestamp
}
```

### Indexes:
- `sia_case_id`
- `consultant_id`
- `user_id`
- `is_lead`

## Integration with Existing APIs

### Consultant API Integration
The team assignment feature integrates with the existing consultant API:

**Endpoint**: `GET http://127.0.0.1:8001/api/consultants`

This endpoint:
- Syncs consultants from Gsolve (if `refresh=true`, default)
- Returns all available consultants with their details
- Used to populate team member selection dropdowns

## API Usage Example

```python
import requests

BASE_URL = "http://127.0.0.1:8001/api"

# 1. Get available consultants
consultants = requests.get(f"{BASE_URL}/consultants").json()

# 2. Assign a team member
team_member = requests.post(f"{BASE_URL}/sia/case-team", json={
    "sia_case_id": "case-uuid",
    "consultant_id": consultants[0]['id'],
    "team_role": "Lead Engineer",
    "discipline": "Civil Engineering",
    "is_lead": True
}).json()

# 3. Get case team
team = requests.get(f"{BASE_URL}/sia/cases/case-uuid/team").json()

# 4. Update team member
updated = requests.patch(
    f"{BASE_URL}/sia/case-team/{team_member['id']}",
    params={"team_role": "Senior Engineer"}
).json()

# 5. Remove team member
requests.delete(f"{BASE_URL}/sia/case-team/{team_member['id']}")
```

## Frontend Integration Notes

### At Case Creation/Control Stage:

1. **Display Available Consultants**:
   ```javascript
   fetch('http://127.0.0.1:8001/api/consultants')
     .then(res => res.json())
     .then(consultants => {
       // Populate dropdown/selection list
     });
   ```

2. **Assign Team Members**:
   ```javascript
   fetch('http://127.0.0.1:8001/api/sia/case-team', {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({
       sia_case_id: caseId,
       consultant_id: selectedConsultantId,
       team_role: 'Lead Engineer',
       discipline: 'Civil Engineering',
       is_lead: true
     })
   });
   ```

3. **Display Case Team**:
   ```javascript
   fetch(`http://127.0.0.1:8001/api/sia/cases/${caseId}/team`)
     .then(res => res.json())
     .then(team => {
       // Display team members with their roles
     });
   ```

## Testing

### 1. Initialize Database:
```bash
cd backend
python initialize_core_collections.py
```

### 2. Start Backend Server:
```bash
python main.py
# or
uvicorn main:app --reload --port 8001
```

### 3. Test Endpoints:

```bash
# Get consultants
curl http://127.0.0.1:8001/api/consultants

# Create case (adjust payload as needed)
curl -X POST http://127.0.0.1:8001/api/sia/cases \
  -H "Content-Type: application/json" \
  -d '{"project_id":"your-project-id","case_code":"SIA-001"}'

# Assign team member
curl -X POST http://127.0.0.1:8001/api/sia/case-team \
  -H "Content-Type: application/json" \
  -d '{
    "sia_case_id":"case-uuid",
    "consultant_id":"consultant-uuid",
    "team_role":"Lead Engineer",
    "is_lead":true
  }'

# Get team
curl http://127.0.0.1:8001/api/sia/cases/case-uuid/team
```

## Validation Rules

1. **sia_case_id must exist** - Returns 404 if case not found
2. **Either consultant_id OR user_id required** - Returns 400 if neither provided
3. **Member assignments are unique by ID** - No duplicate prevention by person
4. **Multiple leads allowed** - No enforcement of single lead per case
5. **No cascade delete** - Team members persist even if consultant/user deleted

## Future Enhancements

Potential improvements for future iterations:

1. **Validation**: Prevent duplicate assignments (same person to same case)
2. **Constraints**: Enforce single team lead per case
3. **Notifications**: Notify team members when assigned
4. **Permissions**: Role-based access control for team management
5. **History**: Track team member changes over time
6. **Batch Operations**: Assign multiple team members at once
7. **Templates**: Save and reuse team configurations

## Files Modified

1. `backend/api/SIA/sia_case.py` - Added team assignment functionality
2. `backend/initialize_core_collections.py` - Added team collection initialization

## Files Created

1. `backend/api/SIA/TEAM_ASSIGNMENT.md` - API documentation
2. `backend/api/SIA/test_team_assignment_example.py` - Example usage script
3. `backend/TEAM_ASSIGNMENT_IMPLEMENTATION.md` - This summary document

## Dependencies

No new dependencies required. Uses existing:
- FastAPI
- Motor (MongoDB async driver)
- Pydantic (data validation)
- Python standard library

## Deployment Notes

1. Run initialization script after deploying to production
2. Ensure MongoDB indexes are created
3. Verify consultant sync is working (`/api/consultants/sync`)
4. Test team assignment workflow end-to-end
5. Monitor collection sizes and query performance

## Support

For questions or issues:
1. Review API documentation in `TEAM_ASSIGNMENT.md`
2. Check example script in `test_team_assignment_example.py`
3. Verify database indexes are created
4. Check MongoDB connection and permissions
5. Review FastAPI auto-generated docs at `http://127.0.0.1:8001/docs`
