# coding=utf-8
"""认证相关接口"""

import hashlib
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

import config
from database import get_db

router = APIRouter()


def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


def ok(data=None):
    return {"code": 200, "message": "success", "data": data or {}}


def err(msg: str, code: int = 400):
    return {"code": code, "message": msg, "data": {}}


async def get_current_user(manage_token: Optional[str] = Header(None, alias="Manage-Token")):
    """依赖注入：从 Manage-Token 头获取当前用户"""
    if not manage_token:
        raise HTTPException(status_code=401, detail="未登录")
    async with get_db() as db:
        db.row_factory = lambda c, r: dict(zip([d[0] for d in c.description], r))
        cursor = await db.execute(
            "SELECT id, name, username, role, group_id FROM users WHERE token=?",
            (manage_token,)
        )
        user = await cursor.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    return user


@router.post("/Client/login")
async def login(request: Request):
    body = await request.form()
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", "")).strip()
    if not username or not password:
        return err("用户名和密码不能为空")

    hashed = _md5(password)
    async with get_db() as db:
        db.row_factory = lambda c, r: dict(zip([d[0] for d in c.description], r))
        cursor = await db.execute(
            "SELECT id, name, username, role, group_id, token FROM users WHERE username=? AND password=?",
            (username, hashed)
        )
        user = await cursor.fetchone()

    if not user:
        return err("用户名或密码错误")

    return ok({
        "token": user["token"],
        "name": user["name"],
        "role": user["role"],
        "group_id": user["group_id"],
    })


@router.post("/Client/getUserInfo")
async def get_user_info(user=None, manage_token: Optional[str] = Header(None, alias="Manage-Token")):
    if not manage_token:
        return err("未登录", 20000)
    async with get_db() as db:
        db.row_factory = lambda c, r: dict(zip([d[0] for d in c.description], r))
        cursor = await db.execute(
            "SELECT u.id, u.name, u.username, u.role, u.group_id, g.name as group_name "
            "FROM users u LEFT JOIN groups g ON u.group_id=g.id WHERE u.token=?",
            (manage_token,)
        )
        user = await cursor.fetchone()
    if not user:
        return err("Token 无效", 20000)
    return ok(user)
