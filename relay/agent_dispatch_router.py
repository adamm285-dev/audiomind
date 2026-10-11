"""
agent_dispatch_router.py - Cloud Relay for Antigravity Remote Assistant Dispatch.

Bridges hands-free voice commands captured by Android AppFunctions / Google Assistant
on mobile devices to the user's desktop Antigravity IDE pair-programming harness.
"""

import os
import uuid
import logging
import time
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import get_db, AgentDispatch, DEFAULT_TENANT_ID

logger = logging.getLogger("anti_voice.relay")
router = APIRouter(prefix="/api/agent", tags=["Agent Dispatch"])


def create_signed_token(tenant_id: str, secret: str, ttl_seconds: int = 86400) -> str:
    """Generates an HMAC-SHA256 signed session token for a specific tenant."""
    exp = int(time.time() + ttl_seconds)
    payload = f"{tenant_id}.{exp}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"{tenant_id}.{exp}.{sig}"


def resolve_request_tenant(
    authorization: Optional[str] = Header(None)
) -> str:
    """
    Derives and verifies the tenant ID strictly from the authenticated credential.
    The client-controlled X-Tenant-Id header is intentionally removed and ignored.
    """
    secret = os.environ.get("RELAY_AUTH_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: RELAY_AUTH_SECRET is not configured."
        )

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header."
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme. Expected Bearer token."
        )

    token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token provided."
        )

    # 1. Check if token is an HMAC signed token: <tenant_id>.<exp_ts>.<sig_hex>
    if "." in token:
        parts = token.split(".")
        if len(parts) == 3:
            tenant_id, exp_str, sig = parts
            try:
                exp = float(exp_str)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token structure: timestamp is malformed."
                )

            if time.time() > exp:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Relay session token has expired."
                )

            payload = f"{tenant_id}.{exp_str}".encode("utf-8")
            expected_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or forged token signature."
                )
            return tenant_id

    # 2. Check if token matches RELAY_AUTH_SECRET using constant-time comparison
    if hmac.compare_digest(token, secret):
        return os.environ.get("RELAY_DEFAULT_TENANT", DEFAULT_TENANT_ID)

    # 3. Check server-side token-to-tenant mapping via RELAY_TOKEN_MAP (JSON string)
    token_map_raw = os.environ.get("RELAY_TOKEN_MAP")
    if token_map_raw:
        try:
            token_map = json.loads(token_map_raw)
            if isinstance(token_map, dict):
                for valid_tok, mapped_tenant in token_map.items():
                    if hmac.compare_digest(token, str(valid_tok)):
                        return str(mapped_tenant)
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or unauthorized relay token."
    )


def format_local_timestamp(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


class AgentDispatchCreateRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=4000, description="The voice instruction or command to execute on Antigravity")
    source: Optional[str] = Field("android_appfunction", description="Source client: android_appfunction, web, api")
    client_id: Optional[str] = Field(None, description="Optional target client identifier")
    ttl_seconds: Optional[int] = Field(300, ge=30, le=86400, description="Time-to-live before automatic expiration")


class AgentDispatchResponse(BaseModel):
    success: bool
    dispatch_id: str
    status: str
    instruction: str
    spoken_confirmation: str
    created_at: str


class PendingDispatchItem(BaseModel):
    id: str
    instruction: str
    source: str
    created_at: str
    ttl_seconds: int


class PendingDispatchResponse(BaseModel):
    has_pending: bool
    dispatch: Optional[PendingDispatchItem] = None


class AgentDispatchAckRequest(BaseModel):
    dispatch_id: str
    status: str = Field("EXECUTED", description="Status update: EXECUTED, FAILED")
    execution_summary: Optional[str] = Field(None, description="Spoken or markdown summary of what was accomplished")


class AgentDispatchAckResponse(BaseModel):
    success: bool
    dispatch_id: str
    status: str


class AgentDispatchStatusResponse(BaseModel):
    dispatch_id: str
    tenant_id: str
    instruction: str
    status: str
    source: str
    client_id: Optional[str] = None
    execution_summary: Optional[str] = None
    created_at: Optional[str] = None
    delivered_at: Optional[str] = None
    executed_at: Optional[str] = None


@router.post("/dispatch", response_model=AgentDispatchResponse)
def dispatch_to_agent(
    payload: AgentDispatchCreateRequest,
    tenant_id: str = Depends(resolve_request_tenant),
    db: Session = Depends(get_db)
):
    """
    Queues a voice command or remote engineering instruction to be executed
    by the desktop Antigravity AI pair programmer.
    """
    clean_instruction = payload.instruction.strip()
    if not clean_instruction:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Instruction cannot be empty.")

    dispatch_id = f"disp_{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow()

    dispatch = AgentDispatch(
        id=dispatch_id,
        tenant_id=tenant_id,
        instruction=clean_instruction,
        status="PENDING",
        source=payload.source or "android_appfunction",
        client_id=payload.client_id,
        created_at=now,
        ttl_seconds=payload.ttl_seconds or 300,
    )
    db.add(dispatch)
    db.commit()
    db.refresh(dispatch)

    logger.info(f"[AGENT DISPATCH] Queued dispatch {dispatch_id} for tenant '{tenant_id}': {clean_instruction[:80]}...")

    spoken = "Sent to Antigravity on your desktop."

    return AgentDispatchResponse(
        success=True,
        dispatch_id=dispatch_id,
        status="QUEUED",
        instruction=clean_instruction,
        spoken_confirmation=spoken,
        created_at=format_local_timestamp(now) or now.isoformat()
    )


