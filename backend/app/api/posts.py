"""Post browsing and search endpoints."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.analytics import queries
from app.analytics.source import Filters, filters_dependency
from app.database.mongo import get_db
from app.schemas.models import PostDetail, PostsPage

router = APIRouter(prefix="/api", tags=["posts"])
FiltersQ = Annotated[Filters, Depends(filters_dependency)]
MAX_PAGE = 400  # deep skip() pagination gets slow; the explorer narrows with filters instead


def db_dep():
    return get_db()


@router.get("/posts", response_model=PostsPage, summary="Filtered, paginated posts")
def list_posts(f: FiltersQ, page: int = Query(1, ge=1, le=MAX_PAGE), page_size: int = Query(25, ge=1, le=100),
               sort: Literal["newest", "oldest", "engagement", "relevance"] = "newest", db=Depends(db_dep)):
    return queries.list_posts(db, f, page, page_size, sort)


@router.get("/search", response_model=PostsPage, summary="Full-text search (MongoDB text index) with filters")
def search(f: FiltersQ, page: int = Query(1, ge=1, le=MAX_PAGE), page_size: int = Query(25, ge=1, le=100),
           sort: Literal["relevance", "newest", "engagement"] = "relevance", db=Depends(db_dep)):
    if not f.q or not f.q.strip():
        raise HTTPException(status_code=422, detail="query parameter 'q' is required")
    return queries.list_posts(db, f, page, page_size, sort)


@router.get("/posts/{post_id}", response_model=PostDetail, summary="One post (by MongoDB id or source post id)")
def get_post(post_id: str, db=Depends(db_dep)):
    doc = queries.get_post(db, post_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="post not found")
    return doc
