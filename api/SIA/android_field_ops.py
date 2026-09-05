from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import os, uuid
from dotenv import load_dotenv

load_dotenv(override=True)

MONGODB_URL   = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ginfina")
client = AsyncIOMotorClient(MONGODB_URL)
db     = client[DATABASE_NAME]

device_col        = db["sia_mobile_device"]
download_col      = db["sia_field_case_download"]
session_col       = db["sia_field_session"]
form_col          = db["sia_mobile_form_response"]
poi_cap_col       = db["sia_mobile_poi_capture"]
photo_col         = db["sia_mobile_photo_capture"]
video_col         = db["sia_mobile_video_capture"]
measure_col       = db["sia_mobile_measurement"]
nameplate_col     = db["sia_mobile_nameplate_capture"]
voice_col         = db["sia_mobile_voice_note"]
sketch_col        = db["sia_mobile_sketch"]
ai_check_col      = db["sia_mobile_ai_check"]
req_ev_col        = db["sia_required_evidence_status"]
exit_gate_col     = db["sia_site_exit_gate"]
storage_col       = db["sia_mobile_storage_status"]
sync_q_col        = db["sia_sync_queue"]
sync_batch_col    = db["sia_sync_batch"]
sync_conflict_col = db["sia_sync_conflict"]
integrity_col     = db["sia_sync_integrity_receipt"]
pack_col          = db["sia_portable_data_pack"]
audit_col         = db["sia_device_audit"]

router = APIRouter()

# ════════════════════════════════════════════════════════════
# INIT
# ════════════════════════════════════════════════════════════

async def init_android_field_ops_collections():
    await device_col.create_index("user_id")
    await device_col.create_index("device_uuid", unique=True)

    await download_col.create_index("sia_case_id")
    await download_col.create_index("site_id")
    await download_col.create_index("device_id")
    await download_col.create_index("downloaded_by")

    await session_col.create_index("field_case_download_id")
    await session_col.create_index("survey_visit_id")
    await session_col.create_index("user_id")
    await session_col.create_index("device_id")

    for col in [form_col, poi_cap_col, photo_col, video_col, measure_col,
                nameplate_col, voice_col, sketch_col, ai_check_col,
                req_ev_col, exit_gate_col, storage_col, sync_q_col, sync_batch_col]:
        await col.create_index("field_session_id")

    await form_col.create_index("assessment_pack_id")
    await poi_cap_col.create_index("poi_id")
    await photo_col.create_index("poi_id")
    await video_col.create_index("poi_id")
    await measure_col.create_index("poi_id")
    await nameplate_col.create_index("poi_id")
    await voice_col.create_index("poi_id")
    await sketch_col.create_index("poi_id")
    await req_ev_col.create_index("survey_requirement_id")
    await exit_gate_col.create_index("survey_visit_id")
    await storage_col.create_index("device_id")
    await sync_q_col.create_index("device_id")
    await sync_q_col.create_index("idempotency_key")
    await sync_batch_col.create_index("device_id")
    await sync_conflict_col.create_index("sync_batch_id")
    await integrity_col.create_index("sync_batch_id")

    await pack_col.create_index("sia_case_id")
    await pack_col.create_index("site_id")
    await pack_col.create_index("device_id")
    await pack_col.create_index("created_by")

    await audit_col.create_index("device_id")
    await audit_col.create_index("user_id")
    await audit_col.create_index("field_session_id")

    print("android_field_ops collections initialized")

# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def nid(): return str(uuid.uuid4())

def nf(entity, eid):
    raise HTTPException(status_code=404, detail=f"{entity} '{eid}' not found")

def s(doc):
    d = {k: doc.get(k) for k in doc if k != "_id"}
    d["id"] = str(doc["_id"])
    return d

async def req(col, eid, name):
    doc = await col.find_one({"_id": eid})
    if not doc: nf(name, eid)
    return doc

# ════════════════════════════════════════════════════════════
# SIA_MOBILE_DEVICE
# ════════════════════════════════════════════════════════════

class MobileDeviceCreate(BaseModel):
    user_id:       Optional[str] = Field(None, description="FK → users._id")
    device_uuid:   str = Field(..., max_length=150)
    device_name:   Optional[str] = Field(None, max_length=150)
    device_model:  Optional[str] = Field(None, max_length=150)
    os_version:    Optional[str] = Field(None, max_length=50)
    app_version:   Optional[str] = Field(None, max_length=50)
    is_encrypted:  Optional[bool] = None
    is_active:     Optional[bool] = True
    last_seen_at:  Optional[str] = None

