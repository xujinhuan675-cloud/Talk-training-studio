"""SQLAlchemy implementation of TrainingSessionRepository."""

from __future__ import annotations

from sqlalchemy import String, cast, delete, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.training_studio.catalog import TrainingTaskConfig
from domain.training_studio.session import TrainingSession
from domain.training_studio.session_repository import (
    TrainingSessionAccessScope,
    TrainingSessionHistoryFilter,
    TrainingSessionRepository,
)
from infrastructure.models.training_session import TrainingSessionModel


class SQLAlchemyTrainingSessionRepository(TrainingSessionRepository):
    """SQLAlchemy-backed Training Studio session repository."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _task_config_to_dict(self, config: TrainingTaskConfig) -> dict:
        return {
            "role": config.role,
            "level": config.level,
            "tech_stack": list(config.tech_stack),
            "question_type_ratios": dict(config.question_type_ratios),
            "question_count": config.question_count,
            "framework": config.framework.value,
            "difficulty": config.difficulty.value,
            "category": config.category.value,
            "rubric_version": config.rubric_version,
            "rubric_weights": {
                dimension.value if hasattr(dimension, "value") else str(dimension): weight
                for dimension, weight in config.rubric_weights.items()
            },
            "metadata": dict(config.metadata),
        }

    def _to_entity(self, model: TrainingSessionModel) -> TrainingSession:
        return TrainingSession(
            session_id=model.session_id,
            task_config=TrainingTaskConfig(**dict(model.task_config or {})),
            mode=model.mode,
            scenario_template_id=model.scenario_template_id,
            user_id=model.user_id,
            team_id=model.team_id,
            status=model.status,
            room_id=model.room_id,
            started_at=model.started_at,
            completed_at=model.completed_at,
            report_id=model.report_id,
            score_id=model.score_id,
            message_count=model.message_count,
            failure_reason=model.failure_reason,
        )

    def _apply_model_values(
        self,
        model: TrainingSessionModel,
        session: TrainingSession,
    ) -> None:
        model.task_config = self._task_config_to_dict(session.task_config)
        model.mode = session.mode.value
        model.scenario_template_id = session.scenario_template_id
        model.user_id = session.user_id
        model.team_id = session.team_id
        model.status = session.status.value
        model.room_id = session.room_id
        model.started_at = session.started_at
        model.completed_at = session.completed_at
        model.report_id = session.report_id
        model.score_id = session.score_id
        model.message_count = session.message_count
        model.failure_reason = session.failure_reason

    def _apply_access_scope(self, query, access_scope: TrainingSessionAccessScope | None):
        if access_scope is None:
            return query
        conditions = []
        user_id = (access_scope.user_id or "").strip()
        team_id = (access_scope.team_id or "").strip()
        if user_id:
            conditions.append(TrainingSessionModel.user_id == user_id)
        if access_scope.include_team_scope and team_id:
            conditions.append(TrainingSessionModel.team_id == team_id)
        if not conditions:
            return query.where(false())
        return query.where(or_(*conditions))

    def _apply_list_filters(
        self,
        query,
        *,
        user_id: str | None,
        team_id: str | None,
        scenario_template_id: str | None,
        history_filter: TrainingSessionHistoryFilter | None,
    ):
        if user_id:
            query = query.where(TrainingSessionModel.user_id == user_id)
        if team_id:
            query = query.where(TrainingSessionModel.team_id == team_id)
        if scenario_template_id:
            query = query.where(TrainingSessionModel.scenario_template_id == scenario_template_id)
        if history_filter is None:
            return query
        if history_filter.mode:
            query = query.where(TrainingSessionModel.mode == history_filter.mode)
        if history_filter.source:
            metadata = TrainingSessionModel.task_config["metadata"]
            source_value = history_filter.source.lower()
            query = query.where(
                or_(
                    *(
                        func.lower(metadata[key].as_string()) == source_value
                        for key in ("source", "training_source", "trainingSource")
                    )
                )
            )
        activity_at = func.coalesce(
            TrainingSessionModel.completed_at,
            TrainingSessionModel.started_at,
            TrainingSessionModel.created_at,
        )
        if history_filter.activity_from:
            query = query.where(activity_at >= history_filter.activity_from)
        if history_filter.activity_to:
            query = query.where(activity_at <= history_filter.activity_to)
        if history_filter.query:
            task_config = TrainingSessionModel.task_config
            metadata = task_config["metadata"]
            searchable = [
                TrainingSessionModel.session_id,
                TrainingSessionModel.scenario_template_id,
                task_config["role"].as_string(),
                task_config["category"].as_string(),
                cast(task_config["tech_stack"], String),
            ]
            for key in ("title", "description", "name", "label"):
                searchable.append(metadata[key].as_string())
            for container_key in (
                "scenario",
                "scenario_training",
                "scenarioTraining",
                "task",
                "training",
            ):
                for key in ("title", "description", "name", "label"):
                    searchable.append(metadata[container_key][key].as_string())
            pattern = _escaped_contains_pattern(history_filter.query.lower())
            query = query.where(
                or_(
                    *(
                        func.lower(cast(value, String)).like(pattern, escape="\\")
                        for value in searchable
                    )
                )
            )
        return query

    async def save(self, session: TrainingSession) -> TrainingSession:
        result = await self.session.execute(
            select(TrainingSessionModel).where(
                TrainingSessionModel.session_id == session.session_id
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            model = TrainingSessionModel(session_id=session.session_id)
            self.session.add(model)
        self._apply_model_values(model, session)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get(
        self,
        session_id: str,
        *,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> TrainingSession | None:
        query = select(TrainingSessionModel).where(TrainingSessionModel.session_id == session_id)
        query = self._apply_access_scope(query, access_scope)
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def delete(
        self,
        session_id: str,
        *,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> bool:
        query = delete(TrainingSessionModel).where(TrainingSessionModel.session_id == session_id)
        query = self._apply_access_scope(query, access_scope)
        result = await self.session.execute(query)
        return bool(result.rowcount)

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
        history_filter: TrainingSessionHistoryFilter | None = None,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> list[TrainingSession]:
        query = select(TrainingSessionModel)
        query = self._apply_access_scope(query, access_scope)
        query = self._apply_list_filters(
            query,
            user_id=user_id,
            team_id=team_id,
            scenario_template_id=scenario_template_id,
            history_filter=history_filter,
        )
        activity_at = func.coalesce(
            TrainingSessionModel.completed_at,
            TrainingSessionModel.started_at,
            TrainingSessionModel.created_at,
        )
        result = await self.session.execute(
            query.order_by(
                activity_at.desc(),
                TrainingSessionModel.created_at.desc(),
                TrainingSessionModel.session_id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return [self._to_entity(model) for model in result.scalars().all()]

    async def count(
        self,
        *,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
        history_filter: TrainingSessionHistoryFilter | None = None,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> int:
        query = select(func.count()).select_from(TrainingSessionModel)
        query = self._apply_access_scope(query, access_scope)
        query = self._apply_list_filters(
            query,
            user_id=user_id,
            team_id=team_id,
            scenario_template_id=scenario_template_id,
            history_filter=history_filter,
        )
        result = await self.session.execute(query)
        return int(result.scalar_one())


def _escaped_contains_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
