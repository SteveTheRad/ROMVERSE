from __future__ import annotations

import re
from pathlib import Path

from romverse.core.privacy import WorkspacePrivacy
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.ascension_manager import (
    ASCENSION_MANAGER_LAUNCH_CATEGORY,
    ASCENSION_MANAGER_PACKAGES,
    installed_manager_path,
)
from romverse.guardian.ascension_transfer import (
    ASCENSION_OUTPUT_LIST_COMMAND,
    ASCENSION_OUTPUT_NAME,
    ascension_output_list_digest,
    ascension_output_pull_digest,
)
from romverse.guardian.backup_transfer import MEDIA_BACKUP_REMOTE_PATHS, media_pull_digest
from romverse.guardian.invariants import contains_bootloader_relock
from romverse.guardian.models import (
    GuardianDecision,
    OperationClass,
    OperationRequest,
    RiskLevel,
)


class MilestoneOnePolicy:
    """Deny-by-default policy for the read-only v0.1 milestone."""

    _HOST_COMMANDS = {("version",), ("devices", "-l")}
    _DEVICE_COMMANDS = {
        ("get-state",),
        ("shell", "getprop"),
        ("shell", "getprop", "ro.product.model"),
        ("shell", "getprop", "ro.build.version.release"),
        ("shell", "getprop", "ro.boot.verifiedbootstate"),
        ("shell", "dumpsys", "battery"),
        ("shell", "df", "-k", "/data"),
        ("shell", "cat", "/proc/meminfo"),
        ("shell", "cat", "/proc/uptime"),
        ("shell", "uname", "-r"),
        ("shell", "id"),
        ("shell", "pm", "path", "com.radforge.romverse.companion"),
        ("shell", "pm", "path", "com.topjohnwu.magisk"),
        ("shell", "pm", "path", "me.weishu.kernelsu"),
    }

    def assess(self, request: OperationRequest) -> GuardianDecision:
        command = ((Path(request.executable).name, *request.arguments),)
        if contains_bootloader_relock(command):
            return GuardianDecision(
                False,
                RiskLevel.CRITICAL,
                ("ROMVERSE permanently prohibits bootloader relocking",),
                user_approval_required=False,
            )
        if Path(request.executable).name.casefold() not in {"adb", "adb.exe"}:
            return GuardianDecision(
                False,
                RiskLevel.HIGH,
                ("Guardian only permits the verified ADB executable for device operations",),
            )
        if request.category is not OperationClass.READ_ONLY:
            return GuardianDecision(
                False,
                RiskLevel.CRITICAL
                if request.category is OperationClass.DESTRUCTIVE
                else RiskLevel.HIGH,
                ("v0.1 permits read-only device inspection only",),
            )

        args = request.arguments
        normalized = args
        if len(args) >= 2 and args[0] == "-s":
            normalized = args[2:]
            allowed = normalized in self._DEVICE_COMMANDS
        else:
            allowed = normalized in self._HOST_COMMANDS

        if not allowed:
            return GuardianDecision(
                False,
                RiskLevel.HIGH,
                ("command is not on Guardian's v0.1 read-only allowlist",),
            )
        return GuardianDecision(True, RiskLevel.NONE, ("known read-only probe",))


