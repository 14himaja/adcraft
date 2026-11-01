"""API endpoints for Dynamic Social Knowledge Engine & Hybrid RAG."""

from typing import Annotated, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep, DbDep, UserDep
from app.container import Container
from app.errors import NotFound
from app.services import social_knowledge
from app.services.hybrid_rag import HybridRAG
from app.services.shared_post_resolver import SharedPostContextResolver

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class IngestPostRequest(BaseModel):
    platform: str = Field(description="instagram or facebook")
    platform_post_id: str = Field(description="Platform specific media or post ID")
    post_url: str = Field(default="")
    title: str = Field(default="")
    caption: str = Field(default="")
    media_reference: str | None = None
    media_type: str = Field(default="IMAGE")
    campaign_id: str | None = None
    source: str = Field(default="adcraft")


class PatchPostRequest(BaseModel):
    title: str | None = None
    caption: str | None = None
    media_reference: str | None = None


class ResolveSharedPostRequest(BaseModel):
    message_text: str = Field(default="")
    attachments: list[dict] = Field(default_factory=list)


class RetrieveContextRequest(BaseModel):
    query: str = Field(description="Customer question")
    resolved_post_id: str | None = None
    top_k: int = Field(default=4)


def _ws(user: dict) -> str:
    return user.get("active_workspace_id") or "synxait"


