from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.guardian.approval import ApprovalStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import GuardianDeniedError, OperationClass, OperationRequest
from romverse.guardian.planning import (
    CheckStatus,
    GuardianPreflight,
    OperationManifest,
    PlannedStep,
    Precondition,
    PreflightAssessment,
    PreflightStatus,
)
from romverse.infrastructure.process import CommandResult, CommandRunner, SubprocessRunner
from romverse.rom.models import ProjectError

MAX_APK_ENTRIES = 50_000
MAX_DECLARED_EXPANDED_BYTES = 8 * 1024**3
APK_INSTALL_FAILURE_CODES = frozenset(
    {
        "INSTALL_FAILED_INSUFFICIENT_STORAGE",
        "INSTALL_FAILED_INVALID_APK",
        "INSTALL_FAILED_MISSING_SPLIT",
        "INSTALL_FAILED_NO_MATCHING_ABIS",
        "INSTALL_FAILED_TEST_ONLY",
        "INSTALL_FAILED_UPDATE_INCOMPATIBLE",
        "INSTALL_FAILED_USER_RESTRICTED",
        "INSTALL_FAILED_VERSION_DOWNGRADE",
    }
)
_APK_INSTALL_FAILURE_ALIASES = {
    "CPU_ABI_INCOMPATIBLE": "INSTALL_FAILED_NO_MATCHING_ABIS",
    "INSTALL_PARSE_FAILED_NOT_APK": "INSTALL_FAILED_INVALID_APK",
}


@dataclass(frozen=True, slots=True)
class ApkInstallRequest:
    apk_path: str
    device_serial: str
    allow_downgrade: bool = False
    execution_locked: bool = True
    battery_percent: int | None = None
    device_free_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class ApkInspection:
    path: str
    file_size: int
    sha256: str
    entry_count: int
    dex_count: int
    has_manifest: bool
    has_legacy_signature: bool
    valid: bool
    findings: tuple[str, ...]
    package_name: str = ""
    app_label: str = ""
    version_name: str = ""
    version_code: str = ""
    min_sdk: str = ""
    target_sdk: str = ""
    native_abis: tuple[str, ...] = ()
    permission_count: int | None = None
    signature_verified: bool | None = None
    signer_sha256: str = ""
    signer_subject: str = ""


@dataclass(frozen=True, slots=True)
class ApkInstallPlan:
    request: ApkInstallRequest
    target_key: str
    inspection: ApkInspection
    manifest: OperationManifest
    assessment: PreflightAssessment

    @property
    def digest(self) -> str:
        return self.assessment.manifest_digest

    @property
    def safety_ready(self) -> bool:
        return all(
            not check.required or check.status is CheckStatus.PASS
            for check in self.manifest.preconditions
        )


def extract_apk_install_failure_code(output: str) -> str:
    """Return one recognized, privacy-safe Package Manager failure identity."""

    bounded = output.replace("\x00", " ")[:4_000].upper()
    matches = re.findall(
        r"\b(?:INSTALL_(?:FAILED|PARSE_FAILED)_[A-Z0-9_]+|CPU_ABI_INCOMPATIBLE)\b",
        bounded,
    )
    recognized = {
        _APK_INSTALL_FAILURE_ALIASES.get(item, item)
        for item in matches
        if _APK_INSTALL_FAILURE_ALIASES.get(item, item) in APK_INSTALL_FAILURE_CODES
    }
    return next(iter(recognized)) if len(recognized) == 1 else ""


def build_install_arguments(request: ApkInstallRequest) -> tuple[str, ...]:
    """Return the exact bounded ADB argument vector for a guarded install."""
    validate_install_request(request)
    return ("-s", request.device_serial, "install", str(Path(request.apk_path).expanduser()))


def validate_install_request(request: ApkInstallRequest) -> None:
    path = Path(request.apk_path).expanduser()
    if path.suffix.casefold() != ".apk" or not path.is_file():
        raise ProjectError("APK install requires an existing .apk file")
    if not request.device_serial:
        raise ProjectError("APK install requires an authorized device")
    if request.allow_downgrade:
        raise ProjectError("APK downgrades remain locked pending Guardian policy")


