"""Portfolio upload: one markdown or text file into the user's index, nothing deleted."""

import asyncio
import re

from fastapi import APIRouter

from apps.api.deps import State, User
from apps.api.schemas import UploadIn, UploadOut
from rag.ingest.documents import Document

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post("/upload", response_model=UploadOut, status_code=201)
async def upload(body: UploadIn, state: State, user: User) -> UploadOut:
    persona = user["persona"]
    slug = re.sub(r"[^a-z0-9]+", "-", body.filename.lower()).strip("-")
    doc = Document(evidence_id=f"{persona}:upload:{slug}", persona=persona, type=body.type, text=body.text,
                   skills=sorted(set(re.findall(r"`([A-Za-z][\w.+-]{1,30})`", body.text)))[:5],
                   source_path=f"upload/{user['username']}/{body.filename}")
    # embedding is cpu work
    stats = await asyncio.to_thread(state.index, [doc], persona)
    return UploadOut(evidence_id=doc.evidence_id, added=stats.added, updated=stats.updated,
                     chunks=stats.chunks_embedded)
