from __future__ import annotations

import hashlib
import json
import zipfile

from romverse.applications.receipts import ApkReceiptStore
from romverse.device.apk_install import ApkInstallRequest, create_install_plan
from romverse.infrastructure.process import CommandResult


def _plan(tmp_path):
    apk = tmp_path / "reviewed-demo.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"bounded manifest")
        archive.writestr("classes.dex", b"dex\n035\0")
        archive.writestr("META-INF/DEMO.RSA", b"certificate")
    return create_install_plan(
        ApkInstallRequest(
            str(apk),
            "PRIVATE-SERIAL",
            battery_percent=90,
            device_free_bytes=1024**3,
        ),
        "pseudonymous-device-key",
    )


def test_apk_receipts_are_atomic_integrity_bound_and_privacy_safe(tmp_path) -> None:
    store = ApkReceiptStore(tmp_path)
    plan = _plan(tmp_path)

    preflight = store.write_preflight(plan)
    loaded_preflight = store.load_latest_preflight()
    assert loaded_preflight.valid
    assert loaded_preflight.integrity_verified
    assert loaded_preflight.data == preflight.data
    assert loaded_preflight.data["device_command_executed"] is False

    result = CommandResult(
        ("adb", "-s", "PRIVATE-SERIAL", "install", str(plan.inspection.path)),
        0,
        "Performing Streamed Install\nSuccess\nPRIVATE OUTPUT",
        "PRIVATE ERROR",
    )
    install = store.write_install(plan, result, True)
    loaded_install = store.load_latest_install()
    assert loaded_install.valid
    assert loaded_install.integrity_verified
    assert loaded_install.data == install.data
    assert loaded_install.data["device_command_executed"] is True
    assert loaded_install.data["failure_code"] == ""
    assert store.history_count("apk-preflight") == 1
    assert store.history_count("apk-install") == 1
    assert not list(store.root.glob(".*.tmp"))

    encoded = json.dumps({"preflight": preflight.data, "install": install.data})
    for private_value in (
        "PRIVATE-SERIAL",
        str(plan.inspection.path),
        "PRIVATE OUTPUT",
        "PRIVATE ERROR",
        "stdout",
        "stderr",
        "apk_path",
        "device_serial",
    ):
        assert private_value not in encoded


def test_failed_apk_receipt_keeps_only_the_exact_safe_failure_identity(tmp_path) -> None:
    store = ApkReceiptStore(tmp_path)
    plan = _plan(tmp_path)
    private_detail = "private package path and device-specific explanation"
    record = store.write_install(
        plan,
        CommandResult(
            ("adb",),
            1,
            "",
            f"Failure [INSTALL_FAILED_VERSION_DOWNGRADE: {private_detail}]",
        ),
        False,
    )

    loaded = store.load_latest_install()
    assert loaded.valid
    assert loaded.integrity_verified
    assert loaded.data is not None
    assert loaded.data["failure_code"] == "INSTALL_FAILED_VERSION_DOWNGRADE"
    assert len(loaded.data["failure_identity"]) == 64
    assert private_detail not in json.dumps(record.data)

    hostile = dict(loaded.data)
    hostile["failure_code"] = "INSTALL_FAILED_INVALID_APK"
    hostile.pop("receipt_digest")
    hostile["receipt_digest"] = hashlib.sha256(
        json.dumps(
            hostile,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    store.latest_install_path.write_text(json.dumps(hostile), encoding="utf-8")
    rejected = store.load_latest_install()
    assert not rejected.valid
    assert "failure identity binding" in rejected.reason.casefold()


def test_apk_receipt_tampering_and_wrong_location_are_rejected(tmp_path) -> None:
    store = ApkReceiptStore(tmp_path)
    plan = _plan(tmp_path)
    store.write_preflight(plan)

    data = json.loads(store.latest_preflight_path.read_text(encoding="utf-8"))
    data["execution_locked"] = not data["execution_locked"]
    store.latest_preflight_path.write_text(json.dumps(data), encoding="utf-8")
    rejected = store.load_latest_preflight()
    assert not rejected.valid
    assert "integrity mismatch" in rejected.reason.casefold()

    install = store.write_install(plan, CommandResult(("adb",), 1, "", "failed"), False)
    store.latest_preflight_path.write_text(
        install.latest_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    wrong_kind = store.load_latest_preflight()
    assert not wrong_kind.valid
    assert "kind" in wrong_kind.reason.casefold()


def test_legacy_apk_receipts_are_reviewable_but_never_claim_integrity(tmp_path) -> None:
    store = ApkReceiptStore(tmp_path)
    store.root.mkdir(parents=True)
    store.latest_preflight_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "apk_name": "legacy.apk",
                "status": "review",
                "risk": "medium",
            }
        ),
        encoding="utf-8",
    )
    loaded = store.load_latest_preflight()
    assert loaded.valid
    assert not loaded.integrity_verified
    assert "legacy" in loaded.reason.casefold()

    legacy = json.loads(store.latest_preflight_path.read_text(encoding="utf-8"))
    legacy["device_serial"] = "PRIVATE-SERIAL"
    store.latest_preflight_path.write_text(json.dumps(legacy), encoding="utf-8")
    assert not store.load_latest_preflight().valid