def inspect_apk(
    path: Path,
    *,
    aapt_executable: Path | None = None,
    apksigner_executable: Path | None = None,
    runner: CommandRunner | None = None,
    progress: Callable[[int], None] | None = None,
) -> ApkInspection:
    """Inspect bounded APK container metadata without extracting or executing content."""
    last_progress = -1

    def report(value: int) -> None:
        nonlocal last_progress
        bounded = max(0, min(100, int(value)))
        if progress is not None and bounded > last_progress:
            progress(bounded)
        last_progress = max(last_progress, bounded)

    path = path.expanduser().resolve()
    if path.suffix.casefold() != ".apk" or not path.is_file():
        raise ProjectError("APK inspection requires an existing .apk file")
    report(0)
    digest = _sha256(
        path,
        lambda done, total: report(round(done * 70 / max(total, 1))),
    )
    report(70)
    findings: list[str] = []
    if not zipfile.is_zipfile(path):
        report(100)
        return ApkInspection(
            str(path),
            path.stat().st_size,
            digest,
            0,
            0,
            False,
            False,
            False,
            ("File is not a valid APK/ZIP container",),
        )

    entry_count = 0
    expanded_bytes = 0
    dex_count = 0
    has_manifest = False
    has_signature = False
    valid = True
    names: set[str] = set()
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            entry_total = max(len(entries), 1)
            for entry_index, entry in enumerate(entries, start=1):
                entry_count += 1
                if entry_count > MAX_APK_ENTRIES:
                    findings.append(f"APK exceeds the {MAX_APK_ENTRIES:,}-entry safety limit")
                    valid = False
                    break
                expanded_bytes += max(0, entry.file_size)
                if expanded_bytes > MAX_DECLARED_EXPANDED_BYTES:
                    findings.append("APK declares more than 8 GiB of expanded content")
                    valid = False
                    break
                normalized = entry.filename.replace("\\", "/")
                parts = tuple(part for part in normalized.split("/") if part)
                if "\\" in entry.filename:
                    findings.append("APK contains an ambiguous backslash path")
                    valid = False
                if normalized.startswith("/") or ".." in parts:
                    findings.append("APK contains an unsafe absolute or parent-traversal path")
                    valid = False
                if normalized in names:
                    findings.append("APK contains duplicate entry names")
                    valid = False
                names.add(normalized)
                if stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK:
                    findings.append("APK contains a symbolic-link entry")
                    valid = False
                if entry.flag_bits & 0x1:
                    findings.append("APK contains an encrypted entry")
                    valid = False
                if normalized == "AndroidManifest.xml":
                    has_manifest = True
                if normalized.startswith("classes") and normalized.endswith(".dex"):
                    dex_count += 1
                upper = normalized.upper()
                if upper.startswith("META-INF/") and upper.endswith((".RSA", ".DSA", ".EC")):
                    has_signature = True
                report(70 + round(entry_index * 15 / entry_total))
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        findings.append(f"APK container could not be read: {type(exc).__name__}")
        valid = False
    report(85)

    if not has_manifest:
        findings.append("AndroidManifest.xml is missing")
        valid = False
    if dex_count == 0:
        findings.append("No classes*.dex entries found; this may be a resource-only APK")
    identity: dict[str, object] = {}
    signature: dict[str, object] = {}
    tool_runner = runner or SubprocessRunner()
    if valid and aapt_executable is not None:
        report(87)
        identity, identity_error = _inspect_package_identity(path, aapt_executable, tool_runner)
        if identity_error:
            findings.append(identity_error)
        report(92)
    if valid and apksigner_executable is not None:
        report(94)
        signature, signature_error = _inspect_signature(path, apksigner_executable, tool_runner)
        if signature_error:
            findings.append(signature_error)
        if signature.get("signature_verified") is False:
            valid = False
            findings.append("APK signature verification failed; Guardian will not install it")
        report(98)
    if not has_signature and signature.get("signature_verified") is not True:
        findings.append(
            "No legacy META-INF certificate was visible; modern APK Signature Scheme data may still be present"
        )
    if valid and not findings:
        findings.append("APK container structure passed bounded inspection")
    report(100)
    return ApkInspection(
        str(path),
        path.stat().st_size,
        digest,
        entry_count,
        dex_count,
        has_manifest,
        has_signature,
        valid,
        tuple(dict.fromkeys(findings)),
        package_name=str(identity.get("package_name", "")),
        app_label=str(identity.get("app_label", "")),
        version_name=str(identity.get("version_name", "")),
        version_code=str(identity.get("version_code", "")),
        min_sdk=str(identity.get("min_sdk", "")),
        target_sdk=str(identity.get("target_sdk", "")),
        native_abis=tuple(identity.get("native_abis", ())),
        permission_count=identity.get("permission_count"),
        signature_verified=signature.get("signature_verified"),
        signer_sha256=str(signature.get("signer_sha256", "")),
        signer_subject=str(signature.get("signer_subject", "")),
    )


