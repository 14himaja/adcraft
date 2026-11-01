"""SharedPostContextResolver: Identifies the exact social post shared in a DM conversation."""

import re
from dataclasses import dataclass
from typing import Literal

import structlog
from app.services.embeddings import cosine_similarity, generate_embedding

log = structlog.get_logger()

INSTAGRAM_POST_URL_REGEX = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)", re.IGNORECASE
)
FACEBOOK_POST_URL_REGEX = re.compile(
    r"https?://(?:www\.)?facebook\.com/[^/]+/posts/([0-9]+)", re.IGNORECASE
)
POST_ID_REGEX = re.compile(r"\b(?:post|ad|id)[:\s#]*([0-9A-Za-z_-]{6,40})\b", re.IGNORECASE)


@dataclass
class ResolvedPost:
    post_id: str  # internal database _id as string
    platform_post_id: str
    post_url: str
    title: str
    caption: str
    summary: str
    match_method: Literal[
        "exact_platform_id",
        "exact_url",
        "attachment_metadata",
        "caption_match",
        "media_reference",
        "semantic_similarity",
    ]
    confidence: float
    is_ambiguous: bool = False
    candidate_titles: list[str] | None = None


class SharedPostContextResolver:
    """Service to resolve shared social media posts from customer messages and webhook attachments."""

    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    async def resolve(
        self,
        *,
        workspace_id: str,
        message_text: str = "",
        attachments: list[dict] | None = None,
    ) -> ResolvedPost | None:
        """Resolves the shared post using strict prioritized matching."""
        attachments = attachments or []
        query_text = (message_text or "").strip()

        # Step 1: Check Exact Platform Post ID from attachments or message
        # Inspect attachments
        for att in attachments:
            payload = att.get("payload") or {}
            target_id = att.get("id") or payload.get("id") or payload.get("media_id")
            if target_id:
                post = await self.db.social_posts.find_one({
                    "workspace_id": workspace_id,
                    "platform_post_id": str(target_id),
                    "post_status": "published",
                })
                if post:
                    return self._build_resolved(post, "exact_platform_id", 1.0)

            # Check attachment URL
            att_url = payload.get("url") or payload.get("permalink") or ""
            if att_url:
                post = await self._find_by_url(workspace_id, att_url)
                if post:
                    return self._build_resolved(post, "exact_url", 1.0)

        # Step 2: Extract Post URL from message text
        if query_text:
            url_match = INSTAGRAM_POST_URL_REGEX.search(query_text) or FACEBOOK_POST_URL_REGEX.search(query_text)
            if url_match:
                extracted_url = url_match.group(0)
                shortcode = url_match.group(1)
                post = await self._find_by_url_or_code(workspace_id, extracted_url, shortcode)
                if post:
                    return self._build_resolved(post, "exact_url", 1.0)

            # Check for explicit ID mentioned in text (e.g. "Post #123456" or "id: 123456")
            id_match = POST_ID_REGEX.search(query_text)
            if id_match:
                extracted_id = id_match.group(1)
                post = await self.db.social_posts.find_one({
                    "workspace_id": workspace_id,
                    "platform_post_id": extracted_id,
                    "post_status": "published",
                })
                if post:
                    return self._build_resolved(post, "exact_platform_id", 0.98)

        # Step 3: Available platform attachment metadata (title, text)
        for att in attachments:
            payload = att.get("payload") or {}
            att_title = payload.get("title") or att.get("title") or ""
            if att_title and len(att_title) > 4:
                post = await self.db.social_posts.find_one({
                    "workspace_id": workspace_id,
                    "post_status": "published",
                    "$or": [
                        {"title": {"$regex": re.escape(att_title), "$options": "i"}},
                        {"caption": {"$regex": re.escape(att_title), "$options": "i"}},
                    ],
                })
                if post:
                    return self._build_resolved(post, "attachment_metadata", 0.92)

        # If no message text and no recognized attachment, we cannot resolve
        if not query_text:
            return None

        # Step 4: Caption substring or exact matching
        if len(query_text) > 15:
            # Check if text is a significant substring of caption or title
            post = await self.db.social_posts.find_one({
                "workspace_id": workspace_id,
                "post_status": "published",
                "$or": [
                    {"caption": {"$regex": re.escape(query_text[:50]), "$options": "i"}},
                    {"title": {"$regex": re.escape(query_text[:50]), "$options": "i"}},
                ],
            })
            if post:
                return self._build_resolved(post, "caption_match", 0.88)

        # Step 5 & 6: Semantic similarity across indexed post records
        return await self._semantic_match(workspace_id, query_text)

    async def _find_by_url(self, workspace_id: str, url: str) -> dict | None:
        clean_url = url.split("?")[0].rstrip("/")
        return await self.db.social_posts.find_one({
            "workspace_id": workspace_id,
            "post_status": "published",
            "post_url": {"$regex": f"^{re.escape(clean_url)}", "$options": "i"},
        })

    async def _find_by_url_or_code(self, workspace_id: str, full_url: str, shortcode: str) -> dict | None:
        post = await self._find_by_url(workspace_id, full_url)
        if post:
            return post
        # Try matching platform_post_id with shortcode
        return await self.db.social_posts.find_one({
            "workspace_id": workspace_id,
            "post_status": "published",
            "$or": [
                {"platform_post_id": shortcode},
                {"post_url": {"$regex": re.escape(shortcode), "$options": "i"}},
            ],
        })

    async def _semantic_match(self, workspace_id: str, query: str) -> ResolvedPost | None:
        """Finds closest active post knowledge chunk using hybrid semantic + keyword scoring."""
        query_emb = await generate_embedding(query, self.settings)
        cursor = self.db.knowledge_chunks.find({
            "workspace_id": workspace_id,
            "is_active": True,
        })

        # Tokenize meaningful query words (>2 chars, excluding stop words)
        STOP_WORDS = {"the", "and", "for", "with", "about", "tell", "this", "that", "can", "you", "our", "your", "are", "have"}
        q_words = [w for w in re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", query.lower()) if w not in STOP_WORDS]

        scores: list[tuple[float, dict]] = []
        async for chunk in cursor:
            emb = chunk.get("embedding")
            chunk_text = (chunk.get("text") or "").lower()
            if emb:
                sim = cosine_similarity(query_emb, emb)
                # Compute token overlap ratio
                token_matches = sum(1 for w in q_words if w in chunk_text) if q_words else 0
                token_ratio = token_matches / len(q_words) if q_words else 0.0

                # If no keywords match at all, require very high semantic similarity
                if q_words and token_matches == 0 and sim < 0.65:
                    continue

                # Hybrid score combining dense cosine similarity and lexical overlap
                hybrid_score = round(0.4 * sim + 0.6 * token_ratio, 3)
                if hybrid_score >= 0.25:
                    scores.append((hybrid_score, chunk))

        if not scores:
            return None

        # Sort descending by similarity
        scores.sort(key=lambda s: s[0], reverse=True)
        best_sim, best_chunk = scores[0]

        # Check for ambiguity: if second match is within 0.05 of best match from a different post
        post_oid = best_chunk.get("post_id")
        candidates = []
        for sim, c in scores[:4]:
            if sim >= best_sim - 0.06 and c.get("post_id") != post_oid:
                other_post = await self.db.social_posts.find_one({"_id": self._parse_oid(c.get("post_id"))})
                if other_post and other_post.get("title") and other_post["title"] not in candidates:
                    candidates.append(other_post["title"])

        post = await self.db.social_posts.find_one({
            "_id": self._parse_oid(post_oid),
            "post_status": "published",
        })
        if not post:
            return None

        if candidates:
            # Ambiguous match: multiple distinct posts are close
            main_title = post.get("title") or post.get("subject") or "This post"
            all_candidates = [main_title] + candidates
            return ResolvedPost(
                post_id=str(post["_id"]),
                platform_post_id=post.get("platform_post_id", ""),
                post_url=post.get("post_url", ""),
                title=post.get("title", ""),
                caption=post.get("caption", ""),
                summary=post.get("summary", ""),
                match_method="semantic_similarity",
                confidence=round(best_sim, 2),
                is_ambiguous=True,
                candidate_titles=all_candidates[:3],
            )

        return self._build_resolved(post, "semantic_similarity", round(best_sim, 2))

    def _build_resolved(self, post: dict, method: str, confidence: float) -> ResolvedPost:
        return ResolvedPost(
            post_id=str(post["_id"]),
            platform_post_id=post.get("platform_post_id", ""),
            post_url=post.get("post_url", ""),
            title=post.get("title", ""),
            caption=post.get("caption", ""),
            summary=post.get("summary", ""),
            match_method=method,
            confidence=confidence,
            is_ambiguous=False,
            candidate_titles=None,
        )

    def _parse_oid(self, val):
        from bson import ObjectId
        try:
            return ObjectId(str(val))
        except Exception:
            return val