class MobileDeviceResponse(MobileDeviceCreate):
    id: str; created_at: datetime

@router.post("/sia/mobile-devices", response_model=MobileDeviceResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_mobile_device(data: MobileDeviceCreate):
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await device_col.insert_one(doc); return s(doc)

@router.get("/sia/mobile-devices/{device_id}", response_model=MobileDeviceResponse, tags=["SIA - Android Field Ops"])
async def get_mobile_device(device_id: str):
    doc = await device_col.find_one({"_id": device_id})
    if not doc: nf("Mobile Device", device_id)
    return s(doc)

@router.get("/sia/mobile-devices", response_model=List[MobileDeviceResponse], tags=["SIA - Android Field Ops"])
async def list_mobile_devices():
    docs = await device_col.find({}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_FIELD_CASE_DOWNLOAD
# ════════════════════════════════════════════════════════════

class FieldCaseDownloadCreate(BaseModel):
    sia_case_id:     str = Field(...)
    site_id:         str = Field(...)
    survey_visit_id: Optional[str] = None
    device_id:       str = Field(...)
    downloaded_by:   Optional[str] = Field(None, description="FK → users._id")
    pack_version:    Optional[str] = Field(None, max_length=50)
    downloaded_at:   Optional[str] = None
    download_status: Optional[str] = Field(None, max_length=50)
    offline_ready:   Optional[bool] = None

class FieldCaseDownloadResponse(FieldCaseDownloadCreate):
    id: str; created_at: datetime

@router.post("/sia/field-case-downloads", response_model=FieldCaseDownloadResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_field_case_download(data: FieldCaseDownloadCreate):
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await download_col.insert_one(doc); return s(doc)

@router.get("/sia/cases/{case_id}/field-case-downloads", response_model=List[FieldCaseDownloadResponse], tags=["SIA - Android Field Ops"])
async def get_downloads_by_case(case_id: str):
    docs = await download_col.find({"sia_case_id": case_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_FIELD_SESSION
# ════════════════════════════════════════════════════════════

class FieldSessionCreate(BaseModel):
    field_case_download_id: str = Field(...)
    survey_visit_id:        str = Field(...)
    user_id:                Optional[str] = Field(None, description="FK → users._id")
    device_id:              str = Field(...)
    started_at:             Optional[str] = None
    ended_at:               Optional[str] = None
    session_status:         Optional[str] = Field(None, max_length=50)
    offline_mode:           Optional[bool] = None
    start_latitude:         Optional[float] = None
    start_longitude:        Optional[float] = None

class FieldSessionResponse(FieldSessionCreate):
    id: str; created_at: datetime

@router.post("/sia/field-sessions", response_model=FieldSessionResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_field_session(data: FieldSessionCreate):
    await req(download_col, data.field_case_download_id, "Field Case Download")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await session_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}", response_model=FieldSessionResponse, tags=["SIA - Android Field Ops"])
async def get_field_session(session_id: str):
    doc = await session_col.find_one({"_id": session_id})
    if not doc: nf("Field Session", session_id)
    return s(doc)

@router.get("/sia/field-case-downloads/{download_id}/sessions", response_model=List[FieldSessionResponse], tags=["SIA - Android Field Ops"])
async def get_sessions_by_download(download_id: str):
    docs = await session_col.find({"field_case_download_id": download_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_MOBILE_FORM_RESPONSE
# ════════════════════════════════════════════════════════════

class MobileFormResponseCreate(BaseModel):
    field_session_id:    str = Field(...)
    assessment_pack_id:  Optional[str] = None
    poi_id:              Optional[str] = None
    question_code:       Optional[str] = Field(None, max_length=100)
    question_text:       Optional[str] = None
    response_value:      Optional[str] = None
    unit:                Optional[str] = Field(None, max_length=50)
    applicability_status: Optional[str] = Field(None, max_length=50)
    validation_status:   Optional[str] = Field(None, max_length=50)
    answered_at:         Optional[str] = None

class MobileFormResponseResponse(MobileFormResponseCreate):
    id: str; created_at: datetime

@router.post("/sia/mobile-form-responses", response_model=MobileFormResponseResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_form_response(data: MobileFormResponseCreate):
    await req(session_col, data.field_session_id, "Field Session")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await form_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}/form-responses", response_model=List[MobileFormResponseResponse], tags=["SIA - Android Field Ops"])
async def get_form_responses(session_id: str):
    docs = await form_col.find({"field_session_id": session_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_MOBILE_POI_CAPTURE
# ════════════════════════════════════════════════════════════

class MobilePOICaptureCreate(BaseModel):
    field_session_id: str = Field(...)
    poi_id:           str = Field(...)
    geometry_type:    Optional[str] = Field(None, max_length=50)
    geometry_data:    Optional[str] = None
    gps_accuracy:     Optional[float] = None
    captured_at:      Optional[str] = None
    captured_by:      Optional[str] = Field(None, description="FK → users._id")

class MobilePOICaptureResponse(MobilePOICaptureCreate):
    id: str; created_at: datetime

@router.post("/sia/mobile-poi-captures", response_model=MobilePOICaptureResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_poi_capture(data: MobilePOICaptureCreate):
    await req(session_col, data.field_session_id, "Field Session")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await poi_cap_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}/poi-captures", response_model=List[MobilePOICaptureResponse], tags=["SIA - Android Field Ops"])
async def get_poi_captures(session_id: str):
    docs = await poi_cap_col.find({"field_session_id": session_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_MOBILE_PHOTO_CAPTURE
# ════════════════════════════════════════════════════════════

class MobilePhotoCaptureCreate(BaseModel):
    field_session_id: str = Field(...)
    poi_id:           Optional[str] = None
    file_name:        Optional[str] = Field(None, max_length=255)
    file_path:        Optional[str] = None
    file_hash:        Optional[str] = Field(None, max_length=255)
    latitude:         Optional[float] = None
    longitude:        Optional[float] = None
    gps_accuracy:     Optional[float] = None
    direction:        Optional[float] = None
    annotation:       Optional[str] = None
    captured_at:      Optional[str] = None
    captured_by:      Optional[str] = Field(None, description="FK → users._id")

class MobilePhotoCaptureResponse(MobilePhotoCaptureCreate):
    id: str; created_at: datetime

@router.post("/sia/mobile-photo-captures", response_model=MobilePhotoCaptureResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_photo_capture(data: MobilePhotoCaptureCreate):
    await req(session_col, data.field_session_id, "Field Session")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await photo_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}/photo-captures", response_model=List[MobilePhotoCaptureResponse], tags=["SIA - Android Field Ops"])
async def get_photo_captures(session_id: str):
    docs = await photo_col.find({"field_session_id": session_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_MOBILE_VIDEO_CAPTURE
# ════════════════════════════════════════════════════════════

class MobileVideoCaptureCreate(BaseModel):
    field_session_id: str = Field(...)
    poi_id:           Optional[str] = None
    file_name:        Optional[str] = Field(None, max_length=255)
    file_path:        Optional[str] = None
    file_hash:        Optional[str] = Field(None, max_length=255)
    start_latitude:   Optional[float] = None
    start_longitude:  Optional[float] = None
    spoken_note:      Optional[str] = None
    captured_at:      Optional[str] = None
    captured_by:      Optional[str] = Field(None, description="FK → users._id")

class MobileVideoCaptureResponse(MobileVideoCaptureCreate):
    id: str; created_at: datetime

@router.post("/sia/mobile-video-captures", response_model=MobileVideoCaptureResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_video_capture(data: MobileVideoCaptureCreate):
    await req(session_col, data.field_session_id, "Field Session")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await video_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}/video-captures", response_model=List[MobileVideoCaptureResponse], tags=["SIA - Android Field Ops"])
async def get_video_captures(session_id: str):
    docs = await video_col.find({"field_session_id": session_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_MOBILE_MEASUREMENT
# ════════════════════════════════════════════════════════════

class MobileMeasurementCreate(BaseModel):
    field_session_id:    str = Field(...)
    poi_id:              Optional[str] = None
    instrument_id:       Optional[str] = None
    measurement_type:    Optional[str] = Field(None, max_length=100)
    measurement_value:   Optional[float] = None
    unit:                Optional[str] = Field(None, max_length=50)
    measurement_method:  Optional[str] = Field(None, max_length=100)
    instrument_serial:   Optional[str] = Field(None, max_length=100)
    calibration_status:  Optional[str] = Field(None, max_length=50)
    accuracy:            Optional[float] = None
    tolerance:           Optional[float] = None
    latitude:            Optional[float] = None
    longitude:           Optional[float] = None
    measured_at:         Optional[str] = None
    measured_by:         Optional[str] = Field(None, description="FK → users._id")

class MobileMeasurementResponse(MobileMeasurementCreate):
    id: str; created_at: datetime

@router.post("/sia/mobile-measurements", response_model=MobileMeasurementResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_measurement(data: MobileMeasurementCreate):
    await req(session_col, data.field_session_id, "Field Session")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await measure_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}/measurements", response_model=List[MobileMeasurementResponse], tags=["SIA - Android Field Ops"])
async def get_measurements(session_id: str):
    docs = await measure_col.find({"field_session_id": session_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_MOBILE_NAMEPLATE_CAPTURE
# ════════════════════════════════════════════════════════════

class MobileNameplateCaptureCreate(BaseModel):
    field_session_id: str = Field(...)
    poi_id:           Optional[str] = None
    image_file_path:  Optional[str] = None
    ocr_text:         Optional[str] = None
    proposed_data:    Optional[str] = None
    confirmed_data:   Optional[str] = None
    user_confirmed:   Optional[bool] = None
    confirmed_by:     Optional[str] = Field(None, description="FK → users._id")
    captured_at:      Optional[str] = None

class MobileNameplateCaptureResponse(MobileNameplateCaptureCreate):
    id: str; created_at: datetime

@router.post("/sia/mobile-nameplate-captures", response_model=MobileNameplateCaptureResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_nameplate_capture(data: MobileNameplateCaptureCreate):
    await req(session_col, data.field_session_id, "Field Session")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await nameplate_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}/nameplate-captures", response_model=List[MobileNameplateCaptureResponse], tags=["SIA - Android Field Ops"])
async def get_nameplate_captures(session_id: str):
    docs = await nameplate_col.find({"field_session_id": session_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_MOBILE_VOICE_NOTE
# ════════════════════════════════════════════════════════════

class MobileVoiceNoteCreate(BaseModel):
    field_session_id:     str = Field(...)
    poi_id:               Optional[str] = None
    audio_file_path:      Optional[str] = None
    transcription:        Optional[str] = None
    transcription_status: Optional[str] = Field(None, max_length=50)
    recorded_at:          Optional[str] = None
    recorded_by:          Optional[str] = Field(None, description="FK → users._id")

class MobileVoiceNoteResponse(MobileVoiceNoteCreate):
    id: str; created_at: datetime

@router.post("/sia/mobile-voice-notes", response_model=MobileVoiceNoteResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_voice_note(data: MobileVoiceNoteCreate):
    await req(session_col, data.field_session_id, "Field Session")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await voice_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}/voice-notes", response_model=List[MobileVoiceNoteResponse], tags=["SIA - Android Field Ops"])
async def get_voice_notes(session_id: str):
    docs = await voice_col.find({"field_session_id": session_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_MOBILE_SKETCH
# ════════════════════════════════════════════════════════════

class MobileSketchCreate(BaseModel):
    field_session_id: str = Field(...)
    poi_id:           Optional[str] = None
    sketch_type:      Optional[str] = Field(None, max_length=100)
    file_path:        Optional[str] = None
    description:      Optional[str] = None
    created_by:       Optional[str] = Field(None, description="FK → users._id")

class MobileSketchResponse(MobileSketchCreate):
    id: str; created_at: datetime

@router.post("/sia/mobile-sketches", response_model=MobileSketchResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_sketch(data: MobileSketchCreate):
    await req(session_col, data.field_session_id, "Field Session")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await sketch_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}/sketches", response_model=List[MobileSketchResponse], tags=["SIA - Android Field Ops"])
async def get_sketches(session_id: str):
    docs = await sketch_col.find({"field_session_id": session_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_MOBILE_AI_CHECK
# ════════════════════════════════════════════════════════════

AI_CHECK_TYPES = ["IMAGE_BLUR","DUPLICATE_IMAGE","OCR","MISSING_EVIDENCE","VALUE_CONFLICT","GPS_PLAUSIBILITY"]

class MobileAICheckCreate(BaseModel):
    field_session_id:  str = Field(...)
    check_type:        Optional[str] = Field(None, max_length=100,
                           description=f"One of: {', '.join(AI_CHECK_TYPES)}")
    source_record_type: Optional[str] = Field(None, max_length=100)
    source_record_id:  Optional[str] = None
    result:            Optional[str] = Field(None, max_length=100)
    confidence_score:  Optional[float] = None
    message:           Optional[str] = None
    user_confirmed:    Optional[bool] = None
    checked_at:        Optional[str] = None

class MobileAICheckResponse(MobileAICheckCreate):
    id: str; created_at: datetime

@router.post("/sia/mobile-ai-checks", response_model=MobileAICheckResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_ai_check(data: MobileAICheckCreate):
    await req(session_col, data.field_session_id, "Field Session")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await ai_check_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}/ai-checks", response_model=List[MobileAICheckResponse], tags=["SIA - Android Field Ops"])
async def get_ai_checks(session_id: str):
    docs = await ai_check_col.find({"field_session_id": session_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_REQUIRED_EVIDENCE_STATUS
# ════════════════════════════════════════════════════════════

EV_STATUSES = ["COLLECTED","NOT_APPLICABLE","INACCESSIBLE_UNSAFE","UNKNOWN","DATA_GAP"]

class RequiredEvidenceStatusCreate(BaseModel):
    field_session_id:      str = Field(...)
    survey_requirement_id: str = Field(...)
    poi_id:                Optional[str] = None
    evidence_status:       str = Field(..., max_length=50,
                               description=f"One of: {', '.join(EV_STATUSES)}")
    exception_reason:      Optional[str] = None
    evidence_id:           Optional[str] = None
    data_gap_id:           Optional[str] = None
    updated_at:            Optional[str] = None
    updated_by:            Optional[str] = Field(None, description="FK → users._id")

class RequiredEvidenceStatusResponse(RequiredEvidenceStatusCreate):
    id: str; created_at: datetime

@router.post("/sia/required-evidence-status", response_model=RequiredEvidenceStatusResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_required_evidence_status(data: RequiredEvidenceStatusCreate):
    await req(session_col, data.field_session_id, "Field Session")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await req_ev_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}/required-evidence-status", response_model=List[RequiredEvidenceStatusResponse], tags=["SIA - Android Field Ops"])
async def get_required_evidence_status(session_id: str):
    docs = await req_ev_col.find({"field_session_id": session_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_SITE_EXIT_GATE
# ════════════════════════════════════════════════════════════

class SiteExitGateCreate(BaseModel):
    field_session_id:  str = Field(...)
    survey_visit_id:   str = Field(...)
    mandatory_count:   Optional[int] = None
    completed_count:   Optional[int] = None
    exception_count:   Optional[int] = None
    unresolved_count:  Optional[int] = None
    gate_status:       Optional[str] = Field(None, max_length=50)
    exit_decision:     Optional[str] = Field(None, max_length=50)
    exit_comment:      Optional[str] = None
    completed_by:      Optional[str] = Field(None, description="FK → users._id")
    completed_at:      Optional[str] = None

class SiteExitGateResponse(SiteExitGateCreate):
    id: str; created_at: datetime

@router.post("/sia/site-exit-gates", response_model=SiteExitGateResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_site_exit_gate(data: SiteExitGateCreate):
    await req(session_col, data.field_session_id, "Field Session")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await exit_gate_col.insert_one(doc); return s(doc)

@router.get("/sia/field-sessions/{session_id}/site-exit-gates", response_model=List[SiteExitGateResponse], tags=["SIA - Android Field Ops"])
async def get_site_exit_gates(session_id: str):
    docs = await exit_gate_col.find({"field_session_id": session_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_MOBILE_STORAGE_STATUS
# ════════════════════════════════════════════════════════════

class MobileStorageStatusCreate(BaseModel):
    device_id:           str = Field(...)
    field_session_id:    Optional[str] = None
    total_storage_mb:    Optional[int] = None
    used_storage_mb:     Optional[int] = None
    free_storage_mb:     Optional[int] = None
    pending_media_count: Optional[int] = None
    warning_status:      Optional[str] = Field(None, max_length=50)
    recorded_at:         Optional[str] = None

class MobileStorageStatusResponse(MobileStorageStatusCreate):
    id: str; created_at: datetime

@router.post("/sia/mobile-storage-status", response_model=MobileStorageStatusResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_storage_status(data: MobileStorageStatusCreate):
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await storage_col.insert_one(doc); return s(doc)

@router.get("/sia/mobile-devices/{device_id}/storage-status", response_model=List[MobileStorageStatusResponse], tags=["SIA - Android Field Ops"])
async def get_storage_status(device_id: str):
    docs = await storage_col.find({"device_id": device_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_SYNC_QUEUE
# ════════════════════════════════════════════════════════════

class SyncQueueCreate(BaseModel):
    device_id:        str = Field(...)
    field_session_id: Optional[str] = None
    operation_type:   Optional[str] = Field(None, max_length=100)
    record_type:      Optional[str] = Field(None, max_length=100)
    record_id:        Optional[str] = None
    idempotency_key:  Optional[str] = Field(None, max_length=255)
    retry_count:      Optional[int] = 0
    sync_status:      Optional[str] = Field(None, max_length=50)
    last_error:       Optional[str] = None
    last_attempt_at:  Optional[str] = None

class SyncQueueResponse(SyncQueueCreate):
    id: str; created_at: datetime

@router.post("/sia/sync-queue", response_model=SyncQueueResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_sync_queue_item(data: SyncQueueCreate):
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await sync_q_col.insert_one(doc); return s(doc)

@router.get("/sia/mobile-devices/{device_id}/sync-queue", response_model=List[SyncQueueResponse], tags=["SIA - Android Field Ops"])
async def get_sync_queue(device_id: str):
    docs = await sync_q_col.find({"device_id": device_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_SYNC_BATCH
# ════════════════════════════════════════════════════════════

class SyncBatchCreate(BaseModel):
    device_id:          str = Field(...)
    field_session_id:   Optional[str] = None
    batch_code:         str = Field(..., max_length=100)
    sync_started_at:    Optional[str] = None
    sync_completed_at:  Optional[str] = None
    total_items:        Optional[int] = None
    accepted_items:     Optional[int] = None
    rejected_items:     Optional[int] = None
    quarantined_items:  Optional[int] = None
    batch_status:       Optional[str] = Field(None, max_length=50)

class SyncBatchResponse(SyncBatchCreate):
    id: str; created_at: datetime

@router.post("/sia/sync-batches", response_model=SyncBatchResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_sync_batch(data: SyncBatchCreate):
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await sync_batch_col.insert_one(doc); return s(doc)

@router.get("/sia/mobile-devices/{device_id}/sync-batches", response_model=List[SyncBatchResponse], tags=["SIA - Android Field Ops"])
async def get_sync_batches(device_id: str):
    docs = await sync_batch_col.find({"device_id": device_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_SYNC_CONFLICT
# ════════════════════════════════════════════════════════════

class SyncConflictCreate(BaseModel):
    sync_batch_id:     str = Field(...)
    record_type:       Optional[str] = Field(None, max_length=100)
    record_id:         Optional[str] = None
    local_value:       Optional[str] = None
    server_value:      Optional[str] = None
    conflict_type:     Optional[str] = Field(None, max_length=100)
    resolution_status: Optional[str] = Field(None, max_length=50)
    resolved_by:       Optional[str] = Field(None, description="FK → users._id")
    resolved_at:       Optional[str] = None

class SyncConflictResponse(SyncConflictCreate):
    id: str; created_at: datetime

@router.post("/sia/sync-conflicts", response_model=SyncConflictResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_sync_conflict(data: SyncConflictCreate):
    await req(sync_batch_col, data.sync_batch_id, "Sync Batch")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await sync_conflict_col.insert_one(doc); return s(doc)

@router.get("/sia/sync-batches/{batch_id}/conflicts", response_model=List[SyncConflictResponse], tags=["SIA - Android Field Ops"])
async def get_sync_conflicts(batch_id: str):
    docs = await sync_conflict_col.find({"sync_batch_id": batch_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_SYNC_INTEGRITY_RECEIPT
# ════════════════════════════════════════════════════════════

class SyncIntegrityReceiptCreate(BaseModel):
    sync_batch_id:      str = Field(...)
    receipt_code:       Optional[str] = Field(None, max_length=100)
    manifest_hash:      Optional[str] = Field(None, max_length=255)
    integrity_status:   Optional[str] = Field(None, max_length=50)
    accepted_count:     Optional[int] = None
    rejected_count:     Optional[int] = None
    quarantined_count:  Optional[int] = None
    received_at:        Optional[str] = None

class SyncIntegrityReceiptResponse(SyncIntegrityReceiptCreate):
    id: str; created_at: datetime

@router.post("/sia/sync-integrity-receipts", response_model=SyncIntegrityReceiptResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_integrity_receipt(data: SyncIntegrityReceiptCreate):
    await req(sync_batch_col, data.sync_batch_id, "Sync Batch")
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await integrity_col.insert_one(doc); return s(doc)

@router.get("/sia/sync-batches/{batch_id}/integrity-receipts", response_model=List[SyncIntegrityReceiptResponse], tags=["SIA - Android Field Ops"])
async def get_integrity_receipts(batch_id: str):
    docs = await integrity_col.find({"sync_batch_id": batch_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_PORTABLE_DATA_PACK
# ════════════════════════════════════════════════════════════

class PortableDataPackCreate(BaseModel):
    sia_case_id:      str = Field(...)
    site_id:          str = Field(...)
    survey_visit_id:  Optional[str] = None
    device_id:        Optional[str] = None
    pack_code:        str = Field(..., max_length=100)
    pack_version:     Optional[str] = Field(None, max_length=50)
    schema_version:   Optional[str] = Field(None, max_length=50)
    manifest_path:    Optional[str] = None
    checksum:         Optional[str] = Field(None, max_length=255)
    export_method:    Optional[str] = Field(None, max_length=50)
    pack_status:      Optional[str] = Field(None, max_length=50)
    created_by:       Optional[str] = Field(None, description="FK → users._id")
    imported_at:      Optional[str] = None

class PortableDataPackResponse(PortableDataPackCreate):
    id: str; created_at: datetime

@router.post("/sia/portable-data-packs", response_model=PortableDataPackResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_portable_data_pack(data: PortableDataPackCreate):
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await pack_col.insert_one(doc); return s(doc)

@router.get("/sia/portable-data-packs/{pack_id}", response_model=PortableDataPackResponse, tags=["SIA - Android Field Ops"])
async def get_portable_data_pack(pack_id: str):
    doc = await pack_col.find_one({"_id": pack_id})
    if not doc: nf("Portable Data Pack", pack_id)
    return s(doc)

@router.get("/sia/cases/{case_id}/portable-data-packs", response_model=List[PortableDataPackResponse], tags=["SIA - Android Field Ops"])
async def get_packs_by_case(case_id: str):
    docs = await pack_col.find({"sia_case_id": case_id}).to_list(1000); return [s(d) for d in docs]

# ════════════════════════════════════════════════════════════
# SIA_DEVICE_AUDIT
# ════════════════════════════════════════════════════════════

class DeviceAuditCreate(BaseModel):
    device_id:        str = Field(...)
    user_id:          Optional[str] = Field(None, description="FK → users._id")
    field_session_id: Optional[str] = None
    event_type:       Optional[str] = Field(None, max_length=100)
    local_timestamp:  Optional[str] = None
    timezone_offset:  Optional[str] = Field(None, max_length=20)
    server_timestamp: Optional[str] = None
    clock_anomaly:    Optional[bool] = None
    event_details:    Optional[str] = None

class DeviceAuditResponse(DeviceAuditCreate):
    id: str; created_at: datetime

@router.post("/sia/device-audits", response_model=DeviceAuditResponse, status_code=201, tags=["SIA - Android Field Ops"])
async def create_device_audit(data: DeviceAuditCreate):
    doc = {"_id": nid(), **data.model_dump(), "created_at": datetime.utcnow()}
    await audit_col.insert_one(doc); return s(doc)

@router.get("/sia/mobile-devices/{device_id}/audits", response_model=List[DeviceAuditResponse], tags=["SIA - Android Field Ops"])
async def get_device_audits(device_id: str):
    docs = await audit_col.find({"device_id": device_id}).to_list(1000); return [s(d) for d in docs]
