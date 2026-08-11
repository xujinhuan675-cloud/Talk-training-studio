"""Thin realtime guidance layer for Training Studio sessions.

The service is intentionally deterministic by default and owns no network
dependency. A future adapter can inject an LLM callback that receives the same
bounded state and returns extra guide events.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum

from application.services.training_studio.feedback_policy import (
    TrainingFeedbackMode,
    localized_guidance_text,
    resolve_training_feedback_contract,
)

logger = logging.getLogger(__name__)


class TranscriptSpeaker(StrEnum):
    USER = "user"
    COUNTERPART = "counterpart"
    COACH = "coach"
    SYSTEM = "system"


class GuideEventType(StrEnum):
    NEXT_REPLY = "next_reply"
    RISK = "risk"
    OMISSION = "omission"
    ASK_BACK = "ask_back"
    DELIVERY_NUDGE = "delivery_nudge"
    CORRECTION = "correction"


class GuideSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class TranscriptTurn:
    speaker: TranscriptSpeaker | str
    text: str
    turn_id: str | None = None
    created_at: datetime | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def normalized_speaker(self) -> str:
        return self.speaker.value if isinstance(self.speaker, TranscriptSpeaker) else str(self.speaker)


@dataclass(frozen=True)
class GuideEvent:
    event_type: GuideEventType | str
    severity: GuideSeverity | str
    title: str
    message: str
    suggested_text: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_sse_payload(self) -> dict[str, object]:
        """Return a JSON-ready payload shape for future SSE adapters."""

        event_type = self.event_type.value if isinstance(self.event_type, GuideEventType) else self.event_type
        severity = self.severity.value if isinstance(self.severity, GuideSeverity) else self.severity
        payload: dict[str, object] = {
            "event_type": event_type,
            "severity": severity,
            "title": self.title,
            "message": self.message,
            "suggested_text": self.suggested_text,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class GuidanceState:
    training_session_id: str
    task_goal: str
    rubric: dict[str, object]
    recent_turns: tuple[TranscriptTurn, ...]
    window_size: int
    total_turn_count: int
    feedback_mode: TrainingFeedbackMode = TrainingFeedbackMode.ASSISTED
    language: str = "en-US"

    @property
    def user_turns(self) -> tuple[TranscriptTurn, ...]:
        return tuple(turn for turn in self.recent_turns if turn.normalized_speaker == TranscriptSpeaker.USER)

    @property
    def counterpart_turns(self) -> tuple[TranscriptTurn, ...]:
        return tuple(
            turn for turn in self.recent_turns if turn.normalized_speaker == TranscriptSpeaker.COUNTERPART
        )


LLMGuidanceCallback = Callable[[GuidanceState], Sequence[GuideEvent | dict[str, object]]]
AsyncLLMGuidanceCallback = Callable[
    [GuidanceState], Awaitable[Sequence[GuideEvent | dict[str, object]]]
]


class TrainingLiveGuidanceService:
    """Generate small guidance candidates over a bounded transcript window."""

    _OBJECTION_RE = re.compile(
        r"\b("
        r"concern|worried|worry|not convinced|disagree|pushback|objection|"
        r"too expensive|cost|budget|risk|risky|however|but|doesn'?t work|"
        r"not sure|doubt|issue|problem"
        r")\b",
        re.IGNORECASE,
    )
    _QUESTION_RE = re.compile(
        r"\?|？|(^|\n)\s*(what|why|how|when|where|who|which)\b|"
        r"\b(can|could|would)\s+you\b",
        re.I,
    )
    _WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
    _FILLER_PREFIX_RE = re.compile(
        r"^\s*(?P<filler>(?:嗯+|呃+|啊+|um+|uh+|erm+))(?:[，,、.。\s]*)",
        re.IGNORECASE,
    )
    _LEADING_SPOKEN_FILLER_RE = re.compile(
        r"^\s*(?:(?:嗯+|啊+|呃+|额+|就是|然后|那个|其实|um+|uh+)\s*[,，、]?\s*)+",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        window_size: int = 8,
        max_events: int = 5,
        monologue_word_threshold: int = 95,
        llm_callback: LLMGuidanceCallback | None = None,
        async_llm_callback: AsyncLLMGuidanceCallback | None = None,
    ) -> None:
        if window_size < 1:
            raise ValueError("window_size must be at least 1")
        if max_events < 1:
            raise ValueError("max_events must be at least 1")
        self.window_size = window_size
        self.max_events = max_events
        self.monologue_word_threshold = monologue_word_threshold
        self.llm_callback = llm_callback
        self.async_llm_callback = async_llm_callback

    def build_state(
        self,
        *,
        training_session_id: str,
        task_goal: str,
        rubric: dict[str, object] | None,
        recent_turns: Iterable[TranscriptTurn | dict[str, object]],
        feedback_mode: TrainingFeedbackMode | str = TrainingFeedbackMode.ASSISTED,
        language: str = "en-US",
    ) -> GuidanceState:
        turns = tuple(self._coerce_turn(turn) for turn in recent_turns)
        contract = resolve_training_feedback_contract(
            {"feedbackMode": str(feedback_mode), "replyLanguage": language},
            default_mode=TrainingFeedbackMode.ASSISTED,
        )
        return GuidanceState(
            training_session_id=training_session_id,
            task_goal=task_goal,
            rubric=dict(rubric or {}),
            recent_turns=turns[-self.window_size :],
            window_size=self.window_size,
            total_turn_count=len(turns),
            feedback_mode=contract.mode,
            language=contract.reply_language,
        )

    def generate_guidance(
        self,
        *,
        training_session_id: str,
        task_goal: str,
        rubric: dict[str, object] | None = None,
        recent_turns: Iterable[TranscriptTurn | dict[str, object]] = (),
        feedback_mode: TrainingFeedbackMode | str = TrainingFeedbackMode.ASSISTED,
        language: str = "en-US",
    ) -> list[GuideEvent]:
        state = self.build_state(
            training_session_id=training_session_id,
            task_goal=task_goal,
            rubric=rubric,
            recent_turns=recent_turns,
            feedback_mode=feedback_mode,
            language=language,
        )
        if state.feedback_mode == TrainingFeedbackMode.SIMULATION:
            return []
        events = self._deterministic_events(state)
        if self.llm_callback is not None:
            events.extend(self._coerce_event(event) for event in self.llm_callback(state))
        return self._events_for_mode(state, events)[: self.max_events]

    async def generate_guidance_async(
        self,
        *,
        training_session_id: str,
        task_goal: str,
        rubric: dict[str, object] | None = None,
        recent_turns: Iterable[TranscriptTurn | dict[str, object]] = (),
        feedback_mode: TrainingFeedbackMode | str = TrainingFeedbackMode.ASSISTED,
        language: str = "en-US",
    ) -> list[GuideEvent]:
        state = self.build_state(
            training_session_id=training_session_id,
            task_goal=task_goal,
            rubric=rubric,
            recent_turns=recent_turns,
            feedback_mode=feedback_mode,
            language=language,
        )
        if state.feedback_mode == TrainingFeedbackMode.SIMULATION:
            return []
        events = self._deterministic_events(state)
        if self.llm_callback is not None:
            events.extend(self._coerce_event(event) for event in self.llm_callback(state))
        if self.async_llm_callback is not None:
            try:
                llm_events = await self.async_llm_callback(state)
            except Exception:
                logger.exception("Training live guidance LLM callback failed")
            else:
                events.extend(self._coerce_event(event) for event in llm_events)
        return self._events_for_mode(state, events)[: self.max_events]

    def _deterministic_events(self, state: GuidanceState) -> list[GuideEvent]:
        if state.feedback_mode == TrainingFeedbackMode.SIMULATION:
            return []
        if state.feedback_mode == TrainingFeedbackMode.DRILL:
            return self._build_drill_correction(state)
        return [
            *self._detect_filler_opening(state),
            *self._detect_objection(state),
            *self._detect_delivery_nudge(state),
            *self._detect_missing_question(state),
            *self._build_next_reply(state),
        ]

    def _detect_filler_opening(self, state: GuidanceState) -> list[GuideEvent]:
        latest_user_turn = self._latest_turn(state.user_turns)
        if latest_user_turn is None:
            return []
        match = self._FILLER_PREFIX_RE.match(latest_user_turn.text)
        if match is None:
            return []
        revised = latest_user_turn.text[match.end() :].strip()
        if not revised:
            return []
        return [
            GuideEvent(
                event_type=GuideEventType.DELIVERY_NUDGE,
                severity=GuideSeverity.INFO,
                title=localized_guidance_text(
                    state.language,
                    english="Remove the filler opening",
                    chinese="去掉开头的口头填充词",
                ),
                message=localized_guidance_text(
                    state.language,
                    english="Remove the opening filler and state the core message directly.",
                    chinese="删掉开头的口头填充词，直接说出核心信息。",
                ),
                suggested_text=revised,
                metadata={
                    "training_session_id": state.training_session_id,
                    "targetTurnId": latest_user_turn.turn_id,
                    "matchedFiller": match.group("filler"),
                    "rule": "leading_filler",
                },
            )
        ]

    def _build_drill_correction(self, state: GuidanceState) -> list[GuideEvent]:
        latest_user_turn = self._latest_turn(state.user_turns)
        if latest_user_turn is None:
            return []
        compact_answer = self._LEADING_SPOKEN_FILLER_RE.sub("", latest_user_turn.text).strip()
        removed_fillers = bool(compact_answer and compact_answer != latest_user_turn.text.strip())
        return [
            GuideEvent(
                event_type=GuideEventType.CORRECTION,
                severity=GuideSeverity.INFO,
                title=localized_guidance_text(
                    state.language,
                    english="Review the last answer",
                    chinese="纠正上一句表达",
                ),
                message=localized_guidance_text(
                    state.language,
                    english=(
                        "Remove the opening filler and lead with the main point."
                        if removed_fillers
                        else "Lead with the main point, then add one concrete reason or example."
                    ),
                    chinese=(
                        "删掉开头的口头填充词，直接说出核心信息。"
                        if removed_fillers
                        else "先说核心信息，再补充一个具体原因或例子。"
                    ),
                ),
                suggested_text=compact_answer if removed_fillers else None,
                metadata={
                    "training_session_id": state.training_session_id,
                    "feedbackMode": TrainingFeedbackMode.DRILL.value,
                    "language": state.language,
                    "targetTurnId": latest_user_turn.turn_id,
                    "channel": "side_event",
                    "requiresRetry": False,
                    "source": "deterministic_fallback",
                },
            )
        ]

    def _events_for_mode(
        self,
        state: GuidanceState,
        events: Sequence[GuideEvent],
    ) -> list[GuideEvent]:
        if state.feedback_mode == TrainingFeedbackMode.SIMULATION:
            return []
        if state.feedback_mode == TrainingFeedbackMode.ASSISTED:
            return [
                self._with_contract_metadata(event, state)
                for event in events
                if self._event_type(event) != "correction"
            ]

        corrections = [event for event in events if self._event_type(event) == "correction"]
        llm_corrections = [
            event for event in corrections if event.metadata.get("source") == "llm"
        ]
        return [
            self._with_contract_metadata(event, state)
            for event in (llm_corrections or corrections)
        ]

    @staticmethod
    def _with_contract_metadata(event: GuideEvent, state: GuidanceState) -> GuideEvent:
        metadata = dict(event.metadata)
        metadata.setdefault("feedbackMode", state.feedback_mode.value)
        metadata.setdefault("language", state.language)
        metadata.setdefault("channel", "side_event")
        return replace(event, metadata=metadata)

    def _detect_delivery_nudge(self, state: GuidanceState) -> list[GuideEvent]:
        latest_user_turn = self._latest_turn(state.user_turns)
        if latest_user_turn is None:
            return []
        word_count = len(self._WORD_RE.findall(latest_user_turn.text))
        if word_count < self.monologue_word_threshold:
            return []
        return [
            GuideEvent(
                event_type=GuideEventType.DELIVERY_NUDGE,
                severity=GuideSeverity.WARNING,
                title=localized_guidance_text(
                    state.language,
                    english="Tighten the delivery",
                    chinese="收紧表达",
                ),
                message=localized_guidance_text(
                    state.language,
                    english=(
                        "Your last answer is running long. Land the point, pause, "
                        "and invite the other side in."
                    ),
                    chinese="上一句偏长。先落到重点，停一下，再邀请对方回应。",
                ),
                suggested_text=localized_guidance_text(
                    state.language,
                    english="Let me pause there. Which part would you like me to go deeper on?",
                    chinese="我先说到这里。你希望我重点展开哪一部分？",
                ),
                metadata={
                    "training_session_id": state.training_session_id,
                    "word_count": word_count,
                    "threshold": self.monologue_word_threshold,
                },
            )
        ]

    def _detect_missing_question(self, state: GuidanceState) -> list[GuideEvent]:
        user_text = " ".join(turn.text for turn in state.user_turns)
        if not user_text or self._QUESTION_RE.search(user_text):
            return []

        ask_back = GuideEvent(
            event_type=GuideEventType.ASK_BACK,
            severity=GuideSeverity.INFO,
            title=localized_guidance_text(
                state.language,
                english="Ask a calibration question",
                chinese="先问一个校准问题",
            ),
            message=localized_guidance_text(
                state.language,
                english=(
                    "You have not asked a question in the recent window. Pull out the "
                    "counterpart's priority before continuing."
                ),
                chinese="最近几轮还没有提问。继续表达前，先确认对方最在意的重点。",
            ),
            suggested_text=localized_guidance_text(
                state.language,
                english="Before I go further, what matters most to you in this situation?",
                chinese="在我继续之前，我想先确认一下，这件事里你最看重什么？",
            ),
            metadata={
                "training_session_id": state.training_session_id,
                "window_size": state.window_size,
                "rule": "no_user_question_in_window",
            },
        )
        omission = GuideEvent(
            event_type=GuideEventType.OMISSION,
            severity=GuideSeverity.WARNING,
            title=localized_guidance_text(
                state.language,
                english="Discovery gap",
                chinese="信息探索不足",
            ),
            message=localized_guidance_text(
                state.language,
                english=(
                    "The recent exchange is light on discovery. Add one focused question "
                    "before pitching or defending."
                ),
                chinese="最近的交流缺少信息探索。提出方案或辩护前，先补一个聚焦问题。",
            ),
            suggested_text=localized_guidance_text(
                state.language,
                english="What constraint or success metric should I optimize for?",
                chinese="我应该优先满足哪个约束或成功指标？",
            ),
            metadata={
                "training_session_id": state.training_session_id,
                "task_goal": state.task_goal,
                "rubric_keys": sorted(state.rubric.keys()),
            },
        )
        return [ask_back, omission]

    def _detect_objection(self, state: GuidanceState) -> list[GuideEvent]:
        latest_counterpart = self._latest_turn(state.counterpart_turns)
        if latest_counterpart is None:
            return []
        match = self._OBJECTION_RE.search(latest_counterpart.text)
        if match is None:
            return []
        return [
            GuideEvent(
                event_type=GuideEventType.RISK,
                severity=GuideSeverity.WARNING,
                title=localized_guidance_text(
                    state.language,
                    english="Objection surfaced",
                    chinese="对方提出了异议",
                ),
                message=localized_guidance_text(
                    state.language,
                    english=(
                        "The counterpart just signaled resistance. Acknowledge it before "
                        "adding more evidence."
                    ),
                    chinese="对方刚刚表达了阻力。先接住异议，再补充证据。",
                ),
                suggested_text=localized_guidance_text(
                    state.language,
                    english=(
                        "That concern makes sense. Can I check whether the main issue is "
                        "impact, cost, or timing?"
                    ),
                    chinese="这个顾虑可以理解。我确认一下，主要问题是影响、成本还是时间？",
                ),
                metadata={
                    "training_session_id": state.training_session_id,
                    "risk_type": "objection",
                    "matched_phrase": match.group(0).lower(),
                },
            )
        ]

    def _build_next_reply(self, state: GuidanceState) -> list[GuideEvent]:
        if not state.recent_turns:
            suggested = localized_guidance_text(
                state.language,
                english=(
                    "Start by clarifying the goal and asking what the other side cares about most."
                ),
                chinese="先确认目标，再询问对方最关心什么。",
            )
        elif self._latest_turn(state.counterpart_turns) is not None:
            suggested = localized_guidance_text(
                state.language,
                english=(
                    "Acknowledge their point, ask one clarifying question, then give a "
                    "concise answer."
                ),
                chinese="先回应对方的观点，追问一个澄清问题，再给出简洁回答。",
            )
        else:
            suggested = localized_guidance_text(
                state.language,
                english="Give the short answer first, support it with one example, then pause.",
                chinese="先给简短答案，再用一个例子支撑，然后停下来。",
            )

        return [
            GuideEvent(
                event_type=GuideEventType.NEXT_REPLY,
                severity=GuideSeverity.INFO,
                title=localized_guidance_text(
                    state.language,
                    english="Next reply candidate",
                    chinese="下一句建议",
                ),
                message=localized_guidance_text(
                    state.language,
                    english="A compact next move based on the current bounded transcript window.",
                    chinese="根据当前有限对话窗口生成的简短下一步建议。",
                ),
                suggested_text=suggested,
                metadata={
                    "training_session_id": state.training_session_id,
                    "window_size": state.window_size,
                    "total_turn_count": state.total_turn_count,
                    "strategy": "bounded_recent_turns",
                },
            )
        ]

    def _coerce_turn(self, turn: TranscriptTurn | dict[str, object]) -> TranscriptTurn:
        if isinstance(turn, TranscriptTurn):
            return turn
        return TranscriptTurn(
            speaker=turn.get("speaker", TranscriptSpeaker.USER),
            text=str(turn.get("text", "")),
            turn_id=str(turn["turn_id"]) if turn.get("turn_id") is not None else None,
            created_at=turn.get("created_at") if isinstance(turn.get("created_at"), datetime) else None,
            metadata=dict(turn.get("metadata") or {}),
        )

    def _coerce_event(self, event: GuideEvent | dict[str, object]) -> GuideEvent:
        if isinstance(event, GuideEvent):
            return event
        return GuideEvent(
            event_type=event.get("event_type", GuideEventType.NEXT_REPLY),
            severity=event.get("severity", GuideSeverity.INFO),
            title=str(event.get("title", "Guidance")),
            message=str(event.get("message", "")),
            suggested_text=(
                str(event["suggested_text"]) if event.get("suggested_text") is not None else None
            ),
            metadata=dict(event.get("metadata") or {}),
        )

    def _latest_turn(self, turns: Sequence[TranscriptTurn]) -> TranscriptTurn | None:
        return turns[-1] if turns else None

    @staticmethod
    def _event_type(event: GuideEvent) -> str:
        if isinstance(event.event_type, GuideEventType):
            return event.event_type.value
        return str(event.event_type).strip().lower()
