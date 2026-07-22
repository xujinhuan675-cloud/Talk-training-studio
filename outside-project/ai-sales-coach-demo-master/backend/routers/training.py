# coding=utf-8
"""
陪练中心全部业务接口（对齐 ai_service_vue/src/api/training.js 的 URL 契约）

接口列表：
  维度：dimensionList / dimensionAdd / dimensionEdit / dimensionDelete / dimensionStatus
  场景：scenarioList / scenarioAdd / scenarioEdit / scenarioDelete / scenarioStatus / scenarioListForUser
  会话：startSession / sendMessage / messageList / endSession / sessionResult / sessionDetail
  统计：sessionHistory / leaderboardTeam / leaderboardPersonal / scenarioTeamAvg / employeeList / groupList
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

import config
from database import get_db
from routers.auth import get_current_user
from services.ai_service import ScoreParseError, build_fallback_score, get_customer_reply, score_session

router = APIRouter()


# ───────── 辅助 ─────────

class AIQuotaExceeded(Exception):
    pass

def ok(data=None):
    return {"code": 200, "message": "success", "data": data if data is not None else {}}


def err(msg: str, code: int = 400):
    return {"code": code, "message": msg, "data": {}}


def _row_factory(cursor, row):
    return dict(zip([d[0] for d in cursor.description], row))


async def _auth(manage_token: Optional[str]) -> dict:
    if not manage_token:
        raise HTTPException(status_code=401, detail="未登录")
    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute(
            "SELECT id, name, role, group_id FROM users WHERE token=?", (manage_token,)
        )
        user = await cur.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Token 无效")
    return user


async def _get_form(request: Request) -> dict:
    form = await request.form()
    return {k: v for k, v in form.items()}


async def _consume_ai_quota(user: dict, request: Request, action: str):
    """Public demo guardrail: limit real AI calls by account and IP per day."""
    if config.AI_MODE != "real":
        return

    scopes = [
        ("user", str(user["id"]), config.AI_DAILY_LIMIT_PER_USER),
        ("ip", request.client.host if request.client else "unknown", config.AI_DAILY_LIMIT_PER_IP),
    ]
    today = datetime.now().strftime("%Y-%m-%d")

    async with get_db() as db:
        db.row_factory = _row_factory
        for scope_type, scope_key, limit in scopes:
            if limit <= 0:
                continue
            cur = await db.execute(
                """SELECT count FROM ai_usage
                   WHERE usage_date=? AND scope_type=? AND scope_key=? AND action=?""",
                (today, scope_type, scope_key, action),
            )
            row = await cur.fetchone()
            if row and row["count"] >= limit:
                raise AIQuotaExceeded("今日公开演示 AI 额度已用完，请稍后再试或本地配置自己的 Qwen Key。")

        for scope_type, scope_key, limit in scopes:
            if limit <= 0:
                continue
            await db.execute(
                """INSERT INTO ai_usage(usage_date, scope_type, scope_key, action, count, updated_at)
                   VALUES(?,?,?,?,1,CURRENT_TIMESTAMP)
                   ON CONFLICT(usage_date, scope_type, scope_key, action)
                   DO UPDATE SET count=count+1, updated_at=CURRENT_TIMESTAMP""",
                (today, scope_type, scope_key, action),
            )
        await db.commit()


# ═══════════════════════════════════════════════════════════════
#  维度管理
# ═══════════════════════════════════════════════════════════════

@router.post("/Client/training/dimensionList")
async def dimension_list(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    await _auth(manage_token)
    form = await _get_form(request)
    page = int(form.get("page", 1))
    limit = int(form.get("limit", 50))
    offset = (page - 1) * limit

    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute(
            "SELECT COUNT(*) as cnt FROM training_dimension WHERE status != -1"
        )
        total = (await cur.fetchone())["cnt"]
        cur = await db.execute(
            "SELECT d.*, (SELECT COUNT(*) FROM scenario_dimension sd WHERE sd.dimension_id=d.id) as ref_count "
            "FROM training_dimension d WHERE d.status != -1 ORDER BY d.id LIMIT ? OFFSET ?",
            (limit, offset)
        )
        rows = await cur.fetchall()

    return ok({"list": rows, "total": total})


@router.post("/Client/training/dimensionAdd")
async def dimension_add(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    await _auth(manage_token)
    form = await _get_form(request)
    name = str(form.get("name", "")).strip()
    description = str(form.get("description", "")).strip()
    status = int(form.get("status", 1))
    if not name:
        return err("维度名称不能为空")

    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO training_dimension(name, description, status) VALUES(?,?,?)",
            (name, description, status)
        )
        await db.commit()
        new_id = cur.lastrowid

    return ok({"id": new_id})


@router.post("/Client/training/dimensionEdit")
async def dimension_edit(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    await _auth(manage_token)
    form = await _get_form(request)
    dim_id = int(form.get("id", 0))
    name = str(form.get("name", "")).strip()
    description = str(form.get("description", "")).strip()
    status = form.get("status")

    if not dim_id or not name:
        return err("参数缺失")

    async with get_db() as db:
        if status is not None:
            await db.execute(
                "UPDATE training_dimension SET name=?, description=?, status=? WHERE id=?",
                (name, description, int(status), dim_id)
            )
        else:
            await db.execute(
                "UPDATE training_dimension SET name=?, description=? WHERE id=?",
                (name, description, dim_id)
            )
        await db.commit()

    return ok()


@router.post("/Client/training/dimensionDelete")
async def dimension_delete(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    await _auth(manage_token)
    form = await _get_form(request)
    dim_id = int(form.get("id", 0))
    if not dim_id:
        return err("参数缺失")

    async with get_db() as db:
        await db.execute("UPDATE training_dimension SET status=-1 WHERE id=?", (dim_id,))
        await db.commit()

    return ok()


@router.post("/Client/training/dimensionStatus")
async def dimension_status(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    await _auth(manage_token)
    form = await _get_form(request)
    dim_id = int(form.get("id", 0))
    status = int(form.get("status", 1))
    if not dim_id:
        return err("参数缺失")

    async with get_db() as db:
        await db.execute("UPDATE training_dimension SET status=? WHERE id=?", (status, dim_id))
        await db.commit()

    return ok()


# ═══════════════════════════════════════════════════════════════
#  场景管理
# ═══════════════════════════════════════════════════════════════

async def _fetch_scenario_with_dims(db, scenario_id: int) -> Optional[dict]:
    db.row_factory = _row_factory
    cur = await db.execute(
        "SELECT * FROM training_scenario WHERE id=? AND status != -1", (scenario_id,)
    )
    sc = await cur.fetchone()
    if not sc:
        return None
    # 加载关联维度配置
    cur = await db.execute(
        """SELECT sd.dimension_id as id, d.name, sd.weight
           FROM scenario_dimension sd
           JOIN training_dimension d ON d.id=sd.dimension_id
           WHERE sd.scenario_id=?""",
        (scenario_id,)
    )
    dims = await cur.fetchall()
    sc["dimension_config"] = dims
    return sc


@router.post("/Client/training/scenarioList")
async def scenario_list(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    await _auth(manage_token)
    form = await _get_form(request)
    page = int(form.get("page", 1))
    limit = int(form.get("limit", 20))
    offset = (page - 1) * limit
    keyword = str(form.get("keyword", "")).strip()
    difficulty = form.get("difficulty")

    where = ["status != -1"]
    params = []
    if keyword:
        where.append("name LIKE ?")
        params.append(f"%{keyword}%")
    if difficulty:
        where.append("difficulty=?")
        params.append(int(difficulty))

    where_sql = " AND ".join(where)

    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute(f"SELECT COUNT(*) as cnt FROM training_scenario WHERE {where_sql}", params)
        total = (await cur.fetchone())["cnt"]
        cur = await db.execute(
            f"SELECT * FROM training_scenario WHERE {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset]
        )
        rows = await cur.fetchall()
        for sc in rows:
            cur2 = await db.execute(
                "SELECT sd.dimension_id as id, d.name, sd.weight FROM scenario_dimension sd "
                "JOIN training_dimension d ON d.id=sd.dimension_id WHERE sd.scenario_id=?",
                (sc["id"],)
            )
            sc["dimension_config"] = await cur2.fetchall()

    return ok({"list": rows, "total": total})


@router.post("/Client/training/scenarioAdd")
async def scenario_add(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    await _auth(manage_token)
    form = await _get_form(request)
    name = str(form.get("name", "")).strip()
    if not name:
        return err("场景名称不能为空")

    difficulty = int(form.get("difficulty", 2))
    persona = str(form.get("persona", "")).strip()
    scene_desc = str(form.get("scene_desc", "")).strip()
    opening = str(form.get("opening") or form.get("opening_message") or "").strip() or None
    is_required = int(form.get("is_required", 0))
    status = int(form.get("status", 1))
    # dimension_config: JSON string [{"id":1,"weight":25}, ...]
    dim_config_raw = str(form.get("dimension_config", "[]"))
    try:
        dim_config = json.loads(dim_config_raw)
    except Exception:
        dim_config = []

    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO training_scenario(name, difficulty, persona, scene_desc, opening, is_required, status) "
            "VALUES(?,?,?,?,?,?,?)",
            (name, difficulty, persona, scene_desc, opening, is_required, status)
        )
        new_id = cur.lastrowid
        for d in dim_config:
            dim_id = d.get("id") or d.get("dimension_id")
            if not dim_id:
                continue
            await db.execute(
                "INSERT INTO scenario_dimension(scenario_id, dimension_id, weight) VALUES(?,?,?)",
                (new_id, int(dim_id), int(d["weight"]))
            )
        await db.commit()

    return ok({"id": new_id})


@router.post("/Client/training/scenarioEdit")
async def scenario_edit(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    await _auth(manage_token)
    form = await _get_form(request)
    sc_id = int(form.get("id", 0))
    if not sc_id:
        return err("参数缺失")

    name = str(form.get("name", "")).strip()
    difficulty = int(form.get("difficulty", 2))
    persona = str(form.get("persona", "")).strip()
    scene_desc = str(form.get("scene_desc", "")).strip()
    opening = str(form.get("opening") or form.get("opening_message") or "").strip() or None
    is_required = int(form.get("is_required", 0))
    status = int(form.get("status", 1))
    dim_config_raw = str(form.get("dimension_config", "[]"))
    try:
        dim_config = json.loads(dim_config_raw)
    except Exception:
        dim_config = []

    async with get_db() as db:
        await db.execute(
            "UPDATE training_scenario SET name=?,difficulty=?,persona=?,scene_desc=?,opening=?,"
            "is_required=?,status=? WHERE id=?",
            (name, difficulty, persona, scene_desc, opening, is_required, status, sc_id)
        )
        await db.execute("DELETE FROM scenario_dimension WHERE scenario_id=?", (sc_id,))
        for d in dim_config:
            dim_id = d.get("id") or d.get("dimension_id")
            if not dim_id:
                continue
            await db.execute(
                "INSERT INTO scenario_dimension(scenario_id, dimension_id, weight) VALUES(?,?,?)",
                (sc_id, int(dim_id), int(d["weight"]))
            )
        await db.commit()

    return ok()


@router.post("/Client/training/scenarioDelete")
async def scenario_delete(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    await _auth(manage_token)
    form = await _get_form(request)
    sc_id = int(form.get("id", 0))
    if not sc_id:
        return err("参数缺失")

    async with get_db() as db:
        await db.execute("UPDATE training_scenario SET status=-1 WHERE id=?", (sc_id,))
        await db.commit()

    return ok()


@router.post("/Client/training/scenarioStatus")
async def scenario_status(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    await _auth(manage_token)
    form = await _get_form(request)
    sc_id = int(form.get("id", 0))
    status = int(form.get("status", 1))
    if not sc_id:
        return err("参数缺失")

    async with get_db() as db:
        await db.execute("UPDATE training_scenario SET status=? WHERE id=?", (status, sc_id))
        await db.commit()

    return ok()


@router.post("/Client/training/scenarioListForUser")
async def scenario_list_for_user(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    """坐席可见的场景列表（含个人练习次数和最新分数）"""
    user = await _auth(manage_token)
    form = await _get_form(request)
    keyword = str(form.get("keyword", "")).strip()
    difficulty = form.get("difficulty")
    is_required = form.get("is_required")

    where = ["sc.status = 1"]
    params: list = []
    if keyword:
        where.append("sc.name LIKE ?")
        params.append(f"%{keyword}%")
    if difficulty != "" and difficulty is not None:
        where.append("sc.difficulty=?")
        params.append(int(difficulty))
    if is_required != "" and is_required is not None:
        where.append("sc.is_required=?")
        params.append(int(is_required))

    where_sql = " AND ".join(where)

    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute(
            f"SELECT * FROM training_scenario sc WHERE {where_sql} ORDER BY sc.is_required DESC, sc.difficulty ASC",
            params
        )
        scenarios = await cur.fetchall()

        for sc in scenarios:
            # 练习次数
            cur2 = await db.execute(
                "SELECT COUNT(*) as cnt FROM training_session WHERE user_id=? AND scenario_id=? AND status IN (1,2,3)",
                (user["id"], sc["id"])
            )
            sc["my_practice_count"] = (await cur2.fetchone())["cnt"]
            # 最新评分（取最新一次 status=2 的会话分数）
            cur3 = await db.execute(
                """SELECT ts.total_score FROM training_score ts
                   JOIN training_session sess ON sess.session_id=ts.session_id
                   WHERE sess.user_id=? AND sess.scenario_id=? AND ts.status=1
                   ORDER BY sess.ended_at DESC LIMIT 1""",
                (user["id"], sc["id"])
            )
            score_row = await cur3.fetchone()
            sc["my_latest_score"] = score_row["total_score"] if score_row else None

    return ok(scenarios)


# ═══════════════════════════════════════════════════════════════
#  演练会话
# ═══════════════════════════════════════════════════════════════

@router.post("/Client/training/startSession")
async def start_session(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    user = await _auth(manage_token)
    form = await _get_form(request)
    sc_id = int(form.get("scenario_id", 0))
    if not sc_id:
        return err("场景ID不能为空")

    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute(
            "SELECT * FROM training_scenario WHERE id=? AND status=1", (sc_id,)
        )
        sc = await cur.fetchone()
        if not sc:
            return err("场景不存在或已停用")

        # 建 session
        session_id = str(uuid.uuid4())
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "INSERT INTO training_session(session_id, user_id, scenario_id, status, created_at) VALUES(?,?,?,?,?)",
            (session_id, user["id"], sc_id, 0, created_at)
        )

        # 如果有开场白，插入第一条 customer 消息
        has_opening = bool(sc.get("opening"))
        if has_opening:
            await db.execute(
                "INSERT INTO training_message(session_id, seq, role, content) VALUES(?,1,1,?)",
                (session_id, sc["opening"])
            )
            await db.execute(
                "UPDATE training_session SET message_count=1 WHERE session_id=?", (session_id,)
            )

        await db.commit()

    return ok({
        "session_id": session_id,
        "scenario": sc,
        "has_opening": has_opening,
        "opening_message": sc.get("opening") if has_opening else None,
    })


@router.post("/Client/training/sendMessage")
async def send_message(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    """
    存储用户(sales)消息，后台异步调用 Qwen 获取客户回复。
    立即返回 {seat_message, pending_customer_reply: True}，
    前端通过 messageList 轮询拿到 AI 回复。
    """
    user = await _auth(manage_token)
    form = await _get_form(request)
    session_id = str(form.get("session_id", "")).strip()
    content = str(form.get("content", "")).strip()
    if not session_id or not content:
        return err("参数缺失")
    try:
        await _consume_ai_quota(user, request, "chat")
    except AIQuotaExceeded as e:
        return err(str(e), 429)

    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute(
            "SELECT * FROM training_session WHERE session_id=? AND user_id=? AND status=0",
            (session_id, user["id"])
        )
        sess = await cur.fetchone()
        if not sess:
            return err("会话不存在或已结束")

        # 当前最大 seq
        cur = await db.execute(
            "SELECT MAX(seq) as max_seq FROM training_message WHERE session_id=?", (session_id,)
        )
        row = await cur.fetchone()
        next_seq = (row["max_seq"] or 0) + 1

        # 插入 sales 消息
        await db.execute(
            "INSERT INTO training_message(session_id, seq, role, content) VALUES(?,?,2,?)",
            (session_id, next_seq, content)
        )
        await db.execute(
            "UPDATE training_session SET message_count=message_count+1 WHERE session_id=?",
            (session_id,)
        )
        await db.commit()

        # 取场景信息
        cur = await db.execute(
            "SELECT * FROM training_scenario WHERE id=?", (sess["scenario_id"],)
        )
        sc = await cur.fetchone()

        # 取全部历史消息（用于 AI 上下文）
        cur = await db.execute(
            "SELECT role, content FROM training_message WHERE session_id=? ORDER BY seq",
            (session_id,)
        )
        all_msgs = await cur.fetchall()

    seat_message = {"seq": next_seq, "role": 2, "content": content}

    # 构造 AI 消息格式（role: 1→customer, 2→sales 转为 sales/customer）
    ai_msgs = [
        {"role": "sales" if m["role"] == 2 else "customer", "content": m["content"]}
        for m in all_msgs
    ]

    # 启动后台任务
    asyncio.create_task(_async_get_customer_reply(session_id, sc, ai_msgs, next_seq + 1))

    return ok({
        "seat_message": seat_message,
        "pending_customer_reply": True,
    })


async def _async_get_customer_reply(session_id: str, sc: dict, messages: list, next_seq: int):
    """后台任务：调用 Qwen 获取客户回复并写库"""
    try:
        reply = await get_customer_reply(
            persona=sc.get("persona", ""),
            scene_desc=sc.get("scene_desc", ""),
            difficulty=sc.get("difficulty", 2),
            messages=messages,
        )
        async with get_db() as db:
            await db.execute(
                "INSERT INTO training_message(session_id, seq, role, content) VALUES(?,?,1,?)",
                (session_id, next_seq, reply)
            )
            await db.execute(
                "UPDATE training_session SET message_count=message_count+1 WHERE session_id=?",
                (session_id,)
            )
            await db.commit()
    except Exception as e:
        import logging
        logging.error(f"AI 客户回复失败 session={session_id}: {e}")
        fallback = "我这边暂时没有收到完整回复。你可以先继续说明方案的价值、价格和保障，我再根据你的介绍追问。"
        try:
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO training_message(session_id, seq, role, content) VALUES(?,?,1,?)",
                    (session_id, next_seq, fallback)
                )
                await db.execute(
                    "UPDATE training_session SET message_count=message_count+1 WHERE session_id=?",
                    (session_id,)
                )
                await db.commit()
        except Exception as write_error:
            logging.error(f"AI 兜底回复写入失败 session={session_id}: {write_error}")


@router.post("/Client/training/messageList")
async def message_list(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    """返回 last_seq 之后的新消息（用于前端轮询 AI 客户回复）"""
    user = await _auth(manage_token)
    form = await _get_form(request)
    session_id = str(form.get("session_id", "")).strip()
    last_seq = int(form.get("last_seq", 0))

    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute(
            "SELECT id, seq, role, content FROM training_message "
            "WHERE session_id=? AND seq>? ORDER BY seq",
            (session_id, last_seq)
        )
        rows = await cur.fetchall()

    return ok(rows)


@router.post("/Client/training/endSession")
async def end_session(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    user = await _auth(manage_token)
    form = await _get_form(request)
    session_id = str(form.get("session_id", "")).strip()
    if not session_id:
        return err("参数缺失")
    try:
        await _consume_ai_quota(user, request, "score")
    except AIQuotaExceeded as e:
        return err(str(e), 429)

    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute(
            "SELECT sess.*, sc.name as sc_name, sc.persona, sc.scene_desc, sc.difficulty "
            "FROM training_session sess JOIN training_scenario sc ON sc.id=sess.scenario_id "
            "WHERE sess.session_id=? AND sess.user_id=? AND sess.status=0",
            (session_id, user["id"])
        )
        sess = await cur.fetchone()
        if not sess:
            return err("会话不存在或已结束")

        now = datetime.now()
        created_at = datetime.fromisoformat(sess["created_at"]) if sess.get("created_at") else now
        duration_sec = int((now - created_at).total_seconds())

        # 获取消息
        cur = await db.execute(
            "SELECT role, content FROM training_message WHERE session_id=? ORDER BY seq",
            (session_id,)
        )
        messages = await cur.fetchall()
        message_count = len(messages)

        # 标记结束，status=1（评分中）
        await db.execute(
            "UPDATE training_session SET status=1, ended_at=?, duration_sec=?, message_count=? WHERE session_id=?",
            (now.strftime("%Y-%m-%d %H:%M:%S"), duration_sec, message_count, session_id)
        )
        # 插入评分占位（status=0 = 评分中）
        await db.execute(
            "INSERT OR IGNORE INTO training_score(session_id, status) VALUES(?,0)",
            (session_id,)
        )
        await db.commit()

        # 获取场景维度配置
        cur = await db.execute(
            """SELECT sd.dimension_id, d.name as dimension_name, sd.weight, d.description as scoring_criteria
               FROM scenario_dimension sd JOIN training_dimension d ON d.id=sd.dimension_id
               WHERE sd.scenario_id=?""",
            (sess["scenario_id"],)
        )
        dims = await cur.fetchall()

    # 转换消息格式
    ai_messages = [
        {"role": "sales" if m["role"] == 2 else "customer", "content": m["content"]}
        for m in messages
    ]

    # 后台评分任务
    asyncio.create_task(_async_score(session_id, sess, dims, ai_messages))

    return ok({"session_id": session_id})


async def _async_score(session_id: str, sess: dict, dims: list, messages: list):
    """后台评分任务"""
    async def save_score(result: dict):
        async with get_db() as db:
            await db.execute(
                """UPDATE training_score
                   SET total_score=?, dimension_scores=?, summary=?, highlights=?, suggestions=?, status=1
                   WHERE session_id=?""",
                (
                    result["total_score"],
                    json.dumps(result["dimension_scores"], ensure_ascii=False),
                    result["summary"],
                    json.dumps(result["highlights"], ensure_ascii=False),
                    json.dumps(result["suggestions"], ensure_ascii=False),
                    session_id,
                )
            )
            await db.execute(
                "UPDATE training_session SET status=2 WHERE session_id=?", (session_id,)
            )
            await db.commit()

    try:
        result = await score_session(
            scenario_name=sess["sc_name"],
            persona=sess.get("persona", ""),
            scene_desc=sess.get("scene_desc", ""),
            difficulty=sess.get("difficulty", 2),
            dimensions=dims,
            messages=messages,
        )
        await save_score(result)
    except ScoreParseError as e:
        import logging
        logging.error(f"评分 JSON 解析失败，已使用兜底评分 session={session_id}: {e}")
        await save_score(build_fallback_score(dims, messages))
    except Exception as e:
        import logging
        logging.error(f"评分失败，已使用兜底评分 session={session_id}: {e}")
        await save_score(build_fallback_score(dims, messages))


@router.post("/Client/training/sessionResult")
async def session_result(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    """前端轮询：返回会话状态和评分结果"""
    user = await _auth(manage_token)
    form = await _get_form(request)
    session_id = str(form.get("session_id", "")).strip()
    if not session_id:
        return err("参数缺失")

    async with get_db() as db:
        db.row_factory = _row_factory
        # 会话信息
        cur = await db.execute(
            """SELECT sess.*, sc.name as scenario_name, sc.difficulty, sc.is_required
               FROM training_session sess
               JOIN training_scenario sc ON sc.id=sess.scenario_id
               WHERE sess.session_id=?""",
            (session_id,)
        )
        sess = await cur.fetchone()
        if not sess:
            return err("会话不存在")

        # 评分结果
        cur = await db.execute(
            "SELECT * FROM training_score WHERE session_id=?", (session_id,)
        )
        score_row = await cur.fetchone()

        # 消息
        cur = await db.execute(
            "SELECT id, seq, role, content FROM training_message WHERE session_id=? ORDER BY seq",
            (session_id,)
        )
        messages = await cur.fetchall()

    score = None
    # status: 0=进行中 1=已结束(评分中) 2=已评分 3=评分失败
    # 前端 result 页: status 1=评分中, 2=完成, 3=失败
    if score_row and score_row["status"] == 1:
        score = {
            "total_score": score_row["total_score"],
            "dimension_scores": json.loads(score_row["dimension_scores"] or "[]"),
            "summary": score_row["summary"],
            "highlights": json.loads(score_row["highlights"] or "[]"),
            "suggestions": json.loads(score_row["suggestions"] or "[]"),
        }

    return ok({
        "status": sess["status"],   # 1=评分中 2=已评分 3=评分失败
        "session": sess,
        "score": score,
        "messages": messages,
    })


@router.post("/Client/training/sessionDetail")
async def session_detail(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    """返回会话详情（用于再练一次入口）"""
    user = await _auth(manage_token)
    form = await _get_form(request)
    session_id = str(form.get("session_id", "")).strip()
    if not session_id:
        return err("参数缺失")

    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute(
            """SELECT sess.*, sc.name as scenario_name, sc.difficulty, sc.persona,
                      sc.scene_desc, sc.opening, sc.is_required
               FROM training_session sess
               JOIN training_scenario sc ON sc.id=sess.scenario_id
               WHERE sess.session_id=?""",
            (session_id,)
        )
        sess = await cur.fetchone()
        if not sess:
            return ok({"session": None, "messages": []})

        cur = await db.execute(
            "SELECT id, seq, role, content FROM training_message WHERE session_id=? ORDER BY seq",
            (session_id,)
        )
        messages = await cur.fetchall()

        cur = await db.execute(
            "SELECT * FROM training_score WHERE session_id=?", (session_id,)
        )
        score_row = await cur.fetchone()

    score = None
    if score_row and score_row["status"] == 1:
        score = {
            "total_score": score_row["total_score"],
            "dimension_scores": json.loads(score_row["dimension_scores"] or "[]"),
            "summary": score_row["summary"],
            "highlights": json.loads(score_row["highlights"] or "[]"),
            "suggestions": json.loads(score_row["suggestions"] or "[]"),
        }

    return ok({"session": sess, "score": score, "messages": messages})


# ═══════════════════════════════════════════════════════════════
#  记录 & 统计
# ═══════════════════════════════════════════════════════════════

@router.post("/Client/training/sessionHistory")
async def session_history(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    user = await _auth(manage_token)
    form = await _get_form(request)
    page = int(form.get("page", 1))
    limit = int(form.get("limit", 15))
    offset = (page - 1) * limit
    keyword = str(form.get("keyword", "")).strip()
    group_id = form.get("group_id")
    scenario_id = form.get("scenario_id")
    date_start = str(form.get("date_start", "")).strip()
    date_end = str(form.get("date_end", "")).strip()

    where = ["sess.status IN (1,2,3)"]
    params = []

    # 权限：staff 只能看自己
    if user["role"] == "staff":
        where.append("sess.user_id=?")
        params.append(user["id"])
    elif user["role"] == "leader":
        where.append("u.group_id=?")
        params.append(user["group_id"])

    if keyword:
        where.append("(u.name LIKE ? OR sc.name LIKE ?)")
        params += [f"%{keyword}%", f"%{keyword}%"]
    if group_id:
        where.append("u.group_id=?")
        params.append(int(group_id))
    if scenario_id:
        where.append("sess.scenario_id=?")
        params.append(int(scenario_id))
    if date_start:
        where.append("DATE(sess.ended_at) >= ?")
        params.append(date_start)
    if date_end:
        where.append("DATE(sess.ended_at) <= ?")
        params.append(date_end)

    where_sql = " AND ".join(where)

    async with get_db() as db:
        db.row_factory = _row_factory
        count_sql = (
            "SELECT COUNT(*) as cnt FROM training_session sess "
            "JOIN users u ON u.id=sess.user_id "
            "JOIN training_scenario sc ON sc.id=sess.scenario_id "
            f"WHERE {where_sql}"
        )
        cur = await db.execute(count_sql, params)
        total = (await cur.fetchone())["cnt"]

        list_sql = (
            "SELECT sess.session_id, sess.user_id, u.name as user_name, u.group_id, "
            "sc.name as scenario_name, sc.difficulty, sess.status, "
            "ts.total_score, sess.duration_sec, sess.message_count, sess.ended_at "
            "FROM training_session sess "
            "JOIN users u ON u.id=sess.user_id "
            "JOIN training_scenario sc ON sc.id=sess.scenario_id "
            "LEFT JOIN training_score ts ON ts.session_id=sess.session_id "
            f"WHERE {where_sql} "
            "ORDER BY sess.ended_at DESC LIMIT ? OFFSET ?"
        )
        cur = await db.execute(list_sql, params + [limit, offset])
        rows = await cur.fetchall()

    return ok({
        "list": rows,
        "total": total,
        "viewer": {
            "id": user["id"],
            "is_staff": 1 if user["role"] == "staff" else 0,
            "is_group_manager": 1 if user["role"] == "leader" else 0,
            "role": user["role"],
        }
    })


@router.post("/Client/training/leaderboardTeam")
async def leaderboard_team(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    user = await _auth(manage_token)
    form = await _get_form(request)
    group_id = form.get("group_id")

    async with get_db() as db:
        db.row_factory = _row_factory

        # 必练场景总数（启用的）
        cur = await db.execute(
            "SELECT COUNT(*) as cnt FROM training_scenario WHERE is_required=1 AND status=1"
        )
        required_total = (await cur.fetchone())["cnt"]

        # 参与人数（有过练习的 staff）
        where_group = "AND u.group_id=?" if group_id else ""
        gparams = [int(group_id)] if group_id else []

        cur = await db.execute(
            f"SELECT COUNT(DISTINCT sess.user_id) as cnt FROM training_session sess "
            f"JOIN users u ON u.id=sess.user_id WHERE u.role='staff' {where_group}",
            gparams
        )
        participants = (await cur.fetchone())["cnt"]

        # 各员工的必练完成情况
        cur = await db.execute(
            f"""SELECT u.id as user_id, u.name as user_name, u.group_id,
                   COUNT(DISTINCT CASE WHEN sc.is_required=1 AND ts.status=1 THEN sess.scenario_id END) as rf,
                   COUNT(DISTINCT CASE WHEN sc.is_required=1 THEN sc.id END) as rt,
                   COUNT(sess.id) as practice_count
                FROM users u
                LEFT JOIN training_session sess ON sess.user_id=u.id AND sess.status IN (1,2,3)
                LEFT JOIN training_scenario sc ON sc.id=sess.scenario_id
                LEFT JOIN training_score ts ON ts.session_id=sess.session_id
                WHERE u.role='staff' {where_group}
                GROUP BY u.id""",
            gparams
        )
        all_staff = await cur.fetchall()

        # 入榜人员（必练完成度=100%）
        ranked_users = [s for s in all_staff if s["rt"] > 0 and s["rf"] >= s["rt"]]
        unfinished_users = [s for s in all_staff if not (s["rt"] > 0 and s["rf"] >= s["rt"])]

        # 计算入榜人员的平均分
        ranks = []
        for s in ranked_users:
            # 每个必练场景取最新一次评分
            cur = await db.execute(
                """SELECT AVG(latest.total_score) as avg_score
                   FROM (
                     SELECT ts.total_score, sess.scenario_id,
                            ROW_NUMBER() OVER (PARTITION BY sess.scenario_id ORDER BY sess.ended_at DESC) as rn
                     FROM training_session sess
                     JOIN training_score ts ON ts.session_id=sess.session_id
                     JOIN training_scenario sc ON sc.id=sess.scenario_id
                     WHERE sess.user_id=? AND sc.is_required=1 AND ts.status=1
                   ) latest WHERE latest.rn=1""",
                (s["user_id"],)
            )
            avg_row = await cur.fetchone()
            avg_score = round(avg_row["avg_score"]) if avg_row and avg_row["avg_score"] is not None else None
            ranks.append({**s, "avg_score": avg_score})

        ranks.sort(key=lambda r: (-(r["avg_score"] or 0)))
        ranked_count = len(ranks)
        team_avg = None
        if ranks:
            valid = [r["avg_score"] for r in ranks if r["avg_score"] is not None]
            team_avg = round(sum(valid) / len(valid)) if valid else None

        # SQLite JSON 聚合在不同版本兼容性不一，统一用 Python 聚合维度均分。
        cur = await db.execute(
            f"""SELECT ts.dimension_scores, sess.scenario_id
                FROM training_score ts
                JOIN training_session sess ON sess.session_id=ts.session_id
                JOIN users u ON u.id=sess.user_id
                WHERE u.role='staff' AND ts.status=1 {where_group}""",
            gparams
        )
        score_rows = await cur.fetchall()

        # Python 聚合维度均分
        dim_agg: dict = {}
        for sr in score_rows:
            ds = json.loads(sr["dimension_scores"] or "[]")
            for d in ds:
                did = d["dimension_id"]
                if did not in dim_agg:
                    dim_agg[did] = {"name": d["dimension_name"], "scores": [], "scenario_ids": set()}
                dim_agg[did]["scores"].append(d["score"])
                dim_agg[did]["scenario_ids"].add(sr["scenario_id"])

        weak_dimensions = []
        for did, agg in sorted(dim_agg.items(), key=lambda x: sum(x[1]["scores"]) / len(x[1]["scores"])):
            avg = round(sum(agg["scores"]) / len(agg["scores"]))
            # 获取场景名
            sc_names = []
            for scid in agg["scenario_ids"]:
                cur = await db.execute("SELECT name FROM training_scenario WHERE id=?", (scid,))
                r = await cur.fetchone()
                if r:
                    sc_names.append(r["name"])
            weak_dimensions.append({
                "dimension_id": did,
                "name": agg["name"],
                "avg_score": avg,
                "is_weak": avg < 70,
                "scenario_names": sc_names,
            })

        # 场景均分
        sc_agg: dict = {}
        for sr in score_rows:
            scid = sr["scenario_id"]
            ds = json.loads(sr["dimension_scores"] or "[]")
            total = sum(d["score"] for d in ds) / max(len(ds), 1)
            if scid not in sc_agg:
                sc_agg[scid] = {"scores": [], "count": 0}
            sc_agg[scid]["scores"].append(total)
            sc_agg[scid]["count"] += 1

        scenario_avg = []
        for scid, agg in sc_agg.items():
            cur = await db.execute(
                "SELECT name, difficulty FROM training_scenario WHERE id=?", (scid,)
            )
            sc_row = await cur.fetchone()
            if sc_row:
                avg_s = round(sum(agg["scores"]) / len(agg["scores"]))
                scenario_avg.append({
                    "scenario_id": scid,
                    "name": sc_row["name"],
                    "difficulty": sc_row["difficulty"],
                    "avg_score": avg_s,
                    "participant_count": agg["count"],
                })
        scenario_avg.sort(key=lambda x: x["avg_score"])

        # 未完成名单
        unfinished = []
        for s in unfinished_users:
            rt = required_total  # 全部必练场景数
            rf = s["rf"]
            cur = await db.execute(
                """SELECT sc.name FROM training_scenario sc
                   WHERE sc.is_required=1 AND sc.status=1
                   AND sc.id NOT IN (
                     SELECT sess.scenario_id FROM training_session sess
                     JOIN training_score ts ON ts.session_id=sess.session_id
                     WHERE sess.user_id=? AND ts.status=1
                   )""",
                (s["user_id"],)
            )
            missing = [r["name"] for r in await cur.fetchall()]
            unfinished.append({
                **s,
                "required_finished": rf,
                "required_total": rt,
                "required_completion": rf / rt if rt else 0,
                "missing_scenarios": missing,
                "avg_score": None,
            })
        unfinished.sort(key=lambda x: -x["required_completion"])

    return ok({
        "stats": {
            "participants": participants,
            "ranked": ranked_count,
            "unfinishedActive": len(unfinished),
            "teamAvg": team_avg,
        },
        "ranks": ranks,
        "weak_dimensions": weak_dimensions,
        "scenario_avg": scenario_avg,
        "unfinished": unfinished,
    })


@router.post("/Client/training/leaderboardPersonal")
async def leaderboard_personal(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    user = await _auth(manage_token)
    form = await _get_form(request)
    target_user_id = int(form.get("user_id") or user["id"])

    if user["role"] == "staff":
        target_user_id = user["id"]

    async with get_db() as db:
        db.row_factory = _row_factory

        cur = await db.execute(
            "SELECT id, name, role, group_id FROM users WHERE id=? AND role='staff'",
            (target_user_id,)
        )
        target = await cur.fetchone()
        if not target:
            return ok(None)

        if user["role"] == "leader" and target["group_id"] != user["group_id"]:
            return err("无权查看该员工数据", 403)

        cur = await db.execute(
            """SELECT u.id as user_id, u.name as user_name, u.group_id,
                   COUNT(sess.id) as practice_count,
                   COUNT(DISTINCT CASE WHEN sc.is_required=1 AND ts.status=1 THEN sess.scenario_id END) as rf,
                   COUNT(DISTINCT CASE WHEN sc.is_required=1 THEN sc.id END) as rt
                FROM users u
                LEFT JOIN training_session sess ON sess.user_id=u.id AND sess.status IN (1,2,3)
                LEFT JOIN training_scenario sc ON sc.id=sess.scenario_id
                LEFT JOIN training_score ts ON ts.session_id=sess.session_id
                WHERE u.role='staff'
                GROUP BY u.id"""
        )
        all_staff = await cur.fetchall()

        ranks = []
        for s in all_staff:
            if s["rt"] > 0 and s["rf"] >= s["rt"]:
                cur = await db.execute(
                    """SELECT AVG(latest.total_score) as avg_score
                       FROM (
                         SELECT ts.total_score,
                                ROW_NUMBER() OVER (PARTITION BY sess.scenario_id ORDER BY sess.ended_at DESC) as rn
                         FROM training_session sess
                         JOIN training_score ts ON ts.session_id=sess.session_id
                         JOIN training_scenario sc ON sc.id=sess.scenario_id
                         WHERE sess.user_id=? AND sc.is_required=1 AND ts.status=1
                       ) latest WHERE latest.rn=1""",
                    (s["user_id"],)
                )
                avg_row = await cur.fetchone()
                avg_score = round(avg_row["avg_score"]) if avg_row and avg_row["avg_score"] is not None else None
                ranks.append({**s, "avg_score": avg_score, "is_ranked": True})
            else:
                ranks.append({**s, "avg_score": None, "is_ranked": False})

        ranks.sort(key=lambda r: (0 if r["is_ranked"] else 1, -(r["avg_score"] or 0)))
        # 标注当前用户排名
        rank = next((i + 1 for i, r in enumerate(ranks) if r["user_id"] == target_user_id and r["is_ranked"]), None)
        target_rank_row = next((r for r in ranks if r["user_id"] == target_user_id), None)

        cur = await db.execute(
            "SELECT COUNT(*) as cnt FROM training_scenario WHERE is_required=1 AND status=1"
        )
        required_total = (await cur.fetchone())["cnt"]

        cur = await db.execute(
            """SELECT COUNT(DISTINCT sess.scenario_id) as cnt
               FROM training_session sess
               JOIN training_score ts ON ts.session_id=sess.session_id
               JOIN training_scenario sc ON sc.id=sess.scenario_id
               WHERE sess.user_id=? AND sc.is_required=1 AND sc.status=1 AND ts.status=1""",
            (target_user_id,)
        )
        required_finished = (await cur.fetchone())["cnt"]

        cur = await db.execute(
            """SELECT id, name FROM training_scenario
               WHERE is_required=1 AND status=1 AND id NOT IN (
                 SELECT sess.scenario_id FROM training_session sess
                 JOIN training_score ts ON ts.session_id=sess.session_id
                 WHERE sess.user_id=? AND ts.status=1
               )""",
            (target_user_id,)
        )
        missing_required = await cur.fetchall()

        cur = await db.execute(
            """SELECT DATE(ended_at) as d FROM training_session
               WHERE user_id=? AND ended_at IS NOT NULL
               GROUP BY DATE(ended_at) ORDER BY d DESC""",
            (target_user_id,)
        )
        practice_days = [r["d"] for r in await cur.fetchall()]
        streak_days = 0
        if practice_days:
            from datetime import date, timedelta
            day_set = set(practice_days)
            cursor = date.today()
            while cursor.strftime("%Y-%m-%d") in day_set:
                streak_days += 1
                cursor -= timedelta(days=1)

        cur = await db.execute(
            """SELECT ts.dimension_scores
               FROM training_score ts
               JOIN training_session sess ON sess.session_id=ts.session_id
               WHERE sess.user_id=? AND ts.status=1""",
            (target_user_id,)
        )
        score_rows = await cur.fetchall()
        dim_agg = {}
        for sr in score_rows:
            for d in json.loads(sr["dimension_scores"] or "[]"):
                did = d["dimension_id"]
                if did not in dim_agg:
                    dim_agg[did] = {"dimension_id": did, "name": d["dimension_name"], "scores": []}
                dim_agg[did]["scores"].append(d["score"])
        ability_profile = [
            {
                "dimension_id": agg["dimension_id"],
                "name": agg["name"],
                "avg_score": round(sum(agg["scores"]) / len(agg["scores"])),
            }
            for agg in dim_agg.values()
        ]
        ability_profile.sort(key=lambda x: x["avg_score"])

        cur = await db.execute(
            """SELECT sc.id as scenario_id, sc.name, sc.difficulty, sc.is_required,
                      COUNT(sess.id) as practice_count,
                      (
                        SELECT ts2.total_score
                        FROM training_session sess2
                        JOIN training_score ts2 ON ts2.session_id=sess2.session_id
                        WHERE sess2.user_id=? AND sess2.scenario_id=sc.id AND ts2.status=1
                        ORDER BY sess2.ended_at DESC LIMIT 1
                      ) as my_score
               FROM training_scenario sc
               LEFT JOIN training_session sess ON sess.scenario_id=sc.id AND sess.user_id=? AND sess.status IN (1,2,3)
               WHERE sc.status=1
               GROUP BY sc.id, sc.name, sc.difficulty, sc.is_required
               ORDER BY sc.is_required DESC, sc.difficulty ASC""",
            (target_user_id, target_user_id)
        )
        scenario_stats = await cur.fetchall()

        status = "unstart"
        if target_rank_row and target_rank_row["practice_count"] > 0:
            status = "ranked" if rank else "partial"

    return ok({
        "user": {"id": target["id"], "name": target["name"], "group_id": target["group_id"]},
        "status": status,
        "rank": rank,
        "avg_score": target_rank_row["avg_score"] if target_rank_row else None,
        "required_finished": required_finished,
        "required_total": required_total,
        "missing_required": missing_required,
        "streak_days": streak_days,
        "ability_profile": ability_profile,
        "scenario_stats": scenario_stats,
    })


@router.post("/Client/training/scenarioTeamAvg")
async def scenario_team_avg(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    user = await _auth(manage_token)
    form = await _get_form(request)
    group_id = form.get("group_id")
    target_user_id = form.get("user_id")
    if target_user_id and not group_id:
        async with get_db() as db:
            db.row_factory = _row_factory
            cur = await db.execute("SELECT group_id FROM users WHERE id=?", (int(target_user_id),))
            target = await cur.fetchone()
            if target:
                group_id = target["group_id"]

    where_group = "AND u.group_id=?" if group_id else ""
    params = [int(group_id)] if group_id else []

    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute(
            f"""SELECT sc.id as scenario_id, sc.name, sc.difficulty,
                   ROUND(AVG(ts.total_score)) as team_avg,
                   COUNT(ts.id) as practice_count
                FROM training_scenario sc
                LEFT JOIN training_session sess ON sess.scenario_id=sc.id AND sess.status=2
                LEFT JOIN training_score ts ON ts.session_id=sess.session_id AND ts.status=1
                LEFT JOIN users u ON u.id=sess.user_id
                WHERE sc.status=1 {where_group}
                GROUP BY sc.id, sc.name, sc.difficulty
                ORDER BY sc.is_required DESC, sc.difficulty ASC""",
            params
        )
        rows = await cur.fetchall()

    return ok({str(r["scenario_id"]): r["team_avg"] for r in rows})


@router.post("/Client/training/employeeList")
async def employee_list(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    user = await _auth(manage_token)
    form = await _get_form(request)
    group_id = form.get("group_id")

    where = ["role='staff'"]
    params = []
    if group_id:
        where.append("group_id=?")
        params.append(int(group_id))
    if user["role"] == "staff":
        where.append("id=?")
        params.append(user["id"])
    if user["role"] == "leader":
        where.append("group_id=?")
        params.append(user["group_id"])

    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute(
            f"SELECT id, name, group_id FROM users WHERE {' AND '.join(where)}",
            params
        )
        rows = await cur.fetchall()

    return ok({
        "list": rows,
        "viewer": {
            "id": user["id"],
            "is_staff": 1 if user["role"] == "staff" else 0,
            "is_group_manager": 1 if user["role"] == "leader" else 0,
            "role": user["role"],
        }
    })


@router.post("/Client/training/groupList")
async def group_list(
    request: Request,
    manage_token: Optional[str] = Header(None, alias="Manage-Token"),
):
    await _auth(manage_token)
    async with get_db() as db:
        db.row_factory = _row_factory
        cur = await db.execute("SELECT id, name FROM groups ORDER BY id")
        rows = await cur.fetchall()
    return ok(rows)
