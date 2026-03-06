from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

from config import Settings


class MongoEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.client = AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)
        self.db: AsyncIOMotorDatabase = self.client[settings.mongo_db_name]

    async def ensure_indexes(self) -> None:
        await self.db.users.create_indexes(
            [
                IndexModel([('user_id', ASCENDING)], unique=True),
                IndexModel([('intent', ASCENDING), ('age', ASCENDING), ('gender', ASCENDING)]),
                IndexModel([('elo', DESCENDING)]),
                IndexModel([('referred_by', ASCENDING)]),
            ]
        )
        await self.db.swipes.create_indexes(
            [
                IndexModel([('user_id', ASCENDING), ('target_id', ASCENDING)], unique=True),
                IndexModel([('target_id', ASCENDING), ('action', ASCENDING)]),
                IndexModel([('created_at', DESCENDING)]),
            ]
        )
        await self.db.blocks.create_indexes(
            [
                IndexModel([('user_id', ASCENDING), ('blocked_id', ASCENDING)], unique=True),
            ]
        )
        await self.db.chat_logs.create_indexes(
            [
                IndexModel([('session_id', ASCENDING), ('created_at', DESCENDING)]),
                IndexModel([('created_at', DESCENDING)]),
            ]
        )

    async def upsert_user(self, user_id: int, data: dict[str, Any]) -> None:
        payload = {
            **data,
            'updated_at': datetime.now(timezone.utc),
            '$setOnInsert': {
                'created_at': datetime.now(timezone.utc),
                'elo': 1000,
                'reveal_tokens': 0,
                'vip_priority': 0,
                'streak_days': 0,
                'last_seen_date': None,
            },
        }
        set_on_insert = payload.pop('$setOnInsert')
        await self.db.users.update_one(
            {'user_id': user_id},
            {'$set': payload, '$setOnInsert': set_on_insert},
            upsert=True,
        )

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        return await self.db.users.find_one({'user_id': user_id})

    async def set_referral(self, user_id: int, referred_by: int) -> None:
        await self.db.users.update_one(
            {'user_id': user_id, 'referred_by': {'$exists': False}},
            {
                '$set': {'referred_by': referred_by},
                '$inc': {'reveal_tokens': 1, 'vip_priority': 1},
            },
        )
        await self.db.users.update_one(
            {'user_id': referred_by},
            {'$inc': {'reveal_tokens': 2, 'vip_priority': 2}},
        )

    async def add_swipe(self, user_id: int, target_id: int, action: str) -> None:
        await self.db.swipes.update_one(
            {'user_id': user_id, 'target_id': target_id},
            {
                '$set': {
                    'action': action,
                    'created_at': datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def has_mutual_like(self, user_id: int, target_id: int) -> bool:
        their_like = await self.db.swipes.find_one(
            {'user_id': target_id, 'target_id': user_id, 'action': {'$in': ['like', 'superlike']}}
        )
        return bool(their_like)

    async def add_block_pair(self, user_id: int, blocked_id: int, reason: str) -> None:
        await self.db.blocks.update_one(
            {'user_id': user_id, 'blocked_id': blocked_id},
            {'$set': {'reason': reason, 'created_at': datetime.now(timezone.utc)}},
            upsert=True,
        )

    async def are_blocked(self, a: int, b: int) -> bool:
        doc = await self.db.blocks.find_one(
            {
                '$or': [
                    {'user_id': a, 'blocked_id': b},
                    {'user_id': b, 'blocked_id': a},
                ]
            }
        )
        return bool(doc)

    async def log_chat(self, session_id: str, from_user: int, to_user: int, text: str, status: str = 'forwarded') -> None:
        await self.db.chat_logs.insert_one(
            {
                'session_id': session_id,
                'from_user': from_user,
                'to_user': to_user,
                'text': text,
                'status': status,
                'created_at': datetime.now(timezone.utc),
            }
        )

    async def close(self) -> None:
        self.client.close()
