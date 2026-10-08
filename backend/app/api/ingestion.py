"""File upload and ingestion job endpoints."""

from __future__ import annotations

import itertools
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.config import PROJECT_DIR, get_settings
from app.database import mongo
from app.ingestion.readers import UnsupportedFormatError, detect_format, expand_paths, iter_records
from app.schemas.models import IngestionJob, StartIngestion, UploadResponse
from app.services import jobs

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])
DATA_DIR = PROJECT_DIR / "data"
CHUNK = 1024 * 1024


def _job_out(d: dict) -> dict:
    d = dict(d)
    d["id"] = d.pop("_id")
    return d


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED,
             summary="Upload a CSV / JSON / JSONL file (optionally .gz) for ingestion")
async def upload(file: UploadFile = File(...)):
    settings = get_settings()
    name = Path(file.filename or "").name
    try:
        fmt = detect_format(Path(name))
    except UnsupportedFormatError as e:
        raise HTTPException(status_code=415, detail=str(e)) from e
    upload_id = uuid.uuid4().hex[:12]
    safe = re.sub(r"[^\w.\-]", "_", name)[-120:]
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.upload_dir / f"{upload_id}__{safe}"
    limit = settings.max_upload_mb * CHUNK
    size = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(CHUNK):
            size += len(chunk)
            if size > limit:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"file larger than {settings.max_upload_mb} MB")
            out.write(chunk)
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="empty file")
    try:
        first = next(iter(iter_records(dest)), None)
    except Exception as e:  # noqa: BLE001 - any parse failure means the file is unusable
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"could not parse file: {e}") from e
    if not first or "__parse_error__" in first:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="file contains no readable records")
    return UploadResponse(upload_id=upload_id, filename=name, size_bytes=size, format=fmt,
                          preview_columns=list(first.keys())[:50])


def _resolve_upload(upload_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", upload_id):
        raise HTTPException(status_code=422, detail="invalid upload_id")
    matches = list(get_settings().upload_dir.glob(f"{upload_id}__*"))
    if not matches:
        raise HTTPException(status_code=404, detail="upload not found")
    return matches[0]


def _resolve_path(path: str) -> Path:
    p = (PROJECT_DIR / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    data_root = DATA_DIR.resolve()
    # Only files inside data/ may be ingested (raw dataset folders are symlinked there).
    allowed_roots = [data_root] + [c.resolve() for c in data_root.glob("raw/*") if c.is_symlink()]
    if not any(p == r or r in p.parents for r in allowed_roots):
        raise HTTPException(status_code=403, detail="path must be inside the project's data/ directory")
    if not p.exists():
        raise HTTPException(status_code=404, detail="path not found")
    return p


@router.post("/start", response_model=IngestionJob, status_code=status.HTTP_202_ACCEPTED,
             summary="Start a background ingestion job (then NLP + incremental rollups)")
def start(req: StartIngestion):
    if bool(req.upload_id) == bool(req.path):
        raise HTTPException(status_code=422, detail="provide exactly one of upload_id or path")
    target = _resolve_upload(req.upload_id) if req.upload_id else _resolve_path(req.path)
    files = expand_paths([target])
    if not files:
        raise HTTPException(status_code=422, detail="no supported files found")
    job_id = jobs.start_job(files, profile=req.profile, source=req.source, batch_size=req.batch_size,
                            limit=req.limit, run_nlp=req.run_nlp, refresh_rollups=req.refresh_rollups)
    return _job_out(mongo.get_db()[mongo.INGESTION_JOBS].find_one({"_id": job_id}))


@router.get("/jobs", response_model=list[IngestionJob], summary="Recent ingestion jobs")
def list_jobs(limit: int = Query(20, ge=1, le=100)):
    cur = mongo.get_db()[mongo.INGESTION_JOBS].find({}, sort=[("started_at", -1)], limit=limit)
    return [_job_out(d) for d in cur]


@router.get("/jobs/{job_id}", response_model=IngestionJob, summary="One ingestion job")
def get_job(job_id: str):
    d = mongo.get_db()[mongo.INGESTION_JOBS].find_one({"_id": job_id})
    if not d:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_out(d)


@router.get("/preview", summary="Preview the first records of a data file (before ingesting)")
def preview(path: str, n: int = Query(5, ge=1, le=50)):
    p = _resolve_path(path)
    files = expand_paths([p])
    if not files:
        raise HTTPException(status_code=422, detail="no supported files found")
    return {"file": str(files[0].relative_to(PROJECT_DIR)) if PROJECT_DIR in files[0].parents else files[0].name,
            "records": list(itertools.islice(iter_records(files[0]), n))}
