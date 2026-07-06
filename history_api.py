from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
import os
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app_user:strong_password_here@db:5432/chainlit_db")

class ThreadOut(BaseModel):
    id: str
    name: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

@app.on_event("startup")
async def startup():
    app.state.pool = await asyncpg.create_pool(DATABASE_URL)

@app.on_event("shutdown")
async def shutdown():
    await app.state.pool.close()

@app.get("/threads", response_model=List[ThreadOut])
async def get_threads(x_user_id: str = Header(..., alias="X-User-ID")):
    async with app.state.pool.acquire() as conn:
        user = await conn.fetchrow('SELECT id FROM "User" WHERE identifier = $1', x_user_id)
        if not user:
            return []
        user_id = user['id']
        rows = await conn.fetch("""
            SELECT id, name, "createdAt" as created_at, "updatedAt" as updated_at
            FROM "Thread"
            WHERE "userId" = $1
            ORDER BY "createdAt" DESC
        """, user_id)
        return [ThreadOut(**dict(r)) for r in rows]

@app.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, x_user_id: str = Header(..., alias="X-User-ID")):
    async with app.state.pool.acquire() as conn:
        user = await conn.fetchrow('SELECT id FROM "User" WHERE identifier = $1', x_user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user_id = user['id']
        thread = await conn.fetchrow('SELECT "userId" FROM "Thread" WHERE id = $1', thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        if thread['userId'] != user_id:
            raise HTTPException(status_code=403, detail="Not your thread")
        await conn.execute('DELETE FROM "Thread" WHERE id = $1', thread_id)
        return {"success": True}
