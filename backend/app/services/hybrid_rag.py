"""Hybrid RAG: Combines authoritative structured records with semantic vector retrieval."""

from dataclasses import dataclass
from bson import ObjectId
import structlog

from app.services.embeddings import cosine_similarity, generate_embedding

log = structlog.get_logger()


@dataclass
class HybridContext:
    workspace_id: str
    resolved_post: dict | None
    offer: dict | None
    products: list[dict]
    semantic_chunks: list[dict]
    general_knowledge: str
    prompt_context: str
    unknown_validity: bool = False
    is_expired: bool = False


class HybridRAG:
    """Retrieval service combining structured database facts and vector embeddings."""

    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    async def retrieve(
        self,
        *,
        workspace_id: str,
        query: str,
        resolved_post_id: str | None = None,
        top_k: int = 4,
    ) -> HybridContext:
        """Retrieves and assembles grounded hybrid context."""
        resolved_post = None
        offer = None
        products = []
        unknown_validity = False
        is_expired = False

        # Priority 1: Authoritative structured post from DB
        if resolved_post_id:
            try:
                oid = ObjectId(resolved_post_id)
                resolved_post = await self.db.social_posts.find_one({
                    "_id": oid,
                    "workspace_id": workspace_id,
                    "post_status": "published",
                })
            except Exception:
                resolved_post = None

            if resolved_post:
                # Priority 2: Verified offer associated with that post
                offer = await self.db.offers.find_one({
                    "post_id": resolved_post_id,
                    "workspace_id": workspace_id,
                })
                if offer:
                    if offer.get("offer_status") == "UNKNOWN_VALIDITY" or not offer.get("valid_until"):
                        unknown_validity = True
                    elif offer.get("offer_status") == "EXPIRED":
                        is_expired = True

                # Priority 3: Related product details
                cursor_prod = self.db.products.find({"workspace_id": workspace_id, "product_status": "active"})
                products = [p async for p in cursor_prod]

        # Priority 4: Semantic vector search over active knowledge chunks
        semantic_chunks = []
        if query.strip():
            query_emb = await generate_embedding(query, self.settings)
            chunk_filter = {
                "workspace_id": workspace_id,
                "is_active": True,
            }
            # Exclude current post chunks if already retrieved structured
            if resolved_post_id:
                chunk_filter["post_id"] = {"$ne": resolved_post_id}

            cursor_chunks = self.db.knowledge_chunks.find(chunk_filter)
            scored_chunks = []
            async for ch in cursor_chunks:
                emb = ch.get("embedding")
                if emb:
                    sim = cosine_similarity(query_emb, emb)
                    if sim >= 0.28:  # relevance threshold
                        scored_chunks.append((sim, ch))

            scored_chunks.sort(key=lambda s: s[0], reverse=True)
            semantic_chunks = [c for _, c in scored_chunks[:top_k]]

        # Priority 5: General business knowledge from dm_settings
        dm_settings = await self.db.dm_settings.find_one({"user_id": resolved_post.get("user_id") if resolved_post else None})
        if not dm_settings:
            # Fallback to query by workspace
            dm_settings = await self.db.dm_settings.find_one() or {}
        general_knowledge = dm_settings.get("knowledge", "")
        tone = dm_settings.get("tone", "Friendly and concise")
        business_name = dm_settings.get("business_name", "")

        # Format prompt_context
        prompt_lines = []
        if business_name:
            prompt_lines.append(f"Business: {business_name}")
        if tone:
            prompt_lines.append(f"Tone: {tone}")
        if general_knowledge:
            prompt_lines.append(f"General Business Information:\n{general_knowledge}")

        if resolved_post:
            prompt_lines.append("\n=== CURRENT DISCUSSED POST (SHARED BY CUSTOMER) ===")
            prompt_lines.append(f"Post Title: {resolved_post.get('title', 'N/A')}")
            prompt_lines.append(f"Platform URL: {resolved_post.get('post_url', 'N/A')}")
            prompt_lines.append(f"Summary: {resolved_post.get('summary', 'N/A')}")
            if resolved_post.get("caption"):
                prompt_lines.append(f"Original Caption:\n{resolved_post['caption']}")

            if offer:
                prompt_lines.append("\n=== VERIFIED OFFER DETAILS FOR THIS POST ===")
                prompt_lines.append(f"Offer: {offer.get('offer_description')}")
                if offer.get("price") is not None:
                    prompt_lines.append(f"Price: ₹{offer['price']}")
                if offer.get("discount"):
                    prompt_lines.append(f"Discount: {offer['discount']}")
                if offer.get("valid_until"):
                    prompt_lines.append(f"Valid Until: {offer['valid_until']}")
                else:
                    prompt_lines.append("Valid Until: UNKNOWN (No expiry date was specified by the owner)")
                prompt_lines.append(f"Offer Status: {offer.get('offer_status')}")

                if offer.get("terms_and_conditions"):
                    prompt_lines.append(f"Terms & Conditions: {', '.join(offer['terms_and_conditions'])}")

                if is_expired:
                    prompt_lines.append("CRITICAL: THIS OFFER HAS EXPIRED. Do NOT claim it is currently active.")
                elif unknown_validity:
                    prompt_lines.append(
                        "CRITICAL: The offer expiry is UNKNOWN. If the customer specifically asks whether "
                        "this offer is still available or valid today, do NOT confirm validity; trigger human escalation."
                    )

        if semantic_chunks:
            prompt_lines.append("\n=== RELATED BUSINESS KNOWLEDGE & FAQS ===")
            for i, ch in enumerate(semantic_chunks, 1):
                prompt_lines.append(f"{i}. {ch['text']}")

        prompt_context = "\n".join(prompt_lines)

        return HybridContext(
            workspace_id=workspace_id,
            resolved_post=resolved_post,
            offer=offer,
            products=products,
            semantic_chunks=semantic_chunks,
            general_knowledge=general_knowledge,
            prompt_context=prompt_context,
            unknown_validity=unknown_validity,
            is_expired=is_expired,
        )

