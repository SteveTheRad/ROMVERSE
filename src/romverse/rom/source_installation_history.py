"""Bounded, read-only installation history; no new execution or health authority."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path, PurePosixPath

from romverse.guardian.local_flash import LocalFlashState
from romverse.guardian.source_installation import (
    SourceInstallationResult,
    SourceInstallationStepResult,
    validate_source_installation_provenance,
)
from romverse.infrastructure.local_store import read_json_object
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_installation import (
    POPSICLE_PHYSICAL_PARTITIONS,
    POPSICLE_SCRIPT_SHA256,
)


@dataclass(frozen=True, slots=True)
class SourceInstallationOutcome:
    state: str
    summary: str
    receipt_path: Path
    source_sha256: str
    completed_count: int
    expected_count: int
    boot_status: str
    boot_receipt_path: Path | None = None
    device_key: str = ""
    product: str = ""
    result: SourceInstallationResult | None = None
    historical: bool = True
    current_artifact_bytes_verified: bool = False
    project_id: str = ""


_BASE_FIELDS = {
    "format",
    "schema_version",
    "plan_id",
    "plan_digest",
    "project_id",
    "source_sha256",
    "recipe_digest",
    "script_sha256",
    "device_key",
    "product",
    "fastboot_sha256",
    "initial_slot",
    "steps",
    "wipe",
    "reboot",
    "consent",
    "started_at",
    "state",
    "in_flight_step",
    "results",
    "phone_change_attempted",
    "phone_state_uncertain",
    "reboot_requested",
    "android_arrival_verified",
    "boot_verified",
    "readback_verified",
    "production_certification",
}
_TERMINAL_FIELDS = _BASE_FIELDS | {"completed_at", "summary", "record_digest"}
_OPTIONAL_FIELDS = {"image_snapshots", "snapshots_verified"}
_MAX_RECORD_BYTES = 2 * 1024 * 1024
_MAX_TOTAL_BYTES = 8 * 1024 * 1024


def load_latest_source_installation(
    store: RomProjectStore, project_id: str
) -> SourceInstallationOutcome | None:
    """Load the newest source-associated record, without tools or firmware hashing.

    A malformed newer record never reveals an older success instead. A strictly
    reconstructed terminal result may be passed to LocalBoot, which must perform
    its own exact-phone/receipt validation; this function does not authorize it.
    """
    project = store.get(project_id)
    if project.original is None:
        return None
    source = project.original.sha256
    root = store.workspace / "guardian" / "source-installation"
    try:
        paths = _recent(root)
    except (OSError, ValueError):
        return _attention(
            root,
            source,
            "Installation history is unavailable or exceeds its safe read bound.",
            project_id,
        )
    total = 0
    candidates = []
    for path in paths:
        try:
            total += path.stat().st_size
            if total > _MAX_TOTAL_BYTES:
                return _attention(
                    path,
                    source,
                    "Installation history exceeds its bounded review budget.",
                    project_id,
                )
            document = read_json_object(
                path, boundary=store.workspace, maximum_bytes=_MAX_RECORD_BYTES
            )
            # Association only: this is deliberately not fresh archive verification.
            if document.get("project_id") != project_id or document.get("source_sha256") != source:
                # Corrupted association is not trustworthy enough to skip over.
                if not _sealed(document):
                    return _attention(
                        path,
                        source,
                        "A newer installation record cannot be verified; earlier success is not shown.",
                        project_id,
                    )
                continue
            if document.get("state") not in {state.value for state in LocalFlashState}:
                outcome = _attention(
                    path,
                    source,
                    "The latest installation was interrupted or is unfinished. Its phone outcome is unconfirmed; inspect it before retrying.",
                    project_id,
                )
                # Sealed unfinished intents have trustworthy recorded chronology.
                # Unsealed/corrupt intents cannot safely be dated or skipped.
                if not _sealed(document):
                    return outcome
                started = _installation_start(document, path)
                candidates.append((started, started, outcome, None))
                continue
            result = _terminal_result(document, path)
            outcome = SourceInstallationOutcome(
                result.state.value,
                (
                    "Historical rebuilt-candidate installation: "
                    if document["format"] == "romverse.candidate-installation"
                    else "Historical installation: "
                )
                + result.summary[:800],
                path,
                source,
                result.completed_count,
                len(document["steps"]),
                "No linked boot-check record",
                None,
                document["device_key"],
                document["product"],
                result,
                project_id=project_id,
            )
            candidates.append(
                (_time(document["started_at"]), _time(document["completed_at"]), outcome, document)
            )
        except (OSError, ValueError, TypeError, KeyError, ProjectError):
            return _attention(
                path,
                source,
                "The latest installation record is incomplete or invalid. Earlier success is not shown; review the saved evidence and phone.",
                project_id,
            )
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    latest = candidates[0]
    if any(item[:2] == latest[:2] and item[2].state != latest[2].state for item in candidates[1:]):
        return _attention(
            latest[2].receipt_path,
            source,
            "Installation records have ambiguous chronology; no older success is selected.",
            project_id,
        )
    outcome, document = latest[2:]
    if document is None:
        return outcome
    boot_status, boot_path = _boot_history(store.workspace, document, outcome.receipt_path)
    return replace(outcome, boot_status=boot_status, boot_receipt_path=boot_path)


def _attention(path: Path, source: str, summary: str, project_id: str) -> SourceInstallationOutcome:
    return SourceInstallationOutcome(
        "attention",
        "Historical record: " + summary,
        path,
        source,
        0,
        0,
        "No validated linked boot result",
        project_id=project_id,
    )


def _recent(root: Path) -> list[Path]:
    if root.is_symlink() or root.parent.is_symlink():
        raise ValueError("Linked history directory")
    if not root.exists():
        return []
    paths = []
    for index, path in enumerate(root.iterdir()):
        if index >= 1024:
            raise ValueError("Too many history entries")
        if path.suffix == ".json":
            if path.is_symlink() or not path.is_file():
                raise ValueError("Unsafe history entry")
            paths.append(path)
    # Never discard candidate records based on mutable filesystem timestamps.
    # Exceeding the read bound is explicit attention, not an older-success fallback.
    if len(paths) > 128:
        raise ValueError("Too many records for bounded chronological review")
    return sorted(paths)


def _installation_start(document, path):
    candidate = validate_source_installation_provenance(document)
    fields = _BASE_FIELDS | ({"candidate_provenance"} if candidate else set())
    if (
        type(document.get("schema_version")) is not int
        or document["schema_version"] != 1
        or not re.fullmatch(r"[a-f0-9]{32}\.json", path.name)
        or document.get("plan_id") != path.stem
        or document.get("script_sha256") != POPSICLE_SCRIPT_SHA256
        or document.get("state") not in {"preparing", "staging", "prepared", "command-in-flight"}
        or not fields <= set(document) <= fields | _OPTIONAL_FIELDS | {"record_digest"}
        or any(
            document.get(key) is not False
            for key in ("boot_verified", "readback_verified", "production_certification")
        )
    ):
        raise ValueError("Invalid unfinished installation chronology")
    return _time(document["started_at"])


def _terminal_result(document: dict, path: Path) -> SourceInstallationResult:
    candidate = validate_source_installation_provenance(document)
    fields = _TERMINAL_FIELDS | ({"candidate_provenance"} if candidate else set())
    if (
        not fields <= set(document) <= fields | _OPTIONAL_FIELDS
        or not _sealed(document)
        or not re.fullmatch(r"[a-f0-9]{32}\.json", path.name)
        or document["plan_id"] != path.stem
        or type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["script_sha256"] != POPSICLE_SCRIPT_SHA256
        or document["product"] != "popsicle"
        or not isinstance(document["device_key"], str)
        or not re.fullmatch(r"[a-f0-9]{20}", document["device_key"])
        or any(
            not _sha(document[key])
            for key in ("plan_digest", "source_sha256", "recipe_digest", "fastboot_sha256")
        )
        or document["consent"] != "explicit-source-installation-exact-plan"
        or document["initial_slot"] not in {"a", "b"}
        or not isinstance(document["summary"], str)
        or len(document["summary"]) > 8192
        or any(
            type(document[key]) is not bool
            for key in (
                "wipe",
                "reboot",
                "phone_change_attempted",
                "phone_state_uncertain",
                "reboot_requested",
                "android_arrival_verified",
            )
        )
        or any(
            document[key] is not False
            for key in ("boot_verified", "readback_verified", "production_certification")
        )
        or document["phone_change_attempted"] is not document["phone_state_uncertain"]
        or (document["android_arrival_verified"] and not document["reboot_requested"])
    ):
        raise ValueError("Invalid installation contract")
    started, ended = _time(document["started_at"]), _time(document["completed_at"])
    if ended < started:
        raise ValueError("Invalid operation times")
    steps = _steps(document)
    inflight = document["in_flight_step"]
    raw_results = document["results"]
    if not isinstance(raw_results, list) or len(raw_results) > len(steps):
        raise ValueError("Invalid result count")
    if inflight is not None and (
        type(inflight) is not int or inflight != len(raw_results) or inflight >= len(steps)
    ):
        raise ValueError("Invalid unfinished step")
    if raw_results and not document["phone_change_attempted"]:
        raise ValueError("Non-mutating result claims commands")
    results = []
    previous_end = started
    for index, entry in enumerate(raw_results):
        step = steps[index]
        if not isinstance(entry, dict) or set(entry) != {
            "index",
            "action",
            "partition",
            "command",
            "started_at",
            "completed_at",
            "returncode",
            "timed_out",
            "output",
            "verified_slot",
        }:
            raise ValueError("Invalid command result fields")
        if (
            type(entry["index"]) is not int
            or entry["index"] != index
            or entry["action"] != step["action"]
            or entry["partition"] != step["partition"]
            or not isinstance(entry["command"], list)
            or entry["command"] != _command(step)
            or type(entry["returncode"]) is not int
            or type(entry["timed_out"]) is not bool
            or not isinstance(entry["output"], str)
            or len(entry["output"]) > 8192
            or entry["verified_slot"]
            not in ({"", "a"} if entry["action"] == "set_active" else {""})
        ):
            raise ValueError("Invalid ordered command result")
        entry_start, entry_end = _time(entry["started_at"]), _time(entry["completed_at"])
        if not previous_end <= entry_start <= entry_end <= ended:
            raise ValueError("Incoherent command times")
        previous_end = entry_end
        results.append(
            SourceInstallationStepResult(**{**entry, "command": tuple(entry["command"])})
        )
    if any(not result.completed for result in results[:-1]):
        raise ValueError("Commands continued after failure")
    state = LocalFlashState(document["state"])
    if state is LocalFlashState.COMPLETED and (
        len(results) != len(steps)
        or not document["phone_change_attempted"]
        or not all(result.completed for result in results)
        or any(result.action == "set_active" and result.verified_slot != "a" for result in results)
        or inflight is not None
        or document["reboot_requested"] is not document["reboot"]
    ):
        raise ValueError("Unproven completion")
    if state is LocalFlashState.REJECTED and (
        document["phone_change_attempted"] or results or inflight is not None
    ):
        raise ValueError("Rejected record claims changes")
    if document["reboot_requested"] and (
        not document["reboot"]
        or not document["phone_change_attempted"]
        or len(results) < len(steps) - 1
    ):
        raise ValueError("Reboot was not reached")
    _snapshots(document, steps, path)
    return SourceInstallationResult(
        state,
        document["summary"],
        path,
        tuple(results),
        document["phone_change_attempted"],
        document["phone_state_uncertain"],
        document["reboot_requested"],
        document["android_arrival_verified"],
        observed_device=None,
        boot_verified=False,
    )


def _steps(document):
    expected = [("set_active", "", "a", "")]
    expected.extend(("flash", part + "_a", "", "") for part in POPSICLE_PHYSICAL_PARTITIONS)
    expected.extend(
        (
            ("flash", "super", "", "700M"),
            ("flash", "vbmeta_system_a", "", ""),
            ("flash", "vbmeta_a", "", ""),
        )
    )
    if document["wipe"]:
        expected.extend((("erase", "metadata", "", ""), ("erase", "userdata", "", "")))
    expected.append(("set_active", "", "a", ""))
    if document["reboot"]:
        expected.append(("reboot", "", "", ""))
    steps = document["steps"]
    if not isinstance(steps, list) or len(steps) != len(expected):
        raise ValueError("Incomplete source procedure")
    members = set()
    for step, wanted in zip(steps, expected, strict=True):
        if (
            not isinstance(step, dict)
            or set(step) != {"action", "partition", "image_member", "slot", "chunk_size"}
            or tuple(step[key] for key in ("action", "partition", "slot", "chunk_size")) != wanted
        ):
            raise ValueError("Changed source procedure")
        member = step["image_member"]
        if not isinstance(member, str):
            raise ValueError("Invalid image member")
        if step["action"] == "flash":
            normalized = _member(member)
            if normalized in members:
                raise ValueError("Repeated image member")
            members.add(normalized)
        elif member:
            raise ValueError("Image assigned to non-write")
    return steps


def _snapshots(document, steps, path):
    if "snapshots_verified" in document and type(document["snapshots_verified"]) is not bool:
        raise ValueError("Invalid snapshot state")
    snapshots = document.get("image_snapshots")
    if document["phone_change_attempted"] and (
        document.get("snapshots_verified") is not True
        or not isinstance(snapshots, list)
        or len(snapshots) != 50
    ):
        raise ValueError("No verified complete image inventory")
    if snapshots is None:
        return
    if not isinstance(snapshots, list) or len(snapshots) != 50:
        raise ValueError("Incomplete snapshot declaration")
    expected = {step["image_member"] for step in steps if step["action"] == "flash"}
    observed = set()
    for item in snapshots:
        if (
            not isinstance(item, dict)
            or set(item)
            != {"member", "relative_path", "sha256", "size_bytes", "expanded_size_bytes"}
            or not _sha(item["sha256"])
            or any(
                type(item[key]) is not int or not 0 < item[key] <= 1024**4
                for key in ("size_bytes", "expanded_size_bytes")
            )
        ):
            raise ValueError("Invalid snapshot evidence")
        if (
            item["member"] not in expected
            or item["member"] in observed
            or item["relative_path"]
            != f"guardian/source-installation/images/{path.stem}/{item['sha256']}.img"
        ):
            raise ValueError("Snapshot association changed")
        observed.add(item["member"])


def _command(step):
    command = ["fastboot", "-s", "<device>"]
    action = step["action"]
    if action == "flash":
        if step["chunk_size"]:
            command.extend(("-S", step["chunk_size"]))
        command.extend((action, step["partition"], "<reviewed-image>"))
    elif action == "set_active":
        command.extend((action, step["slot"]))
    elif action == "erase":
        command.extend((action, step["partition"]))
    else:
        command.append(action)
    return command


def _boot_history(workspace, install, install_path):
    binding = {
        "relative_path": install_path.relative_to(workspace).as_posix(),
        "record_digest": install["record_digest"],
        "plan_digest": install["plan_digest"],
        "device_key": install["device_key"],
    }
    labels = {
        "stable": "Historical Android boot observed · subsystem checks pending",
        "waiting": "Historical boot check: waiting",
        "settling": "Historical boot check: settling",
        "attention": "Historical boot check: needs attention",
        "cancelled": "Historical boot check: stopped",
    }
    try:
        total = 0
        candidates = []
        for path in _recent(workspace / "guardian" / "local-boot"):
            total += path.stat().st_size
            if total > _MAX_TOTAL_BYTES:
                raise ValueError("Boot history read bound")
            record = read_json_object(path, boundary=workspace, maximum_bytes=512 * 1024)
            if not _sealed(record):
                raise ValueError("Invalid newer boot record")
            if (
                record.get("flash_binding") != binding
                or record.get("device_key") != install["device_key"]
            ):
                continue
            fields = {
                "format",
                "schema_version",
                "session_id",
                "device_key",
                "started_at",
                "updated_at",
                "adb_sha256",
                "flash_binding",
                "status",
                "summary",
                "sample_count",
                "elapsed_seconds",
                "boot_observed",
                "terminal",
                "failure_kind",
                "stable_window_required_seconds",
                "minimum_sample_spacing_seconds",
                "restarts_observed",
                "samples",
                "execution_authority",
                "phone_changed",
                "readback_verified",
                "subsystems_verified",
                "guardian_execution_certified",
                "production_certified",
                "record_digest",
            }
            if (
                set(record) != fields
                or record["format"] != "romverse.local-boot-observation"
                or type(record["schema_version"]) is not int
                or record["schema_version"] != 1
                or record["session_id"] != path.stem
                or not re.fullmatch(r"[a-f0-9]{32}\.json", path.name)
                or record["status"] not in labels
                or not _sha(record["adb_sha256"])
                or record["execution_authority"] != "none"
                or any(
                    record[key] is not False
                    for key in (
                        "phone_changed",
                        "readback_verified",
                        "subsystems_verified",
                        "guardian_execution_certified",
                        "production_certified",
                    )
                )
            ):
                raise ValueError("Invalid boot contract")
            if (
                type(record["sample_count"]) is not int
                or not isinstance(record["samples"], list)
                or record["sample_count"] != len(record["samples"])
                or not 0 <= record["sample_count"] <= 256
                or any(type(record[key]) is not bool for key in ("boot_observed", "terminal"))
                or type(record["restarts_observed"]) is not int
                or record["restarts_observed"] < 0
                or not isinstance(record["summary"], str)
                or len(record["summary"]) > 8192
                or not isinstance(record["failure_kind"], str)
            ):
                raise ValueError("Invalid boot observations")
            if _time(record["updated_at"]) < _time(record["started_at"]) or not all(
                _finite(record[key])
                for key in (
                    "elapsed_seconds",
                    "stable_window_required_seconds",
                    "minimum_sample_spacing_seconds",
                )
            ):
                raise ValueError("Invalid boot timing")
            if record["status"] == "stable" and (
                record["terminal"] is not True
                or record["boot_observed"] is not True
                or record["failure_kind"]
                or record["sample_count"] < 3
                or record["stable_window_required_seconds"] < 60
                or record["minimum_sample_spacing_seconds"] < 0.5
                or record["elapsed_seconds"] < 60
            ):
                raise ValueError("Incomplete recorded stable observation")
            _boot_samples(record)
            candidates.append(
                (
                    _time(record["started_at"]),
                    _time(record["updated_at"]),
                    labels[record["status"]],
                    path,
                )
            )
        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            latest = candidates[0]
            if any(item[:2] == latest[:2] and item[2] != latest[2] for item in candidates[1:]):
                raise ValueError("Ambiguous boot-session chronology")
            return latest[2], latest[3]
    except (OSError, ValueError, TypeError, KeyError, ProjectError):
        return "Historical boot record needs review · no verified status shown", None
    return "No linked boot-check record", None


def _boot_samples(record):
    """Check the recorded sample structure and stable interval, not today's phone."""
    fields = {
        "elapsed_seconds",
        "uptime_seconds",
        "boot_complete",
        "boot_id_sha256",
        "identity_sha256",
        "build_fingerprint_sha256",
        "slot_suffix",
    }
    previous_elapsed = -1.0
    window = []
    spacing = record["minimum_sample_spacing_seconds"]
    for sample in record["samples"]:
        if not isinstance(sample, dict) or not _finite(sample.get("elapsed_seconds")):
            raise ValueError("Invalid recorded boot sample")
        elapsed = sample["elapsed_seconds"]
        if not previous_elapsed <= elapsed <= record["elapsed_seconds"]:
            raise ValueError("Invalid sample chronology")
        previous_elapsed = elapsed
        if set(sample) == {"elapsed_seconds", "failure_kind"}:
            if not isinstance(sample["failure_kind"], str) or not sample["failure_kind"]:
                raise ValueError("Invalid observation failure")
            window = []
            continue
        if (
            set(sample) != fields
            or not _finite(sample["uptime_seconds"])
            or type(sample["boot_complete"]) is not bool
            or any(
                not _sha(sample[key])
                for key in ("boot_id_sha256", "identity_sha256", "build_fingerprint_sha256")
            )
            or sample["slot_suffix"] not in {"", "_a", "_b"}
        ):
            raise ValueError("Invalid boot sample fields")
        if not sample["boot_complete"]:
            window = []
            continue
        if window:
            previous = window[-1]
            delta = elapsed - previous["elapsed_seconds"]
            advance = sample["uptime_seconds"] - previous["uptime_seconds"]
            if (
                any(
                    sample[key] != previous[key]
                    for key in (
                        "boot_id_sha256",
                        "identity_sha256",
                        "build_fingerprint_sha256",
                        "slot_suffix",
                    )
                )
                or not spacing <= delta <= max(15.0, 3 * spacing)
                or advance <= 0
                or abs(delta - advance) > max(2.0, delta * 0.2)
            ):
                window = []
        window.append(sample)
    if record["status"] == "stable":
        if len(window) < 3:
            raise ValueError("No coherent recorded stable interval")
        elapsed = window[-1]["elapsed_seconds"] - window[0]["elapsed_seconds"]
        advance = window[-1]["uptime_seconds"] - window[0]["uptime_seconds"]
        if elapsed < record["stable_window_required_seconds"] or abs(elapsed - advance) > max(
            2.0, elapsed * 0.1
        ):
            raise ValueError("Recorded stable window is incomplete")


def _sealed(document):
    return _sha(document.get("record_digest")) and document["record_digest"] == _digest(
        {key: value for key, value in document.items() if key != "record_digest"}
    )


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _member(value):
    if not value or "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Invalid image path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() == ".":
        raise ValueError("Unsafe image path")
    return path.as_posix()


def _time(value):
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("Timestamp has no timezone")
    return result


def _finite(value):
    return type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 1e15
