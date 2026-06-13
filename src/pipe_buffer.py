from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pipe_messages (
    id BIGSERIAL PRIMARY KEY,
    dedup_key TEXT NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_pipe_pending
    ON pipe_messages (status, next_retry)
    WHERE status = 'pending';
"""


class PipeBuffer:
    MAX_ATTEMPTS = 10

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._database_url, min_size=1, max_size=5)
        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        logger.info("PostgreSQL буфер подключён")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def enqueue(self, dedup_key: str, payload: dict[str, Any]) -> bool:
        if not self._pool:
            return False
        query = """
            INSERT INTO pipe_messages (dedup_key, payload)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (dedup_key) DO NOTHING
            RETURNING id
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, dedup_key, json.dumps(payload, ensure_ascii=False))
        return row is not None

    async def fetch_pending(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self._pool:
            return []
        query = """
            SELECT id, dedup_key, payload, attempts
            FROM pipe_messages
            WHERE status = 'pending'
              AND next_retry <= NOW()
            ORDER BY created_at
            LIMIT $1
            FOR UPDATE SKIP LOCKED
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
        return [
            {
                "id": row["id"],
                "dedup_key": row["dedup_key"],
                "payload": json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"],
                "attempts": row["attempts"],
            }
            for row in rows
        ]

    async def mark_sent(self, row_id: int) -> None:
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE pipe_messages
                SET status = 'sent', sent_at = NOW(), last_error = NULL
                WHERE id = $1
                """,
                row_id,
            )

    async def mark_retry(self, row_id: int, attempts: int, error: str) -> None:
        if not self._pool:
            return
        if attempts >= self.MAX_ATTEMPTS:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE pipe_messages
                    SET status = 'failed', attempts = $2, last_error = $3
                    WHERE id = $1
                    """,
                    row_id,
                    attempts,
                    error[:500],
                )
            return

        delay_sec = min(300, 5 * (2 ** min(attempts, 6)))
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE pipe_messages
                SET attempts = $2,
                    last_error = $3,
                    next_retry = NOW() + ($4 || ' seconds')::interval
                WHERE id = $1
                """,
                row_id,
                attempts,
                error[:500],
                str(delay_sec),
            )

    async def stats(self) -> dict[str, int]:
        if not self._pool:
            return {}
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT status, COUNT(*) AS count
                FROM pipe_messages
                GROUP BY status
                """
            )
        return {row["status"]: row["count"] for row in rows}
