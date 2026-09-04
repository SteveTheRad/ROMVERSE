from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from romverse.device.models import AndroidDevice, DeviceState
from romverse.infrastructure.payload_dumper import PayloadDumperRelease
from romverse.infrastructure.provisioning import ProvisionStrategy, ToolProvisionItem
from romverse.infrastructure.tools import ToolStatus
from romverse.platform.host import LinuxHost
from romverse.ui.toolchain_center import (
    ToolchainCenter,
    ToolchainDownloadWorker,
    ToolchainSetupDialog,
)


class _NoCommandRunner:
    def run(self, *_args, **_kwargs):
        raise AssertionError("The Forge Arsenal evidence surface must not run a phone command")


def test_forge_arsenal_worker_uses_measured_progress_and_honest_verification_phase(
    tmp_path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    release = PayloadDumperRelease(
        "2.0.2",
        "payload-dumper-go_2.0.2_linux_amd64.tar.gz",
        "https://github.com/ssut/payload-dumper-go/releases/download/2.0.2/payload-dumper-go_2.0.2_linux_amd64.tar.gz",
        "a" * 64,
    )
    monkeypatch.setattr(
        "romverse.ui.toolchain_center.resolve_latest_payload_dumper",
        lambda _host: release,
    )

    def install(_release, destination, *, boundary, progress):
        assert boundary == tmp_path
        progress(0, 1_000)
        progress(250, 1_000)
        progress(250, 1_000)
        progress(1_000, 1_000)
        progress(0, 0)
        return destination / "payload-dumper-go", "b" * 64

    monkeypatch.setattr("romverse.ui.toolchain_center.install_payload_dumper_release", install)
    worker = ToolchainDownloadWorker(
        LinuxHost(),
        ["Payload Dumper"],
        tmp_path / "tools" / "downloads",
        boundary=tmp_path,
    )
    phases = []
    progress = []
    completed = []
    worker.signals.phase.connect(lambda label, determinate: phases.append((label, determinate)))
    worker.signals.progress.connect(progress.append)
    worker.signals.complete.connect(completed.append)

    worker.run()

    assert progress == [0, 25, 100]
    assert any("Resolving" in label and not determinate for label, determinate in phases)
    download_phases = [item for item in phases if "Downloading" in item[0]]
    assert download_phases[-2:] == [
        ("Downloading and verifying Payload Dumper 2.0.2…", True),
        ("Downloading and verifying Payload Dumper 2.0.2…", False),
    ]
    assert completed and "Payload Dumper 2.0.2" in completed[0]


def test_forge_arsenal_renders_guardian_routed_device_communication_without_commands(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "romverse.ui.toolchain_center.ToolVerifier.verify_extended",
        lambda _verifier: (
            ToolStatus("ADB", True, "/bin/true", "fixture", "Ready"),
            ToolStatus("Fastboot", True, "/bin/true", "fixture", "Ready"),
        ),
    )
    center = ToolchainCenter(
        LinuxHost(distribution_id="fedora"),
        _NoCommandRunner(),
        workspace=tmp_path,
    )
    center.show()
    app.processEvents()
    try:
        recovery = AndroidDevice(
            "private-serial",
            DeviceState.RECOVERY,
            manufacturer="Samsung",
            model="SM-S928B",
        )
        center.set_device_communication_evidence([recovery])
        visible = " ".join(label.text() for label in center.findChildren(QLabel))
        assert "ADB recovery communication verified" in visible
        assert "private-serial" not in visible
        assert "Phone-change authority: none" in visible

        fastbootd = AndroidDevice("private-serial", DeviceState.FASTBOOTD, model="Phone")
        center.set_device_communication_evidence([fastbootd])
        visible = " ".join(label.text() for label in center.findChildren(QLabel))
        assert "fastbootd communication verified" in visible
        assert "No reboot, unlock, erase, flash, or write command was available" in visible
    finally:
        center.close()


def test_forge_arsenal_requires_explicit_target_when_multiple_transports_are_visible(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "romverse.ui.toolchain_center.ToolVerifier.verify_extended",
        lambda _verifier: (ToolStatus("ADB", False, detail="Not ready"),),
    )
    center = ToolchainCenter(
        LinuxHost(distribution_id="fedora"),
        _NoCommandRunner(),
        workspace=tmp_path,
    )
    center.show()
    app.processEvents()
    try:
        observed = [
            AndroidDevice("first-secret", DeviceState.DEVICE, model="First Phone"),
            AndroidDevice("second-secret", DeviceState.FASTBOOT, model="Second Phone"),
        ]
        center.set_device_communication_evidence([], observed_devices=observed)
        visible = " ".join(label.text() for label in center.findChildren(QLabel))
        assert "Choose the target in Command Deck" in visible
        assert "2 Android transports are visible" in visible
        assert "first-secret" not in visible
        assert "second-secret" not in visible
        manifest_buttons = [
            button
            for button in center.findChildren(QPushButton)
            if button.text() == "Export reproducible manifest"
        ]
        assert len(manifest_buttons) == 1
        assert manifest_buttons[0].isEnabled()
    finally:
        center.close()


def test_forge_arsenal_progress_widget_switches_modes_without_inventing_progress(
    tmp_path,
) -> None:
    QApplication.instance() or QApplication([])
    dialog = ToolchainSetupDialog(
        LinuxHost(),
        (),
        tmp_path,
        required_names=("ADB",),
    )

    dialog._download_phase("Contacting official source…", False)
    assert dialog.progress.minimum() == 0
    assert dialog.progress.maximum() == 0
    assert not dialog.progress.isTextVisible()

    dialog._download_phase("Downloading official bytes…", True)
    assert dialog.progress.maximum() == 100
    assert dialog.progress.value() == 0
    dialog.progress.report(42)
    assert dialog.progress.value() == 42

    dialog._download_phase("Verifying downloaded package…", False)
    assert dialog.progress.maximum() == 0
    assert not dialog.progress.isTextVisible()
    dialog.close()


def test_empty_automatic_forge_setup_completes_without_stranding_user(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    dialog = ToolchainSetupDialog(
        LinuxHost(),
        (ToolStatus("ADB", True, "/bin/true", "fixture", "Ready"),),
        tmp_path,
        required_names=("ADB",),
        auto_start=True,
        auto_close=True,
    )

    result = dialog.exec()

    assert result == dialog.DialogCode.Accepted
    assert dialog.last_success is True
    assert "already verified" in dialog.last_message


def test_forge_arsenal_shows_managed_apk_tool_capability_boundaries(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    dialog = ToolchainSetupDialog(
        LinuxHost(distribution_id="fedora"),
        (
            ToolStatus("AAPT2", False, detail="Not ready"),
            ToolStatus("APK Signer", False, detail="Not ready"),
        ),
        tmp_path,
        required_names=("AAPT2", "APK Signer"),
    )
    dialog.show()
    app.processEvents()
    try:
        visible_copy = " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert dialog.checks["AAPT2"].isChecked()
        assert dialog.checks["APK Signer"].isChecked()
        assert "PINNED" in visible_copy.upper()
        assert "verification-only" in visible_copy
        assert "full SDK Build Tools" in visible_copy
        assert visible_copy.count("ROMVERSE MANAGED DOWNLOAD") == 2
    finally:
        dialog.close()


def test_forge_worker_connects_both_managed_apk_artifacts(tmp_path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    calls = []

    def install_aapt(destination, *, boundary, progress):
        calls.append(("aapt2", destination, boundary))
        progress(1, 1)
        progress(0, 0)
        return destination / "android-aapt2" / "aapt2", "a" * 64

    def install_signer(destination, *, boundary, progress):
        calls.append(("apksig", destination, boundary))
        progress(1, 1)
        progress(0, 0)
        return destination / "android-apk-verifier" / "apksigner", "b" * 64

    monkeypatch.setattr("romverse.ui.toolchain_center.install_pinned_aapt2", install_aapt)
    monkeypatch.setattr("romverse.ui.toolchain_center.install_pinned_apk_verifier", install_signer)
    worker = ToolchainDownloadWorker(
        LinuxHost(distribution_id="fedora"),
        ["AAPT2", "APK Signer"],
        tmp_path / "tools" / "downloads",
        boundary=tmp_path,
    )
    completed = []
    worker.signals.complete.connect(completed.append)

    worker.run()

    assert [call[0] for call in calls] == ["aapt2", "apksig"]
    assert completed
    assert "AAPT2" in completed[0]
    assert "verification-only" in completed[0]


def test_forge_arsenal_worker_routes_fedora_system_plan_through_authorized_installer(
    tmp_path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    host = LinuxHost(distribution_id="fedora")
    plan_item = ToolProvisionItem(
        "LZ4",
        ProvisionStrategy.SYSTEM,
        "official",
        ("lz4",),
    )
    calls = []

    def install(items, selected_host, runner):
        calls.append((items, selected_host, runner))
        return True, "Fedora installed: lz4"

    monkeypatch.setattr("romverse.ui.toolchain_center.install_system_packages", install)
    worker = ToolchainDownloadWorker(
        host,
        ["LZ4"],
        tmp_path / "tools" / "downloads",
        plan_items=(plan_item,),
        boundary=tmp_path,
    )
    phases = []
    completed = []
    worker.signals.phase.connect(lambda label, determinate: phases.append((label, determinate)))
    worker.signals.complete.connect(completed.append)

    worker.run()

    assert len(calls) == 1
    assert calls[0][0] == (plan_item,)
    assert calls[0][1] is host
    assert any("operating system" in label for label, _determinate in phases)
    assert completed == ["Downloaded and prepared: Fedora installed: lz4"]


def test_forge_arsenal_unknown_length_download_stays_indeterminate(tmp_path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])

    def install(name, _url, destination, required_files, *, boundary, progress):
        assert name == "platform-tools"
        assert required_files == ("adb", "fastboot")
        assert boundary == tmp_path
        progress(0, 0)
        progress(512, 0)
        progress(1_024, 0)
        progress(0, 0)
        return destination / name, "c" * 64

    monkeypatch.setattr("romverse.ui.toolchain_center.install_official_archive", install)
    worker = ToolchainDownloadWorker(
        LinuxHost(),
        ["ADB", "Fastboot"],
        tmp_path / "tools" / "downloads",
        boundary=tmp_path,
    )
    phases = []
    progress = []
    worker.signals.phase.connect(lambda label, determinate: phases.append((label, determinate)))
    worker.signals.progress.connect(progress.append)

    worker.run()

    assert not progress
    download_phases = [item for item in phases if "platform-tools" in item[0]]
    assert download_phases
    assert all(not determinate for _label, determinate in download_phases)
