import pytest

from application.services.training_studio.realtime_session import (
    RealtimeEventType,
    RealtimeSession,
    RealtimeSessionStateError,
    RealtimeSessionStatus,
)


def test_realtime_session_audio_flow_records_ordered_events():
    session = RealtimeSession(session_id="session-1")

    started = session.start({"room_id": 7})
    audio = session.receive_audio(b"abc", "audio/webm")
    committed = session.commit_audio()
    delta = session.transcript_delta("hel")
    done = session.transcript_done("hello")
    output = session.send_audio(b"voice", "audio/mpeg")
    closed = session.close("done")

    assert started.type == RealtimeEventType.SESSION_STARTED
    assert started.payload == {"room_id": 7}
    assert audio.payload == {"bytes": 3, "mime_type": "audio/webm", "sequence": 1}
    assert committed.status == RealtimeSessionStatus.PROCESSING
    assert delta.payload == {"text": "hel"}
    assert done.payload == {"text": "hello"}
    assert output.status == RealtimeSessionStatus.SPEAKING
    assert closed.status == RealtimeSessionStatus.CLOSED
    assert [event.type for event in session.events] == [
        RealtimeEventType.SESSION_STARTED,
        RealtimeEventType.AUDIO_INPUT,
        RealtimeEventType.AUDIO_COMMITTED,
        RealtimeEventType.TRANSCRIPT_DELTA,
        RealtimeEventType.TRANSCRIPT_DONE,
        RealtimeEventType.AUDIO_OUTPUT,
        RealtimeEventType.SESSION_CLOSED,
    ]


def test_realtime_session_rejects_output_before_processing():
    session = RealtimeSession()
    session.start()
    session.listen()

    with pytest.raises(RealtimeSessionStateError, match="Cannot send audio"):
        session.send_audio(b"voice")


def test_realtime_session_fail_then_close():
    session = RealtimeSession()
    session.start()

    error = session.fail("upstream unavailable", "upstream_error")
    closed = session.close()

    assert error.status == RealtimeSessionStatus.ERROR
    assert error.payload == {
        "message": "upstream unavailable",
        "code": "upstream_error",
    }
    assert closed.status == RealtimeSessionStatus.CLOSED


def test_realtime_session_closed_is_terminal():
    session = RealtimeSession()
    session.close()

    with pytest.raises(RealtimeSessionStateError, match="Invalid realtime transition"):
        session.start()
