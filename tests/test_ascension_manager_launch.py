from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from romverse.ascension.handoff import RootPatchHandoffReceipt
from romverse.ascension.manager_launch import (
    RootManagerLaunchService,
    load_root_manager_launch,
)
from romverse.ascension.models import AscensionMethod, OfficialRootAsset, OfficialRootRelease
from romverse.core.privacy import WorkspacePrivacy
from romverse.device.apk_install import ApkInspection
from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.ascension_manager import manager_launch_arguments, manager_path_arguments
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import GuardianDeniedError, OperationClass, OperationRequest
from romverse.guardian.policy import GuardianPolicy
from romverse.infrastructure.process import CommandResult
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


class _ReleaseService:
    OFFICIAL_PACKAGES = {
        AscensionMethod.MAGISK: "com.topjohnwu.magisk",
        AscensionMethod.KERNELSU_LKM: "me.weishu.kernelsu",
    }
    OFFICIAL_SIGNERS = {
        AscensionMethod.MAGISK: "1" * 64,
        AscensionMethod.KERNELSU_LKM: "2" * 64,
    }

    def __init__(self, expected: bytes) -> None:
        self.expected = expected

    def verify_artifact(self, release: OfficialRootRelease, path: Path) -> ApkInspection:
        value = path.read_bytes()
        digest = hashlib.sha256(value).hexdigest()
        if value != self.expected or digest != release.asset.sha256:
            raise ProjectError("Official root manager failed exact size or SHA-256 verification")
        return ApkInspection(
            str(path),
            len(value),
            digest,
            3,
            1,
            True,
            True,
            True,
            ("Verified test package",),
            package_name=self.OFFICIAL_PACKAGES[release.provider],
            signature_verified=True,
            signer_sha256=self.OFFICIAL_SIGNERS[release.provider],
        )


class _Runner:
    remote = "/data/app/~~verified/com.topjohnwu.magisk-release/base.apk"

    def __init__(self, manager_bytes: bytes) -> None:
        self.manager_bytes = manager_bytes
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10, cwd=None):
        call = tuple(map(str, args))
        self.calls.append(call)
        if call[3:6] == ("shell", "pm", "path"):
            return CommandResult(call, 0, f"package:{self.remote}\n", "")
        if "pull" in call:
            Path(call[-1]).write_bytes(self.manager_bytes)
            return CommandResult(call, 0, "1 file pulled\n", "")
        if "monkey" in call:
            return CommandResult(call, 0, "Events injected: 1\n", "")
        return CommandResult(call, 1, "", "unexpected command")


def _service(tmp_path: Path, manager_bytes: bytes, monkeypatch):
    workspace = tmp_path / "workspace"
    store = RomProjectStore(workspace)
    project_id = "project-1"
    (store.projects_root / project_id).mkdir(parents=True)
    approvals = ApprovalStore(workspace)
    runner = _Runner(manager_bytes)
    gateway = ExecutionGateway(GuardianPolicy(workspace), runner)
    releases = _ReleaseService(manager_bytes)
    service = RootManagerLaunchService(
        store,
        Path("/usr/bin/adb"),
        gateway,
        approvals,
        release_service=releases,  # type: ignore[arg-type]
    )
    manager_digest = hashlib.sha256(manager_bytes).hexdigest()
    asset = OfficialRootAsset(
        AscensionMethod.MAGISK,
        "topjohnwu/Magisk",
        "v-test",
        "2026-08-30T00:00:00+00:00",
        "Magisk-v-test.apk",
        len(manager_bytes),
        manager_digest,
        "https://github.com/topjohnwu/Magisk/releases/download/v-test/Magisk-v-test.apk",
    )
    release = OfficialRootRelease(
        AscensionMethod.MAGISK,
        asset.repository,
        asset.tag,
        asset.published_at,
        asset,
        "https://github.com/topjohnwu/Magisk/releases/tag/v-test",
    )
    device = AndroidDevice(
        "PRIVATE-SERIAL",
        DeviceState.DEVICE,
        codename="popsicle",
    )
    device_key = WorkspacePrivacy(workspace).pseudonym(device.serial)
    handoff = RootPatchHandoffReceipt(
        1,
        "receipt-1",
        project_id,
        AscensionMethod.MAGISK,
        "2026-08-30T00:00:00+00:00",
        "capsule-digest",
        device_key,
        device.codename,
        manager_digest,
        "3" * 64,
        "/sdcard/Download/ROMVERSE-33333333-init_boot.img",
        True,
        True,
        False,
        False,
        True,
        "4" * 64,
    )
    monkeypatch.setattr(service, "_context", lambda *_args: (handoff, release))
    return service, approvals, runner, device, handoff