class GuardianPolicy(MilestoneOnePolicy):
    """Deny-by-default policy with one narrowly approved reversible mutation."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.approvals = ApprovalStore(workspace)
        self.privacy = WorkspacePrivacy(workspace)

    def assess(self, request: OperationRequest) -> GuardianDecision:
        if request.category is OperationClass.READ_ONLY:
            if request.operation_id == "backup.pull_media":
                return self._assess_media_backup(request)
            if request.operation_id == "ascension.list_outputs":
                return self._assess_ascension_output_list(request)
            if request.operation_id == "ascension.pull_output":
                return self._assess_ascension_output_pull(request)
            if request.operation_id == "ascension.manager_path":
                return self._assess_ascension_manager_path(request)
            if request.operation_id == "ascension.pull_manager":
                return self._assess_ascension_manager_pull(request)
            return super().assess(request)
        if request.category is not OperationClass.STATE_CHANGING:
            return super().assess(request)
        if request.operation_id in {"repair.adb_kill_server", "repair.adb_start_server"}:
            return self._assess_adb_host_repair(request)
        if request.operation_id == "apk.install":
            return self._assess_apk_install(request)
        if request.operation_id == "ascension.transfer_input":
            return self._assess_ascension_transfer(request)
        if request.operation_id == "ascension.launch_manager":
            return self._assess_ascension_manager_launch(request)
        return super().assess(request)

    def _assess_adb_host_repair(self, request: OperationRequest) -> GuardianDecision:
        expected_arguments = {
            "repair.adb_kill_server": ("kill-server",),
            "repair.adb_start_server": ("start-server",),
        }
        expected = expected_arguments.get(request.operation_id)
        if (
            Path(request.executable).name.casefold() not in {"adb", "adb.exe"}
            or expected is None
            or request.arguments != expected
            or request.target != "host:adb-server"
            or request.approval_target != "host:adb-server"
            or not request.approval_digest
            or not self.approvals.is_approved(request.approval_digest, request.approval_target)
        ):
            return self._deny_install(
                "ADB host recovery is outside its exact approved daemon-only form"
            )
        return GuardianDecision(
            True,
            RiskLevel.LOW,
            ("Exact host ADB daemon recovery approved; no Android-device command is permitted",),
            user_approval_required=True,
        )

    def _assess_ascension_manager_path(self, request: OperationRequest) -> GuardianDecision:
        args = request.arguments
        if (
            Path(request.executable).name.casefold() not in {"adb", "adb.exe"}
            or len(args) != 6
            or args[0] != "-s"
            or args[2:5] != ("shell", "pm", "path")
            or args[5] not in ASCENSION_MANAGER_PACKAGES
            or not args[1]
            or request.target != args[1]
        ):
            return self._deny_install(
                "Ascension Manager package lookup is outside Guardian's bounded form"
            )
        if not self._approved_for_serial(request, args[1]):
            return self._deny_install("Ascension Manager package lookup lacks exact user approval")
        return GuardianDecision(
            True,
            RiskLevel.LOW,
            ("Exact allowlisted Manager package path lookup approved by the user",),
            user_approval_required=True,
        )

    def _assess_ascension_manager_pull(self, request: OperationRequest) -> GuardianDecision:
        args = request.arguments
        if (
            Path(request.executable).name.casefold() not in {"adb", "adb.exe"}
            or len(args) != 5
            or args[0] != "-s"
            or args[2] != "pull"
            or not args[1]
            or request.target != args[1]
        ):
            return self._deny_install(
                "Ascension Manager verification copy is outside Guardian's bounded form"
            )
        remote, local = args[3], Path(args[4])
        try:
            parent = local.parent.resolve(strict=True)
        except OSError:
            return self._deny_install("Ascension Manager verification destination is unavailable")
        if (
            not installed_manager_path(remote)
            or not local.is_absolute()
            or local.is_symlink()
            or local.name != "installed-manager.apk"
            or not parent.name.startswith(".manager-inspection-")
            or not parent.is_relative_to(self.workspace / "projects")
        ):
            return self._deny_install(
                "Ascension Manager verification source or destination was rejected"
            )
        if not self._approved_for_serial(request, args[1]):
            return self._deny_install(
                "Ascension Manager verification copy lacks exact user approval"
            )
        return GuardianDecision(
            True,
            RiskLevel.MEDIUM,
            ("Exact installed Manager APK verification copy approved by the user",),
            user_approval_required=True,
        )

    def _assess_ascension_manager_launch(self, request: OperationRequest) -> GuardianDecision:
        args = request.arguments
        if (
            Path(request.executable).name.casefold() not in {"adb", "adb.exe"}
            or len(args) != 9
            or args[0] != "-s"
            or args[2:5] != ("shell", "monkey", "-p")
            or args[5] not in ASCENSION_MANAGER_PACKAGES
            or args[6:] != ("-c", ASCENSION_MANAGER_LAUNCH_CATEGORY, "1")
            or not args[1]
            or request.target != args[1]
        ):
            return self._deny_install(
                "Ascension Manager launch is outside Guardian's bounded open-only form"
            )
        if not self._approved_for_serial(request, args[1]):
            return self._deny_install("Ascension Manager launch lacks exact user approval")
        return GuardianDecision(
            True,
            RiskLevel.LOW,
            ("Exact verified Manager open-only handoff approved by the user",),
            user_approval_required=True,
        )

    def _approved_for_serial(self, request: OperationRequest, serial: str) -> bool:
        expected_target = self.privacy.pseudonym(serial)
        return bool(
            request.approval_target == expected_target
            and request.approval_digest
            and self.approvals.is_approved(request.approval_digest, expected_target)
        )

    def _assess_media_backup(self, request: OperationRequest) -> GuardianDecision:
        if Path(request.executable).name.casefold() not in {"adb", "adb.exe"}:
            return self._deny_install("Phone media backup requires the verified ADB executable")
        args = request.arguments
        if len(args) != 5 or args[0] != "-s" or args[2] != "pull":
            return self._deny_install("Phone media backup is outside Guardian's bounded pull form")
        serial, remote, local_raw = args[1], args[3], args[4]
        local = Path(local_raw)
        if (
            not serial
            or request.target != serial
            or remote not in MEDIA_BACKUP_REMOTE_PATHS
            or not local.is_absolute()
            or local.is_symlink()
            or local.name != remote.rsplit("/", 1)[-1]
        ):
            return self._deny_install("Phone media backup target, scope, or path was rejected")
        try:
            parent = local.parent.resolve(strict=True)
        except OSError:
            return self._deny_install("Phone media backup destination is unavailable")
        if parent.is_relative_to(self.workspace):
            return self._deny_install("Phone media backup must stay outside the ROMVERSE workspace")
        expected_target = self.privacy.pseudonym(serial)
        digest = media_pull_digest(serial, remote, parent / local.name)
        if request.approval_target != expected_target or request.approval_digest != digest:
            return self._deny_install(
                "Phone media backup approval is not bound to this exact transfer"
            )
        if not self.approvals.is_approved(digest, expected_target):
            return self._deny_install("No approval exists for this exact phone media transfer")
        return GuardianDecision(
            True,
            RiskLevel.MEDIUM,
            ("Exact read-only shared-storage copy approved by the user",),
            user_approval_required=True,
        )

    def _assess_ascension_output_list(self, request: OperationRequest) -> GuardianDecision:
        args = request.arguments
        if (
            Path(request.executable).name.casefold() not in {"adb", "adb.exe"}
            or len(args) != 2 + len(ASCENSION_OUTPUT_LIST_COMMAND)
            or args[0] != "-s"
            or tuple(args[2:]) != ASCENSION_OUTPUT_LIST_COMMAND
            or not args[1]
            or request.target != args[1]
        ):
            return self._deny_install("Ascension output scan is outside Guardian's bounded form")
        target = self.privacy.pseudonym(args[1])
        digest = ascension_output_list_digest(args[1])
        if (
            request.approval_target != target
            or request.approval_digest != digest
            or not self.approvals.is_approved(digest, target)
        ):
            return self._deny_install("Ascension output scan lacks exact user approval")
        return GuardianDecision(
            True,
            RiskLevel.MEDIUM,
            ("User approved a filename-only scan of the phone Downloads folder",),
            user_approval_required=True,
        )

    def _assess_ascension_output_pull(self, request: OperationRequest) -> GuardianDecision:
        args = request.arguments
        if (
            Path(request.executable).name.casefold() not in {"adb", "adb.exe"}
            or len(args) != 5
            or args[0] != "-s"
            or args[2] != "pull"
            or not args[1]
            or request.target != args[1]
        ):
            return self._deny_install(
                "Ascension output retrieval is outside Guardian's bounded form"
            )
        remote, local = args[3], Path(args[4])
        name = remote.removeprefix("/sdcard/Download/")
        try:
            parent = local.parent.resolve(strict=True)
        except OSError:
            return self._deny_install("Ascension output destination is unavailable")
        if (
            not remote.startswith("/sdcard/Download/")
            or not ASCENSION_OUTPUT_NAME.fullmatch(name)
            or local.name != name
            or not local.is_absolute()
            or local.is_symlink()
            or not parent.is_relative_to(self.workspace)
        ):
            return self._deny_install("Ascension output source or destination was rejected")
        target = self.privacy.pseudonym(args[1])
        digest = ascension_output_pull_digest(args[1], remote, local)
        if (
            request.approval_target != target
            or request.approval_digest != digest
            or not self.approvals.is_approved(digest, target)
        ):
            return self._deny_install("Ascension output retrieval lacks exact user approval")
        return GuardianDecision(
            True,
            RiskLevel.MEDIUM,
            ("Exact manager-patched image retrieval approved by the user",),
            user_approval_required=True,
        )

    def _assess_apk_install(self, request: OperationRequest) -> GuardianDecision:
        if Path(request.executable).name.casefold() not in {"adb", "adb.exe"}:
            return self._deny_install("APK installation requires the verified ADB executable")
        args = request.arguments
        if (
            len(args) != 4
            or args[0] != "-s"
            or not args[1]
            or args[2] != "install"
            or Path(args[3]).suffix.casefold() != ".apk"
            or not Path(args[3]).is_file()
        ):
            return self._deny_install("APK command is outside Guardian's bounded install form")
        if request.target != args[1]:
            return self._deny_install("Selected device does not match the command target")
        expected_target = self.privacy.pseudonym(request.target)
        if not request.approval_target or request.approval_target != expected_target:
            return self._deny_install("Guardian approval is not bound to this device")
        if not request.approval_digest or not self.approvals.is_approved(
            request.approval_digest, request.approval_target
        ):
            return self._deny_install("No approval exists for this exact APK install plan")
        return GuardianDecision(
            True,
            RiskLevel.MEDIUM,
            ("Exact APK plan and device binding approved by the user",),
            user_approval_required=True,
        )

    def _assess_ascension_transfer(self, request: OperationRequest) -> GuardianDecision:
        if Path(request.executable).name.casefold() not in {"adb", "adb.exe"}:
            return self._deny_install("Ascension transfer requires the verified ADB executable")
        args = request.arguments
        if len(args) != 5 or args[0] != "-s" or args[2] != "push":
            return self._deny_install("Ascension transfer is outside Guardian's bounded form")
        serial, local_raw, remote = args[1], args[3], args[4]
        local = Path(local_raw)
        try:
            resolved = local.resolve(strict=True)
        except OSError:
            return self._deny_install("Ascension transfer input is unavailable")
        if (
            not serial
            or request.target != serial
            or local.is_symlink()
            or not resolved.is_file()
            or resolved.suffix.casefold() != ".img"
            or not resolved.is_relative_to(self.workspace)
            or not re.fullmatch(
                r"/sdcard/Download/ROMVERSE-[0-9a-f]{8}-[A-Za-z0-9_.-]{1,96}\.img",
                remote,
            )
        ):
            return self._deny_install("Ascension transfer paths or target failed validation")
        expected_target = self.privacy.pseudonym(serial)
        if request.approval_target != expected_target:
            return self._deny_install("Ascension approval is not bound to this device")
        if not request.approval_digest or not self.approvals.is_approved(
            request.approval_digest, request.approval_target
        ):
            return self._deny_install("No approval exists for this exact Ascension transfer")
        return GuardianDecision(
            True,
            RiskLevel.MEDIUM,
            ("Exact source-bound image transfer and device were approved by the user",),
            user_approval_required=True,
        )

    @staticmethod
    def _deny_install(reason: str) -> GuardianDecision:
        return GuardianDecision(
            False,
            RiskLevel.HIGH,
            (reason,),
            user_approval_required=True,
        )
