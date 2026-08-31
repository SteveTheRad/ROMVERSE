import stat
import zipfile
from pathlib import Path

import pytest

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.apk_install import (
    ApkInstallRequest,
    ApkInstallService,
    build_install_arguments,
    create_install_plan,
    inspect_apk,
    install_preflight,
    install_succeeded,
    validate_install_request,
)
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import GuardianDeniedError
from romverse.guardian.policy import GuardianPolicy
from romverse.infrastructure.process import CommandResult
from romverse.rom.models import ProjectError


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10):
        self.calls.append(tuple(args))
        return CommandResult(tuple(args), 0, "Performing Streamed Install\nSuccess\n", "")


class ApkMetadataRunner:
    def __init__(self, *, signature_ok: bool = True) -> None:
        self.signature_ok = signature_ok
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10, cwd=None):
        call = tuple(str(part) for part in args)
        self.calls.append(call)
        if "badging" in call:
            return CommandResult(
                call,
                0,
                "\n".join(
                    (
                        "package: name='com.radforge.demo' versionCode='42' versionName='4.2'",
                        "sdkVersion:'26'",
                        "targetSdkVersion:'35'",
                        "uses-permission: name='android.permission.INTERNET'",
                        "uses-permission: name='android.permission.CAMERA'",
                        "application-label:'ROMVERSE Demo'",
                        "native-code: 'arm64-v8a' 'x86_64'",
                    )
                ),
                "",
            )
        output = "\n".join(
            (
                "Verifies" if self.signature_ok else "DOES NOT VERIFY",
                "Signer #1 certificate DN: C=AU, O=RadForge, CN=ROMVERSE Demo",
                "Signer #1 certificate SHA-256 digest: " + "a" * 64,
            )
        )
        return CommandResult(call, 0 if self.signature_ok else 1, output, "")


def valid_apk(tmp_path: Path) -> Path:
    path = tmp_path / "demo.apk"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"binary-manifest-placeholder")
        archive.writestr("classes.dex", b"dex\n035\0")
        archive.writestr("META-INF/DEMO.RSA", b"certificate-placeholder")
    return path


def test_apk_install_request_is_locked_and_validates_file(tmp_path):
    apk = tmp_path / "demo.apk"
    apk.write_bytes(b"apk")
    request = ApkInstallRequest(str(apk), "device")
    validate_install_request(request)
    assert request.execution_locked


def test_apk_install_rejects_downgrade(tmp_path):
    apk = tmp_path / "demo.apk"
    apk.write_bytes(b"apk")
    with pytest.raises(ProjectError, match="downgrades"):
        validate_install_request(ApkInstallRequest(str(apk), "device", True))


def test_apk_install_preflight_requires_review(tmp_path):
    apk = tmp_path / "demo.apk"
    apk.write_bytes(b"apk")
    assessment = install_preflight(ApkInstallRequest(str(apk), "device"))
    assert assessment.approval_required
    assert assessment.execution_locked


def test_apk_install_arguments_are_explicit_and_bounded(tmp_path):
    apk = tmp_path / "demo.apk"
    apk.write_bytes(b"apk")
    request = ApkInstallRequest(str(apk), "serial-123")
    assert build_install_arguments(request) == ("-s", "serial-123", "install", str(apk))


def test_apk_inspection_records_bounded_container_identity(tmp_path):
    apk = valid_apk(tmp_path)
    with zipfile.ZipFile(apk, "a") as archive:
        archive.writestr("assets/progress-fixture.bin", b"x" * 3 * 1024 * 1024)
    progress: list[int] = []
    inspection = inspect_apk(apk, progress=progress.append)
    assert inspection.valid
    assert inspection.has_manifest
    assert inspection.has_legacy_signature
    assert inspection.dex_count == 1
    assert len(inspection.sha256) == 64
    assert progress[0] == 0
    assert progress[-1] == 100
    assert progress == sorted(set(progress))
    assert any(0 < value < 70 for value in progress)
    assert any(70 < value < 100 for value in progress)


