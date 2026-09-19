"""Initialize pilot users, project and assessment packs explicitly.

Run from backend: python -B initialize_core_collections.py
Creates the existing pilot accounts only if users is empty and adds a dummy
Hospital Solar Project and SIA assessment packs if missing. Existing records
are preserved. No packs are automatically selected for a case.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from dotenv import load_dotenv


async def seed_dummy_project(auth, project):
    code = "DEMO-HSP-001"
    identity = str(uuid5(NAMESPACE_URL, "ginfina:dummy-project:DEMO-HSP-001"))
    existing = await project.projects_collection.find_one({"$or": [
        {"_id": identity}, {"project_code": code},
    ]})
    if existing:
        print(f"Dummy project {code} already exists; preserved without changes.")
        return

    owner = await auth.users_collection.find_one({"email": "admin@gx1.com", "is_active": True})
    if not owner:
        owner = await auth.users_collection.find_one({"role": "admin", "is_active": True})
    if not owner:
        print("Dummy project skipped: no active admin account exists.")
        return

    timestamp = datetime.now(timezone.utc)
    data = {
        "_id": identity,
        "gsolve_project_id": -1,  # Dummy placeholder; not a real Gsolve project.
        "project_code": code,
        "project_name": "Hospital Solar Project",
        "project_status": "ACTIVE",
        "user_id": str(owner["_id"]),
        "is_dummy": True,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    # A stable ID and insert-only upsert also protect against simultaneous runs.
    result = await project.projects_collection.update_one(
        {"_id": identity}, {"$setOnInsert": data}, upsert=True,
    )
    print(f"Dummy project {code}: {'created' if result.upserted_id else 'already exists'}.")


async def seed_assessment_packs(sia_case):
    collection = sia_case.assessment_pack_collection
    await collection.create_index("pack_code")
    await collection.create_index("is_active")
    packs = [
        ("AP-001", "Initial Site Assessment Pack", "Standard"),
        ("AP-002", "Environmental Impact Assessment Pack", "Environmental"),
        ("AP-003", "Structural Engineering Assessment Pack", "Structural"),
        ("AP-004", "Geotechnical Survey Pack", "Geotechnical"),
        ("AP-005", "Electrical Infrastructure Assessment Pack", "Electrical"),
    ]
    created = 0
    for code, name, pack_type in packs:
        identity = str(uuid5(NAMESPACE_URL, f"ginfina:assessment-pack:{code}"))
        existing = await collection.find_one({"$or": [{"_id": identity}, {"pack_code": code}]})
        if existing:
            continue
        result = await collection.update_one({"_id": identity}, {"$setOnInsert": {
            "_id": identity,
            "pack_code": code,
            "pack_name": name,
            "pack_type": pack_type,
            "is_active": True,
        }}, upsert=True)
        created += int(result.upserted_id is not None)
    # Check the same response schema used by the selection screen's GET API.
    records = await sia_case.get_all_assessment_packs()
    for record in records:
        sia_case.AssessmentPackResponse(**record)
    print(f"sia_assessment_pack: {created} added; {len(records)} total records.")


async def initialize():
    # Resolve the intended backend configuration even when called from repo root.
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
    from api import auth, project
    from api.SIA import sia_case

    try:
        await asyncio.wait_for(auth.client.admin.command("ping"), timeout=20)
        # Existing rows, passwords and project IDs are never replaced.
        await auth.init_db()
        await project.init_projects_collection()
        await seed_dummy_project(auth, project)
        await seed_assessment_packs(sia_case)
        print(f"users: {await auth.users_collection.count_documents({})} records")
        print(f"ginfina_project: {await project.projects_collection.count_documents({})} records")
        print("Core collections initialized. Existing records were preserved.")
        print("Deleted project records require a backup or recreation through the project API.")
    finally:
        auth.client.close()
        project.client.close()
        sia_case.client.close()


if __name__ == "__main__":
    try:
        asyncio.run(initialize())
    except Exception as error:
        # Connection errors can contain credentials: report the class only.
        print(f"Initialization failed ({type(error).__name__}). Check MongoDB connectivity and permissions.")
        raise SystemExit(1) from None
