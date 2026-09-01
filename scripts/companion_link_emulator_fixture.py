from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from romverse.companion.pairing import create_pairing_code
from romverse.companion.telemetry import (
    CompanionTelemetry,
    DeviceDnaCapabilityTelemetry,
    LiveConsoleTelemetryEvent,
)
from romverse.companion.transport import CompanionTransport


def fixture_telemetry() -> CompanionTelemetry:
    event = LiveConsoleTelemetryEvent(
        event_id="emulator-link-contract",
        updated_at=datetime.now(UTC).isoformat(),
        source="ROMVERSE Link fixture",
        stage="emulator-read-only-verification",
        title="Emulator Link contract verified",
        summary="The Android runtime received genuine TLS-pinned Desktop telemetry.",
        explanation=(
            "This contained fixture exercises pairing, approval, telemetry parsing, Live Console, "
            "and the return health channel without touching a physical phone."
        ),
        next_action="Recreate the Activity and prove the remembered session reconnects.",
        state="succeeded",
        progress_percent=100,
        confidence="verified",
        guardian_protected=True,
    )
    capability = DeviceDnaCapabilityTelemetry(
        capability_id="link.read_only",
        label="Read-only Companion Link",
        state="SUPPORTED",
        detail="TLS-pinned emulator integration fixture; execution authority remains none.",
    )
    return CompanionTelemetry(
        battery_percent=73,
        storage_used_bytes=32 * 1024 * 1024,
        storage_total_bytes=128 * 1024 * 1024,
        ascension_state="review_ready",
        ascension_project="Emulator Ascension Fixture",
        ascension_method="magisk",
        ascension_target_partition="init_boot",
        ascension_blocker_count=0,
        ascension_stage_number=9,
        ascension_stage_title="Ready for final Guardian review",
        ascension_next_action="Review the exact manifest on ROMVERSE Desktop.",
        ascension_why="The exact phone, source image, and rollback route must still match.",
        ascension_romverse_action=(
            "ROMVERSE verified the official manager provenance and compiled a read-only review."
        ),
        ascension_manager_state="verified",
        ascension_manager_repository="topjohnwu/Magisk",
        ascension_manager_tag="v30.7",
        ascension_manager_asset="Magisk-v30.7.apk",
        ascension_manager_sha256_ref="e0d32d2123532860",
        live_console_events=(event,),
        nexus_status="ready-for-guardian",
        nexus_objective="build-rom",
        nexus_current_stage="Verification",
        guardian_review_state="ready",
        device_dna_state="ready",
        device_dna_project="Emulator Link Fixture",
        device_dna_profile_ref="a" * 16,
        device_dna_capabilities=(capability,),
    )


def emit(**payload: object) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), flush=True)


def main() -> int:
    pairing = create_pairing_code(ttl_minutes=3)
    with TemporaryDirectory(prefix="romverse-link-emulator-") as temporary:
        transport = CompanionTransport(
            lambda: pairing,
            fixture_telemetry,
            identity_root=Path(temporary),
        )
        if not transport.available:
            emit(state="unavailable", detail=transport.availability_error)
            return 2
        transport.start()
        emit(
            state="ready",
            emulator_host=f"10.0.2.2:{transport.port}",
            pairing_code=pairing.code,
            certificate_sha256=transport.certificate_sha256,
            safety_code=transport.safety_code,
            execution_authority="none",
        )
        deadline = time.monotonic() + 90.0
        first_snapshot_at = None
        approved = False
        try:
            while time.monotonic() < deadline:
                if transport.pending and not approved:
                    approved = transport.approve()
                    emit(state="approved", approved=approved)
                received_at = transport.remote_snapshot_received_at
                if received_at is not None and first_snapshot_at is None:
                    first_snapshot_at = received_at
                    snapshot = transport.latest_remote_snapshot
                    emit(
                        state="first-health-snapshot",
                        model=snapshot.model if snapshot is not None else "",
                    )
                elif received_at is not None and received_at != first_snapshot_at:
                    snapshot = transport.latest_remote_snapshot
                    emit(
                        state="complete",
                        model=snapshot.model if snapshot is not None else "",
                        vitalis_state=snapshot.vitalis_state if snapshot is not None else "",
                        execution_authority="none",
                    )
                    return 0
                time.sleep(0.1)
            emit(
                state="timeout",
                approved=approved,
                first_health_snapshot=first_snapshot_at is not None,
            )
            return 1
        finally:
            transport.close()


if __name__ == "__main__":
    raise SystemExit(main())
