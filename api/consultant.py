"""Gsolve consultant directory synchronization and database-backed reads."""
import asyncio
from datetime import datetime
import os
from typing import List, Optional
import uuid

import bcrypt
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, SecretStr
from pymongo.errors import DuplicateKeyError

load_dotenv(override=True)
client = AsyncIOMotorClient(os.getenv('MONGODB_URL', 'mongodb://localhost:27017'))
db = client[os.getenv('DATABASE_NAME', 'ginfina')]
consultants_collection = db['ginfina_consultant']
router = APIRouter()


class ConsultantDetails(BaseModel):
    consultant_id: int = Field(..., strict=True, gt=0)
    salutation: Optional[str] = None
    name: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    consultant_company: Optional[str] = None
    company_id: Optional[int] = None


class ExternalConsultant(ConsultantDetails):
    password: Optional[SecretStr] = None


class ConsultantResponse(ConsultantDetails):
    id: str
    created_at: datetime
    updated_at: datetime
    synced_at: datetime


def serialize_consultant(doc):
    return {**{key: doc.get(key) for key in ConsultantDetails.model_fields},
            'id': str(doc['_id']), 'created_at': doc['created_at'],
            'updated_at': doc['updated_at'], 'synced_at': doc['synced_at']}


async def init_consultants_collection():
    await consultants_collection.create_index('consultant_id', unique=True)
    await consultants_collection.create_index('email')


def hash_password(value):
    return bcrypt.hashpw(value.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


async def sync_gsolve_consultants():
    url = os.getenv('GSOLVE_CONSULTANTS_URL', 'https://app-gsolve.green.com.pg/api/v1/consultants/')
    headers = {'Accept': 'application/json'}
    if os.getenv('GSOLVE_API_TOKEN'):
        headers['Authorization'] = f"Bearer {os.environ['GSOLVE_API_TOKEN']}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as upstream:
            response = await upstream.post(url, json={'user_type': 'Consultant', 'project_source': 'GInfina'}, headers=headers)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(504, 'Gsolve consultants request timed out') from None
    except httpx.HTTPError:
        raise HTTPException(502, 'Unable to fetch consultants from Gsolve') from None
    try:
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('code') != '001' or payload.get('status') != 'success' or not isinstance(payload.get('data'), list):
            raise ValueError('Invalid response')
        consultants = [ExternalConsultant.model_validate(row) for row in payload['data']]
        if len({row.consultant_id for row in consultants}) != len(consultants):
            raise ValueError('Duplicate consultant IDs')
        # bcrypt must not silently truncate long passwords.
        if any(row.password and len(row.password.get_secret_value().encode('utf-8')) > 72 for row in consultants):
            raise ValueError('Unsupported password length')
    except ValueError:
        raise HTTPException(502, 'Gsolve returned an invalid consultants response; no consultants were synced') from None

    now = datetime.utcnow()
    for consultant in consultants:
        values = consultant.model_dump(exclude={'password'})
        values.update(updated_at=now, synced_at=now)
        if consultant.password and consultant.password.get_secret_value():
            values['password_hash'] = await asyncio.to_thread(hash_password, consultant.password.get_secret_value())
        query = {'consultant_id': consultant.consultant_id}
        update = {'$set': values, '$unset': {'password': ''}, '$setOnInsert': {
            '_id': str(uuid.uuid5(uuid.NAMESPACE_URL, f'gsolve:consultant:{consultant.consultant_id}')),
            'created_at': now,
        }}
        try:
            await consultants_collection.update_one(query, update, upsert=True)
        except DuplicateKeyError:
            await consultants_collection.update_one(query, {'$set': values, '$unset': {'password': ''}})
    return len(consultants)


@router.post('/consultants/sync')
async def sync_consultants():
    count = await sync_gsolve_consultants()
    return {'message': 'Consultants synced successfully', 'synced_count': count}


@router.get('/consultants', response_model=List[ConsultantResponse])
async def get_consultants(refresh: bool = True):
    """Sync then read MongoDB; refresh=false reads saved records only."""
    if refresh:
        await sync_gsolve_consultants()
    rows = await consultants_collection.find({}).sort('name', 1).to_list(length=None)
    return [serialize_consultant(row) for row in rows]


@router.get('/consultants/{consultant_id}', response_model=ConsultantResponse)
async def get_consultant(consultant_id: int):
    """Read a saved consultant by their Gsolve consultant ID."""
    doc = await consultants_collection.find_one({'consultant_id': consultant_id})
    if doc is None:
        raise HTTPException(404, 'Consultant not found')
    return serialize_consultant(doc)
