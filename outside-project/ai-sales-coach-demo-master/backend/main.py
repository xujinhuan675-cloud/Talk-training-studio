# coding=utf-8
"""FastAPI 入口"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
import database
import seed_data
from routers import auth, training

app = FastAPI(title="AI销冠陪练中心 Demo", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(training.router)


@app.on_event("startup")
async def startup():
    await database.init_db()
    if config.AUTO_SEED_DEMO:
        async with database.get_db() as db:
            cur = await db.execute("SELECT COUNT(*) FROM users")
            user_count = (await cur.fetchone())[0]
        if user_count == 0:
            await seed_data.run()


@app.get("/health")
async def health():
    return {"status": "ok"}


dist_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if dist_dir.exists():
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
