from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.blog_service import generate_today_top10, get_post, list_posts

router = APIRouter()


def _serialize(p):
    return {
        "slug": p.slug, "title": p.title, "summary": p.summary,
        "body_md": p.body_md, "tags": [t for t in (p.tags or "").split(",") if t],
        "published_at": p.published_at.isoformat() if p.published_at else None,
    }


@router.get("/")
async def list_all(session: AsyncSession = Depends(get_db)):
    rows = await list_posts(session)
    if not rows:
        # seed evergreen + today on cold start so SEO never lands on empty
        from app.services.blog_service import _SEEDS, _maybe_seed
        for slug in _SEEDS:
            await _maybe_seed(session, slug)
        await generate_today_top10(session)
        rows = await list_posts(session)
    return [{"slug": p.slug, "title": p.title, "summary": p.summary,
             "tags": [t for t in (p.tags or "").split(",") if t],
             "published_at": p.published_at.isoformat() if p.published_at else None} for p in rows]


@router.get("/{slug}")
async def get_one(slug: str, session: AsyncSession = Depends(get_db)):
    post = await get_post(session, slug)
    if not post:
        raise HTTPException(404, f"post {slug} not found")
    return _serialize(post)