def test_installed_official_manager_is_verified_removed_and_opened(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager_bytes = b"official-root-manager"
    service, approvals, runner, device, _handoff = _service(
        tmp_path,
        manager_bytes,
        monkeypatch,
    )
    path_plan = service.plan_path("project-1", AscensionMethod.MAGISK, device)
    with pytest.raises(GuardianDeniedError, match="explicitly approved"):
        service.resolve_path(path_plan)
    assert runner.calls == []

    approvals.issue(path_plan.approval_digest, path_plan.device_key)
    launch_plan = service.resolve_path(path_plan)
    assert launch_plan.installed_apk_path == runner.remote
    with pytest.raises(GuardianDeniedError, match="not explicitly approved"):
        service.execute(launch_plan)
    assert len(runner.calls) == 1

    approvals.issue(launch_plan.approval_digest, launch_plan.device_key)
    progress: list[int] = []
    receipt = service.execute(launch_plan, progress.append)

    assert progress == []
    assert receipt.installed_package_verified
    assert receipt.manager_opened
    assert receipt.execution_authority == "none"
    assert not receipt.root_applied
    assert not receipt.image_flashed
    assert receipt.phone_changed
    assert not Path(launch_plan.local_verification_path).exists()
    assert service.load("project-1", AscensionMethod.MAGISK) == receipt
    handoff, release = service._context("project-1", AscensionMethod.MAGISK)
    monkeypatch.setattr(
        "romverse.ascension.manager_launch.load_root_patch_handoff",
        lambda *_args: handoff,
    )
    monkeypatch.setattr(
        service.release_service,
        "load_verified",
        lambda _method: (release, Path("/verified-manager.apk")),
        raising=False,
    )
    assert (
        load_root_manager_launch(
            service.store,
            service.release_service,  # type: ignore[arg-type]
            "project-1",
            AscensionMethod.MAGISK,
        )
        == receipt
    )
    assert tuple(call[3] for call in runner.calls) == ("shell", "shell", "pull", "shell")
    assert runner.calls[-1][3:] == (
        "shell",
        "monkey",
        "-p",
        "com.topjohnwu.magisk",
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
    )
    receipt_path = (
        service.store.projects_root
        / "project-1"
        / "ascension"
        / "manager-launch"
        / service.RECEIPT_NAME
    )
    document = receipt_path.read_text(encoding="utf-8")
    assert "PRIVATE-SERIAL" not in document
    assert runner.remote not in document
    assert json.loads(document)["execution_authority"] == "none"
    history = receipt_path.parent / f"manager-launch-{receipt.receipt_id[:12]}.romverse"
    assert stat.S_IMODE(receipt_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(history.stat().st_mode) == 0o600

    original = receipt_path.read_bytes()
    hostile = json.loads(original)
    hostile["unexpected_field"] = "must fail closed"
    receipt_path.write_text(json.dumps(hostile), encoding="utf-8")
    assert service.load("project-1", AscensionMethod.MAGISK) is None

    hostile = json.loads(original)
    hostile["manager_opened"] = 1
    unsigned = {
        key: value for key, value in hostile.items() if key not in {"format", "receipt_digest"}
    }
    hostile["receipt_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    receipt_path.write_text(json.dumps(hostile), encoding="utf-8")
    assert service.load("project-1", AscensionMethod.MAGISK) is None

    receipt_path.write_bytes(original)
    with receipt_path.open("r+b") as stream:
        stream.truncate(service.MAX_RECEIPT_BYTES + 1)
    assert service.load("project-1", AscensionMethod.MAGISK) is None

    receipt_path.write_bytes(original)
    outside = tmp_path / "outside-manager-launch.romverse"
    outside.write_bytes(original)
    receipt_path.unlink()
    receipt_path.symlink_to(outside)
    assert service.load("project-1", AscensionMethod.MAGISK) is None
    receipt_path.unlink()
    receipt_path.write_bytes(original)
    assert service.load("project-1", AscensionMethod.MAGISK) == receipt


def test_changed_installed_manager_is_blocked_before_launch_and_cleaned(
    tmp_path: Path,
    monkeypatch,
) -> None:
    official = b"official-root-manager"
    service, approvals, runner, device, _handoff = _service(tmp_path, official, monkeypatch)
    path_plan = service.plan_path("project-1", AscensionMethod.MAGISK, device)
    approvals.issue(path_plan.approval_digest, path_plan.device_key)
    launch_plan = service.resolve_path(path_plan)
    approvals.issue(launch_plan.approval_digest, launch_plan.device_key)
    runner.manager_bytes = b"replaced-manager"

    with pytest.raises(ProjectError, match="exact size or SHA-256"):
        service.execute(launch_plan)

    assert not any("monkey" in call for call in runner.calls)
    assert not Path(launch_plan.local_verification_path).exists()
    with pytest.raises(GuardianDeniedError, match="plan changed"):
        service.execute(replace(launch_plan, package_name="com.example.rogue"))


def test_guardian_allows_only_exact_manager_lookup_pull_and_open(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    inspection = (
        workspace
        / "projects"
        / "project-1"
        / "ascension"
        / "manager-launch"
        / ".manager-inspection-test"
    )
    inspection.mkdir(parents=True)
    serial = "PRIVATE-SERIAL"
    target = WorkspacePrivacy(workspace).pseudonym(serial)
    approval = "approved-manager-open"
    ApprovalStore(workspace).issue(approval, target)
    policy = GuardianPolicy(workspace)

    def decision(operation_id: str, category: OperationClass, arguments: tuple[str, ...]):
        return policy.assess(
            OperationRequest(
                operation_id,
                category,
                "/usr/bin/adb",
                arguments,
                "test",
                serial,
                approval,
                target,
            )
        )

    assert decision(
        "ascension.manager_path",
        OperationClass.READ_ONLY,
        manager_path_arguments(serial, "com.topjohnwu.magisk"),
    ).allowed
    assert decision(
        "ascension.pull_manager",
        OperationClass.READ_ONLY,
        (
            "-s",
            serial,
            "pull",
            _Runner.remote,
            str(inspection / "installed-manager.apk"),
        ),
    ).allowed
    assert decision(
        "ascension.launch_manager",
        OperationClass.STATE_CHANGING,
        manager_launch_arguments(serial, "com.topjohnwu.magisk"),
    ).allowed
    assert not decision(
        "ascension.launch_manager",
        OperationClass.STATE_CHANGING,
        (
            "-s",
            serial,
            "shell",
            "monkey",
            "-p",
            "com.example.rogue",
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ),
    ).allowed
    assert not decision(
        "ascension.pull_manager",
        OperationClass.READ_ONLY,
        (
            "-s",
            serial,
            "pull",
            "/sdcard/private.txt",
            str(inspection / "installed-manager.apk"),
        ),
    ).allowed
