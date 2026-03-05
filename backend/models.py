from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from typing import Literal

from pydantic import BaseModel, field_validator

DOMAIN_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,}$"
)

IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


class SnapshotRef(BaseModel):
    timestamp: str
    url: str


class SnapshotDetail(BaseModel):
    timestamp: str
    url: str
    digest: str | None = None


class PathGroup(BaseModel):
    path: str
    score: int  # 1=low, 2=homepage, 3=high
    count: int
    first: str  # YYYYMMDDhhmmss
    last: str
    snapshots: list[SnapshotDetail]


class ScanConfig(BaseModel):
    cap: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    depth: Literal["quick", "standard", "full"] = "standard"
    categories: list[str] | None = None
    smart_dedup: bool = True

    @field_validator("cap")
    @classmethod
    def cap_bounds(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("cap must be >= 1")
        return v


class DateRange(BaseModel):
    first: str | None = None
    last: str | None = None


class PreflightResponse(BaseModel):
    domain: str
    total_snapshots: int
    html_snapshots: int
    unique_paths: int
    unique_content: int
    date_range: DateRange
    suggested_config: ScanConfig
    path_groups: list[PathGroup] = []


class JobCreate(BaseModel):
    domain: str
    config: ScanConfig | None = None
    selected_snapshots: list[SnapshotRef] | None = None

    @field_validator("domain", mode="before")
    @classmethod
    def normalize_domain(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) > 255:
            raise ValueError("Domain too long (max 255 characters)")
        for prefix in ("https://", "http://"):
            if v.startswith(prefix):
                raise ValueError("Provide a domain, not a URL (no http(s)://)")
        v = v.removeprefix("www.").rstrip("/")
        if IP_RE.match(v):
            raise ValueError("IP addresses are not supported, use a domain name")
        if not DOMAIN_RE.match(v):
            raise ValueError(f"Invalid domain format: {v}")
        return v


class JobResponse(BaseModel):
    job_id: str


class JobStatus(BaseModel):
    id: str
    domain: str
    status: str
    progress: int
    step: str
    created_at: datetime
    updated_at: datetime
    meta: dict[str, Any] | None = None
    results: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    active_jobs: int
    uptime_seconds: float


class StatsResponse(BaseModel):
    total_scans_run: int
    active_jobs: int
