import pytest


def _entries(catalog: dict, channel: str) -> list[dict]:
    return list(catalog["channels"].get(channel, []))


def _find_entry(catalog: dict, *, channel: str, module: str) -> dict:
    for entry in _entries(catalog, channel):
        if entry["module"] == module:
            return entry
    raise AssertionError(f"missing {channel} catalog entry for {module}")


def test_pipecat_provider_catalog_localizes_installed_channels():
    pytest.importorskip("pipecat")

    from infrastructure.external.pipecat import pipecat_provider_catalog

    catalog = pipecat_provider_catalog()

    assert catalog["schemaVersion"] == 1
    assert catalog["package"] == "pipecat"
    assert catalog["source"] == "local_installed_pipecat_package"
    assert catalog["entryCount"] > 50
    for channel in (
        "stt",
        "tts",
        "llm",
        "realtime",
        "transport",
        "vad",
        "turn_detection",
    ):
        assert _entries(catalog, channel), f"{channel} should have local Pipecat entries"

    assert _find_entry(
        catalog,
        channel="stt",
        module="pipecat.services.openai.stt",
    )["adapterStatus"] == "runtime_integrated"
    assert _find_entry(
        catalog,
        channel="tts",
        module="pipecat.services.openai.tts",
    )["adapterStatus"] == "runtime_integrated"
    assert _find_entry(
        catalog,
        channel="llm",
        module="pipecat.services.openrouter.llm",
    )["adapterStatus"] == "runtime_integrated"
    websocket = _find_entry(
        catalog,
        channel="transport",
        module="pipecat.transports.websocket.fastapi",
    )
    assert websocket["provider"] == "websocket"
    assert websocket["variant"] == "fastapi"
    assert websocket["adapterStatus"] == "runtime_integrated"

    deepgram = _find_entry(
        catalog,
        channel="stt",
        module="pipecat.services.deepgram.stt",
    )
    assert deepgram["adapterStatus"] == "inventory_only"


def test_pipecat_provider_catalog_summary_is_capability_safe():
    pytest.importorskip("pipecat")

    from infrastructure.external.pipecat import pipecat_provider_catalog_summary

    summary = pipecat_provider_catalog_summary()

    assert summary["schemaVersion"] == 1
    assert summary["packageVersion"]
    assert "openai" in summary["channels"]["stt"]["runtimeIntegrated"]
    assert "openrouter" in summary["channels"]["llm"]["runtimeIntegrated"]
    assert "deepgram" in summary["channels"]["stt"]["inventoryOnly"]
    assert "elevenlabs" in summary["channels"]["tts"]["inventoryOnly"]


def test_pipecat_capability_response_exposes_provider_catalog_summary():
    pytest.importorskip("pipecat")

    from infrastructure.external.pipecat import pipecat_realtime_capability_response

    response = pipecat_realtime_capability_response(
        require_websocket=True,
        openai_api_key_available=True,
        include_source_snapshot=False,
        input_audio_format="pcm16",
        output_audio_format="pcm16",
    )

    summary = response["providerCatalogSummary"]
    assert "openai" in summary["channels"]["stt"]["runtimeIntegrated"]
    assert "openrouter" in summary["channels"]["llm"]["runtimeIntegrated"]
    assert "daily" in summary["channels"]["transport"]["inventoryOnly"]


def test_pipecat_source_snapshot_contains_full_provider_catalog():
    pytest.importorskip("pipecat")

    from infrastructure.external.pipecat import pipecat_source_snapshot

    snapshot = pipecat_source_snapshot()

    assert "pipecat.services.openrouter.llm" in snapshot["runtimeIntegratedProviderModules"]
    catalog = snapshot["providerCatalog"]
    assert catalog["schemaVersion"] == 1
    assert _find_entry(
        catalog,
        channel="llm",
        module="pipecat.services.openrouter.llm",
    )["adapterStatus"] == "runtime_integrated"
