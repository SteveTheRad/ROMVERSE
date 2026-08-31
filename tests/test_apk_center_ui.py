from __future__ import annotations

import os
import zipfile
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.device.apk_install import ApkInstallRequest, create_install_plan, inspect_apk
from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.ui.apk_center import ApkCenter


def _ready_plan(tmp_path):
    apk = tmp_path / "ui-review.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex\n035\0")
    return create_install_plan(
        ApkInstallRequest(
            str(apk),
            "PRIVATE-SERIAL",
            battery_percent=90,
            device_free_bytes=1024**3,
        ),
        "private-device-key",
    )


def _device() -> AndroidDevice:
    return AndroidDevice(
        "PRIVATE-SERIAL",
        DeviceState.DEVICE,
        manufacturer="Google",
        model="Test Phone",
        battery_percent=90,
        storage=StorageInfo(available_bytes=1024**3),
    )


def _device_with_evidence(battery: int | None, available: int | None) -> AndroidDevice:
    return AndroidDevice(
        "PRIVATE-SERIAL",
        DeviceState.DEVICE,
        manufacturer="Google",
        model="Test Phone",
        battery_percent=battery,
        storage=StorageInfo(available_bytes=available),
    )


def test_apk_center_requires_a_saved_preflight_before_approval(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    center = ApkCenter(tmp_path, install_service=object())
    center.set_devices([_device()])
    plan = _ready_plan(tmp_path)

    def fail_write(_plan):
        raise OSError("disk unavailable")

    monkeypatch.setattr(center.receipts, "write_preflight", fail_write)
    center._plan_ready(plan)
    app.processEvents()

    assert not center.approve.isEnabled()
    assert not center.install_button.isEnabled()
    assert "receipt could not be saved" in center.result_label.text().casefold()
    center.close()


def test_apk_center_loads_only_verified_receipt_as_verified(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    plan = _ready_plan(tmp_path)
    first = ApkCenter(tmp_path)
    first.receipts.write_preflight(plan)
    first.close()

    center = ApkCenter(tmp_path)
    app.processEvents()
    assert "integrity verified" in center.result_label.text().casefold()
    assert "ui-review.apk" in center.file_label.text()
    center.close()


def test_apk_center_inspects_locally_without_a_connected_phone(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    plan = _ready_plan(tmp_path)
    center = ApkCenter(tmp_path, install_service=object())

    assert center.choose.isEnabled()
    center._inspection_ready(inspect_apk(tmp_path / "ui-review.apk"))
    app.processEvents()

    assert center.current_inspection is not None
    assert center.current_plan is None
    assert not center.approve.isEnabled()
    assert not center.install_button.isEnabled()
    assert "connect and authorize" in center.result_label.text().casefold()
    assert plan.inspection.sha256 in center.hash_label.text()
    center.close()


def test_apk_center_automatically_binds_inspected_apk_then_clears_on_disconnect(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    _ready_plan(tmp_path)
    center = ApkCenter(tmp_path, install_service=object())
    center._inspection_ready(inspect_apk(tmp_path / "ui-review.apk"))
    monkeypatch.setattr("romverse.ui.apk_center.start_background", lambda worker: worker.execute())

    center.set_devices([_device()])
    app.processEvents()

    assert center.current_plan is not None
    assert center.current_plan.request.device_serial == "PRIVATE-SERIAL"
    assert center.approve.isEnabled()
    assert "phone checks passed" in center.result_label.text().casefold()

    center.set_devices([])
    app.processEvents()
    assert center.current_plan is None
    assert center.current_inspection is not None
    assert center.choose.isEnabled()
    assert not center.approve.isEnabled()
    assert "safely cleared" in center.result_label.text().casefold()
    center.close()


def test_apk_center_retries_blocked_plan_when_device_evidence_improves(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    _ready_plan(tmp_path)
    center = ApkCenter(tmp_path, install_service=object())
    center._inspection_ready(inspect_apk(tmp_path / "ui-review.apk"))
    monkeypatch.setattr("romverse.ui.apk_center.start_background", lambda worker: worker.execute())

    center.set_devices([_device_with_evidence(None, None)])
    app.processEvents()
    assert center.current_plan is not None
    assert not center.current_plan.safety_ready

    center.set_devices([_device_with_evidence(90, 1024**3)])
    app.processEvents()
    assert center.current_plan is not None
    assert center.current_plan.safety_ready
    assert center.approve.isEnabled()
    center.close()


def test_apk_center_activates_newly_verified_runtime_without_reselecting_apk(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    plan = _ready_plan(tmp_path)
    center = ApkCenter(tmp_path)
    center.set_devices([_device()])
    center._plan_ready(plan)
    app.processEvents()
    assert not center.approve.isEnabled()

    center.set_install_service(object())  # type: ignore[arg-type]
    app.processEvents()
    assert center.approve.isEnabled()
    assert not center.install_button.isEnabled()
    assert "platform tools are ready" in center.result_label.text().casefold()
    center.close()


def test_apk_center_shows_decoded_identity_and_verified_signer(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = ApkCenter(tmp_path)
    inspection = replace(
        _ready_plan(tmp_path).inspection,
        package_name="com.radforge.demo",
        app_label="ROMVERSE Demo",
        version_name="4.2",
        version_code="42",
        min_sdk="26",
        target_sdk="35",
        native_abis=("arm64-v8a",),
        permission_count=2,
        signature_verified=True,
        signer_sha256="a" * 64,
    )

    center._show_inspection(inspection)
    app.processEvents()

    assert "ROMVERSE Demo" in center.file_label.text()
    assert "com.radforge.demo" in center.hash_label.text()
    assert "version 4.2 (42)" in center.hash_label.text()
    assert "minimum 26" in center.hash_label.text()
    assert "arm64-v8a" in center.hash_label.text()
    assert "Signature: VERIFIED" in center.hash_label.text()
    center.close()


def test_apk_center_uses_real_determinate_inspection_and_honest_install_progress(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    center = ApkCenter(tmp_path)

    center._set_busy("Inspecting", determinate=True)
    center.progress.report(42)
    app.processEvents()
    assert not center.progress.isHidden()
    assert center.progress.minimum() == 0
    assert center.progress.maximum() == 100
    assert center.progress.value() == 42
    assert center.progress.isTextVisible()

    center._set_idle()
    center._set_busy("Installing")
    app.processEvents()
    assert not center.progress.isHidden()
    assert center.progress.minimum() == 0
    assert center.progress.maximum() == 0
    assert not center.progress.isTextVisible()

    center._set_idle()
    assert center.progress.isHidden()
    center.close()