def _inspect_package_identity(
    path: Path,
    executable: Path,
    runner: CommandRunner,
) -> tuple[dict[str, object], str]:
    tool = executable.expanduser().resolve()
    if not tool.is_file():
        return {}, "Verified AAPT2 path is unavailable; package identity was not decoded"
    result = runner.run((str(tool), "dump", "badging", str(path)), timeout=20)
    if not result.ok:
        detail = _single_line(result.stderr or result.stdout or "no diagnostic")
        return {}, f"AAPT2 could not decode package identity: {detail}"
    lines = result.stdout.splitlines()
    package_line = next((line for line in lines if line.startswith("package:")), "")
    if not package_line:
        return {}, "AAPT2 returned no package identity; Guardian retained the container result only"
    package = _quoted_fields(package_line)
    application_line = next((line for line in lines if line.startswith("application-label:")), "")
    app_label = _first_quoted_value(application_line)
    min_sdk = _first_quoted_value(
        next((line for line in lines if line.startswith("minSdkVersion:")), "")
    )
    if not min_sdk:
        min_sdk = _first_quoted_value(
            next((line for line in lines if line.startswith("sdkVersion:")), "")
        )
    target_sdk = _first_quoted_value(
        next((line for line in lines if line.startswith("targetSdkVersion:")), "")
    )
    native_abis = tuple(
        dict.fromkeys(
            _quoted_values(next((line for line in lines if line.startswith("native-code:")), ""))
        )
    )
    permission_count = sum(line.startswith("uses-permission:") for line in lines)
    package_name = _clean_metadata(package.get("name", ""), 255)
    if not package_name:
        return {}, "AAPT2 returned an empty package name; package identity was not trusted"
    return (
        {
            "package_name": package_name,
            "app_label": _clean_metadata(app_label, 180),
            "version_name": _clean_metadata(package.get("versionName", ""), 120),
            "version_code": _clean_metadata(package.get("versionCode", ""), 80),
            "min_sdk": _clean_metadata(min_sdk, 40),
            "target_sdk": _clean_metadata(target_sdk, 40),
            "native_abis": tuple(_clean_metadata(item, 80) for item in native_abis[:16]),
            "permission_count": permission_count,
        },
        "",
    )


def _inspect_signature(
    path: Path,
    executable: Path,
    runner: CommandRunner,
) -> tuple[dict[str, object], str]:
    tool = executable.expanduser().resolve()
    if not tool.is_file():
        return (
            {},
            "Verified APK Signer path is unavailable; cryptographic signature was not checked",
        )
    result = runner.run((str(tool), "verify", "--verbose", "--print-certs", str(path)), timeout=30)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    sha_match = re.search(r"Signer #1 certificate SHA-256 digest:\s*([0-9a-fA-F]{64})", output)
    subject_match = re.search(r"Signer #1 certificate DN:\s*(.+)", output)
    signature = {
        "signature_verified": bool(result.ok),
        "signer_sha256": sha_match.group(1).casefold() if sha_match else "",
        "signer_subject": _clean_metadata(subject_match.group(1), 240) if subject_match else "",
    }
    if result.ok:
        return signature, ""
    detail = _single_line(result.stderr or result.stdout or "verification failed")
    return signature, f"APK Signer rejected the cryptographic signature: {detail}"


def _quoted_fields(line: str) -> dict[str, str]:
    return {
        key: _clean_metadata(value, 512)
        for key, value in re.findall(r"([A-Za-z][A-Za-z0-9_]*)='([^']*)'", line)
    }


def _quoted_values(line: str) -> tuple[str, ...]:
    return tuple(value for value in re.findall(r"'([^']*)'", line))


def _first_quoted_value(line: str) -> str:
    values = _quoted_values(line)
    return values[0] if values else ""


def _clean_metadata(value: str, limit: int) -> str:
    return " ".join(str(value).replace("\x00", "").split())[:limit]


def _single_line(value: str) -> str:
    return _clean_metadata(value, 240) or "no diagnostic"


def create_install_plan(
    request: ApkInstallRequest,
    target_key: str,
    *,
    aapt_executable: Path | None = None,
    apksigner_executable: Path | None = None,
    runner: CommandRunner | None = None,
    progress: Callable[[int], None] | None = None,
) -> ApkInstallPlan:
    validate_install_request(request)
    if not target_key:
        raise ProjectError("APK install plan requires a privacy-safe device key")
    inspection = inspect_apk(
        Path(request.apk_path),
        aapt_executable=aapt_executable,
        apksigner_executable=apksigner_executable,
        runner=runner,
        progress=progress,
    )
    manifest = _install_manifest(request, target_key, inspection)
    assessment = GuardianPreflight().assess(manifest, execution_supported=True)
    return ApkInstallPlan(request, target_key, inspection, manifest, assessment)


def install_preflight(request: ApkInstallRequest):
    validate_install_request(request)
    inspection = inspect_apk(Path(request.apk_path))
    return GuardianPreflight().assess(
        _install_manifest(request, request.device_serial, inspection),
        execution_supported=True,
    )


