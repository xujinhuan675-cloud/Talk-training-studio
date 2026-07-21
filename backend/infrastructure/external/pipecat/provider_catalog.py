"""Local Pipecat provider inventory for TalkWise migration planning.

The project should depend on Pipecat's installed package for implementation,
not copy upstream provider code into this repository. This module localizes the
provider/channel contract we expose to the product, tests, and docs.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import inspect
import pkgutil
from dataclasses import dataclass
from functools import lru_cache
from types import ModuleType
from typing import Any, Iterable


PIPECAT_PROVIDER_CATALOG_SCHEMA_VERSION = 1
_SERVICE_ROOT = "pipecat.services"
_TRANSPORT_ROOT = "pipecat.transports"
_AUDIO_ROOT = "pipecat.audio"
_AUDIO_VAD_ROOT = "pipecat.audio.vad"
_AUDIO_TURN_ROOT = "pipecat.audio.turn"
_TURNS_ROOT = "pipecat.turns"

_SERVICE_CORE_MODULES = {
    "ai_service",
    "image_service",
    "llm_service",
    "mcp_service",
    "settings",
    "stt_latency",
    "stt_service",
    "tts_service",
    "vision_service",
    "websocket_service",
}

_RUNTIME_INTEGRATED_MODULES = {
    "pipecat.audio.vad.silero": "runtime_integrated",
    "pipecat.audio.vad.vad_analyzer": "runtime_integrated",
    "pipecat.processors.audio.vad_processor": "runtime_integrated",
    "pipecat.services.openai.stt": "runtime_integrated",
    "pipecat.services.openai.tts": "runtime_integrated",
    "pipecat.services.openai.llm": "runtime_integrated",
    "pipecat.services.openrouter.llm": "runtime_integrated",
    "pipecat.transports.websocket.fastapi": "runtime_integrated",
    "pipecat.turns.user_turn_processor": "runtime_integrated",
    "pipecat.turns.user_turn_strategies": "runtime_integrated",
    "pipecat.turns.user_turn_completion_mixin": "runtime_integrated",
}

_CATALOG_ROOTS = (
    _SERVICE_ROOT,
    _TRANSPORT_ROOT,
    _AUDIO_VAD_ROOT,
    _AUDIO_TURN_ROOT,
    _TURNS_ROOT,
)


@dataclass(frozen=True)
class PipecatProviderCatalogEntry:
    """A local inventory entry for one Pipecat-owned provider/module."""

    channel: str
    provider: str
    module: str
    source: str
    package: str = "pipecat"
    variant: str | None = None
    class_names: tuple[str, ...] = ()
    adapter_status: str = "inventory_only"
    module_spec_available: bool = True
    import_available: bool | None = None
    import_error: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "channel": self.channel,
            "provider": self.provider,
            "module": self.module,
            "source": self.source,
            "package": self.package,
            "adapterStatus": self.adapter_status,
            "moduleSpecAvailable": self.module_spec_available,
        }
        if self.variant:
            data["variant"] = self.variant
        if self.class_names:
            data["classes"] = list(self.class_names)
        if self.import_available is not None:
            data["importAvailable"] = self.import_available
        if self.import_error:
            data["importError"] = self.import_error
        return data


def pipecat_provider_catalog(
    *,
    probe_imports: bool = False,
) -> dict[str, Any]:
    """Return the local Pipecat provider catalog grouped by channel."""

    entries = sorted(
        _iter_pipecat_provider_entries(probe_imports=probe_imports),
        key=lambda item: (item.channel, item.provider, item.module),
    )
    channels: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        channels.setdefault(entry.channel, []).append(entry.to_public_dict())

    return {
        "schemaVersion": PIPECAT_PROVIDER_CATALOG_SCHEMA_VERSION,
        "package": "pipecat",
        "packageVersion": _pipecat_version(),
        "source": "local_installed_pipecat_package",
        "probeImports": probe_imports,
        "entryCount": len(entries),
        "channels": channels,
        "summary": _provider_catalog_summary(entries),
    }


def pipecat_provider_catalog_summary() -> dict[str, Any]:
    """Return a compact summary suitable for capability payload metadata."""

    entries = tuple(_iter_pipecat_provider_entries(probe_imports=False))
    return {
        "schemaVersion": PIPECAT_PROVIDER_CATALOG_SCHEMA_VERSION,
        "packageVersion": _pipecat_version(),
        "source": "local_installed_pipecat_package",
        "channels": _provider_catalog_summary(entries),
    }


def pipecat_integrated_provider_modules() -> tuple[str, ...]:
    """Return Pipecat modules that are wired into the runtime adapter today."""

    return tuple(sorted(_RUNTIME_INTEGRATED_MODULES))


@lru_cache(maxsize=2)
def _iter_pipecat_provider_entries_cached(probe_imports: bool) -> tuple[PipecatProviderCatalogEntry, ...]:
    return tuple(_discover_pipecat_provider_entries(probe_imports=probe_imports))


def _iter_pipecat_provider_entries(
    *,
    probe_imports: bool,
) -> Iterable[PipecatProviderCatalogEntry]:
    return _iter_pipecat_provider_entries_cached(bool(probe_imports))


def _discover_pipecat_provider_entries(
    *,
    probe_imports: bool,
) -> Iterable[PipecatProviderCatalogEntry]:
    seen: set[str] = set()
    for root in _CATALOG_ROOTS:
        for module_name in _walk_pipecat_modules(root):
            if module_name in seen:
                continue
            seen.add(module_name)
            classified = _classify_module(module_name)
            if classified is None:
                continue
            channel, provider, variant = classified
            yield _entry(
                channel=channel,
                provider=provider,
                module=module_name,
                source=root,
                variant=variant,
                probe_imports=probe_imports,
            )


def _walk_pipecat_modules(root: str) -> tuple[str, ...]:
    try:
        module = importlib.import_module(root)
    except Exception:
        return ()
    module_path = getattr(module, "__path__", None)
    if module_path is None:
        return ()
    names = []
    for info in pkgutil.walk_packages(module_path, f"{root}."):
        name = info.name
        if ".tests" in name or "._" in name:
            continue
        names.append(name)
    return tuple(sorted(names))


def _classify_module(module_name: str) -> tuple[str, str, str | None] | None:
    if module_name.startswith(f"{_SERVICE_ROOT}."):
        return _classify_service_module(module_name)
    if module_name.startswith(f"{_TRANSPORT_ROOT}."):
        return _classify_transport_module(module_name)
    if module_name.startswith(f"{_AUDIO_VAD_ROOT}."):
        return _classify_audio_vad_module(module_name)
    if module_name.startswith(f"{_AUDIO_TURN_ROOT}."):
        return _classify_audio_turn_module(module_name)
    if module_name.startswith(f"{_TURNS_ROOT}."):
        return _classify_turn_module(module_name)
    return None


def _classify_service_module(module_name: str) -> tuple[str, str, str | None] | None:
    suffix = module_name[len(f"{_SERVICE_ROOT}.") :]
    parts = suffix.split(".")
    if not parts or parts[0] in _SERVICE_CORE_MODULES:
        return None

    provider = parts[0]
    leaf = parts[-1]
    middle = parts[1:-1]

    if "realtime" in middle or "gemini_live" in middle or "nova_sonic" in middle:
        return ("realtime", _provider_id(provider, middle), leaf if leaf != "llm" else None)
    if leaf in {"stt", "tts", "llm", "image", "video"}:
        return (leaf, _provider_id(provider, middle), None)
    if leaf == "vision":
        return ("vision", _provider_id(provider, middle), None)
    if leaf == "memory":
        return ("memory", _provider_id(provider, middle), None)
    if leaf in {"turns", "events", "rtvi"}:
        return ("service_extension", _provider_id(provider, middle), leaf)
    return None


def _classify_transport_module(module_name: str) -> tuple[str, str, str | None] | None:
    suffix = module_name[len(f"{_TRANSPORT_ROOT}.") :]
    parts = suffix.split(".")
    if len(parts) < 2:
        return None
    provider = parts[0]
    variant = ".".join(parts[1:]) if len(parts) > 1 else None
    return ("transport", provider, variant)


def _classify_audio_vad_module(module_name: str) -> tuple[str, str, str | None] | None:
    provider = module_name[len(f"{_AUDIO_VAD_ROOT}.") :]
    if provider in {"data", "vad_analyzer", "vad_controller"}:
        return ("vad_support", provider, None)
    return ("vad", provider, None)


def _classify_audio_turn_module(module_name: str) -> tuple[str, str, str | None] | None:
    provider = module_name[len(f"{_AUDIO_TURN_ROOT}.") :]
    if provider in {"base_turn_analyzer", "smart_turn"}:
        return ("turn_analysis", provider, None)
    return ("turn_analysis", provider, None)


def _classify_turn_module(module_name: str) -> tuple[str, str, str | None] | None:
    provider = module_name[len(f"{_TURNS_ROOT}.") :]
    return ("turn_detection", provider, None)


def _entry(
    *,
    channel: str,
    provider: str,
    module: str,
    source: str,
    variant: str | None,
    probe_imports: bool,
) -> PipecatProviderCatalogEntry:
    import_available: bool | None = None
    import_error: str | None = None
    class_names: tuple[str, ...] = ()
    module_spec_available = _module_spec_available(module)

    if probe_imports and module_spec_available:
        try:
            imported = importlib.import_module(module)
            import_available = True
            class_names = _public_class_names(imported)
        except Exception as exc:
            import_available = False
            import_error = f"{exc.__class__.__name__}: {exc}"

    return PipecatProviderCatalogEntry(
        channel=channel,
        provider=provider,
        module=module,
        source=source,
        variant=variant,
        class_names=class_names,
        adapter_status=_RUNTIME_INTEGRATED_MODULES.get(module, "inventory_only"),
        module_spec_available=module_spec_available,
        import_available=import_available,
        import_error=import_error,
    )


def _provider_id(provider: str, middle: list[str]) -> str:
    if not middle:
        return provider
    return ".".join([provider, *middle])


def _provider_catalog_summary(
    entries: Iterable[PipecatProviderCatalogEntry],
) -> dict[str, Any]:
    summary: dict[str, dict[str, Any]] = {}
    for entry in entries:
        bucket = summary.setdefault(
            entry.channel,
            {
                "count": 0,
                "providers": set(),
                "runtimeIntegrated": set(),
                "inventoryOnly": set(),
            },
        )
        bucket["count"] += 1
        bucket["providers"].add(entry.provider)
        target = (
            bucket["runtimeIntegrated"]
            if entry.adapter_status == "runtime_integrated"
            else bucket["inventoryOnly"]
        )
        target.add(entry.provider)

    public: dict[str, Any] = {}
    for channel, data in sorted(summary.items()):
        public[channel] = {
            "count": data["count"],
            "providers": sorted(data["providers"]),
            "runtimeIntegrated": sorted(data["runtimeIntegrated"]),
            "inventoryOnly": sorted(data["inventoryOnly"]),
        }
    return public


def _public_class_names(module: ModuleType) -> tuple[str, ...]:
    names = []
    for name, value in inspect.getmembers(module, inspect.isclass):
        if name.startswith("_"):
            continue
        if getattr(value, "__module__", "") != module.__name__:
            continue
        names.append(name)
    return tuple(sorted(names))


def _module_spec_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _pipecat_version() -> str | None:
    for package_name in ("pipecat-ai", "pipecat"):
        try:
            return importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            continue
    try:
        module = importlib.import_module("pipecat")
    except Exception:
        return None
    return str(getattr(module, "__version__", "") or "") or None


__all__ = [
    "PIPECAT_PROVIDER_CATALOG_SCHEMA_VERSION",
    "PipecatProviderCatalogEntry",
    "pipecat_integrated_provider_modules",
    "pipecat_provider_catalog",
    "pipecat_provider_catalog_summary",
]
