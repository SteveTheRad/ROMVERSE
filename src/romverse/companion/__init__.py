"""ROMVERSE Companion pairing and read-only transport contracts."""

from romverse.companion.telemetry import (
    ActivityEvent,
    CompanionTelemetry,
    LiveConsoleTelemetryEvent,
    RawTerminalTelemetryRecord,
    RemoteCompanionSnapshot,
)
from romverse.companion.transport import CompanionTransport

__all__ = [
    "ActivityEvent",
    "CompanionTelemetry",
    "CompanionTransport",
    "RemoteCompanionSnapshot",
    "LiveConsoleTelemetryEvent",
    "RawTerminalTelemetryRecord",
]
