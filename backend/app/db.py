from pymongo import AsyncMongoClient
from pymongo.errors import OperationFailure

from app.config import Settings

INDEXES: dict[str, list[tuple[list[tuple[str, int]], dict]]] = {
    "users": [([("email", 1)], {"unique": True})],
    "meta_connections": [
        ([("user_id", 1)], {"unique": True}),
        ([("instagram_user_id", 1)], {}),
        ([("page_id", 1)], {}),
    ],
    "user_ai_settings": [([("user_id", 1)], {"unique": True})],
    "campaigns": [([("user_id", 1), ("status", 1)], {})],
    "campaign_versions": [([("campaign_id", 1), ("version", 1)], {"unique": True})],
    "messages": [([("campaign_id", 1), ("created_at", 1)], {})],
    "approvals": [([("campaign_id", 1), ("action", 1)], {})],
    "publish_runs": [([("campaign_id", 1), ("version", 1)], {"unique": True})],
    "insights_daily": [
        ([("meta_object_id", 1), ("level", 1), ("day", 1)], {"unique": True}),
        ([("campaign_id", 1), ("day", 1)], {}),
    ],
    "analysis_reports": [([("campaign_id", 1), ("created_at", 1)], {})],
    "optimization_proposals": [([("campaign_id", 1), ("status", 1)], {})],
    "agent_runs": [([("campaign_id", 1), ("created_at", 1)], {})],
    "dm_settings": [([("user_id", 1)], {"unique": True})],
    "dm_threads": [
        ([("user_id", 1), ("customer_id", 1)], {"unique": True}),
        ([("user_id", 1), ("updated_at", -1)], {}),
    ],
    "dm_seen": [([("at", 1)], {"expireAfterSeconds": 7 * 86400})],
    "organic_posts": [([("user_id", 1), ("created_at", -1)], {})],
    "social_posts": [
        ([("workspace_id", 1), ("platform", 1), ("platform_post_id", 1)], {"unique": True}),
        ([("workspace_id", 1), ("post_status", 1)], {}),
        ([("campaign_id", 1)], {}),
    ],
    "offers": [
        ([("workspace_id", 1), ("post_id", 1)], {}),
        ([("workspace_id", 1), ("offer_status", 1)], {}),
    ],
    "products": [
        ([("workspace_id", 1), ("product_name", 1)], {}),
    ],
    "knowledge_chunks": [
        ([("workspace_id", 1), ("is_active", 1)], {}),
        ([("workspace_id", 1), ("business_id", 1)], {}),
        ([("workspace_id", 1), ("platform_post_id", 1)], {}),
        ([("workspace_id", 1), ("campaign_id", 1)], {}),
        ([("post_id", 1)], {}),
    ],
    "knowledge_jobs": [
        ([("workspace_id", 1), ("status", 1)], {}),
        ([("post_id", 1)], {}),
    ],
    "post_deletion_audit": [
        ([("workspace_id", 1), ("deleted_at", -1)], {}),
    ],
    "audit_log": [([("campaign_id", 1), ("ts", 1)], {}), ([("correlation_id", 1)], {})],
}


def connect(settings: Settings) -> AsyncMongoClient:
    return AsyncMongoClient(settings.mongodb_uri, tz_aware=True)


async def ensure_indexes(db) -> None:
    for collection, specs in INDEXES.items():
        for keys, options in specs:
            try:
                await db[collection].create_index(keys, **options)
            except OperationFailure as exc:
                # MongoDB cannot change an existing index's unique option in place.
                # Upgrade a same-key non-unique index safely after checking for duplicates.
                if exc.code != 86 or not options.get("unique"):
                    raise
                index_cursor = await db[collection].list_indexes()
                indexes = [index async for index in index_cursor]
                existing = next(
                    (index for index in indexes if list(index["key"].items()) == keys), None
                )
                if not existing or existing.get("unique"):
                    raise
                duplicate_cursor = await db[collection].aggregate([
                    {"$group": {"_id": f"${keys[0][0]}", "count": {"$sum": 1}}},
                    {"$match": {"count": {"$gt": 1}}},
                    {"$limit": 1},
                ])
                duplicates = await duplicate_cursor.to_list(1)
                if duplicates:
                    raise RuntimeError(
                        f"Cannot make {collection}.{existing['name']} unique: duplicate records exist"
                    ) from exc
                await db[collection].drop_index(existing["name"])
                await db[collection].create_index(keys, **options)