def test_apk_inspection_decodes_identity_and_verifies_signer_with_verified_tools(tmp_path):
    apk = valid_apk(tmp_path)
    aapt = tmp_path / "aapt2"
    signer = tmp_path / "apksigner"
    aapt.write_text("tool", encoding="utf-8")
    signer.write_text("tool", encoding="utf-8")
    runner = ApkMetadataRunner()

    inspection = inspect_apk(
        apk,
        aapt_executable=aapt,
        apksigner_executable=signer,
        runner=runner,
    )

    assert inspection.valid
    assert inspection.package_name == "com.radforge.demo"
    assert inspection.app_label == "ROMVERSE Demo"
    assert inspection.version_name == "4.2"
    assert inspection.version_code == "42"
    assert inspection.min_sdk == "26"
    assert inspection.target_sdk == "35"
    assert inspection.native_abis == ("arm64-v8a", "x86_64")
    assert inspection.permission_count == 2
    assert inspection.signature_verified is True
    assert inspection.signer_sha256 == "a" * 64
    assert len(runner.calls) == 2


def test_apk_inspection_blocks_signature_rejected_by_verified_signer(tmp_path):
    apk = valid_apk(tmp_path)
    signer = tmp_path / "apksigner"
    signer.write_text("tool", encoding="utf-8")

    inspection = inspect_apk(
        apk,
        apksigner_executable=signer,
        runner=ApkMetadataRunner(signature_ok=False),
    )

    assert not inspection.valid
    assert inspection.signature_verified is False
    assert "Guardian will not install" in " ".join(inspection.findings)


def test_apk_inspection_rejects_duplicate_and_symbolic_link_entries(tmp_path):
    duplicate = tmp_path / "duplicate.apk"
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(duplicate, "w") as archive,
    ):
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"first")
        archive.writestr("classes.dex", b"second")
    duplicate_result = inspect_apk(duplicate)
    assert not duplicate_result.valid
    assert "duplicate entry names" in " ".join(duplicate_result.findings)

    linked = tmp_path / "linked.apk"
    link = zipfile.ZipInfo("assets/redirect")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(linked, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex")
        archive.writestr(link, b"../../outside")
    linked_result = inspect_apk(linked)
    assert not linked_result.valid
    assert "symbolic-link entry" in " ".join(linked_result.findings)


def test_apk_plan_requires_safety_evidence_and_unlocks_supported_execution(tmp_path):
    apk = valid_apk(tmp_path)
    ready = create_install_plan(
        ApkInstallRequest(
            str(apk),
            "serial-123",
            battery_percent=80,
            device_free_bytes=1024**3,
        ),
        "private-device-key",
    )
    assert ready.safety_ready
    assert not ready.assessment.execution_locked
    assert ready.assessment.approval_required

    low_battery = create_install_plan(
        ApkInstallRequest(
            str(apk),
            "serial-123",
            battery_percent=10,
            device_free_bytes=1024**3,
        ),
        "private-device-key",
    )
    assert not low_battery.safety_ready
    assert low_battery.assessment.execution_locked


def test_guardian_executes_only_exact_approved_unchanged_apk_plan(tmp_path):
    apk = valid_apk(tmp_path)
    serial = "PRIVATE-SERIAL"
    target_key = WorkspacePrivacy(tmp_path).pseudonym(serial)
    plan = create_install_plan(
        ApkInstallRequest(str(apk), serial, battery_percent=90, device_free_bytes=1024**3),
        target_key,
    )
    approvals = ApprovalStore(tmp_path)
    runner = RecordingRunner()
    service = ApkInstallService(
        Path("/usr/bin/adb"),
        ExecutionGateway(GuardianPolicy(tmp_path), runner),
        approvals,
    )

    with pytest.raises(GuardianDeniedError, match="not been approved"):
        service.install(plan)
    assert runner.calls == []

    approvals.issue(plan.digest, target_key)
    result = service.install(plan)
    assert install_succeeded(result)
    assert runner.calls == [("/usr/bin/adb", "-s", serial, "install", str(apk.resolve()))]


def test_guardian_blocks_apk_changed_after_approval(tmp_path):
    apk = valid_apk(tmp_path)
    serial = "PRIVATE-SERIAL"
    target_key = WorkspacePrivacy(tmp_path).pseudonym(serial)
    plan = create_install_plan(
        ApkInstallRequest(str(apk), serial, battery_percent=90, device_free_bytes=1024**3),
        target_key,
    )
    approvals = ApprovalStore(tmp_path)
    approvals.issue(plan.digest, target_key)
    runner = RecordingRunner()
    service = ApkInstallService(
        Path("/usr/bin/adb"),
        ExecutionGateway(GuardianPolicy(tmp_path), runner),
        approvals,
    )
    with zipfile.ZipFile(apk, "a") as archive:
        archive.writestr("assets/changed.txt", b"changed after approval")

    with pytest.raises(GuardianDeniedError, match="changed after approval"):
        service.install(plan)
    assert runner.calls == []
