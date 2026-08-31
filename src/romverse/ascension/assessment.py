from __future__ import annotations

import hashlib
import os
from pathlib import Path

from romverse.ascension.binding import AscensionSourceBindingService
from romverse.ascension.evidence import AscensionEvidenceService, inspect_android_boot_image
from romverse.ascension.models import (
    AscensionAssessment,
    AscensionGate,
    AscensionMethod,
    AscensionRecommendation,
    GateState,
)
from romverse.ascension.releases import OfficialRootReleaseService
from romverse.ascension.support import KernelSuSupportEvidenceService
from romverse.backup.handoff import BackupHandoffService
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device.root_identity import review_root_identity
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.process import SubprocessRunner
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.recovery_evidence import RecoveryEvidenceService
from romverse.rom.source_identity import identify_firmware_source
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService


class AscensionAssessmentService:
    """Assess root preparation from observed evidence without changing a device."""

    MAX_TREE_ENTRIES = 250_000
    MAX_PATCH_TARGET_CANDIDATES = 32
    MAX_PATCH_TARGET_BYTES = 1024 * 1024 * 1024
    HASH_CHUNK_SIZE = 4 * 1024 * 1024
    CANDIDATE_NAMES = ("init_boot.img", "boot.img", "recovery.img")

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        release_service: OfficialRootReleaseService | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.release_service = release_service

    def assess(
        self,
        project_id: str,
        method: AscensionMethod,
        device: AndroidDevice | None = None,
        companion: object | None = None,
    ) -> AscensionAssessment:
        companion_only = False
        if (device is None or device.state is not DeviceState.DEVICE) and companion is not None:
            bootloader_state = str(getattr(companion, "bootloader_state", "unknown"))
            root_signal = str(getattr(companion, "root_signal", "unknown"))
            device = AndroidDevice(
                "authenticated-companion",
                DeviceState.DEVICE,
                transport="companion",
                manufacturer=str(getattr(companion, "manufacturer", "")),
                model=str(getattr(companion, "model", "")),
                codename=str(getattr(companion, "device_codename", "")),
                android_version=str(getattr(companion, "android_version", "")),
                bootloader_locked=(
                    True
                    if bootloader_state == "locked"
                    else False
                    if bootloader_state == "unlocked"
                    else None
                ),
                root_detected=(
                    True
                    if root_signal == "observed"
                    else False
                    if root_signal == "not_observed"
                    else None
                ),
                root_signal_source="companion-local-indicators",
                root_manager_candidate=str(getattr(companion, "root_manager_candidate", "unknown")),
                root_manager_evidence="official-signer-check",
                kernel_version=str(getattr(companion, "kernel_release", "")),
            )
            companion_only = True
        project = self.store.get(project_id)
        gates: list[AscensionGate] = []
        source_summary = "No protected firmware source"
        identity = None
        exact_pack = None
        source_blueprint = None
        binding = None

        if project.original is None:
            gates.append(
                self._blocked(
                    "source",
                    "Protected firmware source",
                    "No immutable source is attached to this project.",
                    "Import and verify firmware for the exact device and region.",
                )
            )
        else:
            identity = identify_firmware_source(project.original.original_name)
            source_summary = identity.summary
            gates.append(
                AscensionGate(
                    "source",
                    "Protected firmware source",
                    GateState.PASS,
                    f"SHA-256 protected source: {project.original.sha256[:16]}…; {source_summary}",
                )
            )
            source_resolution = self.registry.resolve_source(project.original.sha256)
            exact_pack = source_resolution.pack if source_resolution.matched else None
            source_blueprint = FirmwareSourceIntelligenceService(
                self.store,
                (),
                SubprocessRunner(),
            ).load(project_id)
            if exact_pack is None and source_blueprint is None:
                gates.append(
                    self._blocked(
                        "source-contract",
                        "Exact Device Pack contract",
                        source_resolution.reason,
                        "Publish or install a signed Device Pack bound to this exact firmware SHA-256.",
                    )
                )

            elif exact_pack is not None:
                gates.append(
                    AscensionGate(
                        "source-contract",
                        "Exact Device Pack contract",
                        GateState.PASS,
                        f"{exact_pack.display_name} is bound to this exact source digest.",
                    )
                )
            else:
                assert source_blueprint is not None
                gates.append(
                    AscensionGate(
                        "source-contract",
                        "Source build blueprint",
                        GateState.PASS,
                        f"ROMVERSE verified a {source_blueprint.source_kind} blueprint bound to this exact source ({source_blueprint.blueprint_digest[:16]}…).",
                        "The blueprint authorizes contained patch preparation only; Guardian still requires signed recovery and flash evidence before a device-changing handoff.",
                    )
                )

            binding = AscensionSourceBindingService(self.store, self.registry).resolve(project_id)
            if binding.device_dna_digest:
                dna_state = (
                    GateState.BLOCKED
                    if binding.device_dna_state.value == "UNSUPPORTED"
                    else GateState.PASS
                    if binding.device_dna_state.value == "SUPPORTED"
                    else GateState.ATTENTION
                )
                gates.append(
                    AscensionGate(
                        "device-dna",
                        "Device DNA identity binding",
                        dna_state,
                        f"Profile {binding.device_dna_digest[:16]}…; identity capability {binding.device_dna_state.value}; source authority {binding.authority}.",
                        (
                            "Resolve the Device DNA identity warning before a Guardian handoff."
                            if dna_state is not GateState.PASS
                            else ""
                        ),
                    )
                )
            else:
                gates.append(
                    AscensionGate(
                        "device-dna",
                        "Device DNA identity binding",
                        GateState.ATTENTION,
                        "The protected source has not yet been compiled into Device DNA.",
                        "Return to ROM Studio detection so ROMVERSE can compile Device DNA; local rollback preparation may continue, but final Guardian planning cannot.",
                    )
                )

        candidates, truncated = self._image_candidates(project_id)
        patch_target, target_detail = self._resolve_patch_target(project_id, candidates, method)
        if patch_target:
            gates.append(
                AscensionGate(
                    "patch-target",
                    "Patch target image",
                    GateState.PASS,
                    target_detail,
                )
            )
        else:
            detail = target_detail or (
                "No contained init_boot.img, boot.img, or recovery.img was found."
            )
            if truncated:
                detail += " The tree entry safety limit was reached."
            gates.append(
                self._blocked(
                    "patch-target",
                    "Patch target image",
                    detail,
                    "Extract the exact firmware partitions in Partition Atlas, then reassess.",
                )
            )

        if device is None or device.state is not DeviceState.DEVICE:
            gates.append(
                self._blocked(
                    "live-device",
                    "Authorized live device",
                    "No authorized Android device is available for identity comparison.",
                    "Connect the phone, authorize USB debugging, and scan again.",
                )
            )
        else:
            gates.append(
                AscensionGate(
                    "live-device",
                    "Authorized live device",
                    GateState.ATTENTION if companion_only else GateState.PASS,
                    (
                        f"Authenticated Companion identity available for {device.display_name} ({device.codename or 'unknown codename'})."
                        if companion_only
                        else f"Read-only ADB identity available for {device.display_name} ({device.codename or 'unknown codename'})."
                    ),
                    "A wired, explicitly authorized handoff is still required before any patch or installation stage."
                    if companion_only
                    else "",
                )
            )
            source_codename = binding.codename if binding is not None else ""
            if binding is not None and binding.matches(device):
                gates.append(
                    AscensionGate(
                        "device-match",
                        "Source and device identity",
                        GateState.PASS,
                        f"Protected source and connected device both identify as {source_codename}; authority {binding.authority}."
                        + (
                            f" Device DNA {binding.device_dna_digest[:16]}… is attached."
                            if binding.device_dna_digest
                            else " Device DNA remains pending before final Guardian planning."
                        ),
                    )
                )
            else:
                conflict = "; ".join(binding.conflicts) if binding is not None else ""
                gates.append(
                    self._blocked(
                        "device-match",
                        "Source and device identity",
                        f"Source codename {source_codename or 'unconfirmed'} does not exactly match live codename {device.codename or 'unknown'}."
                        + (f" {conflict}" if conflict else ""),
                        "Select firmware for the connected device; ROMVERSE never guesses across models.",
                    )
                )
            if device.bootloader_locked is False:
                gates.append(
                    AscensionGate(
                        "bootloader",
                        "Bootloader state",
                        GateState.PASS,
                        "The device reports an unlocked bootloader.",
                    )
                )
            else:
                state = "locked" if device.bootloader_locked else "not verifiable"
                gates.append(
                    AscensionGate(
                        "bootloader",
                        "Bootloader state",
                        GateState.ATTENTION,
                        f"The bootloader is {state}. Safe local rooted-ROM preparation may continue, but Guardian will block every device-write handoff until an explicitly unlocked state is observed.",
                        "Before any later installation, use only the OEM's official unlock process. Unlocking may erase all phone data; ROMVERSE never unlocks or relocks it automatically.",
                    )
                )
            root_review = review_root_identity(
                device.root_detected,
                device.root_manager_candidate,
                root_signal_source=device.root_signal_source,
                manager_evidence=device.root_manager_evidence,
            )
            gates.append(
                AscensionGate(
                    "root-state",
                    "Existing root identity review",
                    GateState.BLOCKED if device.root_detected is True else GateState.ATTENTION,
                    f"{root_review.title}. {root_review.summary} Confidence: {root_review.confidence}.",
                    root_review.next_action,
                )
            )

        recovery = RecoveryEvidenceService(self.store).assess(project_id)
        backup_handoff = BackupHandoffService(self.store).load(
            project_id,
            None if companion_only else device,
        )
        backup_ready = recovery.external_backup_ready or backup_handoff is not None
        rollback = None
        rollback_error = ""
        if patch_target:
            try:
                rollback = AscensionEvidenceService(self.store).ensure(project_id, patch_target)
            except ProjectError as exc:
                rollback_error = str(exc)
        if rollback is None:
            gates.append(
                self._blocked(
                    "recovery",
                    "Automatic rollback capsule",
                    rollback_error or "A source-bound pristine rollback image is unavailable.",
                    "ROMVERSE will retry after the exact firmware partitions are extracted and verified.",
                )
            )
        else:
            recovery_detail = (
                f"Pristine {rollback.patch_target.source_relative_path} rollback verified "
                f"({rollback.patch_target.sha256[:16]}…)"
            )
            if rollback.stock_recovery is not None:
                recovery_detail += (
                    f"; exact stock recovery captured ({rollback.stock_recovery.sha256[:16]}…)"
                )
            else:
                recovery_detail += "; protected full firmware remains the stock recovery source"
            gates.append(
                AscensionGate(
                    "recovery",
                    "Automatic rollback capsule",
                    GateState.PASS,
                    recovery_detail + "; phone changed: NO.",
                    "This authorizes local root preparation only, never a device write.",
                )
            )
            gates.append(
                AscensionGate(
                    "user-backup",
                    "User-data safety backup",
                    GateState.PASS if backup_ready else GateState.ATTENTION,
                    (
                        "Independently stored external phone backup is registered and verified."
                        if recovery.external_backup_ready
                        else (
                            f"User-confirmed {backup_handoff.provider} backup "
                            f"({backup_handoff.last_backup_label}); restore access, data scope, "
                            "and limitations were reviewed. Cloud contents were not inspected."
                            if backup_handoff is not None
                            else "ROMVERSE prepared partition rollback automatically; a full user-data backup is not claimed."
                        )
                    ),
                    (
                        "Before a device-changing handoff, ROMVERSE will launch the strongest backup route supported by the connected phone and require verified evidence."
                        if not backup_ready
                        else ""
                    ),
                )
            )

        if method is AscensionMethod.KERNELSU_LKM:
            kernel = device.kernel_version.strip() if device is not None else ""
            local_support = KernelSuSupportEvidenceService(
                self.store,
                self.release_service,
            ).load(project_id, device)
            companion_support = str(getattr(companion, "kernelsu_support", "unknown"))
            companion_codename = str(getattr(companion, "device_codename", ""))
            companion_kernel = str(getattr(companion, "kernel_release", ""))
            companion_bound = bool(
                device is not None
                and device.codename
                and kernel
                and companion_codename.casefold() == device.codename.casefold()
                and companion_kernel == kernel
            )
            # Remote Companion telemetry is useful context but cannot prove that the
            # exact official Manager APK was installed and observed on this kernel.
            # Only the source/device/kernel-bound local receipt may clear this gate.
            kernelsu_support = local_support.status if local_support is not None else "unknown"
            support_source = (
                "source-bound, official-Manager local evidence"
                if local_support is not None
                else "no authoritative local support evidence"
            )
            companion_advisory = (
                f" Companion reports {companion_support} for the same codename/kernel, but read-only telemetry cannot authorize this route."
                if companion_bound and companion_support in {"supported", "unsupported"}
                else ""
            )
            support_state = GateState.PASS if kernelsu_support == "supported" else GateState.BLOCKED
            gates.append(
                AscensionGate(
                    "kernel",
                    "KernelSU kernel/KMI evidence",
                    GateState.BLOCKED if not kernel else support_state,
                    (
                        f"Live kernel: {kernel}. KernelSU support: {kernelsu_support} ({support_source})."
                        + (
                            f" Evidence: {local_support.observation}."
                            if local_support is not None
                            else ""
                        )
                        + companion_advisory
                        if kernel
                        else "Kernel version/KMI evidence is unavailable."
                    ),
                    "Allow ROMVERSE to install the verified official KernelSU Manager after approval, then confirm it reports Not installed (supported), not Unsupported. Companion telemetry and online model claims remain advisory; ROMVERSE will not infer KMI compatibility from a model name or Android version.",
                )
            )
        elif identity is not None and identity.manufacturer.casefold() == "xiaomi":
            boot = rollback.boot_image if rollback is not None else None
            gates.append(
                AscensionGate(
                    "ramdisk",
                    "Magisk ramdisk decision",
                    GateState.PASS
                    if boot is not None and boot.ramdisk_present
                    else GateState.ATTENTION,
                    (
                        f"Android boot image v{boot.header_version} verified with a "
                        f"{boot.ramdisk_size_bytes:,}-byte ramdisk; {boot.image_name} is the source-bound patch target."
                        if boot is not None and boot.ramdisk_present
                        else "ROMVERSE could not prove boot ramdisk placement from the extracted target."
                    ),
                    (
                        "ROMVERSE will stop rather than guess until a recognized boot image header is available."
                        if boot is None or not boot.ramdisk_present
                        else ""
                    ),
                )
            )

        return AscensionAssessment(
            project.project_id,
            method,
            source_summary,
            patch_target,
            tuple(gates),
            True,
        )

    def recommend(
        self,
        project_id: str,
        device: AndroidDevice | None = None,
        companion: object | None = None,
    ) -> AscensionRecommendation:
        magisk = self.assess(project_id, AscensionMethod.MAGISK, device, companion)
        kernelsu = self.assess(project_id, AscensionMethod.KERNELSU_LKM, device, companion)
        root_gate = next((gate for gate in magisk.gates if gate.gate_id == "root-state"), None)
        if root_gate is not None and root_gate.state is GateState.BLOCKED:
            return AscensionRecommendation(
                AscensionMethod.MAGISK,
                "Existing root detected — review first",
                "ROMVERSE will not install or prepare a second root method over an already rooted phone. Review the existing manager or restore the exact stock image first.",
                (root_gate.detail, root_gate.resolution),
            )
        kernel_gate = next((gate for gate in kernelsu.gates if gate.gate_id == "kernel"), None)
        bootloader_gate = next(
            (gate for gate in magisk.gates if gate.gate_id == "bootloader"),
            None,
        )
        bootloader_boundary = (
            bootloader_gate.detail
            if bootloader_gate is not None and bootloader_gate.state is not GateState.PASS
            else ""
        )
        if not kernelsu.blocked and kernel_gate is not None and kernel_gate.state is GateState.PASS:
            return AscensionRecommendation(
                AscensionMethod.KERNELSU_LKM,
                "KernelSU LKM recommended",
                "The connected phone reports explicit KernelSU support, and LKM preserves the stock kernel while patching the source-bound ramdisk. This recommendation authorizes local preparation only; Guardian independently checks the bootloader before any device write.",
                tuple(
                    item
                    for item in (
                        kernel_gate.detail,
                        "Exact source and rollback evidence verified",
                        bootloader_boundary,
                    )
                    if item
                ),
                True,
            )
        ramdisk = next((gate for gate in magisk.gates if gate.gate_id == "ramdisk"), None)
        if not magisk.blocked:
            kernelsu_detail = kernel_gate.detail if kernel_gate is not None else ""
            kernelsu_explicitly_unsupported = (
                kernel_gate is not None and "support: unsupported" in kernel_gate.detail
            )
            evidence = tuple(
                item
                for item in (
                    ramdisk.detail if ramdisk is not None else "",
                    (
                        "KernelSU was explicitly reported unsupported for the exact observed kernel; ROMVERSE selected the Magisk fallback."
                        if kernelsu_explicitly_unsupported
                        else "KernelSU was not selected without explicit support evidence"
                    ),
                    kernelsu_detail,
                    bootloader_boundary,
                )
                if item
            )
            return AscensionRecommendation(
                AscensionMethod.MAGISK,
                "Magisk image patch recommended",
                "ROMVERSE verified a same-device image-patch route and will not guess KernelSU compatibility from the model name or Android version. This recommendation authorizes local preparation only; Guardian independently checks the bootloader before any device write.",
                evidence,
                True,
            )
        return AscensionRecommendation(
            AscensionMethod.MAGISK,
            "Complete source and device checks first",
            "Neither root route is ready. ROMVERSE will resolve safe project prerequisites before recommending a device-changing handoff.",
            tuple(gate.detail for gate in magisk.gates if gate.state is GateState.BLOCKED),
        )

    def _image_candidates(self, project_id: str) -> tuple[tuple[str, ...], bool]:
        working_root = self.store.working_root / project_id
        search_roots = (
            (working_root / "tree", ""),
            (working_root / "partitions", "partitions"),
        )
        found: list[str] = []
        entries = 0
        for root, prefix in search_roots:
            if not root.is_dir() or root.is_symlink():
                continue
            for directory, dirnames, filenames in os.walk(root, followlinks=False):
                directory_path = Path(directory)
                dirnames[:] = [
                    name for name in dirnames if not (directory_path / name).is_symlink()
                ]
                entries += len(dirnames) + len(filenames)
                if entries > self.MAX_TREE_ENTRIES:
                    return tuple(sorted(found)), True
                for name in filenames:
                    if name.casefold() not in self.CANDIDATE_NAMES:
                        continue
                    candidate = directory_path / name
                    if candidate.is_symlink() or not candidate.is_file():
                        continue
                    relative = candidate.relative_to(root)
                    found.append(
                        (Path(prefix) / relative).as_posix() if prefix else relative.as_posix()
                    )
        return tuple(sorted(found)), False

    def _resolve_patch_target(
        self,
        project_id: str,
        candidates: tuple[str, ...],
        method: AscensionMethod,
    ) -> tuple[str, str]:
        """Select one byte-authoritative, structurally patchable root target."""

        target_order = (
            ("init_boot.img", "boot.img", "recovery.img")
            if method is AscensionMethod.MAGISK
            else ("init_boot.img", "boot.img")
        )
        skipped: list[str] = []
        for target in target_order:
            matches = tuple(item for item in candidates if Path(item).name.casefold() == target)
            if not matches:
                continue
            if len(matches) > self.MAX_PATCH_TARGET_CANDIDATES:
                return "", (
                    f"ROMVERSE found {len(matches)} contained {target} candidates, exceeding the "
                    f"{self.MAX_PATCH_TARGET_CANDIDATES}-image ambiguity limit. Recreate the "
                    "isolated workspace from one firmware package."
                )
            digest = ""
            copy_detail = ""
            if len(matches) == 1:
                relative = matches[0]
                try:
                    path = self._candidate_path(project_id, relative)
                    size = path.stat().st_size
                except OSError as exc:
                    return "", f"The contained {target} candidate could not be verified: {exc}"
                if size <= 0 or size > self.MAX_PATCH_TARGET_BYTES:
                    return "", (
                        f"Contained candidate {relative} has an invalid root-target size "
                        f"({size:,} bytes); ROMVERSE will not select it automatically."
                    )
                selected = relative
            else:
                identities: list[tuple[str, int, str]] = []
                try:
                    for relative in matches:
                        path = self._candidate_path(project_id, relative)
                        size = path.stat().st_size
                        if size <= 0 or size > self.MAX_PATCH_TARGET_BYTES:
                            return "", (
                                f"Contained candidate {relative} has an invalid root-target size "
                                f"({size:,} bytes); ROMVERSE will not select it automatically."
                            )
                        identities.append((relative, size, self._sha256(path)))
                except OSError as exc:
                    return "", f"A contained {target} candidate could not be verified: {exc}"
                digests = {identity for _relative, _size, identity in identities}
                if len(digests) != 1:
                    conflict = ", ".join(
                        f"{relative} ({identity[:12]}…)"
                        for relative, _size, identity in identities[:6]
                    )
                    return "", (
                        f"Conflicting byte-distinct {target} candidates were found: {conflict}. "
                        "ROMVERSE stopped instead of guessing which partition belongs to the protected source."
                    )
                selected, size, digest = min(
                    identities,
                    key=lambda item: self._target_rank(item[0], target),
                )
                copy_detail = f" ROMVERSE collapsed {len(identities)} byte-identical contained copies to this canonical path."
            try:
                path = self._candidate_path(project_id, selected)
                project_root = (self.store.working_root / project_id).resolve(strict=True)
                boot = inspect_android_boot_image(path, project_root)
            except (OSError, ProjectError) as exc:
                skipped.append(f"{selected}: {exc}")
                continue
            if not boot.ramdisk_present:
                skipped.append(
                    f"{selected}: Android boot v{boot.header_version} contains no patchable ramdisk"
                )
                continue
            digest_detail = (
                f"; SHA-256 {digest[:16]}…"
                if digest
                else "; SHA-256 is sealed by the rollback evidence gate"
            )
            fallback_detail = (
                f" Higher-priority candidates were skipped safely: {'; '.join(skipped)}."
                if skipped
                else ""
            )
            return selected, (
                f"Verified {selected} as the canonical {target} root target "
                f"({size:,} bytes; Android boot v{boot.header_version}; "
                f"ramdisk {boot.ramdisk_size_bytes:,} bytes{digest_detail})."
                f"{copy_detail}{fallback_detail}"
            )
        if method is AscensionMethod.KERNELSU_LKM and any(
            Path(item).name.casefold() == "recovery.img" for item in candidates
        ):
            skipped.append(
                "recovery.img: KernelSU LKM supports only an exact boot or init_boot target"
            )
        if skipped:
            return "", (
                f"No structurally patchable {method.display_name} target was found. "
                + "; ".join(skipped)
            )
        return "", ""

    def _candidate_path(self, project_id: str, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
            raise OSError("unsafe candidate path")
        project_root = self.store.working_root / project_id
        if candidate.parts[0] == "partitions":
            root = project_root / "partitions"
            unresolved = root.joinpath(*candidate.parts[1:])
        else:
            root = project_root / "tree"
            unresolved = root / candidate
        if unresolved.is_symlink():
            raise OSError("symbolic-link candidate")
        path = unresolved.resolve(strict=True)
        root = root.resolve(strict=True)
        if not path.is_file() or not path.is_relative_to(root):
            raise OSError("candidate escaped the isolated workspace")
        return path

    @staticmethod
    def _target_rank(relative: str, target: str) -> tuple[int, int, str]:
        path = Path(relative)
        preferred = {
            f"partitions/{target}": 0,
            f"images/{target}": 1,
            target: 2,
        }
        return preferred.get(path.as_posix().casefold(), 3), len(path.parts), relative.casefold()

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(self.HASH_CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _blocked(gate_id: str, title: str, detail: str, resolution: str) -> AscensionGate:
        return AscensionGate(gate_id, title, GateState.BLOCKED, detail, resolution)