def _install_manifest(
    request: ApkInstallRequest, target_key: str, inspection: ApkInspection
) -> OperationManifest:
    battery_status = (
        CheckStatus.UNKNOWN
        if request.battery_percent is None
        else CheckStatus.PASS
        if request.battery_percent >= 20
        else CheckStatus.FAIL
    )
    required_bytes = max(100 * 1024**2, inspection.file_size * 3)
    storage_status = (
        CheckStatus.UNKNOWN
        if request.device_free_bytes is None
        else CheckStatus.PASS
        if request.device_free_bytes >= required_bytes
        else CheckStatus.FAIL
    )
    return OperationManifest(
        1,
        uuid4().hex,
        datetime.now(UTC).isoformat(),
        "ADB APK install",
        "apk_install",
        target_key,
        (
            Precondition(
                "apk",
                "APK container and identity validated",
                CheckStatus.PASS if inspection.valid else CheckStatus.FAIL,
                f"SHA-256 {inspection.sha256}; {inspection.entry_count} entries; "
                f"package {inspection.package_name or 'not decoded'}; "
                f"signer {inspection.signer_sha256 or 'not cryptographically checked'}",
            ),
            Precondition(
                "device",
                "Device authorization",
                CheckStatus.PASS,
                "Caller supplied an authorized device",
            ),
            Precondition(
                "battery",
                "Battery is at least 20%",
                battery_status,
                f"Observed {request.battery_percent}%"
                if request.battery_percent is not None
                else "Battery evidence unavailable",
            ),
            Precondition(
                "storage",
                "Device has sufficient free data storage",
                storage_status,
                f"Observed {request.device_free_bytes} bytes free; requires {required_bytes}"
                if request.device_free_bytes is not None
                else "Storage evidence unavailable",
            ),
        ),
        (
            PlannedStep(
                "install",
                "Install APK",
                "Guardian-approved ADB install",
                OperationClass.STATE_CHANGING,
                "Changes device application state",
                True,
            ),
        ),
    )


class ApkInstallService:
    """Execute only unchanged, approved APK plans through Guardian's gateway."""

    def __init__(
        self,
        executable: Path,
        gateway: ExecutionGateway,
        approvals: ApprovalStore,
    ) -> None:
        self.executable = str(executable)
        self.gateway = gateway
        self.approvals = approvals

    def install(self, plan: ApkInstallPlan, timeout: float = 180) -> CommandResult:
        if plan.assessment.status is PreflightStatus.BLOCKED or not plan.safety_ready:
            raise GuardianDeniedError("APK plan is blocked by required safety checks")
        current = inspect_apk(Path(plan.request.apk_path))
        if (
            current.sha256 != plan.inspection.sha256
            or current.file_size != plan.inspection.file_size
            or not current.valid
        ):
            raise GuardianDeniedError("APK changed after approval or no longer passes inspection")
        if not self.approvals.is_approved(plan.digest, plan.target_key):
            raise GuardianDeniedError("Exact APK plan has not been approved")
        operation = OperationRequest(
            operation_id="apk.install",
            category=OperationClass.STATE_CHANGING,
            executable=self.executable,
            arguments=build_install_arguments(plan.request),
            purpose="Install the user-reviewed APK",
            target=plan.request.device_serial,
            approval_digest=plan.digest,
            approval_target=plan.target_key,
        )
        return self.gateway.execute(operation, timeout=timeout)


def install_succeeded(result: CommandResult) -> bool:
    return result.ok and any(line.strip() == "Success" for line in result.stdout.splitlines())


def _sha256(
    path: Path,
    progress: Callable[[int, int], None] | None = None,
) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size
    done = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            done += len(chunk)
            if progress is not None:
                progress(done, total)
    return digest.hexdigest()


def plan_summary(plan: ApkInstallPlan) -> str:
    """Return a stable JSON summary suitable for a privacy-safe local receipt."""
    return json.dumps(
        {
            "schema_version": 1,
            "apk_name": Path(plan.inspection.path).name,
            "apk_sha256": plan.inspection.sha256,
            "apk_size": plan.inspection.file_size,
            "entry_count": plan.inspection.entry_count,
            "dex_count": plan.inspection.dex_count,
            "package_name": plan.inspection.package_name,
            "app_label": plan.inspection.app_label,
            "version_name": plan.inspection.version_name,
            "version_code": plan.inspection.version_code,
            "min_sdk": plan.inspection.min_sdk,
            "target_sdk": plan.inspection.target_sdk,
            "permission_count": plan.inspection.permission_count,
            "signature_verified": plan.inspection.signature_verified,
            "signer_sha256": plan.inspection.signer_sha256,
            "target_key": plan.target_key,
            "manifest_digest": plan.digest,
            "status": plan.assessment.status.value,
            "risk": plan.assessment.risk.value,
        },
        sort_keys=True,
    )
