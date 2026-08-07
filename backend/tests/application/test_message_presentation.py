from __future__ import annotations

from application.services.stakeholder.sentence_buffer import SentenceBuffer
from application.services.training_studio.message_presentation import (
    extract_emotion,
    strip_parenthetical_cues_for_speech,
)


def test_extract_emotion_removes_private_marker_and_clamps_score():
    content, score, label = extract_emotion(
        '（皱眉）这个数字我不能接受。<!--emotion:{"score":9,"label":"质疑"}-->'
    )

    assert content == '（皱眉）这个数字我不能接受。'
    assert score == 5
    assert label == '质疑'


def test_speech_filter_removes_all_parenthetical_material():
    assert strip_parenthetical_cues_for_speech('成本（含税）已经超预算。') == '成本已经超预算。'
    assert strip_parenthetical_cues_for_speech('（皱眉）这个数字不对。') == '这个数字不对。'


def test_sentence_buffer_does_not_send_stage_directions_to_tts():
    buffer = SentenceBuffer(min_length=1)

    assert buffer.feed('（皱眉）这个数字不对。') == '这个数字不对。'
    assert buffer.feed('成本（含税）已经超预算。') == '成本已经超预算。'
