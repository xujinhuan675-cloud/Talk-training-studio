# input: DefensePrepService (via dependencies)
# output: defense-prep API 路由 (sessions CRUD + start + report)
# owner: wanhua.gu
# pos: 表示层 - 答辩准备 API 路由；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Defense prep API routes."""
from __future__ import annotations
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from api.dependencies import CurrentUser, get_current_user, get_defense_prep_service
from application.services.defense_prep_service import DefensePrepService
from core.response import success_response
from domain.defense_prep.scenario import ScenarioType
from domain.defense_prep.repository import DefenseSessionAccessScope

router = APIRouter(prefix="/defense-prep", tags=["Defense Prep"])

_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
_ALLOWED_EXTENSIONS = {".pptx", ".pdf", ".docx", ".txt", ".md"}


def _access_scope_for_current_user(current_user: CurrentUser) -> DefenseSessionAccessScope:
    """Translate the authenticated NewAPI identity into a defense scope."""

    return DefenseSessionAccessScope(
        user_id=current_user.user_id,
        team_id=current_user.team_id,
        include_team_scope=current_user.can_manage_team,
        unrestricted=current_user.is_admin,
    )


def _defense_session_error(exc: ValueError) -> HTTPException:
    """Hide missing and out-of-scope defense sessions behind the same response."""

    detail = str(exc)
    if "not found" in detail.lower():
        return HTTPException(status_code=404, detail="Session not found")
    return HTTPException(status_code=400, detail=detail)


@router.post("/sessions")
async def create_session(
    file: UploadFile = File(...),
    persona_ids: str = Form(...),  # comma-separated
    scenario_type: str = Form(...),
    service: DefensePrepService = Depends(get_defense_prep_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    from pathlib import Path

    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件格式: {ext}")
    content = await file.read()
    if len(content) > _MAX_FILE_SIZE:
        raise HTTPException(400, "文件大小不能超过 20MB")
    try:
        st = ScenarioType(scenario_type)
    except ValueError:
        raise HTTPException(400, f"无效的场景类型: {scenario_type}")

    # Parse and validate persona_ids
    pid_list = [p.strip() for p in persona_ids.split(",") if p.strip()]
    if not pid_list:
        raise HTTPException(400, "至少需要选择一位答辩官")
    if len(pid_list) > 5:
        raise HTTPException(400, "最多选择 5 位答辩官")
    if len(pid_list) != len(set(pid_list)):
        raise HTTPException(400, "答辩官不能重复选择")

    try:
        session = await service.create_session(
            file_content=content,
            filename=file.filename or "document",
            persona_ids=pid_list,
            scenario_type=st,
            owner_user_id=current_user.user_id,
            owner_team_id=current_user.team_id,
            access_scope=_access_scope_for_current_user(current_user),
        )
    except ValueError as exc:
        raise _defense_session_error(exc) from exc
    return success_response(
        {
            "id": session.id,
            "persona_ids": session.persona_ids,
            "scenario_type": session.scenario_type.value,
            "document_title": session.document_summary.title,
            "status": session.status,
            "created_at": session.created_at.isoformat() if session.created_at else None,
        }
    )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    service: DefensePrepService = Depends(get_defense_prep_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    session = await service.get_session(
        session_id, access_scope=_access_scope_for_current_user(current_user)
    )
    if session is None:
        raise HTTPException(404, "会话不存在")
    data = {
        "id": session.id,
        "persona_ids": session.persona_ids,
        "scenario_type": session.scenario_type.value,
        "document_title": session.document_summary.title,
        "status": session.status,
        "room_id": session.room_id,
        "training_session_id": session.training_session_id,
        "conversation_id": session.conversation_id,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }
    if session.question_strategy:
        data["question_strategy"] = {
            "questions": [
                {
                    "question": q.question,
                    "dimension": q.dimension,
                    "difficulty": q.difficulty,
                    "asked_by": q.asked_by,
                }
                for q in session.question_strategy.questions
            ]
        }
    return success_response(data)


@router.post("/sessions/{session_id}/start")
async def start_session(
    session_id: int,
    service: DefensePrepService = Depends(get_defense_prep_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        session = await service.start_session(
            session_id, access_scope=_access_scope_for_current_user(current_user)
        )
    except ValueError as exc:
        raise _defense_session_error(exc) from exc
    return success_response(
        {
            "id": session.id,
            "room_id": session.room_id,
            "training_session_id": session.training_session_id,
            "conversation_id": session.conversation_id,
            "status": session.status,
            "question_strategy": {
                "questions": [
                    {
                        "question": q.question,
                        "dimension": q.dimension,
                        "difficulty": q.difficulty,
                        "asked_by": q.asked_by,
                    }
                    for q in (
                        session.question_strategy.questions if session.question_strategy else []
                    )
                ]
            },
        }
    )


@router.get("/sessions/{session_id}/report")
async def get_report(
    session_id: int,
    service: DefensePrepService = Depends(get_defense_prep_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        report = await service.generate_report(
            session_id, access_scope=_access_scope_for_current_user(current_user)
        )
    except ValueError as exc:
        raise _defense_session_error(exc) from exc
    return success_response(report)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: int,
    service: DefensePrepService = Depends(get_defense_prep_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    deleted = await service.delete_session(
        session_id, access_scope=_access_scope_for_current_user(current_user)
    )
    if not deleted:
        raise HTTPException(404, "会话不存在")
    return None