@router.get("/pending", response_model=PendingDispatchResponse)
def get_pending_dispatch(
    tenant_id: str = Depends(resolve_request_tenant),
    db: Session = Depends(get_db)
):
    """
    Polled by the desktop Antigravity harness to fetch the oldest pending instruction.
    Marks retrieved dispatch as DELIVERED to prevent duplicate executions.
    """
    now = datetime.utcnow()

    dispatches = db.query(AgentDispatch).filter(
        AgentDispatch.tenant_id == tenant_id,
        AgentDispatch.status == "PENDING"
    ).order_by(AgentDispatch.created_at.asc()).all()

    valid_dispatch = None
    for d in dispatches:
        expiry = d.created_at + timedelta(seconds=d.ttl_seconds or 300)
        if now > expiry:
            d.status = "EXPIRED"
            continue
        valid_dispatch = d
        break

    if not valid_dispatch:
        db.commit()
        return PendingDispatchResponse(has_pending=False, dispatch=None)

    valid_dispatch.status = "DELIVERED"
    valid_dispatch.delivered_at = now
    db.commit()
    db.refresh(valid_dispatch)

    logger.info(f"[AGENT DISPATCH] Delivered dispatch {valid_dispatch.id} to desktop harness: {valid_dispatch.instruction[:80]}...")

    return PendingDispatchResponse(
        has_pending=True,
        dispatch=PendingDispatchItem(
            id=valid_dispatch.id,
            instruction=valid_dispatch.instruction,
            source=valid_dispatch.source,
            created_at=format_local_timestamp(valid_dispatch.created_at) or valid_dispatch.created_at.isoformat(),
            ttl_seconds=valid_dispatch.ttl_seconds
        )
    )


@router.post("/ack", response_model=AgentDispatchAckResponse)
def acknowledge_dispatch(
    payload: AgentDispatchAckRequest,
    tenant_id: str = Depends(resolve_request_tenant),
    db: Session = Depends(get_db)
):
    """
    Called by the desktop Antigravity harness after submitting or completing
    the instruction in the IDE, recording execution status and response summary.
    Only accepts dispatches in DELIVERED state, and status values EXECUTED or FAILED.
    """
    if payload.status not in {"EXECUTED", "FAILED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status. Allowed values: EXECUTED, FAILED."
        )

    dispatch = db.query(AgentDispatch).filter(
        AgentDispatch.id == payload.dispatch_id,
        AgentDispatch.tenant_id == tenant_id
    ).first()

    if not dispatch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dispatch '{payload.dispatch_id}' not found."
        )

    if dispatch.status != "DELIVERED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dispatch must be in DELIVERED state to be acknowledged (current state: {dispatch.status})."
        )

    now = datetime.utcnow()
    dispatch.status = payload.status
    dispatch.executed_at = now
    if payload.execution_summary:
        dispatch.execution_summary = payload.execution_summary

    db.commit()
    logger.info(f"[AGENT DISPATCH] Acknowledged dispatch {dispatch.id} as {payload.status}")

    return AgentDispatchAckResponse(
        success=True,
        dispatch_id=dispatch.id,
        status=dispatch.status
    )


@router.get("/status/{dispatch_id}", response_model=AgentDispatchStatusResponse)
def get_dispatch_status(
    dispatch_id: str,
    tenant_id: str = Depends(resolve_request_tenant),
    db: Session = Depends(get_db)
):
    """
    Retrieves the current lifecycle status and execution summary of a dispatch.
    """
    dispatch = db.query(AgentDispatch).filter(
        AgentDispatch.id == dispatch_id,
        AgentDispatch.tenant_id == tenant_id
    ).first()

    if not dispatch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dispatch '{dispatch_id}' not found."
        )

    return AgentDispatchStatusResponse(
        dispatch_id=dispatch.id,
        tenant_id=dispatch.tenant_id,
        instruction=dispatch.instruction,
        status=dispatch.status,
        source=dispatch.source,
        client_id=dispatch.client_id,
        execution_summary=dispatch.execution_summary,
        created_at=format_local_timestamp(dispatch.created_at),
        delivered_at=format_local_timestamp(dispatch.delivered_at),
        executed_at=format_local_timestamp(dispatch.executed_at),
    )
