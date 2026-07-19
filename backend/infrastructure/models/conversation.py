# input: SQLAlchemy Base 基类
# output: ConversationModel, MessageModel, RunModel, AgentConfigModel ORM 模型
# owner: unknown
# pos: 基础设施层 - 对话聚合 ORM 模型定义；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Conversation aggregate database model definitions."""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.sql import func

from .base import Base


class ConversationModel(Base):
    """ORM mapping for conversations table."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_status", "status"),
        Index("ix_conversations_created_at", "created_at"),
        {
            "comment": "对话表，记录 AI 对话会话",
        },
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    title = Column(String(255), nullable=False, comment="对话标题")
    system_prompt = Column(Text, nullable=True, comment="系统提示词")
    model = Column(String(100), nullable=True, comment="默认使用的模型")
    status = Column(
        String(20),
        nullable=False,
        default="active",
        server_default=text("'active'"),
        comment="对话状态：active/archived",
    )
    extra_metadata = Column(
        "metadata",
        JSON,
        nullable=True,
        default=dict,
        comment="扩展元数据（JSON）",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )
    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="删除时间（软删除）",
    )

    def __repr__(self) -> str:
        return f"<ConversationModel(id={self.id}, title='{self.title}', status='{self.status}')>"


class MessageModel(Base):
    """ORM mapping for messages table."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_public_id", "public_id", unique=True),
        Index("ix_messages_parent_message_id", "parent_message_id"),
        Index("ix_messages_conversation_branch", "conversation_id", "branch_id", "created_at"),
        {
            "comment": "消息表，记录对话中的消息",
        },
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属对话ID",
    )
    role = Column(
        String(20),
        nullable=False,
        comment="消息角色：system/user/assistant",
    )
    content = Column(Text, nullable=False, comment="消息内容")
    public_id = Column(
        String(64),
        nullable=False,
        comment="稳定公开消息ID，用于消息树与客户端定位",
    )
    parent_message_id = Column(
        String(64),
        nullable=True,
        comment="父消息公开ID，用于消息树与分支遍历",
    )
    branch_id = Column(
        String(64),
        nullable=True,
        server_default=text("'main'"),
        comment="消息分支ID",
    )
    status = Column(
        String(20),
        nullable=False,
        default="active",
        server_default=text("'active'"),
        comment="消息生命周期状态",
    )
    finish_reason = Column(String(100), nullable=True, comment="LLM 完成原因")
    provider = Column(String(100), nullable=True, comment="LLM 提供商")
    model = Column(String(100), nullable=True, comment="LLM 模型")
    content_parts = Column(
        JSON,
        nullable=True,
        default=list,
        comment="结构化消息内容片段",
    )
    run_id = Column(
        Integer,
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联的 Run ID",
    )
    token_count = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Token 数量",
    )
    extra_metadata = Column(
        "metadata",
        JSON,
        nullable=True,
        default=dict,
        comment="扩展元数据（JSON）",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="创建时间",
    )

    def __repr__(self) -> str:
        return (
            f"<MessageModel(id={self.id}, conversation_id={self.conversation_id}, "
            f"role='{self.role}')>"
        )


class RunModel(Base):
    """ORM mapping for runs table."""

    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_conversation_id", "conversation_id"),
        Index("ix_runs_status", "status"),
        Index("ix_runs_public_id", "public_id", unique=True),
        {
            "comment": "Run 表，记录 LLM 调用追踪",
        },
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    public_id = Column(String(64), nullable=False, comment="稳定公开 Run ID")
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属对话ID",
    )
    status = Column(
        String(20),
        nullable=False,
        default="running",
        server_default=text("'running'"),
        comment="Run 状态：running/completed/failed",
    )
    provider = Column(String(100), nullable=True, comment="LLM 提供商")
    model = Column(String(100), nullable=True, comment="使用的模型")
    finish_reason = Column(String(100), nullable=True, comment="LLM 完成原因")
    prompt_tokens = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="输入 token 数",
    )
    completion_tokens = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="输出 token 数",
    )
    total_tokens = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="总 token 数",
    )
    error_message = Column(Text, nullable=True, comment="错误信息")
    extra_metadata = Column(
        "metadata",
        JSON,
        nullable=True,
        default=dict,
        comment="结构化 Run 元数据",
    )
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="开始时间",
    )
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="完成时间",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="创建时间",
    )

    def __repr__(self) -> str:
        return f"<RunModel(id={self.id}, conversation_id={self.conversation_id}, status='{self.status}')>"


class AgentConfigModel(Base):
    """ORM mapping for agent_configs table."""

    __tablename__ = "agent_configs"
    __table_args__ = (
        Index("ix_agent_configs_name", "name", unique=True),
        {
            "comment": "Agent 配置表，记录可复用的 Agent 配置",
        },
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    name = Column(String(100), nullable=False, unique=True, comment="配置名称（唯一）")
    system_prompt = Column(Text, nullable=True, comment="系统提示词")
    model = Column(String(100), nullable=True, comment="使用的模型")
    temperature = Column(Float, nullable=True, comment="温度参数")
    max_tokens = Column(Integer, nullable=True, comment="最大 token 数")
    tool_ids = Column(
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
        comment="绑定的工具 ID 列表",
    )
    mcp_server_ids = Column(
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
        comment="绑定的 MCP server ID 列表",
    )
    extra_metadata = Column(
        "metadata",
        JSON,
        nullable=True,
        default=dict,
        comment="扩展元数据（JSON）",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<AgentConfigModel(id={self.id}, name='{self.name}')>"
