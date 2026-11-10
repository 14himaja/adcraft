import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import UTC, datetime
from pymongo import AsyncMongoClient
from app.security.passwords import hash_password

async def main():
    client = AsyncMongoClient('mongodb://127.0.0.1:27017')
    db = client['acm']
    pwd_hash = hash_password('TestPassword123!')
    now = datetime.now(UTC)

    # 1. Tenant A (Laxmi - Synxait)
    user_a = await db.users.find_one({'email': 'laxmi@gmail.com'})
    if user_a:
        await db.users.update_one(
            {'_id': user_a['_id']},
            {'$set': {'password_hash': pwd_hash, 'active_workspace_id': 'synxait'}}
        )
        print("Tenant A (laxmi@gmail.com) password configured.")
        a_id = user_a['_id']
    else:
        res = await db.users.insert_one({
            'email': 'laxmi@gmail.com',
            'name': 'Laxmi Synxait',
            'password_hash': pwd_hash,
            'active_workspace_id': 'synxait',
            'created_at': now,
        })
        a_id = res.inserted_id
        print("Tenant A (laxmi@gmail.com) created.")

    # Ensure Tenant A has DM Settings enabled
    await db.dm_settings.update_one(
        {'user_id': a_id},
        {'$set': {
            'user_id': a_id,
            'workspace_id': 'synxait',
            'business_name': 'Synxait Fitness & Bakery',
            'tone': 'Friendly, concise, and helpful',
            'knowledge': 'Synxait offers premium fitness smartwatches and organic artisanal baked goods. Store hours 9 AM - 8 PM.',
            'handoff_message': 'Thanks for your message! A team member will reply to you here soon.',
            'enabled': True,
            'updated_at': now,
        }},
        upsert=True
    )

    # Ensure Tenant A connection has active simulated mode
    await db.meta_connections.update_one(
        {'user_id': a_id},
        {'$set': {
            'mode': 'fake',
            'status': 'ACTIVE',
            'page_id': '1415879818267624',
            'page_name': 'Social Ads Demo',
            'instagram_user_id': '17841416182311813',
            'instagram_username': 'synxait',
            'ad_account_id': 'act_29033614559610596',
            'updated_at': now,
        }},
        upsert=True
    )

    # 2. Tenant B (Boutique - Workspace B)
    user_b = await db.users.find_one({'email': 'tenant_b@example.com'})
    if user_b:
        await db.users.update_one(
            {'_id': user_b['_id']},
            {'$set': {'password_hash': pwd_hash, 'active_workspace_id': 'workspace_b'}}
        )
        b_id = user_b['_id']
        print("Tenant B (tenant_b@example.com) password configured.")
    else:
        res = await db.users.insert_one({
            'email': 'tenant_b@example.com',
            'name': 'Tenant B Business',
            'password_hash': pwd_hash,
            'active_workspace_id': 'workspace_b',
            'created_at': now,
        })
        b_id = res.inserted_id
        print("Tenant B (tenant_b@example.com) created.")

    # Ensure Tenant B has DM settings
    await db.dm_settings.update_one(
        {'user_id': b_id},
        {'$set': {
            'user_id': b_id,
            'workspace_id': 'workspace_b',
            'business_name': 'Velvet & Silk Boutique',
            'tone': 'Elegant, luxury concierge tone',
            'knowledge': 'Velvet & Silk offers high-end designer evening wear and custom bridal dresses in Milan.',
            'handoff_message': 'Our stylist will be delighted to assist you shortly.',
            'enabled': True,
            'updated_at': now,
        }},
        upsert=True
    )

    # Ensure Tenant B has a mock meta connection for workspace_b
    await db.meta_connections.update_one(
        {'user_id': b_id},
        {'$set': {
            'user_id': b_id,
            'workspace_id': 'workspace_b',
            'mode': 'fake',
            'status': 'ACTIVE',
            'page_id': 'tenant_b_page_999',
            'page_name': 'Velvet & Silk Boutique Page',
            'instagram_user_id': 'tenant_b_ig_888',
            'instagram_username': 'velvet_silk_official',
            'ad_account_id': 'act_tenant_b_777',
            'token_expires_at': datetime(2030, 1, 1, tzinfo=UTC),
            'updated_at': now,
        }},
        upsert=True
    )
    print("Test accounts and multi-tenant fixtures initialized successfully!")

if __name__ == '__main__':
    asyncio.run(main())
