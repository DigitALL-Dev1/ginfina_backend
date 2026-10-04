# SIA Case Team Assignment

## Overview

The team assignment feature allows assigning consultants and internal users to SIA cases at the Start Case / Case Control stage. Team members can be assigned with specific roles, disciplines, and lead designation.

## API Endpoints

### 1. Get All Consultants
**GET** `http://127.0.0.1:8001/api/consultants`

Retrieves all available consultants from the system. Use this endpoint to populate team selection dropdowns.

**Query Parameters:**
- `refresh` (optional, default: true): Set to false to read cached data without syncing from Gsolve

**Response Example:**
```json
[
  {
    "consultant_id": 123,
    "name": "John Doe",
    "username": "jdoe",
    "email": "john.doe@example.com",
    "consultant_company": "Engineering Co.",
    "company_id": 456,
    "id": "uuid-here",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "synced_at": "2024-01-01T00:00:00Z"
  }
]
```

### 2. Assign Team Member to Case
**POST** `http://127.0.0.1:8001/api/sia/case-team`

Assigns a consultant or user to an SIA case team.

**Request Body:**
```json
{
  "sia_case_id": "case-uuid-here",
  "consultant_id": "consultant-uuid-here",  // For external consultants
  "user_id": "user-uuid-here",              // For internal users (use one or the other)
  "team_role": "Lead Engineer",             // Optional: e.g., "Lead Engineer", "Designer", "Reviewer"
  "discipline": "Civil Engineering",        // Optional: e.g., "Civil", "Electrical", "Structural"
  "is_lead": true,                          // Optional: default false
  "assigned_by": "admin-user-uuid"          // Optional: who made the assignment
}
```

**Notes:**
- Either `consultant_id` OR `user_id` must be provided (not both)
- `consultant_id` should be used for external consultants from the Gsolve system
- `user_id` should be used for internal Ginfina users

**Response (201 Created):**
```json
{
  "id": "team-member-uuid",
  "sia_case_id": "case-uuid-here",
  "consultant_id": "consultant-uuid-here",
  "user_id": null,
  "team_role": "Lead Engineer",
  "discipline": "Civil Engineering",
  "is_lead": true,
  "assigned_by": "admin-user-uuid",
  "created_at": "2024-01-01T12:00:00Z"
}
```

### 3. Get Team Members for a Case
**GET** `http://127.0.0.1:8001/api/sia/cases/{case_id}/team`

Retrieves all team members assigned to a specific SIA case.

**Path Parameters:**
- `case_id`: The UUID of the SIA case

**Response (200 OK):**
```json
[
  {
    "id": "team-member-uuid",
    "sia_case_id": "case-uuid-here",
    "consultant_id": "consultant-uuid-here",
    "user_id": null,
    "team_role": "Lead Engineer",
    "discipline": "Civil Engineering",
    "is_lead": true,
    "assigned_by": "admin-user-uuid",
    "created_at": "2024-01-01T12:00:00Z"
  }
]
```

### 4. Update Team Member Assignment
**PATCH** `http://127.0.0.1:8001/api/sia/case-team/{member_id}`

Updates the role, discipline, or lead status for an existing team member.

**Path Parameters:**
- `member_id`: The UUID of the team member assignment

**Query Parameters (all optional):**
- `team_role`: New team role
- `discipline`: New discipline
- `is_lead`: New lead status (true/false)

**Example:**
```
PATCH http://127.0.0.1:8001/api/sia/case-team/member-uuid?team_role=Senior+Engineer&is_lead=false
```

**Response (200 OK):**
```json
{
  "id": "team-member-uuid",
  "sia_case_id": "case-uuid-here",
  "consultant_id": "consultant-uuid-here",
  "user_id": null,
  "team_role": "Senior Engineer",
  "discipline": "Civil Engineering",
  "is_lead": false,
  "assigned_by": "admin-user-uuid",
  "created_at": "2024-01-01T12:00:00Z"
}
```

### 5. Remove Team Member
**DELETE** `http://127.0.0.1:8001/api/sia/case-team/{member_id}`

Removes a team member assignment from an SIA case.

**Path Parameters:**
- `member_id`: The UUID of the team member assignment

**Response (204 No Content)**

## Usage Flow

### At Case Creation Stage

1. **Fetch available consultants:**
   ```bash
   GET http://127.0.0.1:8001/api/consultants
   ```

2. **Create the SIA case:**
   ```bash
   POST http://127.0.0.1:8001/api/sia/cases
   {
     "project_id": "project-uuid",
     "case_code": "SIA-001",
     "assessment_purpose": "Site Investigation",
     ...
   }
   ```

3. **Assign team members:**
   ```bash
   POST http://127.0.0.1:8001/api/sia/case-team
   {
     "sia_case_id": "newly-created-case-uuid",
     "consultant_id": "consultant-uuid",
     "team_role": "Lead Engineer",
     "discipline": "Civil Engineering",
     "is_lead": true
   }
   ```

4. **Retrieve team to display:**
   ```bash
   GET http://127.0.0.1:8001/api/sia/cases/{case_id}/team
   ```

## Database Schema

### Collection: `sia_case_team`

```javascript
{
  _id: "uuid",                    // Primary key
  sia_case_id: "uuid",            // FK to sia_case._id
  consultant_id: "uuid",          // FK to ginfina_consultant._id (nullable)
  user_id: "uuid",                // FK to users._id (nullable)
  team_role: "Lead Engineer",     // varchar(100), nullable
  discipline: "Civil",            // varchar(100), nullable
  is_lead: false,                 // boolean, default false
  assigned_by: "uuid",            // FK to users._id (nullable)
  created_at: ISODate("...")      // timestamp
}
```

### Indexes:
- `sia_case_id` - For fast lookups by case
- `consultant_id` - For finding all cases a consultant is assigned to
- `user_id` - For finding all cases a user is assigned to
- `is_lead` - For filtering team leads

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Either consultant_id or user_id must be provided"
}
```

### 404 Not Found
```json
{
  "detail": "SIA case 'case-uuid' not found"
}
```

## Integration Notes

- Team assignments are independent of case assessment pack selections
- Multiple team members can be assigned to a single case
- Multiple team leads can exist per case (not enforced at API level)
- Team assignments persist throughout the case lifecycle
- No automatic deletion cascade - remove team members before deleting a case if cleanup is needed
- The consultant API (`/api/consultants`) syncs with Gsolve by default; set `refresh=false` for faster cached reads

## Testing

Run the initialization script to set up indexes:
```bash
cd backend
python initialize_core_collections.py
```

Then test the endpoints:
```bash
# Get consultants
curl http://127.0.0.1:8001/api/consultants

# Assign team member
curl -X POST http://127.0.0.1:8001/api/sia/case-team \
  -H "Content-Type: application/json" \
  -d '{
    "sia_case_id": "your-case-uuid",
    "consultant_id": "consultant-uuid",
    "team_role": "Lead Engineer",
    "is_lead": true
  }'

# Get team
curl http://127.0.0.1:8001/api/sia/cases/your-case-uuid/team
```
