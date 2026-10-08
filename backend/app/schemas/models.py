"""Pydantic request / response schemas for the endpoints with a fixed shape."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    mongodb: bool
    database: str
    posts: int | None = None
    processed_posts: int | None = None
    version: str
    server_version: str | None = None


class SentimentOut(BaseModel):
    label: str | None = None
    score: float | None = None
    confidence: float | None = None
    method: str | None = None


class TopicOut(BaseModel):
    id: str
    label: str | None = None
    weight: float | None = None
    method: str | None = None


class UserOut(BaseModel):
    username: str | None = None
    followers: int | None = None
    account_category: str | None = None


class LocationOut(BaseModel):
    country: str | None = None
    city: str | None = None


class EngagementOut(BaseModel):
    likes: int = 0
    comments: int = 0
    shares: int = 0
    total: int = 0
    synthetic: bool = False


class PostOut(BaseModel):
    id: str
    post_id: str
    text: str
    created_at: datetime
    language: str | None = None
    location: LocationOut | None = None
    hashtags: list[str] = []
    mentions: list[str] = []
    user: UserOut | None = None
    sentiment: SentimentOut | None = None
    topic: TopicOut | None = None
    keywords: list[str] = []
    engagement: EngagementOut | None = None
    is_retweet: bool = False
    post_type: str | None = None
    quality_flags: list[str] = []
    reach: int | None = None
    score: float | None = Field(default=None, description="text-search relevance (search only)")


class PostDetail(PostOut):
    clean_text: str | None = None
    url_count: int | None = None
    emojis: list[str] = []
    identical_text_posts: int | None = None
    source: str | None = None
    ingestion_job_id: str | None = None


class PostsPage(BaseModel):
    items: list[PostOut]
    page: int
    page_size: int
    total: int | None
    total_capped: bool = False
    meta: dict


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int
    format: str
    preview_columns: list[str]


class StartIngestion(BaseModel):
    upload_id: str | None = Field(default=None, description="id returned by /api/ingestion/upload")
    path: str | None = Field(default=None, description="file or folder under the project's data/ directory")
    profile: Literal["generic", "ira538"] = "generic"
    source: str | None = Field(default=None, max_length=60, pattern=r"^[\w\-\. ]+$")
    batch_size: int = Field(default=5000, ge=100, le=50_000)
    limit: int | None = Field(default=None, ge=1)
    run_nlp: bool = True
    refresh_rollups: bool = True


class IngestionJob(BaseModel):
    id: str
    status: str
    profile: str | None = None
    source: str | None = None
    files: list[str] = []
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stats: dict | None = None
    nlp: dict | None = None
    rollups: dict | None = None
    error: str | None = None
