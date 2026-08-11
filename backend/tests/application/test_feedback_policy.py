from application.services.training_studio.feedback_policy import (
    TrainingFeedbackMode,
    counterpart_feedback_instruction,
    resolve_training_feedback_contract,
)
from application.services.stakeholder.stakeholder_chat_service import (
    _selected_reply_language_from_history,
    _training_feedback_metadata_from_history,
)


def test_resolves_mode_and_language_from_training_metadata() -> None:
    contract = resolve_training_feedback_contract(
        {
            "feedbackPolicy": {"mode": "drill"},
            "language": {"replyLanguage": "zh-CN"},
        }
    )

    assert contract.mode == TrainingFeedbackMode.DRILL
    assert contract.reply_language == "zh-CN"
    assert contract.correction_only is True


def test_counterpart_instruction_keeps_correction_out_of_visible_reply() -> None:
    instruction = counterpart_feedback_instruction(TrainingFeedbackMode.DRILL)

    assert "separate structured" in instruction
    assert "visible reply" in instruction
    assert "answer only as the counterpart" in instruction


def test_turn_based_room_recovers_contract_from_persisted_opening_metadata() -> None:
    history = [
        {
            "sender_type": "persona",
            "content": "Let's begin.",
            "metadata": {
                "feedbackMode": "assisted",
                "trainingReplyLanguage": "zh-CN",
            },
        },
        {"sender_type": "user", "content": "好的", "metadata": {}},
    ]

    assert _training_feedback_metadata_from_history(history) == history[0]["metadata"]
    assert _selected_reply_language_from_history(history) == "zh-CN"
