from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import stat
import zipfile
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import (
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.infrastructure.process import SubprocessRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.build_contracts import DeviceBuildContractService
from romverse.rom.build_execution import BuildOutputReceipt, LocalDeviceBuildExecutor
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.recovery_evidence import RecoveryEvidenceService
from romverse.rom.signing_ceremony import (
    OfflineSigningCeremonyService,
    OfflineSigningReceipt,
    SignedArtifactEvidence,
)
from romverse.rom.simulation import RomSimulationService


class ReleaseTier(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PUBLIC = "public"


class ReleasePackageKind(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"
    RECOVERY = "recovery"


class ReleaseGateState(StrEnum):
    PASS = "pass"
    ATTENTION = "attention"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ReleaseGate:
    gate_id: str
    label: str
    state: ReleaseGateState
    evidence: str
    resolution: str


@dataclass(frozen=True, slots=True)
class ReleaseSecurityFinding:
    finding_id: str
    state: ReleaseGateState
    path: str
    detail: str


@dataclass(frozen=True, slots=True)
class ReleaseSecurityScan:
    scanned_files: int
    scanned_bytes: int
    opaque_artifacts: int
    secret_scan_passed: bool
    malware_screen_passed: bool
    findings: tuple[ReleaseSecurityFinding, ...]
    limitations: tuple[str, ...]
    scan_digest: str


@dataclass(frozen=True, slots=True)
class ReleaseForgeAssessment:
    project_id: str
    tier: ReleaseTier
    package_kind: ReleasePackageKind
    gates: tuple[ReleaseGate, ...]
    security: ReleaseSecurityScan
    artifact_names: tuple[str, ...]
    build_receipt_digest: str
    simulation_digest: str
    signing_receipt_digest: str

    @property
    def ready(self) -> bool:
        return bool(self.gates) and all(
            gate.state is not ReleaseGateState.BLOCKED for gate in self.gates
        )


@dataclass(frozen=True, slots=True)
class ReleaseArtifactPlan:
    name: str
    source_path: str
    size_bytes: int
    sha256: str
    signed: bool
    source_receipt: str


@dataclass(frozen=True, slots=True)
class SignedAssemblyInput:
    partition: str
    source_path: str
    size_bytes: int
    sha256: str
    signed: bool


@dataclass(frozen=True, slots=True)
class SignedAssemblyReceipt:
    schema_version: int
    project_id: str
    created_at: str
    build_receipt_digest: str
    signing_receipt_digest: str
    inputs: tuple[SignedAssemblyInput, ...]
    super_path: str
    super_size_bytes: int
    super_sha256: str
    lpdump_sha256: str
    verified: bool
    phone_changed: bool
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class ReleaseForgePlan:
    schema_version: int
    release_id: str
    project_id: str
    created_at: str
    version: str
    tier: ReleaseTier
    package_kind: ReleasePackageKind
    device_pack_id: str
    device_pack_sha256: str
    source_sha256: str
    build_receipt_digest: str
    simulation_digest: str
    simulation_mission_digest: str
    signing_receipt_digest: str
    security_scan_digest: str
    base_release_digest: str
    artifacts: tuple[ReleaseArtifactPlan, ...]
    unchanged_artifacts: tuple[tuple[str, str], ...]
    changelog: tuple[str, ...]
    installation_steps: tuple[str, ...]
    reproducible: bool
    signed_artifacts: bool
    public_certificate_required: bool
    phone_changed: bool
    publishing_authority: str
    plan_digest: str
    certificate_payload_digest: str


@dataclass(frozen=True, slots=True)
class ReleaseCertificateSignature:
    schema_version: int
    project_id: str
    release_id: str
    imported_at: str
    key_id: str
    public_key_sha256: str
    public_key_base64: str
    certificate_payload_digest: str
    signature_base64: str
    verified: bool
    private_key_stored: bool
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class ReleaseBundleReceipt:
    schema_version: int
    release_id: str
    project_id: str
    created_at: str
    version: str
    tier: ReleaseTier
    package_kind: ReleasePackageKind
    plan_digest: str
    certificate_payload_digest: str
    certificate_signature_digest: str
    archive_path: str
    archive_sha256: str
    archive_size_bytes: int
    artifact_count: int
    artifact_bytes: int
    signed_certificate: bool
    published: bool
    phone_changed: bool
    receipt_digest: str


class ReleaseForgeService:
    """Create reproducible local release capsules without publishing or using private keys."""

    PLAN_FORMAT = "romverse.release-forge-plan"
    SIGNATURE_FORMAT = "romverse.release-certificate-signature"
    RECEIPT_FORMAT = "romverse.release-bundle-receipt"
    ASSEMBLY_FORMAT = "romverse.signed-super-assembly-receipt"
    PLAN_NAME = "release-forge-plan.romverse"
    SIGNATURE_NAME = "release-certificate-signature.romverse"
    RECEIPT_NAME = "release-bundle-receipt.romverse"
    ASSEMBLY_NAME = "signed-super-assembly-receipt.romverse"
    MANIFEST_MEMBER = "ROMVERSE-RELEASE-MANIFEST.json"
    PLAN_MEMBER = "ROMVERSE-RELEASE-PLAN.json"
    CERTIFICATE_MEMBER = "ROMVERSE-RELEASE-CERTIFICATE.json"
    CHECKSUM_MEMBER = "SHA256SUMS"
    CHANGELOG_MEMBER = "CHANGELOG.txt"
    INSTALL_MEMBER = "INSTALLATION.txt"
    CERTIFICATE_REQUEST_NAME = "romverse-release-certificate-request.json"
    CERTIFICATE_DOMAIN = b"ROMVERSE-RELEASE-CERTIFICATE-V1\x00"
    SCHEMA_VERSION = 1
    MAX_RECORD_BYTES = 4 * 1024 * 1024
    MAX_ARTIFACTS = 128
    MAX_ARCHIVE_BYTES = 256 * 1024**3
    MAX_SCAN_FILES = 50_000
    MAX_SCAN_BYTES = 256 * 1024 * 1024
    MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024
    CHUNK_SIZE = 4 * 1024 * 1024
    ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
    VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-.][0-9A-Za-z][0-9A-Za-z.-]{0,31})?")
    SECRET_NAMES = re.compile(
        r"(^|/)(?:\.env|id_rsa|id_ed25519|credentials?|secrets?)(?:\.|$)",
        re.IGNORECASE,
    )
    SECRET_PATTERNS = (
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
        re.compile(rb"AKIA[0-9A-Z]{16}"),
        re.compile(rb"gh[pousr]_[A-Za-z0-9]{24,}"),
    )

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...] = (),
    ) -> None:
        self.store = store
        self.registry = registry
        self.tool_statuses = tool_statuses

    def assess(
        self,
        project_id: str,
        tier: ReleaseTier,
        package_kind: ReleasePackageKind,
        *,
        base_plan: ReleaseForgePlan | None = None,
    ) -> ReleaseForgeAssessment:
        project = self.store.get(project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id),
            None,
        )
        build = LocalDeviceBuildExecutor(
            self.store,
            self.registry,
            self.tool_statuses,
            SubprocessRunner(),
        ).load_receipt(project_id)
        simulator = RomSimulationService(
            self.store,
            self.registry,
            self.tool_statuses,
        )
        simulation = simulator.load(project_id)
        mission = simulator.load_mission(project_id)
        signing = self._load_signing(project_id)
        assembly = self.load_signed_assembly(project_id, build=build, signing=signing)
        outputs = tuple(build.outputs) if build is not None else ()
        security = self._security_scan(project_id, outputs)
        gates: list[ReleaseGate] = []
        exact_pack = bool(
            project.original is not None
            and pack is not None
            and pack.build_contract is not None
            and pack.build_contract.source.archive_sha256 == project.original.sha256
        )
        gates.append(
            self._gate(
                "source",
                "Exact source and Device Pack",
                exact_pack,
                "Protected firmware and source-bound Device Pack agree."
                if exact_pack
                else "The project has no exact source-bound build contract.",
                "Select a reviewed Device Pack for this exact protected source.",
            )
        )
        gates.append(
            self._gate(
                "build",
                "Verified reproducible local build",
                build is not None,
                f"Build receipt {build.receipt_digest[:16]}… is current."
                if build is not None
                else "No current successful local build receipt is available.",
                "Build and verify a fresh local candidate.",
            )
        )
        simulation_ready = bool(
            simulation is not None
            and simulation.successful
            and not simulation.expert_edits
            and mission is not None
        )
        gates.append(
            self._gate(
                "simulation",
                "Successful unmodified Digital Twin rehearsal",
                simulation_ready,
                f"Simulation {simulation.receipt_digest[:16]}… and mission are current."
                if simulation_ready and simulation is not None
                else "Release Forge found no current successful Simulation Lab mission.",
                "Resolve the Digital Twin blockers and create its ROM Studio mission.",
            )
        )
        signing_required = tier in {ReleaseTier.TESTING, ReleaseTier.PUBLIC}
        signing_ready = bool(signing is not None and signing.verified)
        gates.append(
            ReleaseGate(
                "signing",
                "Verified AVB signing evidence",
                ReleaseGateState.PASS
                if signing_ready
                else ReleaseGateState.BLOCKED
                if signing_required
                else ReleaseGateState.ATTENTION,
                f"Offline signing receipt {signing.receipt_digest[:16]}… is current."
                if signing_ready and signing is not None
                else "No current externally signed AVB artifact receipt is available.",
                "Complete the offline signing ceremony; private keys remain outside ROMVERSE."
                if signing_required
                else "Development releases remain explicitly unsigned and non-production.",
            )
        )
        artifact_plan = self._artifact_plan(outputs, signing, assembly)
        signing_coverage = bool(artifact_plan) and all(item.signed for item in artifact_plan)
        gates.append(
            ReleaseGate(
                "signing-coverage",
                "Complete release artifact signing coverage",
                ReleaseGateState.PASS
                if signing_coverage
                else ReleaseGateState.BLOCKED
                if signing_required
                else ReleaseGateState.ATTENTION,
                "Every planned release artifact is bound to current signing or signed-assembly evidence."
                if signing_coverage
                else "One or more release artifacts remain development-only.",
                "Complete exact signing and signed final assembly for every packaged artifact."
                if signing_required
                else "The capsule will remain clearly marked as a development build.",
            )
        )
        has_super = any(output.name == "super.img" for output in outputs)
        signed_assembly = bool(signing_ready and outputs and (not has_super or assembly))
        gates.append(
            ReleaseGate(
                "signed-assembly",
                "Signed final container assembly",
                ReleaseGateState.PASS
                if signed_assembly
                else ReleaseGateState.BLOCKED
                if signing_required
                else ReleaseGateState.ATTENTION,
                "The final super container was rebuilt from and unpacked against the current signed partition evidence."
                if signed_assembly
                else "A pre-signing super.img cannot inherit the signature of later child images.",
                "Reassemble and verify super.img from the signed child images."
                if signing_required
                else "Keep the development bundle clearly unsigned.",
            )
        )
        recovery = RecoveryEvidenceService(self.store).assess(project_id)
        gates.append(
            ReleaseGate(
                "recovery",
                "Verified rollback package",
                ReleaseGateState.PASS
                if recovery.stock_recovery_ready
                else ReleaseGateState.BLOCKED
                if tier is ReleaseTier.PUBLIC
                else ReleaseGateState.ATTENTION,
                "; ".join(recovery.evidence),
                "Register and verify the exact stock recovery package."
                if not recovery.stock_recovery_ready
                else "No action required.",
            )
        )
        gates.append(
            self._gate(
                "security",
                "Accidental-secret and malware screen",
                security.secret_scan_passed and security.malware_screen_passed,
                f"Scanned {security.scanned_files} bounded files and {security.scanned_bytes} bytes; "
                f"{security.opaque_artifacts} opaque image(s) remain a stated limitation.",
                "Remove every secret or unexpected executable and scan opaque images in a trusted isolated scanner.",
            )
        )
        first_light = self._first_light_passed(project_id)
        gates.append(
            ReleaseGate(
                "physical-validation",
                "First Light physical validation",
                ReleaseGateState.PASS
                if first_light
                else ReleaseGateState.BLOCKED
                if tier is ReleaseTier.PUBLIC
                else ReleaseGateState.ATTENTION,
                "Current First Light report passed on supported hardware."
                if first_light
                else "No current full physical subsystem report is available.",
                "Complete First Light on supported physical hardware before public release.",
            )
        )
        kind_ready, kind_evidence, kind_resolution = self._package_kind_gate(
            project_id,
            package_kind,
            outputs,
            base_plan,
        )
        gates.append(
            self._gate(
                "package-kind",
                f"{package_kind.value.title()} package inputs",
                kind_ready,
                kind_evidence,
                kind_resolution,
            )
        )
        return ReleaseForgeAssessment(
            project_id,
            tier,
            package_kind,
            tuple(gates),
            security,
            tuple(item.name for item in outputs),
            build.receipt_digest if build else "",
            simulation.receipt_digest if simulation else "",
            signing.receipt_digest if signing else "",
        )

    def prepare_plan(
        self,
        project_id: str,
        version: str,
        tier: ReleaseTier,
        package_kind: ReleasePackageKind,
        changelog: tuple[str, ...],
        *,
        base_plan: ReleaseForgePlan | None = None,
    ) -> ReleaseForgePlan:
        if not self.VERSION.fullmatch(version):
            raise ProjectError("Release version must use a bounded semantic version")
        clean_changelog = tuple(self._text(item, "changelog entry", 500) for item in changelog)
        if not clean_changelog or len(clean_changelog) > 100:
            raise ProjectError("Provide between 1 and 100 concise changelog entries")
        assessment = self.assess(
            project_id,
            tier,
            package_kind,
            base_plan=base_plan,
        )
        blockers = tuple(
            gate.label for gate in assessment.gates if gate.state is ReleaseGateState.BLOCKED
        )
        if blockers:
            raise ProjectError("Release planning is blocked: " + ", ".join(blockers))
        project = self.store.get(project_id)
        pack = next(item for item in self.registry.packs if item.pack_id == project.device_pack_id)
        build = LocalDeviceBuildExecutor(
            self.store,
            self.registry,
            self.tool_statuses,
            SubprocessRunner(),
        ).load_receipt(project_id)
        simulation_service = RomSimulationService(
            self.store,
            self.registry,
            self.tool_statuses,
        )
        simulation = simulation_service.load(project_id)
        mission = simulation_service.load_mission(project_id)
        assert project.original and build and simulation and mission
        signing = self._load_signing(project_id)
        assembly = self.load_signed_assembly(project_id, build=build, signing=signing)
        artifacts = self._artifact_plan(build.outputs, signing, assembly)
        unchanged: tuple[tuple[str, str], ...] = ()
        if package_kind is ReleasePackageKind.INCREMENTAL:
            if base_plan is None:
                raise ProjectError("Choose a verified base Release Forge plan")
            previous = {item.name: item.sha256 for item in base_plan.artifacts}
            unchanged = tuple(
                sorted(
                    (item.name, item.sha256)
                    for item in artifacts
                    if previous.get(item.name) == item.sha256
                )
            )
            artifacts = tuple(item for item in artifacts if previous.get(item.name) != item.sha256)
            if not artifacts:
                raise ProjectError("No changed artifacts exist for an incremental package")
        elif package_kind is ReleasePackageKind.RECOVERY:
            artifacts = tuple(
                item
                for item in artifacts
                if item.name
                in {
                    "recovery.img",
                    "vendor_boot.img",
                    "init_boot.img",
                    "boot.img",
                }
            )
        plan_id = uuid4().hex
        release_id = f"romverse-{version}-{tier.value}-{package_kind.value}-{plan_id[:8]}"
        certificate_payload = self._certificate_payload(
            release_id,
            project_id,
            version,
            tier,
            package_kind,
            pack.pack_id,
            pack.sha256,
            project.original.sha256,
            build.receipt_digest,
            simulation.receipt_digest,
            mission.mission_digest,
            signing.receipt_digest if signing else "",
            assessment.security.scan_digest,
            artifacts,
        )
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "release_id": release_id,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "version": version,
            "tier": tier,
            "package_kind": package_kind,
            "device_pack_id": pack.pack_id,
            "device_pack_sha256": pack.sha256,
            "source_sha256": project.original.sha256,
            "build_receipt_digest": build.receipt_digest,
            "simulation_digest": simulation.receipt_digest,
            "simulation_mission_digest": mission.mission_digest,
            "signing_receipt_digest": signing.receipt_digest if signing else "",
            "security_scan_digest": assessment.security.scan_digest,
            "base_release_digest": base_plan.plan_digest if base_plan else "",
            "artifacts": artifacts,
            "unchanged_artifacts": unchanged,
            "changelog": clean_changelog,
            "installation_steps": self._installation_steps(tier, package_kind),
            "reproducible": True,
            "signed_artifacts": bool(artifacts) and all(item.signed for item in artifacts),
            "public_certificate_required": tier is ReleaseTier.PUBLIC,
            "phone_changed": False,
            "publishing_authority": "none",
            "certificate_payload_digest": _digest(certificate_payload),
        }
        plan = ReleaseForgePlan(
            **payload,
            plan_digest=_digest(payload),
        )
        self._save_plan(plan)
        return plan

    def load_plan(self, project_id: str) -> ReleaseForgePlan | None:
        try:
            data = read_json_object(
                self.store.projects_root / project_id / self.PLAN_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECORD_BYTES,
            )
            if data.pop("format") != self.PLAN_FORMAT:
                return None
            raw_artifacts = data.pop("artifacts")
            data["tier"] = ReleaseTier(data["tier"])
            data["package_kind"] = ReleasePackageKind(data["package_kind"])
            data["unchanged_artifacts"] = tuple(
                (str(name), str(digest)) for name, digest in data["unchanged_artifacts"]
            )
            data["changelog"] = tuple(data["changelog"])
            data["installation_steps"] = tuple(data["installation_steps"])
            plan = ReleaseForgePlan(
                **data,
                artifacts=tuple(ReleaseArtifactPlan(**item) for item in raw_artifacts),
            )
            self._validate_plan(plan)
            return plan
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
            ProjectError,
        ):
            return None

    def export_certificate_request(
        self,
        plan: ReleaseForgePlan,
        destination: Path,
    ) -> Path:
        self._validate_current_plan(plan)
        target = destination.expanduser()
        if target.exists() and target.is_dir():
            target = target / self.CERTIFICATE_REQUEST_NAME
        parent = target.parent.resolve(strict=True)
        if parent.is_relative_to(self.store.workspace.resolve()):
            raise ProjectError(
                "Certificate signing requests must be exported outside the workspace"
            )
        if target.exists() or target.is_symlink():
            raise ProjectError("The certificate signing request export already exists")
        payload = self._certificate_payload_from_plan(plan)
        atomic_write_json(
            target,
            {
                "format": "romverse.release-certificate-request",
                "schema_version": 1,
                "signature_domain_base64": base64.b64encode(self.CERTIFICATE_DOMAIN).decode(
                    "ascii"
                ),
                "certificate_payload": payload,
                "certificate_payload_digest": plan.certificate_payload_digest,
                "private_key_included": False,
            },
            boundary=parent,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )
        return target

    def import_certificate_signature(
        self,
        plan: ReleaseForgePlan,
        envelope_path: Path,
        public_key_path: Path,
        expected_key_id: str,
    ) -> ReleaseCertificateSignature:
        self._validate_current_plan(plan)
        key_id = self._identifier(expected_key_id, "release key ID", 96)
        envelope = read_json_object(
            envelope_path,
            boundary=envelope_path.expanduser().resolve(strict=True).parent,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )
        if (
            set(envelope)
            != {
                "format",
                "schema_version",
                "release_id",
                "key_id",
                "certificate_payload_digest",
                "signature_base64",
            }
            or envelope.get("format") != self.SIGNATURE_FORMAT
        ):
            raise ProjectError("Release certificate signature envelope is invalid")
        if (
            envelope.get("schema_version") != 1
            or envelope.get("release_id") != plan.release_id
            or envelope.get("key_id") != key_id
            or envelope.get("certificate_payload_digest") != plan.certificate_payload_digest
        ):
            raise ProjectError("Release certificate signature does not match this exact plan")
        public_key, public_raw, public_digest = self._public_key(public_key_path)
        try:
            signature = base64.b64decode(
                str(envelope["signature_base64"]),
                validate=True,
            )
            public_key.verify(
                signature,
                self.CERTIFICATE_DOMAIN + _canonical(self._certificate_payload_from_plan(plan)),
            )
        except (InvalidSignature, ValueError, binascii.Error) as exc:
            raise ProjectError("Release certificate signature verification failed") from exc
        payload: dict[str, object] = {
            "schema_version": 1,
            "project_id": plan.project_id,
            "release_id": plan.release_id,
            "imported_at": datetime.now(UTC).isoformat(),
            "key_id": key_id,
            "public_key_sha256": public_digest,
            "public_key_base64": base64.b64encode(public_raw).decode("ascii"),
            "certificate_payload_digest": plan.certificate_payload_digest,
            "signature_base64": str(envelope["signature_base64"]),
            "verified": True,
            "private_key_stored": False,
        }
        receipt = ReleaseCertificateSignature(
            **payload,
            receipt_digest=_digest(payload),
        )
        atomic_write_json(
            self.store.projects_root / plan.project_id / self.SIGNATURE_NAME,
            {"format": self.SIGNATURE_FORMAT, **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )
        return receipt

    def load_certificate_signature(
        self,
        plan: ReleaseForgePlan,
    ) -> ReleaseCertificateSignature | None:
        try:
            data = read_json_object(
                self.store.projects_root / plan.project_id / self.SIGNATURE_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECORD_BYTES,
            )
            if (
                set(data)
                != {
                    "format",
                    *(field.name for field in fields(ReleaseCertificateSignature)),
                }
                or data.pop("format") != self.SIGNATURE_FORMAT
            ):
                return None
            receipt = ReleaseCertificateSignature(**data)
            payload = asdict(receipt)
            digest = payload.pop("receipt_digest")
            if (
                receipt.schema_version != 1
                or receipt.project_id != plan.project_id
                or receipt.release_id != plan.release_id
                or receipt.certificate_payload_digest != plan.certificate_payload_digest
                or not receipt.verified
                or receipt.private_key_stored
                or not _sha256_value(receipt.public_key_sha256)
                or digest != _digest(payload)
            ):
                return None
            public_raw = base64.b64decode(receipt.public_key_base64, validate=True)
            if (
                len(public_raw) != 32
                or hashlib.sha256(public_raw).hexdigest() != receipt.public_key_sha256
            ):
                return None
            Ed25519PublicKey.from_public_bytes(public_raw).verify(
                base64.b64decode(receipt.signature_base64, validate=True),
                self.CERTIFICATE_DOMAIN + _canonical(self._certificate_payload_from_plan(plan)),
            )
            return receipt
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
            InvalidSignature,
            binascii.Error,
        ):
            return None

    def create_bundle(self, plan: ReleaseForgePlan) -> ReleaseBundleReceipt:
        self._validate_current_plan(plan)
        signature = self.load_certificate_signature(plan)
        if plan.public_certificate_required and signature is None:
            raise ProjectError(
                "Public release requires a verified externally signed release certificate"
            )
        artifacts = tuple((item, self._workspace_file(item.source_path)) for item in plan.artifacts)
        total = 0
        for item, path in artifacts:
            actual, size = _hash_file(path)
            if actual != item.sha256 or size != item.size_bytes:
                raise ProjectError(f"Release artifact changed after planning: {item.name}")
            total += size
        if total > self.MAX_ARCHIVE_BYTES:
            raise ProjectError("Release artifacts exceed the 256 GiB package limit")
        free = shutil.disk_usage(self.store.workspace).free
        if free < total + 512 * 1024 * 1024:
            raise ProjectError("Release Forge needs more free workspace storage")
        root = self._release_root(plan.project_id)
        output = root / f"{plan.release_id}.romverse.zip"
        if output.exists() or output.is_symlink():
            raise ProjectError("This exact release bundle already exists")
        temporary = output.with_name(f".{output.name}.{uuid4().hex}.part")
        certificate = {
            **self._certificate_payload_from_plan(plan),
            "certificate_payload_digest": plan.certificate_payload_digest,
            "signature": (
                {
                    "verified": True,
                    "key_id": signature.key_id,
                    "public_key_sha256": signature.public_key_sha256,
                    "public_key_base64": signature.public_key_base64,
                    "signature_base64": signature.signature_base64,
                    "signature_receipt_digest": signature.receipt_digest,
                }
                if signature is not None
                else {
                    "verified": False,
                    "key_id": "",
                    "public_key_sha256": "",
                    "public_key_base64": "",
                    "signature_base64": "",
                    "signature_receipt_digest": "",
                }
            ),
            "private_key_included": False,
            "publishing_authority": "none",
        }
        manifest = {
            "format": "romverse.release-bundle",
            "schema_version": 1,
            "release_id": plan.release_id,
            "project_id": plan.project_id,
            "version": plan.version,
            "tier": plan.tier.value,
            "package_kind": plan.package_kind.value,
            "plan_digest": plan.plan_digest,
            "base_release_digest": plan.base_release_digest,
            "artifacts": [
                {
                    "member": f"artifacts/{item.name}",
                    "name": item.name,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                    "signed": item.signed,
                    "source_receipt": item.source_receipt,
                }
                for item in plan.artifacts
            ],
            "unchanged_artifacts": [
                {"name": name, "sha256": digest} for name, digest in plan.unchanged_artifacts
            ],
            "evidence": {
                "source_sha256": plan.source_sha256,
                "device_pack_sha256": plan.device_pack_sha256,
                "build_receipt_digest": plan.build_receipt_digest,
                "simulation_digest": plan.simulation_digest,
                "simulation_mission_digest": plan.simulation_mission_digest,
                "signing_receipt_digest": plan.signing_receipt_digest,
                "security_scan_digest": plan.security_scan_digest,
                "certificate_payload_digest": plan.certificate_payload_digest,
            },
            "safety": {
                "published": False,
                "phone_changed": False,
                "publishing_authority": "none",
                "private_key_included": False,
            },
        }
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "w+b") as stream:
                with zipfile.ZipFile(stream, "w", allowZip64=True) as archive:
                    self._write_bytes(
                        archive,
                        self.MANIFEST_MEMBER,
                        _pretty_json(manifest),
                    )
                    self._write_bytes(
                        archive,
                        self.PLAN_MEMBER,
                        _pretty_json({"format": self.PLAN_FORMAT, **asdict(plan)}),
                    )
                    self._write_bytes(
                        archive,
                        self.CERTIFICATE_MEMBER,
                        _pretty_json(certificate),
                    )
                    self._write_bytes(
                        archive,
                        self.CHECKSUM_MEMBER,
                        (
                            "".join(
                                f"{item.sha256}  artifacts/{item.name}\n" for item in plan.artifacts
                            )
                        ).encode("utf-8"),
                    )
                    self._write_bytes(
                        archive,
                        self.CHANGELOG_MEMBER,
                        (
                            f"ROMVERSE {plan.version}\n\n"
                            + "\n".join(f"- {item}" for item in plan.changelog)
                            + "\n"
                        ).encode("utf-8"),
                    )
                    self._write_bytes(
                        archive,
                        self.INSTALL_MEMBER,
                        (
                            "ROMVERSE INSTALLATION GUIDE\n\n"
                            + "\n".join(
                                f"{index}. {item}"
                                for index, item in enumerate(plan.installation_steps, 1)
                            )
                            + "\n"
                        ).encode("utf-8"),
                    )
                    for item, path in artifacts:
                        self._write_file(
                            archive,
                            f"artifacts/{item.name}",
                            path,
                        )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, output)
            output.chmod(0o600)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        archive_sha, archive_size = _hash_file(output)
        receipt_payload: dict[str, object] = {
            "schema_version": 1,
            "release_id": plan.release_id,
            "project_id": plan.project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "version": plan.version,
            "tier": plan.tier,
            "package_kind": plan.package_kind,
            "plan_digest": plan.plan_digest,
            "certificate_payload_digest": plan.certificate_payload_digest,
            "certificate_signature_digest": (signature.receipt_digest if signature else ""),
            "archive_path": output.relative_to(self.store.workspace).as_posix(),
            "archive_sha256": archive_sha,
            "archive_size_bytes": archive_size,
            "artifact_count": len(artifacts),
            "artifact_bytes": total,
            "signed_certificate": signature is not None,
            "published": False,
            "phone_changed": False,
        }
        receipt = ReleaseBundleReceipt(
            **receipt_payload,
            receipt_digest=_digest(receipt_payload),
        )
        receipt_path = self.store.projects_root / plan.project_id / self.RECEIPT_NAME
        try:
            atomic_write_json(
                receipt_path,
                {"format": self.RECEIPT_FORMAT, **asdict(receipt)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECORD_BYTES,
            )
        except Exception:
            output.unlink(missing_ok=True)
            raise
        verification = self.verify_bundle(receipt)
        if verification is not None:
            output.unlink(missing_ok=True)
            receipt_path.unlink(missing_ok=True)
            raise ProjectError(verification)
        return receipt

    def load_bundle_receipt(self, project_id: str) -> ReleaseBundleReceipt | None:
        try:
            data = read_json_object(
                self.store.projects_root / project_id / self.RECEIPT_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECORD_BYTES,
            )
            if (
                set(data)
                != {
                    "format",
                    *(field.name for field in fields(ReleaseBundleReceipt)),
                }
                or data.pop("format") != self.RECEIPT_FORMAT
            ):
                return None
            data["tier"] = ReleaseTier(data["tier"])
            data["package_kind"] = ReleasePackageKind(data["package_kind"])
            receipt = ReleaseBundleReceipt(**data)
            payload = asdict(receipt)
            digest = payload.pop("receipt_digest")
            if (
                receipt.schema_version != 1
                or receipt.project_id != project_id
                or receipt.published
                or receipt.phone_changed
                or not _sha256_value(receipt.archive_sha256)
                or digest != _digest(payload)
            ):
                return None
            return receipt
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ):
            return None

    def verify_bundle(self, receipt: ReleaseBundleReceipt) -> str | None:
        """Return None only when the complete local release capsule verifies."""

        try:
            path = self._workspace_file(receipt.archive_path)
            archive_sha, archive_size = _hash_file(path)
            if archive_sha != receipt.archive_sha256 or archive_size != receipt.archive_size_bytes:
                return "Release archive hash or size changed"
            plan = self.load_plan(receipt.project_id)
            if plan is None or plan.plan_digest != receipt.plan_digest:
                return "Release plan is missing or stale"
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                expected = {
                    self.MANIFEST_MEMBER,
                    self.PLAN_MEMBER,
                    self.CERTIFICATE_MEMBER,
                    self.CHECKSUM_MEMBER,
                    self.CHANGELOG_MEMBER,
                    self.INSTALL_MEMBER,
                    *(f"artifacts/{item.name}" for item in plan.artifacts),
                }
                if set(names) != expected or len(names) != len(expected):
                    return "Release archive contains missing or unexpected members"
                metadata_members = {
                    self.MANIFEST_MEMBER,
                    self.PLAN_MEMBER,
                    self.CERTIFICATE_MEMBER,
                    self.CHECKSUM_MEMBER,
                    self.CHANGELOG_MEMBER,
                    self.INSTALL_MEMBER,
                }
                for name in names:
                    info = archive.getinfo(name)
                    relative = PurePosixPath(name)
                    if (
                        relative.is_absolute()
                        or ".." in relative.parts
                        or info.is_dir()
                        or stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK
                    ):
                        return f"Release archive member is unsafe: {name}"
                    if name in metadata_members and info.file_size > self.MAX_RECORD_BYTES:
                        return f"Release metadata member is too large: {name}"
                    if info.compress_type != zipfile.ZIP_STORED:
                        return f"Release member is not reproducibly stored: {name}"
                manifest = json.loads(archive.read(self.MANIFEST_MEMBER))
                archived_plan = json.loads(archive.read(self.PLAN_MEMBER))
                expected_archived_plan = json.loads(
                    _canonical({"format": self.PLAN_FORMAT, **asdict(plan)})
                )
                if archived_plan != expected_archived_plan:
                    return "Archived release plan does not match the exact current plan"
                expected_manifest_artifacts = [
                    {
                        "member": f"artifacts/{item.name}",
                        "name": item.name,
                        "size_bytes": item.size_bytes,
                        "sha256": item.sha256,
                        "signed": item.signed,
                        "source_receipt": item.source_receipt,
                    }
                    for item in plan.artifacts
                ]
                if (
                    manifest.get("format") != "romverse.release-bundle"
                    or manifest.get("release_id") != receipt.release_id
                    or manifest.get("plan_digest") != receipt.plan_digest
                    or manifest.get("safety")
                    != {
                        "published": False,
                        "phone_changed": False,
                        "publishing_authority": "none",
                        "private_key_included": False,
                    }
                    or manifest.get("artifacts") != expected_manifest_artifacts
                    or manifest.get("unchanged_artifacts")
                    != [
                        {"name": name, "sha256": digest}
                        for name, digest in plan.unchanged_artifacts
                    ]
                ):
                    return "Release manifest identity or safety boundary is invalid"
                for artifact in plan.artifacts:
                    digest = hashlib.sha256()
                    size = 0
                    with archive.open(f"artifacts/{artifact.name}") as stream:
                        while chunk := stream.read(self.CHUNK_SIZE):
                            digest.update(chunk)
                            size += len(chunk)
                    if digest.hexdigest() != artifact.sha256 or size != artifact.size_bytes:
                        return f"Release artifact failed verification: {artifact.name}"
                    info = archive.getinfo(f"artifacts/{artifact.name}")
                    if info.file_size != artifact.size_bytes:
                        return f"Release artifact length metadata is invalid: {artifact.name}"
                expected_checksums = "".join(
                    f"{item.sha256}  artifacts/{item.name}\n" for item in plan.artifacts
                ).encode("utf-8")
                if archive.read(self.CHECKSUM_MEMBER) != expected_checksums:
                    return "Release checksum ledger does not match the exact plan"
                certificate = json.loads(archive.read(self.CERTIFICATE_MEMBER))
                expected_certificate = self._certificate_payload_from_plan(plan)
                if (
                    certificate.get("certificate_payload_digest")
                    != receipt.certificate_payload_digest
                    or certificate.get("private_key_included") is not False
                    or certificate.get("publishing_authority") != "none"
                    or bool(certificate.get("signature", {}).get("verified"))
                    != receipt.signed_certificate
                    or any(
                        certificate.get(key) != value for key, value in expected_certificate.items()
                    )
                ):
                    return "Release certificate evidence is invalid"
                signature = certificate.get("signature", {})
                if receipt.signed_certificate:
                    public_raw = base64.b64decode(
                        str(signature.get("public_key_base64", "")),
                        validate=True,
                    )
                    if len(public_raw) != 32 or hashlib.sha256(
                        public_raw
                    ).hexdigest() != signature.get("public_key_sha256"):
                        return "Release certificate public key evidence is invalid"
                    Ed25519PublicKey.from_public_bytes(public_raw).verify(
                        base64.b64decode(
                            str(signature.get("signature_base64", "")),
                            validate=True,
                        ),
                        self.CERTIFICATE_DOMAIN
                        + _canonical(self._certificate_payload_from_plan(plan)),
                    )
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
            zipfile.BadZipFile,
            ProjectError,
            InvalidSignature,
            binascii.Error,
        ) as exc:
            return f"Release verification failed: {exc}"
        return None

    def export_bundle(
        self,
        receipt: ReleaseBundleReceipt,
        destination: Path,
    ) -> Path:
        error = self.verify_bundle(receipt)
        if error is not None:
            raise ProjectError(error)
        source = self._workspace_file(receipt.archive_path)
        folder = destination.expanduser().resolve(strict=True)
        if not folder.is_dir() or folder.is_relative_to(self.store.workspace.resolve()):
            raise ProjectError("Choose a real external export folder")
        output = folder / source.name
        if output.exists() or output.is_symlink():
            raise ProjectError("The release export already exists")
        temporary = output.with_name(f".{output.name}.{uuid4().hex}.part")
        try:
            with source.open("rb") as input_stream:
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                with os.fdopen(descriptor, "wb") as output_stream:
                    while chunk := input_stream.read(self.CHUNK_SIZE):
                        output_stream.write(chunk)
                    output_stream.flush()
                    os.fsync(output_stream.fileno())
            if _hash_file(temporary) != (
                receipt.archive_sha256,
                receipt.archive_size_bytes,
            ):
                raise ProjectError("Exported release failed byte verification")
            os.replace(temporary, output)
            output.chmod(0o600)
            return output
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def assemble_signed_super(self, project_id: str) -> SignedAssemblyReceipt:
        """Rebuild and prove a sparse super image from the current signed child image."""

        build = LocalDeviceBuildExecutor(
            self.store,
            self.registry,
            self.tool_statuses,
            SubprocessRunner(),
        ).load_receipt(project_id)
        signing = self._load_signing(project_id)
        plan = DeviceBuildContractService(
            self.store,
            self.registry,
            self.tool_statuses,
        ).load(project_id)
        if build is None or signing is None or plan is None:
            raise ProjectError(
                "Signed final assembly requires the current build plan, build receipt and offline signing receipt"
            )
        step = next(
            (item for item in plan.steps if item.step_id == "assemble-super"),
            None,
        )
        if step is None or len(step.outputs) != 1:
            raise ProjectError("The Device Pack has no exact signed super assembly plan")
        tools = self._assembly_tools()
        signed = {item.name: item for item in signing.artifacts}
        inputs: list[SignedAssemblyInput] = []
        command = [str(tools["LP Make"])]
        output_parent = self.store.working_root / project_id / "signed-assembly"
        ensure_private_directory(output_parent, boundary=self.store.workspace)
        output_root = output_parent / f"{signing.receipt_digest[:16]}-{uuid4().hex[:8]}"
        output_root.mkdir(mode=0o700)
        output = output_root / "super.img"
        try:
            for token in step.arguments:
                if token == step.outputs[0]:
                    command.append(str(output))
                    continue
                if "=" not in token:
                    command.append(token)
                    continue
                prefix, relative = token.split("=", 1)
                if not prefix.endswith("_a"):
                    command.append(token)
                    continue
                partition = prefix.removesuffix("_a")
                replacement = signed.get(Path(relative).name)
                source = self._workspace_file(
                    replacement.path if replacement is not None else relative
                )
                source_sha, source_size = _hash_file(source)
                if replacement is not None and (
                    source_sha != replacement.sha256 or source_size != replacement.size_bytes
                ):
                    raise ProjectError(f"Signed {replacement.name} changed before assembly")
                inputs.append(
                    SignedAssemblyInput(
                        partition,
                        source.relative_to(self.store.workspace).as_posix(),
                        source_size,
                        source_sha,
                        replacement is not None,
                    )
                )
                command.append(f"{prefix}={source}")
            if not inputs or len({item.partition for item in inputs}) != len(inputs):
                raise ProjectError("Signed assembly partition inputs are incomplete or ambiguous")
            super_capacity = next(
                (
                    int(token.split(":", 1)[1])
                    for token in step.arguments
                    if token.startswith("super:") and token.split(":", 1)[1].isdigit()
                ),
                0,
            )
            if super_capacity <= 0:
                raise ProjectError("Signed assembly plan has no valid super capacity")
            required_free = (
                super_capacity + sum(item.size_bytes for item in inputs) + 512 * 1024 * 1024
            )
            if shutil.disk_usage(self.store.workspace).free < required_free:
                raise ProjectError(
                    "Signed final assembly needs more free workspace storage for build and verification"
                )
            runner = SubprocessRunner()
            result = runner.run(
                tuple(command),
                timeout=4 * 60 * 60,
                cwd=self.store.workspace,
            )
            if not result.ok or not output.is_file() or output.is_symlink():
                raise ProjectError(self._command_failure("LP Make", result.stderr, result.stdout))
            raw = output_root / "super.raw.img"
            unpacked = output_root / "unpacked"
            unpacked.mkdir()
            verification_commands = (
                (str(tools["simg2img"]), str(output), str(raw)),
                (str(tools["LP Unpack"]), str(raw), str(unpacked)),
                (str(tools["LP Dump"]), str(raw)),
            )
            results = []
            for command_args in verification_commands:
                verified = runner.run(
                    command_args,
                    timeout=4 * 60 * 60,
                    cwd=self.store.workspace,
                )
                results.append(verified)
                if not verified.ok:
                    raise ProjectError(
                        self._command_failure(
                            Path(command_args[0]).name, verified.stderr, verified.stdout
                        )
                    )
            for item in inputs:
                actual = unpacked / f"{item.partition}_a.img"
                if not actual.is_file() or actual.is_symlink():
                    raise ProjectError(f"Signed super verification is missing {item.partition}_a")
                if _hash_file(actual) != (item.sha256, item.size_bytes):
                    raise ProjectError(
                        f"Signed super {item.partition}_a differs from its exact input"
                    )
            super_sha, super_size = _hash_file(output)
            payload: dict[str, object] = {
                "schema_version": 1,
                "project_id": project_id,
                "created_at": datetime.now(UTC).isoformat(),
                "build_receipt_digest": build.receipt_digest,
                "signing_receipt_digest": signing.receipt_digest,
                "inputs": [asdict(item) for item in inputs],
                "super_path": output.relative_to(self.store.workspace).as_posix(),
                "super_size_bytes": super_size,
                "super_sha256": super_sha,
                "lpdump_sha256": hashlib.sha256(results[-1].stdout.encode()).hexdigest(),
                "verified": True,
                "phone_changed": False,
            }
            receipt = SignedAssemblyReceipt(
                **{key: value for key, value in payload.items() if key != "inputs"},
                inputs=tuple(inputs),
                receipt_digest=_digest(payload),
            )
            atomic_write_json(
                self.store.projects_root / project_id / self.ASSEMBLY_NAME,
                {"format": self.ASSEMBLY_FORMAT, **asdict(receipt)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECORD_BYTES,
            )
            shutil.rmtree(unpacked, ignore_errors=True)
            raw.unlink(missing_ok=True)
            return receipt
        except Exception:
            shutil.rmtree(output_root, ignore_errors=True)
            raise

    def load_signed_assembly(
        self,
        project_id: str,
        *,
        build=None,
        signing: OfflineSigningReceipt | None = None,
    ) -> SignedAssemblyReceipt | None:
        try:
            data = read_json_object(
                self.store.projects_root / project_id / self.ASSEMBLY_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECORD_BYTES,
            )
            if data.pop("format") != self.ASSEMBLY_FORMAT:
                return None
            raw_inputs = data.pop("inputs")
            if (
                not isinstance(raw_inputs, list)
                or not 1 <= len(raw_inputs) <= self.MAX_ARTIFACTS
                or any(
                    not isinstance(item, dict)
                    or set(item) != {field.name for field in fields(SignedAssemblyInput)}
                    for item in raw_inputs
                )
            ):
                return None
            inputs = tuple(SignedAssemblyInput(**item) for item in raw_inputs)
            receipt = SignedAssemblyReceipt(**data, inputs=inputs)
            payload = asdict(receipt)
            digest = payload.pop("receipt_digest")
            if build is None:
                build = LocalDeviceBuildExecutor(
                    self.store,
                    self.registry,
                    self.tool_statuses,
                    SubprocessRunner(),
                ).load_receipt(project_id)
            if signing is None:
                signing = self._load_signing(project_id)
            if (
                receipt.schema_version != 1
                or receipt.project_id != project_id
                or build is None
                or signing is None
                or receipt.build_receipt_digest != build.receipt_digest
                or receipt.signing_receipt_digest != signing.receipt_digest
                or not receipt.verified
                or receipt.phone_changed
                or not _sha256_value(receipt.super_sha256)
                or not _sha256_value(receipt.lpdump_sha256)
                or len({item.partition for item in inputs}) != len(inputs)
                or any(not self._valid_assembly_input(item) for item in inputs)
                or digest != _digest(payload)
            ):
                return None
            if _hash_file(self._workspace_file(receipt.super_path)) != (
                receipt.super_sha256,
                receipt.super_size_bytes,
            ):
                return None
            for item in inputs:
                if _hash_file(self._workspace_file(item.source_path)) != (
                    item.sha256,
                    item.size_bytes,
                ):
                    return None
            return receipt
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
            ProjectError,
        ):
            return None

    def _assembly_tools(self) -> dict[str, Path]:
        available = {
            item.name: Path(item.path).resolve()
            for item in self.tool_statuses
            if item.available and item.path
        }
        required = {"LP Make", "LP Unpack", "LP Dump", "simg2img"}
        if missing := tuple(sorted(required - available.keys())):
            raise ProjectError("Signed final assembly tools are missing: " + ", ".join(missing))
        if any(not available[name].is_file() for name in required):
            raise ProjectError("A signed final assembly tool is no longer available")
        return available

    @staticmethod
    def _valid_assembly_input(item: SignedAssemblyInput) -> bool:
        return bool(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,119}", item.partition)
            and _safe_relative(item.source_path)
            and type(item.size_bytes) is int
            and item.size_bytes > 0
            and _sha256_value(item.sha256)
            and isinstance(item.signed, bool)
        )

    @staticmethod
    def _command_failure(tool: str, stderr: str, stdout: str) -> str:
        lines = (stderr or stdout).strip().splitlines()
        return f"{tool} failed" + (f": {lines[-1][:240]}" if lines else "")

    def _load_signing(self, project_id: str) -> OfflineSigningReceipt | None:
        avbtool = next(
            (
                Path(item.path)
                for item in self.tool_statuses
                if item.name == "AVBTool" and item.available and item.path
            ),
            None,
        )
        if avbtool is None or not avbtool.is_file():
            return None
        return OfflineSigningCeremonyService(
            self.store,
            self.registry,
            self.tool_statuses,
            avbtool,
            SubprocessRunner(),
        ).load_receipt(project_id)

    def _security_scan(
        self,
        project_id: str,
        outputs: tuple[BuildOutputReceipt, ...],
    ) -> ReleaseSecurityScan:
        findings: list[ReleaseSecurityFinding] = []
        scanned_files = 0
        scanned_bytes = 0
        scan_complete = True
        seen: set[Path] = set()

        def inspect(path: Path, label: str) -> None:
            nonlocal scan_complete, scanned_bytes, scanned_files
            if not scan_complete:
                return
            if scanned_files >= self.MAX_SCAN_FILES:
                scan_complete = False
                return
            if path.is_symlink() or not path.is_file():
                findings.append(
                    ReleaseSecurityFinding(
                        f"unsafe-path-{len(findings) + 1}",
                        ReleaseGateState.BLOCKED,
                        label,
                        "A release input is missing, linked or not a regular file.",
                    )
                )
                return
            resolved = path.resolve()
            if resolved in seen:
                return
            seen.add(resolved)
            size = path.stat().st_size
            scanned_files += 1
            if self.SECRET_NAMES.search(label):
                findings.append(
                    ReleaseSecurityFinding(
                        f"secret-name-{len(findings) + 1}",
                        ReleaseGateState.BLOCKED,
                        label,
                        "A credential- or secret-like filename is present in release inputs.",
                    )
                )
            if size > self.MAX_TEXT_FILE_BYTES:
                return
            if scanned_bytes + size > self.MAX_SCAN_BYTES:
                scan_complete = False
                return
            sample = path.read_bytes()
            scanned_bytes += len(sample)
            if any(pattern.search(sample) for pattern in self.SECRET_PATTERNS):
                findings.append(
                    ReleaseSecurityFinding(
                        f"secret-content-{len(findings) + 1}",
                        ReleaseGateState.BLOCKED,
                        label,
                        "A private-key or credential token pattern is present in release inputs.",
                    )
                )

        for output in outputs:
            try:
                inspect(self._workspace_file(output.path), f"artifact/{output.name}")
            except (OSError, ProjectError):
                findings.append(
                    ReleaseSecurityFinding(
                        f"unsafe-artifact-{len(findings) + 1}",
                        ReleaseGateState.BLOCKED,
                        output.name,
                        "A declared release artifact path could not be verified.",
                    )
                )
        tree = self.store.working_root / project_id / "tree"
        if tree.is_symlink():
            findings.append(
                ReleaseSecurityFinding(
                    "unsafe-working-tree",
                    ReleaseGateState.BLOCKED,
                    "working tree",
                    "The ROM working tree is a symbolic link.",
                )
            )
        elif tree.is_dir():
            for current, directories, files in os.walk(tree, followlinks=False):
                root = Path(current)
                linked = tuple(name for name in directories if (root / name).is_symlink())
                directories[:] = sorted(name for name in directories if name not in linked)
                for name in linked:
                    findings.append(
                        ReleaseSecurityFinding(
                            f"unsafe-tree-link-{len(findings) + 1}",
                            ReleaseGateState.BLOCKED,
                            (root / name).relative_to(tree).as_posix(),
                            "A linked directory is present in the release working tree.",
                        )
                    )
                for name in sorted(files):
                    path = root / name
                    inspect(path, path.relative_to(tree).as_posix())
                    if not scan_complete:
                        break
                if not scan_complete:
                    break
        if not scan_complete:
            findings.append(
                ReleaseSecurityFinding(
                    "scan-boundary-exceeded",
                    ReleaseGateState.BLOCKED,
                    "project evidence",
                    "The bounded security screen reached its file or byte limit before completing.",
                )
            )
        unexpected = tuple(
            item.name
            for item in outputs
            if Path(item.name).suffix.casefold() not in {".img", ".zip", ".bin", ".dat", ".br"}
        )
        if unexpected:
            findings.append(
                ReleaseSecurityFinding(
                    "unexpected-executable-surface",
                    ReleaseGateState.BLOCKED,
                    ", ".join(unexpected),
                    "Release outputs contain a file type outside the bounded Android artifact set.",
                )
            )
        secret_free = not any(
            item.state is ReleaseGateState.BLOCKED
            and (item.finding_id.startswith("secret-") or item.finding_id.startswith("unsafe-"))
            for item in findings
        )
        malware_screen = not unexpected and scan_complete
        opaque = sum(Path(item.name).suffix.casefold() in {".img", ".bin"} for item in outputs)
        payload = {
            "project_id": project_id,
            "scanned_files": scanned_files,
            "scanned_bytes": scanned_bytes,
            "opaque_artifacts": opaque,
            "secret_scan_passed": secret_free,
            "malware_screen_passed": malware_screen,
            "findings": [asdict(item) for item in findings],
            "artifacts": [
                {
                    "name": item.name,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                }
                for item in outputs
            ],
            "limitations": (
                "The built-in screen detects exposed secrets, unsafe names and unexpected executable surfaces; it is not an antivirus signature database.",
                "Opaque Android partition images require trusted filesystem extraction or an external scanner for content-level malware claims.",
            ),
        }
        return ReleaseSecurityScan(
            scanned_files,
            scanned_bytes,
            opaque,
            secret_free,
            malware_screen,
            tuple(findings),
            tuple(payload["limitations"]),
            _digest(payload),
        )

    def _package_kind_gate(
        self,
        project_id: str,
        package_kind: ReleasePackageKind,
        outputs: tuple[BuildOutputReceipt, ...],
        base_plan: ReleaseForgePlan | None,
    ) -> tuple[bool, str, str]:
        names = {item.name for item in outputs}
        if package_kind is ReleasePackageKind.FULL:
            return (
                bool(outputs),
                f"{len(outputs)} current build artifact(s) are available.",
                "Produce a verified local build.",
            )
        if package_kind is ReleasePackageKind.INCREMENTAL:
            base_receipt = self.load_bundle_receipt(project_id)
            ready = bool(
                base_plan is not None
                and base_plan.package_kind is ReleasePackageKind.FULL
                and base_plan.artifacts
                and base_receipt is not None
                and base_receipt.plan_digest == base_plan.plan_digest
                and self.verify_bundle(base_receipt) is None
            )
            return (
                ready,
                "A complete, locally re-verified full release capsule is selected as the base."
                if ready
                else "Incremental packaging needs the current verified full release capsule as its base.",
                "Verify or rebuild the exact full base capsule before preparing its incremental successor.",
            )
        recovery_names = names & {
            "recovery.img",
            "vendor_boot.img",
            "init_boot.img",
            "boot.img",
        }
        return (
            bool(recovery_names),
            "Recovery-capable artifact(s): " + ", ".join(sorted(recovery_names))
            if recovery_names
            else "No reviewed recovery-capable image exists in this build.",
            "Build and verify the Device Pack's declared recovery image.",
        )

    def _artifact_plan(
        self,
        outputs: tuple[BuildOutputReceipt, ...],
        signing: OfflineSigningReceipt | None,
        assembly: SignedAssemblyReceipt | None,
    ) -> tuple[ReleaseArtifactPlan, ...]:
        signed = {item.name: item for item in signing.artifacts} if signing else {}
        results = []
        for output in outputs:
            replacement: SignedArtifactEvidence | None = signed.get(output.name)
            assembled = assembly if output.name == "super.img" else None
            item = assembled or replacement or output
            results.append(
                ReleaseArtifactPlan(
                    output.name,
                    assembled.super_path if assembled is not None else item.path,
                    assembled.super_size_bytes if assembled is not None else item.size_bytes,
                    assembled.super_sha256 if assembled is not None else item.sha256,
                    replacement is not None or assembled is not None,
                    assembled.receipt_digest
                    if assembled is not None
                    else signing.receipt_digest
                    if replacement is not None and signing is not None
                    else "local-build",
                )
            )
        return tuple(sorted(results, key=lambda item: item.name.casefold()))

    def _validate_current_plan(self, plan: ReleaseForgePlan) -> None:
        self._validate_plan(plan)
        current = self.load_plan(plan.project_id)
        if current is None or current.plan_digest != plan.plan_digest:
            raise ProjectError("Release Forge plan is missing, changed or superseded")
        build = LocalDeviceBuildExecutor(
            self.store,
            self.registry,
            self.tool_statuses,
            SubprocessRunner(),
        ).load_receipt(plan.project_id)
        simulator = RomSimulationService(
            self.store,
            self.registry,
            self.tool_statuses,
        )
        simulation = simulator.load(plan.project_id)
        mission = simulator.load_mission(plan.project_id)
        signing = self._load_signing(plan.project_id)
        if (
            build is None
            or build.receipt_digest != plan.build_receipt_digest
            or simulation is None
            or simulation.receipt_digest != plan.simulation_digest
            or mission is None
            or mission.mission_digest != plan.simulation_mission_digest
            or (signing.receipt_digest if signing is not None else "")
            != plan.signing_receipt_digest
            or self._security_scan(plan.project_id, tuple(build.outputs)).scan_digest
            != plan.security_scan_digest
        ):
            raise ProjectError("Release Forge evidence changed; prepare a fresh exact plan")
        for artifact in plan.artifacts:
            path = self._workspace_file(artifact.source_path)
            if _hash_file(path) != (artifact.sha256, artifact.size_bytes):
                raise ProjectError(f"Release artifact changed: {artifact.name}")

    def _validate_plan(self, plan: ReleaseForgePlan) -> None:
        payload = asdict(plan)
        plan_digest = payload.pop("plan_digest", "")
        certificate_digest = payload.get("certificate_payload_digest", "")
        project = self.store.get(plan.project_id)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id),
            None,
        )
        expected_certificate = self._certificate_payload_from_plan(plan)
        if (
            plan.schema_version != self.SCHEMA_VERSION
            or not self.VERSION.fullmatch(plan.version)
            or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{10,159}", plan.release_id)
            or project.original is None
            or pack is None
            or plan.device_pack_id != pack.pack_id
            or plan.device_pack_sha256 != pack.sha256
            or plan.source_sha256 != project.original.sha256
            or len(plan.artifacts) > self.MAX_ARTIFACTS
            or not plan.artifacts
            or len({item.name.casefold() for item in plan.artifacts}) != len(plan.artifacts)
            or any(not self._valid_artifact(item) for item in plan.artifacts)
            or not plan.reproducible
            or plan.phone_changed
            or plan.publishing_authority != "none"
            or plan.public_certificate_required != (plan.tier is ReleaseTier.PUBLIC)
            or (
                plan.tier in {ReleaseTier.TESTING, ReleaseTier.PUBLIC} and not plan.signed_artifacts
            )
            or plan_digest != _digest(payload)
            or certificate_digest != _digest(expected_certificate)
        ):
            raise ProjectError("Release Forge plan failed integrity validation")

    @staticmethod
    def _valid_artifact(item: ReleaseArtifactPlan) -> bool:
        return bool(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,159}", item.name)
            and _safe_relative(item.source_path)
            and type(item.size_bytes) is int
            and 0 < item.size_bytes <= ReleaseForgeService.MAX_ARCHIVE_BYTES
            and _sha256_value(item.sha256)
            and isinstance(item.signed, bool)
            and 0 < len(item.source_receipt) <= 128
        )

    def _workspace_file(self, relative: str) -> Path:
        if not _safe_relative(relative):
            raise ProjectError("Release artifact path is invalid")
        unresolved = self.store.workspace / relative
        current = self.store.workspace
        for part in Path(relative).parts:
            current /= part
            if current.is_symlink():
                raise ProjectError("Release artifacts cannot use symbolic links")
        path = unresolved.resolve(strict=True)
        if (
            not path.is_file()
            or path.is_symlink()
            or not path.is_relative_to(self.store.workspace.resolve())
        ):
            raise ProjectError("Release artifact escaped the ROMVERSE workspace")
        return path

    def _release_root(self, project_id: str) -> Path:
        root = self.store.workspace / "builds" / project_id / "release-forge"
        ensure_private_directory(root, boundary=self.store.workspace)
        return root

    def _save_plan(self, plan: ReleaseForgePlan) -> None:
        self._validate_plan(plan)
        atomic_write_json(
            self.store.projects_root / plan.project_id / self.PLAN_NAME,
            {"format": self.PLAN_FORMAT, **asdict(plan)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_RECORD_BYTES,
        )

    @classmethod
    def _certificate_payload_from_plan(
        cls,
        plan: ReleaseForgePlan,
    ) -> dict[str, object]:
        return cls._certificate_payload(
            plan.release_id,
            plan.project_id,
            plan.version,
            plan.tier,
            plan.package_kind,
            plan.device_pack_id,
            plan.device_pack_sha256,
            plan.source_sha256,
            plan.build_receipt_digest,
            plan.simulation_digest,
            plan.simulation_mission_digest,
            plan.signing_receipt_digest,
            plan.security_scan_digest,
            plan.artifacts,
        )

    @staticmethod
    def _certificate_payload(
        release_id: str,
        project_id: str,
        version: str,
        tier: ReleaseTier,
        package_kind: ReleasePackageKind,
        device_pack_id: str,
        device_pack_sha256: str,
        source_sha256: str,
        build_receipt_digest: str,
        simulation_digest: str,
        simulation_mission_digest: str,
        signing_receipt_digest: str,
        security_scan_digest: str,
        artifacts: tuple[ReleaseArtifactPlan, ...],
    ) -> dict[str, object]:
        return {
            "format": "romverse.release-certificate-payload",
            "schema_version": 1,
            "release_id": release_id,
            "project_id": project_id,
            "version": version,
            "tier": tier.value,
            "package_kind": package_kind.value,
            "device_pack_id": device_pack_id,
            "device_pack_sha256": device_pack_sha256,
            "source_sha256": source_sha256,
            "build_receipt_digest": build_receipt_digest,
            "simulation_digest": simulation_digest,
            "simulation_mission_digest": simulation_mission_digest,
            "signing_receipt_digest": signing_receipt_digest,
            "security_scan_digest": security_scan_digest,
            "artifacts": [
                {
                    "name": item.name,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                    "signed": item.signed,
                }
                for item in artifacts
            ],
            "evidence_claim": "Build and packaging evidence only; physical test claims require First Light receipts.",
            "phone_changed": False,
            "publishing_authority": "none",
        }

    @staticmethod
    def _installation_steps(
        tier: ReleaseTier,
        package_kind: ReleasePackageKind,
    ) -> tuple[str, ...]:
        return (
            f"Confirm this {tier.value} {package_kind.value} package matches the exact Device DNA.",
            "Verify ROMVERSE-RELEASE-MANIFEST.json and SHA256SUMS before use.",
            "Read the known limitations and confirm a current external backup and stock recovery route.",
            "Open the package through ROMVERSE Simulation Lab and Guardian; do not run image commands manually from this archive.",
            "Treat installation as unverified until First Light proves boot and subsystem results on physical hardware.",
        )

    @staticmethod
    def _gate(
        gate_id: str,
        label: str,
        passed: bool,
        evidence: str,
        resolution: str,
    ) -> ReleaseGate:
        return ReleaseGate(
            gate_id,
            label,
            ReleaseGateState.PASS if passed else ReleaseGateState.BLOCKED,
            evidence,
            resolution,
        )

    def _first_light_passed(self, project_id: str) -> bool:
        from romverse.rom.first_light import FirstLightOverall, FirstLightService

        report = FirstLightService(self.store, self.registry).load(project_id)
        return bool(
            report is not None
            and report.overall is FirstLightOverall.VERIFIED
            and report.public_release_ready
        )

    @staticmethod
    def _text(value: str, label: str, maximum: int) -> str:
        clean = str(value).strip()
        if not clean or len(clean) > maximum or "\x00" in clean or "\r" in clean or "\n" in clean:
            raise ProjectError(f"{label.title()} is invalid")
        return clean

    @staticmethod
    def _identifier(value: str, label: str, maximum: int) -> str:
        clean = str(value).strip()
        if not 1 <= len(clean) <= maximum or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*",
            clean,
        ):
            raise ProjectError(f"{label.title()} is invalid")
        return clean

    @staticmethod
    def _public_key(path: Path) -> tuple[Ed25519PublicKey, bytes, str]:
        unresolved = path.expanduser()
        if unresolved.is_symlink():
            raise ProjectError("Release certificate public key cannot be a symbolic link")
        resolved = unresolved.resolve(strict=True)
        if not resolved.is_file() or resolved.stat().st_size > 64 * 1024:
            raise ProjectError("Release certificate public key is invalid")
        raw = resolved.read_bytes()
        try:
            key = serialization.load_pem_public_key(raw)
        except (TypeError, ValueError) as exc:
            raise ProjectError("Release certificate public key is not valid PEM") from exc
        if not isinstance(key, Ed25519PublicKey):
            raise ProjectError("Release certificate public key must be Ed25519")
        public_raw = key.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return key, public_raw, hashlib.sha256(public_raw).hexdigest()

    @classmethod
    def _write_bytes(
        cls,
        archive: zipfile.ZipFile,
        member: str,
        payload: bytes,
    ) -> None:
        info = cls._zip_info(member)
        archive.writestr(info, payload)

    @classmethod
    def _write_file(
        cls,
        archive: zipfile.ZipFile,
        member: str,
        source: Path,
    ) -> None:
        info = cls._zip_info(member)
        with archive.open(info, "w", force_zip64=True) as output, source.open("rb") as input_stream:
            while chunk := input_stream.read(cls.CHUNK_SIZE):
                output.write(chunk)

    @classmethod
    def _zip_info(cls, member: str) -> zipfile.ZipInfo:
        relative = PurePosixPath(member)
        if relative.is_absolute() or ".." in relative.parts or "\\" in member or not member:
            raise ProjectError("Release archive member path is unsafe")
        info = zipfile.ZipInfo(member, cls.ZIP_TIMESTAMP)
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        info.compress_type = zipfile.ZIP_STORED
        return info


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    ).encode("ascii")


def _json_default(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _pretty_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(ReleaseForgeService.CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _sha256_value(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 4096 or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and "." not in path.parts
        and "\\" not in value
    )
