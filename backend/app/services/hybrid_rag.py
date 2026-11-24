"""Hybrid RAG: Combines authoritative structured records with semantic vector retrieval."""

import re
from dataclasses import dataclass
from bson import ObjectId
import structlog

from app.services.embeddings import cosine_similarity, try_embedding

log = structlog.get_logger()

_STOP_WORDS = {"the", "and", "for", "with", "about", "tell", "this", "that", "can", "you", "our", "your", "are", "have", "what", "how"}


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
        user_id: str | ObjectId | None = None,
        query: str,
        resolved_post_id: str | None = None,
        query_embedding: list[float] | None = None,
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
                post_query = {
                    "_id": oid,
                    "workspace_id": workspace_id,
                    "post_status": "published",
                }
                if user_id:
                    uid_str = str(user_id)
                    uid_clauses = [{"user_id": uid_str}]
                    if ObjectId.is_valid(uid_str):
                        uid_clauses.append({"user_id": ObjectId(uid_str)})
                    post_query["$or"] = uid_clauses
                resolved_post = await self.db.social_posts.find_one(post_query)
            except Exception:
                resolved_post = None

            if resolved_post:
                # Priority 2: Verified offer associated with that post
                offer_query = {
                    "post_id": resolved_post_id,
                    "workspace_id": workspace_id,
                }
                if user_id:
                    uid_str = str(user_id)
                    uid_clauses = [{"user_id": uid_str}, {"user_id": None}]
                    if ObjectId.is_valid(uid_str):
                        uid_clauses.append({"user_id": ObjectId(uid_str)})
                    offer_query["$or"] = uid_clauses
                offer = await self.db.offers.find_one(offer_query)
                if offer:
                    st = str(offer.get("offer_status", "")).upper()
                    if st in ("INACTIVE", "EXPIRED"):
                        is_expired = True
                    elif st == "UNKNOWN_VALIDITY" or not offer.get("valid_until"):
                        unknown_validity = True

                # Priority 3: Related product details (Selective scoping to post & query)
                post_title_terms = [
                    w.lower()
                    for w in (resolved_post.get("title", "") + " " + resolved_post.get("subject", "")).split()
                    if len(w) > 3
                ]
                prod_query = {"workspace_id": workspace_id, "product_status": "active"}
                if user_id:
                    uid_str = str(user_id)
                    uid_clauses = [{"user_id": uid_str}, {"user_id": None}]
                    if ObjectId.is_valid(uid_str):
                        uid_clauses.append({"user_id": ObjectId(uid_str)})
                    prod_query["$or"] = uid_clauses
                cursor_prod = self.db.products.find(prod_query)
                all_prods = [p async for p in cursor_prod]
                
                # Filter products relevant to this post or query
                matched_prods = []
                for p in all_prods:
                    p_name = p.get("product_name", "").lower()
                    p_desc = p.get("description", "").lower()
                    if any(term in p_name or term in p_desc for term in post_title_terms):
                        matched_prods.append(p)
                    elif query and any(w.lower() in p_name for w in query.split() if len(w) > 3):
                        matched_prods.append(p)
                # Cap products to top 2 most relevant to prevent context bloat
                products = matched_prods[:2]

        # Priority 4: Semantic vector search over active knowledge chunks
        semantic_chunks = []
        if query.strip():
            if query_embedding is not None:
                query_emb = query_embedding
            else:
                query_emb = await try_embedding(query, self.settings)
            q_words = {
                w for w in re.findall(r"[a-z0-9₹%]{3,}", query.lower()) if w not in _STOP_WORDS
            }
            chunk_filter = {
                "workspace_id": workspace_id,
                "is_active": True,
            }
            if user_id:
                uid_str = str(user_id)
                uid_clauses = [{"user_id": uid_str}, {"user_id": None}]
                if ObjectId.is_valid(uid_str):
                    uid_clauses.append({"user_id": ObjectId(uid_str)})
                chunk_filter["$or"] = uid_clauses
            if resolved_post_id:
                chunk_filter["post_id"] = {"$ne": str(resolved_post_id)}

            cursor_chunks = self.db.knowledge_chunks.find(chunk_filter)
            scored_chunks = []
            seen_texts = set()
            async for ch in cursor_chunks:
                emb = ch.get("embedding")
                ch_text = (ch.get("text") or "").strip()
                if not ch_text or ch_text in seen_texts:
                    continue
                sim = cosine_similarity(query_emb, emb) if emb and query_emb else 0.0
                # Keyword overlap catches exact terms (prices, product names) that vectors can miss
                words = set(re.findall(r"[a-z0-9₹%]{3,}", ch_text.lower()))
                lex = len(q_words & words) / len(q_words) if q_words else 0.0
                if sim >= 0.28 or lex >= 0.5:  # relevance threshold
                    seen_texts.add(ch_text)
                    scored_chunks.append((sim + 0.3 * lex, ch))

            scored_chunks.sort(key=lambda s: s[0], reverse=True)
            semantic_chunks = [c for _, c in scored_chunks[:top_k]]

        # Priority 5: General business knowledge from dm_settings
        effective_user_id = user_id or (resolved_post.get("user_id") if resolved_post else None)
        dm_settings = None
        if effective_user_id and workspace_id:
            uid_str = str(effective_user_id)
            uid_obj = ObjectId(uid_str) if ObjectId.is_valid(uid_str) else None
            user_clause = [{"user_id": uid_str}]
            if uid_obj:
                user_clause.append({"user_id": uid_obj})
            dm_settings = await self.db.dm_settings.find_one({
                "$or": user_clause,
                "workspace_id": workspace_id,
            })
            if not dm_settings:
                dm_settings = await self.db.dm_settings.find_one({"$or": user_clause})
        elif effective_user_id:
            uid_str = str(effective_user_id)
            uid_obj = ObjectId(uid_str) if ObjectId.is_valid(uid_str) else None
            user_clause = [{"user_id": uid_str}]
            if uid_obj:
                user_clause.append({"user_id": uid_obj})
            dm_settings = await self.db.dm_settings.find_one({"$or": user_clause})
        elif workspace_id:
            dm_settings = await self.db.dm_settings.find_one({"workspace_id": workspace_id})

        dm_settings = dm_settings or {}
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
                st = str(offer.get("offer_status", "")).upper()
                if st in ("INACTIVE", "EXPIRED") or is_expired:
                    prompt_lines.append("\n=== OFFER STATUS: THIS OFFER HAS EXPIRED ===")
                    prompt_lines.append(
                        f"CRITICAL: THIS OFFER HAS EXPIRED. The offer '{offer.get('offer_description', 'offer')}' "
                        f"is NOT RUNNING / HAS EXPIRED (status: {st or 'EXPIRED'}). Politely inform the customer that this offer has expired. "
                        "Do NOT confirm that it is valid or currently active."
                    )
                else:
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

                    if unknown_validity:
                        prompt_lines.append(
                            "CRITICAL: The offer expiry is UNKNOWN. If the customer specifically asks whether "
                            "this offer is still available or valid today, do NOT confirm validity; trigger human escalation."
                        )

            if products:
                prompt_lines.append("\n=== ASSOCIATED PRODUCT DETAILS ===")
                for prod in products[:2]:
                    p_line = f"Product: {prod.get('product_name')}"
                    if prod.get("price") is not None:
                        p_line += f" | Price: ₹{prod['price']}"
                    if prod.get("description"):
                        p_line += f" | Details: {prod['description']}"
                    prompt_lines.append(p_line)

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

