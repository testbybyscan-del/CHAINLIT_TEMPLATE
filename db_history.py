import asyncpg
import logging
import json
from datetime import datetime
import os

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app_user:strong_password_here@db:5432/chainlit_db")

class HistorySaver:
    def __init__(self):
        self.pool = None

    async def init_pool(self):
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=10,
                command_timeout=30
            )
            logger.info("Пул соединений с БД создан")

    async def get_or_create_user(self, identifier: str) -> str:
        await self.init_pool()
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT id FROM "User" WHERE identifier = $1', identifier)
            if row:
                return row['id']
            user_id = identifier
            await conn.execute(
                'INSERT INTO "User" (id, identifier, metadata) VALUES ($1, $2, $3)',
                user_id, identifier, json.dumps({})
            )
            logger.info(f"Создан пользователь: {identifier}")
            return user_id

    async def get_or_create_thread(self, thread_id: str, user_id: str, name: str = None) -> str:
        await self.init_pool()
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT id FROM "Thread" WHERE id = $1', thread_id)
            if row:
                return thread_id
            thread_name = name or f"Чат {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            now = datetime.now()
            await conn.execute(
                'INSERT INTO "Thread" (id, "userId", name, "createdAt", "updatedAt", metadata) VALUES ($1, $2, $3, $4, $5, $6)',
                thread_id, user_id, thread_name, now, now, '{}'
            )
            logger.info(f"Создан тред: {thread_id} для пользователя {user_id}")
            return thread_id

    async def save_step(self, thread_id: str, step_id: str, name: str, type: str, content: str, parent_id: str = None):
        await self.init_pool()
        async with self.pool.acquire() as conn:
            now = datetime.now()
            await conn.execute(
                'INSERT INTO "Step" (id, "threadId", name, type, output, "parentId", "createdAt", "updatedAt", "startTime", "endTime", metadata) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)',
                step_id, thread_id, name, type, content, parent_id, now, now, now, now, '{}'
            )
            logger.debug(f"Сохранён шаг {step_id} в треде {thread_id}")

    async def close(self):
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
            logger.info("Пул соединений закрыт")
