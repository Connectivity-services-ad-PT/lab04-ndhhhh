import os
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ======================
# CONFIG
# ======================
SERVICE_NAME = os.getenv("SERVICE_NAME", "iot-ingestion")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.4.0")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "local-dev-token")

app = FastAPI(title="FIT4110 Lab 04 IoT Service", version=SERVICE_VERSION)


# ======================
# ENUMS
# ======================
class SensorMetric(str, Enum):
    temperature = "temperature"
    humidity = "humidity"
    motion = "motion"
    smoke = "smoke"


class SensorUnit(str, Enum):
    celsius = "celsius"
    percent = "percent"
    boolean = "boolean"
    ppm = "ppm"


# ======================
# MODELS
# ======================
class SensorReadingCreate(BaseModel):
    device_id: str = Field(..., min_length=3)
    metric: SensorMetric
    value: float = Field(..., ge=-40, le=80)
    unit: Optional[SensorUnit] = None
    timestamp: str


class SensorReadingCreated(BaseModel):
    reading_id: str
    device_id: str
    metric: SensorMetric
    accepted: bool
    created_at: str


# ======================
# MEMORY DB
# ======================
READINGS: List[Dict] = []


# ======================
# HELPERS
# ======================
def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def next_id():
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"R-{today}-{len(READINGS) + 1:04d}"


# ======================
# AUTH FIX (PASS NEWMAN)
# ======================
def verify_bearer_token(authorization: str = Header(default="")):

    # Missing header
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )

    # Wrong format
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization format"
        )

    token = authorization.split("Bearer ")[1].strip()

    # Wrong token
    if token != AUTH_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer token"
        )

    return True


# ======================
# EXCEPTION HANDLERS
# ======================
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": "about:blank",
            "title": "Error",
            "status": exc.status_code,
            "detail": str(exc.detail),
            "instance": str(request.url.path),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "type": "about:blank",
            "title": "Validation error",
            "status": 422,
            "detail": str(exc.errors()),
            "instance": str(request.url.path),
        },
    )


# ======================
# HEALTH
# ======================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION
    }


# ======================
# CREATE READING
# ======================
@app.post(
    "/readings",
    status_code=201,
    dependencies=[Depends(verify_bearer_token)]
)
def create_reading(payload: SensorReadingCreate, response: Response):

    if payload.metric == SensorMetric.temperature and payload.value >= 80:
        response.headers["X-Warning"] = "high-temperature"

    rid = next_id()
    created_at = now_iso()

    READINGS.append({
        "reading_id": rid,
        "device_id": payload.device_id,
        "metric": payload.metric.value,
        "value": payload.value,
        "unit": payload.unit.value if payload.unit else None,
        "timestamp": payload.timestamp,
        "created_at": created_at,
    })

    return SensorReadingCreated(
        reading_id=rid,
        device_id=payload.device_id,
        metric=payload.metric,
        accepted=True,
        created_at=created_at,
    )


# ======================
# GET LATEST READINGS
# ======================
@app.get("/readings/latest", dependencies=[Depends(verify_bearer_token)]) # <-- SỬA Ở ĐÂY: Thêm /latest vào sau /readings
def latest_readings(
    device_id: Optional[str] = None,
    limit: int = Query(10, ge=1, le=100)
):

    data = READINGS

    if device_id:
        data = [x for x in data if x["device_id"] == device_id]

    return {"items": data[-limit:]}


# ======================
# GET BY ID
# ======================
@app.get("/readings/{reading_id}", dependencies=[Depends(verify_bearer_token)])
def get_reading(reading_id: str):

    for r in READINGS:
        if r["reading_id"] == reading_id:
            return r

    raise HTTPException(status_code=404, detail="Reading not found")