@router.post("/posts/ingest")
async def ingest_post(
    body: IngestPostRequest,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    """Ingests a social post and schedules understanding."""
    ws_id = _ws(user)
    return await social_knowledge.ingest_post(
        db,
        container,
        user_id=user["_id"],
        workspace_id=ws_id,
        platform=body.platform,
        platform_post_id=body.platform_post_id,
        post_url=body.post_url,
        title=body.title,
        caption=body.caption,
        media_reference=body.media_reference,
        media_type=body.media_type,
        campaign_id=body.campaign_id,
        source=body.source,
        auto_process=True,
    )


@router.post("/posts/{post_id}/process")
async def process_post(
    post_id: str,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    """Manually or retrying post understanding & vector indexing."""
    ws_id = _ws(user)
    return await social_knowledge.process_post_understanding(db, container, post_id)


@router.patch("/posts/{post_id}")
async def patch_post(
    post_id: str,
    body: PatchPostRequest,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    """Updates an existing post caption/title and triggers re-indexing."""
    ws_id = _ws(user)
    oid = social_knowledge._to_oid(post_id)
    post = await db.social_posts.find_one({"_id": oid, "workspace_id": ws_id})
    if not post:
        raise NotFound("Post not found")

    updates = {}
    if body.title is not None:
        updates["title"] = body.title
    if body.caption is not None:
        updates["caption"] = body.caption
    if body.media_reference is not None:
        updates["media_reference"] = body.media_reference

    if updates:
        updates["knowledge_status"] = "PENDING"
        updates["updated_at"] = container.clock.now()
        await db.social_posts.update_one({"_id": oid}, {"$set": updates})
        await social_knowledge.process_post_understanding(db, container, post_id)

    updated_post = await db.social_posts.find_one({"_id": oid})
    return {"status": "UPDATED", "post_id": post_id, "knowledge_status": updated_post.get("knowledge_status")}


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    user: UserDep,
    db: DbDep,
) -> dict:
    """Deletes post from active knowledge, disables vector chunks, records audit."""
    ws_id = _ws(user)
    return await social_knowledge.delete_post_knowledge(db, post_id, ws_id, source="user")


@router.post("/posts/sync")
async def sync_external_posts(
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    """Discovers and synchronizes external posts from Meta."""
    ws_id = _ws(user)
    return await social_knowledge.sync_external_posts(db, container, user["_id"], ws_id)


@router.post("/resolve-shared-post")
async def resolve_shared_post(
    body: ResolveSharedPostRequest,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    """Identifies the exact social post from a customer message or attachment."""
    ws_id = _ws(user)
    resolver = SharedPostContextResolver(db, container.settings)
    resolved = await resolver.resolve(
        workspace_id=ws_id,
        message_text=body.message_text,
        attachments=body.attachments,
    )
    if not resolved:
        return {"resolved": False, "post": None}
    return {
        "resolved": True,
        "post": {
            "post_id": resolved.post_id,
            "platform_post_id": resolved.platform_post_id,
            "post_url": resolved.post_url,
            "title": resolved.title,
            "caption": resolved.caption,
            "summary": resolved.summary,
            "match_method": resolved.match_method,
            "confidence": resolved.confidence,
            "is_ambiguous": resolved.is_ambiguous,
            "candidate_titles": resolved.candidate_titles,
        },
    }


@router.post("/retrieve")
async def retrieve_context(
    body: RetrieveContextRequest,
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    """Hybrid RAG retrieval endpoint combining structured records & semantic search."""
    ws_id = _ws(user)
    rag = HybridRAG(db, container.settings)
    h_context = await rag.retrieve(
        workspace_id=ws_id,
        query=body.query,
        resolved_post_id=body.resolved_post_id,
        top_k=body.top_k,
    )
    post_view = None
    if h_context.resolved_post:
        p = dict(h_context.resolved_post)
        p["_id"] = str(p["_id"])
        if "user_id" in p:
            p["user_id"] = str(p["user_id"])
        if "campaign_id" in p and p["campaign_id"]:
            p["campaign_id"] = str(p["campaign_id"])
        if "created_at" in p and hasattr(p["created_at"], "isoformat"):
            p["created_at"] = p["created_at"].isoformat()
        if "updated_at" in p and hasattr(p["updated_at"], "isoformat"):
            p["updated_at"] = p["updated_at"].isoformat()
        if "published_at" in p and hasattr(p["published_at"], "isoformat"):
            p["published_at"] = p["published_at"].isoformat()
        post_view = p

    offer_view = None
    if h_context.offer:
        o = dict(h_context.offer)
        o["_id"] = str(o["_id"])
        if "user_id" in o:
            o["user_id"] = str(o["user_id"])
        if "created_at" in o and hasattr(o["created_at"], "isoformat"):
            o["created_at"] = o["created_at"].isoformat()
        if "updated_at" in o and hasattr(o["updated_at"], "isoformat"):
            o["updated_at"] = o["updated_at"].isoformat()
        offer_view = o

    return {
        "workspace_id": h_context.workspace_id,
        "resolved_post": post_view,
        "offer": offer_view,
        "semantic_chunks": [
            {"chunk_type": ch["chunk_type"], "text": ch["text"]}
            for ch in h_context.semantic_chunks
        ],
        "unknown_validity": h_context.unknown_validity,
        "is_expired": h_context.is_expired,
        "prompt_context": h_context.prompt_context,
    }


@router.post("/offers/sync")
async def sync_offers(
    user: UserDep,
    db: DbDep,
    container: ContainerDep,
) -> dict:
    """Reconciles offer expiries against the current wall clock."""
    ws_id = _ws(user)
    return await social_knowledge.reconcile_offers(db, container, workspace_id=ws_id)


@router.get("/status")
async def knowledge_status(
    user: UserDep,
    db: DbDep,
) -> dict:
    """Operational monitoring of indexed knowledge, posts, and jobs."""
    ws_id = _ws(user)
    return await social_knowledge.get_knowledge_status(db, user["_id"], ws_id)


@router.get("/posts")
async def list_posts(
    user: UserDep,
    db: DbDep,
    status: str = "published",
    limit: int = 50,
) -> list[dict]:
    """Lists social posts in the user's active workspace."""
    ws_id = _ws(user)
    cursor = db.social_posts.find({"workspace_id": ws_id, "post_status": status}).sort("created_at", -1).limit(limit)
    return [
        {
            "id": str(p["_id"]),
            "platform": p.get("platform"),
            "platform_post_id": p.get("platform_post_id"),
            "post_url": p.get("post_url"),
            "title": p.get("title"),
            "caption": p.get("caption"),
            "summary": p.get("summary"),
            "post_type": p.get("post_type"),
            "knowledge_status": p.get("knowledge_status"),
            "post_status": p.get("post_status"),
            "ad_campaign_status": p.get("ad_campaign_status"),
            "created_at": p["created_at"].isoformat() if p.get("created_at") else None,
        }
        async for p in cursor
    ]
