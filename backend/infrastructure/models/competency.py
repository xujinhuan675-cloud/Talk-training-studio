# input: SQLAlchemy Base 基类
# output: CompetencyEvaluationModel ORM 模型
# owner: wanhua.gu
# pos: 基础设施层 - communication-core-v1 能力评估 ORM 定义；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Competency evaluation database model definition."""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from .base import Base


class CompetencyEvaluationModel(Base):
    """ORM mapping for stakeholder_competency_evaluations table."""

    __tablename__ = "stakeholder_competency_evaluations"
    __table_args__ = (
        Index("ix_competency_eval_room_id", "room_id"),
        UniqueConstraint("report_id", name="uq_competency_eval_report_id"),
        {"comment": "沟通能力评估（communication-core-v1）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    report_id = Column(
        Integer,
        ForeignKey("stakeholder_analysis_reports.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联分析报告ID（一对一）",
    )
    room_id = Column(
        Integer,
        ForeignKey("stakeholder_chat_rooms.id", ondelete="SET NULL"),
        nullable=True,
        comment="所属聊天室ID（会话删除后置 NULL，评估保留）",
    )
    scores = Column(JSON, nullable=False, default=dict, comment="版本化的证据锚定评估JSON")
    outcome_rating = Column(
        Float,
        nullable=True,
        default=None,
        comment="本次任务表现（有效性与适切性均值，可空）",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="评估时间",
    )

    def __repr__(self) -> str:
        return f"<CompetencyEvaluationModel(id={self.id}, report_id={self.report_id}, outcome={self.outcome_rating})>"
