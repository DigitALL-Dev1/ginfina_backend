"""
Example script demonstrating SIA Case Team Assignment API usage.

This script shows how to:
1. Fetch available consultants
2. Create an SIA case
3. Assign team members to the case
4. Retrieve and update team assignments

Run with: python test_team_assignment_example.py
(Requires the backend server to be running on http://127.0.0.1:8001)
"""

import requests
import json
from typing import Dict, List, Optional

BASE_URL = "http://127.0.0.1:8001/api"


def get_consultants(refresh: bool = True) -> List[Dict]:
    """Fetch all available consultants."""
    print("\n1. Fetching consultants...")
    response = requests.get(f"{BASE_URL}/consultants", params={"refresh": refresh})
    response.raise_for_status()
    consultants = response.json()
    print(f"   Found {len(consultants)} consultants")
    for c in consultants[:3]:  # Show first 3
        print(f"   - {c['name']} ({c['email']})")
    return consultants


def create_sia_case(project_id: str, case_code: str) -> Dict:
    """Create a new SIA case."""
    print(f"\n2. Creating SIA case '{case_code}'...")
    payload = {
        "project_id": project_id,
        "case_code": case_code,
        "assessment_purpose": "Site Investigation for Hospital Solar Project",
        "assessment_stage": "Initial Assessment"
    }
    response = requests.post(f"{BASE_URL}/sia/cases", json=payload)
    response.raise_for_status()
    case = response.json()
    print(f"   Case created with ID: {case['id']}")
    return case


def assign_team_member(
    sia_case_id: str,
    consultant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    team_role: str = "Engineer",
    discipline: str = "Civil Engineering",
    is_lead: bool = False
) -> Dict:
    """Assign a team member to an SIA case."""
    print(f"\n3. Assigning team member as {team_role}...")
    payload = {
        "sia_case_id": sia_case_id,
        "team_role": team_role,
        "discipline": discipline,
        "is_lead": is_lead
    }
    
    if consultant_id:
        payload["consultant_id"] = consultant_id
    if user_id:
        payload["user_id"] = user_id
    
    response = requests.post(f"{BASE_URL}/sia/case-team", json=payload)
    response.raise_for_status()
    member = response.json()
    print(f"   Team member assigned with ID: {member['id']}")
    print(f"   Role: {member['team_role']}, Lead: {member['is_lead']}")
    return member


def get_case_team(case_id: str) -> List[Dict]:
    """Retrieve all team members for a case."""
    print(f"\n4. Retrieving team for case {case_id}...")
    response = requests.get(f"{BASE_URL}/sia/cases/{case_id}/team")
    response.raise_for_status()
    team = response.json()
    print(f"   Team has {len(team)} members:")
    for member in team:
        print(f"   - {member['team_role']} ({member['discipline']}) - Lead: {member['is_lead']}")
    return team


def update_team_member(
    member_id: str,
    team_role: Optional[str] = None,
    discipline: Optional[str] = None,
    is_lead: Optional[bool] = None
) -> Dict:
    """Update a team member's assignment."""
    print(f"\n5. Updating team member {member_id}...")
    params = {}
    if team_role:
        params["team_role"] = team_role
    if discipline:
        params["discipline"] = discipline
    if is_lead is not None:
        params["is_lead"] = is_lead
    
    response = requests.patch(
        f"{BASE_URL}/sia/case-team/{member_id}",
        params=params
    )
    response.raise_for_status()
    member = response.json()
    print(f"   Updated: {member['team_role']} - Lead: {member['is_lead']}")
    return member


def remove_team_member(member_id: str):
    """Remove a team member from a case."""
    print(f"\n6. Removing team member {member_id}...")
    response = requests.delete(f"{BASE_URL}/sia/case-team/{member_id}")
    response.raise_for_status()
    print("   Team member removed successfully")


def main():
    """Main demonstration flow."""
    print("=" * 60)
    print("SIA Case Team Assignment - Example Usage")
    print("=" * 60)
    
    try:
        # Step 1: Get available consultants
        consultants = get_consultants(refresh=False)
        
        if not consultants:
            print("\n⚠️  No consultants found. Please sync consultants first:")
            print("   POST http://127.0.0.1:8001/api/consultants/sync")
            return
        
        # Step 2: Create a new SIA case (you'll need a valid project_id)
        # For demo purposes, replace with an actual project ID from your database
        project_id = "your-project-id-here"
        case_code = "SIA-DEMO-001"
        
        print(f"\nℹ️  Note: Using project_id '{project_id}'")
        print("   Update this with a valid project ID from your database")
        
        # Uncomment the following lines when you have a valid project_id
        # case = create_sia_case(project_id, case_code)
        # case_id = case['id']
        
        # For demo, using a placeholder case_id
        case_id = "your-case-id-here"
        
        # Step 3: Assign team members
        # Lead Engineer
        # lead_member = assign_team_member(
        #     sia_case_id=case_id,
        #     consultant_id=consultants[0]['id'],
        #     team_role="Lead Engineer",
        #     discipline="Civil Engineering",
        #     is_lead=True
        # )
        
        # Design Engineer
        # design_member = assign_team_member(
        #     sia_case_id=case_id,
        #     consultant_id=consultants[1]['id'] if len(consultants) > 1 else consultants[0]['id'],
        #     team_role="Design Engineer",
        #     discipline="Structural Engineering",
        #     is_lead=False
        # )
        
        # Step 4: Get team
        # team = get_case_team(case_id)
        
        # Step 5: Update a team member
        # if team:
        #     update_team_member(
        #         member_id=team[0]['id'],
        #         team_role="Senior Engineer"
        #     )
        
        # Step 6: Remove a team member (optional)
        # if team and len(team) > 1:
        #     remove_team_member(team[1]['id'])
        
        # Final team check
        # final_team = get_case_team(case_id)
        
        print("\n" + "=" * 60)
        print("✅ Demo completed successfully!")
        print("=" * 60)
        print("\nTo use this script with real data:")
        print("1. Ensure the backend server is running")
        print("2. Sync consultants: POST /api/consultants/sync")
        print("3. Create or get a valid project_id")
        print("4. Uncomment the API calls in main()")
        print("5. Run: python test_team_assignment_example.py")
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: {e}")
        if hasattr(e.response, 'text'):
            print(f"   Response: {e.response.text}")


if __name__ == "__main__":
    main()
