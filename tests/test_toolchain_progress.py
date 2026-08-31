from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.infrastructure.payload_dumper import PayloadDumperRelease
from romverse.platform.host import LinuxHost
from romverse.ui.toolchain_center import ToolchainDownloadWorker, ToolchainSetupDialog


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
