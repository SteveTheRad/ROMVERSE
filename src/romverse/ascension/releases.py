from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from romverse.ascension.models import AscensionMethod, OfficialRootAsset, OfficialRootRelease
from romverse.device.apk_install import ApkInspection, inspect_apk
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.infrastructure.process import CommandRunner, SubprocessRunner
from romverse.rom.models import ProjectError

ProgressCallback = Callable[[int, int], None]
JsonLoader = Callable[[str], dict[str, object]]
StreamLoader = Callable[[str], tuple[object, int, str]]
ApkInspector = Callable[[Path, OfficialRootAsset], ApkInspection]
Clock = Callable[[], datetime]


class OfficialRootConnectivityError(ProjectError):
    """A bounded official-provider connection failure eligible for verified cache fallback."""


@dataclass(frozen=True, slots=True)
class OfficialRootAcquisition:
    """A verified manager plus an honest account of how freshness was established."""

    release: OfficialRootRelease
    path: Path
    mode: str
    explanation: str


@dataclass(frozen=True, slots=True)
class _VerifiedRootArtifact:
    release: OfficialRootRelease
    path: Path
    retrieved_at: datetime
    freshness_receipt_verified: bool


class OfficialRootReleaseService:
    """Resolve and vault official stable root-manager artifacts with pinned hashes."""

    MAX_JSON_BYTES = 2 * 1024 * 1024
    MAX_ASSET_BYTES = 64 * 1024 * 1024
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_RECEIPTS = 64
    MAX_RELEASE_ASSETS = 512
    MAX_OFFLINE_CACHE_AGE = timedelta(days=30)
    MAX_CLOCK_SKEW = timedelta(minutes=5)
    CHUNK_SIZE = 1024 * 1024
    PROVIDERS = {
        AscensionMethod.MAGISK: (
            "topjohnwu/Magisk",
            "https://api.github.com/repos/topjohnwu/Magisk/releases/latest",
        ),
        AscensionMethod.KERNELSU_LKM: (
            "tiann/KernelSU",
            "https://api.github.com/repos/tiann/KernelSU/releases/latest",
        ),
    }
    OFFICIAL_SIGNERS = {
        AscensionMethod.MAGISK: "b4cb83b4dad99f997dbe872f013aa16c14eec41d167021f371f7e1330f273ee6",
        AscensionMethod.KERNELSU_LKM: "c371061b19d8c7d7d6133c6a9bafe198fa944e50c1b31c9d8daa8d7f1fc2d2d6",
    }
    OFFICIAL_PACKAGES = {
        AscensionMethod.MAGISK: "com.topjohnwu.magisk",
        AscensionMethod.KERNELSU_LKM: "me.weishu.kernelsu",
    }
    RECEIPT_KEYS = frozenset(
        {
            "format",
            "schema_version",
            "retrieved_at",
            "release",
            "workspace_path",
            "apk_structure",
            "apk_identity",
            "scope",
            "execution_authority",
            "device_modified",
            "receipt_digest",
        }
    )
    RELEASE_KEYS = frozenset(
        {"provider", "repository", "tag", "published_at", "asset", "source_url"}
    )
    ASSET_KEYS = frozenset(
        {
            "provider",
            "repository",
            "tag",
            "published_at",
            "name",
            "size_bytes",
            "sha256",
            "download_url",
        }
    )
    APK_STRUCTURE_KEYS = frozenset(
        {
            "entry_count",
            "dex_count",
            "manifest_present",
            "legacy_signature_present",
            "valid",
        }
    )
    APK_IDENTITY_KEYS = frozenset(
        {"package_name", "signature_verified", "signer_sha256", "signer_subject"}
    )

    def __init__(
        self,
        workspace: Path,
        json_loader: JsonLoader | None = None,
        stream_loader: StreamLoader | None = None,
        apk_inspector: ApkInspector | None = None,
        aapt_executable: Path | None = None,
        apksigner_executable: Path | None = None,
        runner: CommandRunner | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self._json_loader = json_loader or self._load_json
        self._stream_loader = stream_loader or self._open_stream
        self._apk_inspector = apk_inspector
        self._aapt_executable = self._verified_tool_path(aapt_executable)
        self._apksigner_executable = self._verified_tool_path(apksigner_executable)
        self._runner = runner or SubprocessRunner()
        self._clock = clock or (lambda: datetime.now(UTC))

    def resolve_latest(self, method: AscensionMethod) -> OfficialRootRelease:
        repository, api_url = self.PROVIDERS[method]
        try:
            payload = self._json_loader(api_url)
        except OSError as exc:
            raise OfficialRootConnectivityError(
                "The official root-tool release service could not be reached: "
                + self._failure_detail(exc)
            ) from exc
        if payload.get("draft") is not False or payload.get("prerelease") is not False:
            raise ProjectError("The official latest release is not a stable published release")
        tag = self._clean_text(payload.get("tag_name"), "release tag", 80)
        published = self._clean_text(payload.get("published_at"), "published timestamp", 80)
        source_url = self._validated_url(
            self._clean_text(payload.get("html_url"), "release URL", 500), {"github.com"}
        )
        self._require_repository_release_url(source_url, repository, "tag")
        raw_assets = payload.get("assets")
        if not isinstance(raw_assets, list) or len(raw_assets) > self.MAX_RELEASE_ASSETS:
            raise ProjectError("Official release metadata has no asset list")
        candidates = []
        for raw in raw_assets:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", ""))
            if not self._asset_name_allowed(method, name):
                continue
            if (
                raw.get("state") != "uploaded"
                or raw.get("content_type") != "application/vnd.android.package-archive"
            ):
                continue
            digest = str(raw.get("digest", "")).casefold()
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                continue
            size = raw.get("size")
            if type(size) is not int or not 0 < size <= self.MAX_ASSET_BYTES:
                continue
            download_url = self._validated_url(
                str(raw.get("browser_download_url", "")), {"github.com"}
            )
            self._require_repository_release_url(download_url, repository, "download")
            candidates.append(
                OfficialRootAsset(
                    method,
                    repository,
                    tag,
                    published,
                    name,
                    size,
                    digest.removeprefix("sha256:"),
                    download_url,
                )
            )
        if len(candidates) != 1:
            raise ProjectError(
                "Official release must expose exactly one stable, digest-pinned manager APK"
            )
        release = OfficialRootRelease(
            method,
            repository,
            tag,
            published,
            candidates[0],
            source_url,
        )
        self._validate_release(release, method)
        return release

    def acquire_latest_or_verified(
        self,
        method: AscensionMethod,
        progress: ProgressCallback | None = None,
    ) -> OfficialRootAcquisition:
        """Prefer current official evidence; only connectivity failures may use a fresh cache."""

        try:
            release = self.resolve_latest(method)
            path = self.acquire(release, progress)
        except OfficialRootConnectivityError as exc:
            return self._fresh_cache_fallback(method, exc, progress)
        return OfficialRootAcquisition(
            release,
            path,
            "official-latest",
            "ROMVERSE resolved the current stable release from the official GitHub API and verified its repository, tag, asset path, declared size, and published SHA-256.",
        )

    def acquire(
        self,
        release: OfficialRootRelease,
        progress: ProgressCallback | None = None,
    ) -> Path:
        self._validate_release(release, release.provider)
        asset = release.asset
        root = (
            self.workspace
            / "tools"
            / "ascension"
            / asset.provider.value
            / self._safe_tag(asset.tag)
        )
        ensure_private_directory(root, boundary=self.workspace)
        filename = f"{asset.sha256[:16]}-{self._safe_filename(asset.name)}"
        destination = root / filename
        if (
            destination.is_file()
            and not destination.is_symlink()
            and destination.stat().st_size == asset.size_bytes
            and self._sha256(destination) == asset.sha256
        ):
            inspection = self._validate_manager_apk(destination, asset)
            if not self._make_private_file(destination):
                raise ProjectError("Official root manager vault permissions could not be secured")
            self._write_receipt(root, release, destination, inspection)
            if progress is not None:
                progress(asset.size_bytes, asset.size_bytes)
            return destination

        temporary = root / f".{uuid4().hex}.part.apk"
        try:
            stream, reported_size, final_url = self._stream_loader(asset.download_url)
        except OSError as exc:
            raise OfficialRootConnectivityError(
                "The official root-tool download service could not be reached: "
                + self._failure_detail(exc)
            ) from exc
        try:
            self._validated_url(
                final_url,
                {
                    "github.com",
                    "objects.githubusercontent.com",
                    "release-assets.githubusercontent.com",
                },
            )
        except ProjectError:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
            raise
        digest = hashlib.sha256()
        written = 0
        try:
            with stream:
                if reported_size not in {-1, asset.size_bytes}:
                    raise ProjectError(
                        "Official artifact content length differs from release metadata"
                    )
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(temporary, flags, 0o600)
                with os.fdopen(descriptor, "wb", closefd=True) as output:
                    while True:
                        try:
                            chunk = stream.read(self.CHUNK_SIZE)
                        except OSError as exc:
                            raise OfficialRootConnectivityError(
                                "The official root-tool download was interrupted: "
                                + self._failure_detail(exc)
                            ) from exc
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > self.MAX_ASSET_BYTES or written > asset.size_bytes:
                            raise ProjectError("Official artifact exceeded its declared safe size")
                        output.write(chunk)
                        digest.update(chunk)
                        if progress is not None and written < asset.size_bytes:
                            progress(written, asset.size_bytes)
                    output.flush()
                    os.fsync(output.fileno())
            if written != asset.size_bytes or digest.hexdigest() != asset.sha256:
                raise ProjectError("Official artifact failed its published size or SHA-256 check")
            inspection = self._validate_manager_apk(temporary, asset)
            os.replace(temporary, destination)
            if not self._make_private_file(destination):
                raise ProjectError("Official root manager vault permissions could not be secured")
        finally:
            temporary.unlink(missing_ok=True)
        self._write_receipt(root, release, destination, inspection)
        if progress is not None:
            progress(asset.size_bytes, asset.size_bytes)
        return destination

    def verify_artifact(
        self,
        release: OfficialRootRelease,
        path: Path,
    ) -> ApkInspection:
        """Revalidate exact bytes, official metadata, package identity, and signer."""

        self._validate_release(release, release.provider)
        if path.is_symlink():
            raise ProjectError("Official root manager cannot be a symbolic link")
        try:
            artifact = path.expanduser().resolve(strict=True)
        except OSError as exc:
            raise ProjectError("Official root manager is unavailable") from exc
        if (
            not artifact.is_file()
            or not artifact.is_relative_to(self.workspace)
            or artifact.stat().st_size != release.asset.size_bytes
            or self._sha256(artifact) != release.asset.sha256
        ):
            raise ProjectError("Official root manager failed exact size or SHA-256 verification")
        return self._validate_manager_apk(artifact, release.asset)

    def load_verified(
        self,
        method: AscensionMethod,
    ) -> tuple[OfficialRootRelease, Path] | None:
        """Load the newest still-valid vaulted artifact without trusting its receipt alone."""

        record = self._load_verified_record(method)
        return (record.release, record.path) if record is not None else None

    def _load_verified_record(
        self,
        method: AscensionMethod,
    ) -> _VerifiedRootArtifact | None:
        receipts = self._receipt_paths(method)
        if receipts is None:
            return None
        verified: list[_VerifiedRootArtifact] = []
        now = self._now()
        for receipt_path in receipts:
            try:
                payload = read_json_object(
                    receipt_path,
                    boundary=self.workspace,
                    maximum_bytes=self.MAX_RECEIPT_BYTES,
                )
                schema_version = payload.get("schema_version")
                if not self._valid_receipt_shape(payload, schema_version):
                    continue
                freshness_receipt_verified = schema_version == 2
                if freshness_receipt_verified and payload.get(
                    "receipt_digest"
                ) != self._receipt_digest(payload):
                    continue
                release_data = payload["release"]
                asset_data = release_data["asset"]
                asset = OfficialRootAsset(
                    AscensionMethod(str(asset_data["provider"])),
                    str(asset_data["repository"]),
                    str(asset_data["tag"]),
                    str(asset_data["published_at"]),
                    str(asset_data["name"]),
                    asset_data["size_bytes"],
                    str(asset_data["sha256"]),
                    str(asset_data["download_url"]),
                )
                release = OfficialRootRelease(
                    AscensionMethod(str(release_data["provider"])),
                    str(release_data["repository"]),
                    str(release_data["tag"]),
                    str(release_data["published_at"]),
                    asset,
                    str(release_data["source_url"]),
                )
                relative = Path(payload["workspace_path"])
                unresolved = self.workspace / relative
                if relative.is_absolute() or ".." in relative.parts or unresolved.is_symlink():
                    continue
                expected_relative = (
                    Path("tools")
                    / "ascension"
                    / method.value
                    / self._safe_tag(asset.tag)
                    / f"{asset.sha256[:16]}-{self._safe_filename(asset.name)}"
                )
                if relative != expected_relative or unresolved.parent != receipt_path.parent:
                    continue
                artifact = unresolved.resolve(strict=True)
                retrieved_at = self._timestamp(payload.get("retrieved_at"), "retrieval timestamp")
                if retrieved_at > now + self.MAX_CLOCK_SKEW:
                    continue
                apk_identity = payload.get("apk_identity")
                if not isinstance(apk_identity, dict):
                    continue
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                LocalStoreError,
                ProjectError,
            ):
                continue
            if (
                payload.get("format") != "romverse.official-root-artifact"
                or schema_version not in {1, 2}
                or payload.get("execution_authority") != "none"
                or payload.get("device_modified") is not False
                or release.provider is not method
                or asset.provider is not method
                or not artifact.is_relative_to(self.workspace)
                or not artifact.is_file()
                or artifact.stat().st_size != asset.size_bytes
                or not re.fullmatch(r"[0-9a-f]{64}", asset.sha256)
                or self._sha256(artifact) != asset.sha256
                or apk_identity.get("signature_verified") is not True
                or apk_identity.get("signer_sha256") != self.OFFICIAL_SIGNERS[method]
                or apk_identity.get("package_name")
                not in {
                    "",
                    self.OFFICIAL_PACKAGES[method],
                }
            ):
                continue
            try:
                self._validate_release(release, method)
                # Re-run the cryptographic APK verification on every reuse. The
                # receipt is evidence, not authority, and can never substitute for
                # the official signer check against the current vaulted bytes.
                self.verify_artifact(release, artifact)
            except ProjectError:
                continue
            if not self._make_private_file(artifact) or not self._make_private_file(receipt_path):
                continue
            verified.append(
                _VerifiedRootArtifact(
                    release,
                    artifact,
                    retrieved_at,
                    freshness_receipt_verified,
                )
            )
        if not verified:
            return None
        return max(verified, key=lambda item: item.retrieved_at)

    def _fresh_cache_fallback(
        self,
        method: AscensionMethod,
        failure: OfficialRootConnectivityError,
        progress: ProgressCallback | None,
    ) -> OfficialRootAcquisition:
        cached = self._load_verified_record(method)
        if cached is None:
            raise OfficialRootConnectivityError(
                "The official root-tool service is unavailable and ROMVERSE has no revalidated vaulted manager to use safely"
            ) from failure
        if not cached.freshness_receipt_verified:
            raise OfficialRootConnectivityError(
                "The official root-tool service is unavailable and the vaulted manager predates ROMVERSE freshness receipts. Reconnect once so ROMVERSE can revalidate it online"
            ) from failure
        age = self._now() - cached.retrieved_at
        if age > self.MAX_OFFLINE_CACHE_AGE:
            days = max(31, age.days)
            raise OfficialRootConnectivityError(
                f"The official root-tool service is unavailable and the vaulted manager freshness check is {days} days old. Reconnect so ROMVERSE can verify the current stable release"
            ) from failure
        if progress is not None:
            progress(cached.release.asset.size_bytes, cached.release.asset.size_bytes)
        reason = " ".join(str(failure).split())[:240]
        return OfficialRootAcquisition(
            cached.release,
            cached.path,
            "verified-cache",
            f"Official freshness service unavailable: {reason}. ROMVERSE used a cache verified within the last 30 days after it revalidated the complete APK size, SHA-256, package identity, official signing certificate, repository, tag, and asset URL.",
        )

    def _write_receipt(
        self,
        root: Path,
        release: OfficialRootRelease,
        destination: Path,
        inspection: ApkInspection,
    ) -> None:
        payload = {
            "format": "romverse.official-root-artifact",
            "schema_version": 2,
            "retrieved_at": self._now().isoformat(),
            "release": asdict(release),
            "workspace_path": destination.relative_to(self.workspace).as_posix(),
            "apk_structure": {
                "entry_count": inspection.entry_count,
                "dex_count": inspection.dex_count,
                "manifest_present": inspection.has_manifest,
                "legacy_signature_present": inspection.has_legacy_signature,
                "valid": inspection.valid,
            },
            "apk_identity": {
                "package_name": inspection.package_name,
                "signature_verified": inspection.signature_verified,
                "signer_sha256": inspection.signer_sha256,
                "signer_subject": inspection.signer_subject,
            },
            "scope": "verified-online-root-preparation-only",
            "execution_authority": "none",
            "device_modified": False,
        }
        payload["receipt_digest"] = self._receipt_digest(payload)
        atomic_write_json(
            root / "official-root-artifact.romverse",
            payload,
            boundary=self.workspace,
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )

    def _validate_manager_apk(
        self,
        path: Path,
        asset: OfficialRootAsset,
    ) -> ApkInspection:
        """Require a bounded, cryptographically signed official Android package."""

        if self._apk_inspector is not None:
            inspection = self._apk_inspector(path, asset)
        else:
            signer = self._apksigner_executable or self._path_tool("apksigner")
            if signer is None:
                raise ProjectError(
                    "APK Signer is required to verify the official root manager; install it through Forge Arsenal"
                )
            aapt = self._aapt_executable or self._path_tool("aapt2") or self._path_tool("aapt")
            inspection = inspect_apk(
                path,
                aapt_executable=aapt,
                apksigner_executable=signer,
                runner=self._runner,
            )
        expected_signer = self.OFFICIAL_SIGNERS[asset.provider]
        expected_package = self.OFFICIAL_PACKAGES[asset.provider]
        if (
            not inspection.valid
            or not inspection.has_manifest
            or inspection.dex_count < 1
            or inspection.file_size != asset.size_bytes
            or inspection.sha256 != asset.sha256
            or inspection.signature_verified is not True
            or inspection.signer_sha256 != expected_signer
            or (inspection.package_name and inspection.package_name != expected_package)
        ):
            detail = "; ".join(inspection.findings[:3])
            raise ProjectError(
                "Official root manager failed package, signature, signer, or structure validation"
                + (f": {detail}" if detail else "")
            )
        return inspection

    @staticmethod
    def _verified_tool_path(path: Path | None) -> Path | None:
        if path is None:
            return None
        try:
            resolved = path.expanduser().resolve(strict=True)
        except OSError:
            return None
        return resolved if resolved.is_file() else None

    @classmethod
    def _path_tool(cls, name: str) -> Path | None:
        found = shutil.which(name)
        return cls._verified_tool_path(Path(found)) if found else None

    def _load_json(self, url: str) -> dict[str, object]:
        self._validated_url(url, {"api.github.com"})
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "ROMVERSE/0.1"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            final = self._validated_url(response.geturl(), {"api.github.com"})
            if final != url:
                raise ProjectError("Official metadata request redirected unexpectedly")
            raw = response.read(self.MAX_JSON_BYTES + 1)
        if len(raw) > self.MAX_JSON_BYTES:
            raise ProjectError("Official release metadata exceeded the safety limit")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProjectError("Official release metadata is invalid") from exc
        if not isinstance(payload, dict):
            raise ProjectError("Official release metadata must be an object")
        return payload

    def _open_stream(self, url: str) -> tuple[object, int, str]:
        self._validated_url(url, {"github.com"})
        request = urllib.request.Request(url, headers={"User-Agent": "ROMVERSE/0.1"})
        response = urllib.request.urlopen(request, timeout=30)
        try:
            size = int(response.headers.get("Content-Length", "-1"))
        except ValueError:
            size = -1
        return response, size, response.geturl()

    @staticmethod
    def _asset_name_allowed(method: AscensionMethod, name: str) -> bool:
        if method is AscensionMethod.MAGISK:
            return bool(re.fullmatch(r"Magisk-v[0-9][A-Za-z0-9._-]*\.apk", name)) and (
                "debug" not in name.casefold()
            )
        return bool(re.fullmatch(r"KernelSU_v[0-9][A-Za-z0-9._-]*-release\.apk", name))

    @staticmethod
    def _validated_url(url: str, hosts: set[str]) -> str:
        try:
            split = urlsplit(url)
            port = split.port
        except ValueError as exc:
            raise ProjectError("Official artifact URL is invalid") from exc
        if (
            split.scheme != "https"
            or split.hostname not in hosts
            or split.username
            or split.password
            or port not in {None, 443}
            or split.fragment
        ):
            raise ProjectError("Official artifact URL is not on an approved HTTPS host")
        return url

    @staticmethod
    def _require_repository_release_url(url: str, repository: str, kind: str) -> None:
        path = unquote(urlsplit(url).path)
        expected = f"/{repository}/releases/{kind}/"
        if not path.startswith(expected):
            raise ProjectError(
                "Official artifact metadata does not belong to the expected repository"
            )

    def _validate_release(
        self,
        release: OfficialRootRelease,
        method: AscensionMethod,
    ) -> None:
        repository, _api_url = self.PROVIDERS[method]
        asset = release.asset
        text_fields = (
            release.repository,
            release.tag,
            release.published_at,
            release.source_url,
            asset.repository,
            asset.tag,
            asset.published_at,
            asset.name,
            asset.sha256,
            asset.download_url,
        )
        if (
            release.provider is not method
            or asset.provider is not method
            or any(type(value) is not str for value in text_fields)
            or release.repository != repository
            or asset.repository != repository
            or release.tag != asset.tag
            or release.published_at != asset.published_at
        ):
            raise ProjectError("Official manager identity is not bound to the selected provider")
        tag = self._safe_tag(release.tag)
        if tag != release.tag or not self._asset_name_allowed(method, asset.name):
            raise ProjectError("Official manager release tag or asset name is invalid")
        if (
            type(asset.size_bytes) is not int
            or not 0 < asset.size_bytes <= self.MAX_ASSET_BYTES
            or not re.fullmatch(r"[0-9a-f]{64}", asset.sha256)
        ):
            raise ProjectError("Official manager size or SHA-256 is invalid")
        published = self._timestamp(release.published_at, "published timestamp")
        if published > self._now() + self.MAX_CLOCK_SKEW:
            raise ProjectError("Official published timestamp is unexpectedly in the future")
        self._validated_url(release.source_url, {"github.com"})
        self._validated_url(asset.download_url, {"github.com"})
        self._require_repository_release_url(release.source_url, repository, "tag")
        self._require_repository_release_url(asset.download_url, repository, "download")
        source_path = unquote(urlsplit(release.source_url).path).rstrip("/")
        download_path = unquote(urlsplit(asset.download_url).path)
        if (
            urlsplit(release.source_url).query
            or urlsplit(asset.download_url).query
            or source_path != f"/{repository}/releases/tag/{tag}"
            or download_path != f"/{repository}/releases/download/{tag}/{asset.name}"
        ):
            raise ProjectError("Official manager URLs do not match the exact release tag and asset")

    @staticmethod
    def _timestamp(value: object, label: str) -> datetime:
        text = str(value or "").strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProjectError(f"Official {label} is invalid") from exc
        if parsed.tzinfo is None:
            raise ProjectError(f"Official {label} is invalid")
        return parsed.astimezone(UTC)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ProjectError("ROMVERSE needs a timezone-aware clock for root-tool freshness")
        return value.astimezone(UTC)

    def _receipt_paths(self, method: AscensionMethod) -> tuple[Path, ...] | None:
        """Enumerate only bounded, non-linked tag directories inside the private vault."""

        provider_root = self.workspace / "tools" / "ascension" / method.value
        if not provider_root.exists():
            return ()
        try:
            safe_root = self._validated_existing_directory(provider_root)
            with os.scandir(safe_root) as iterator:
                entries = []
                for entry in iterator:
                    if len(entries) >= self.MAX_RECEIPTS:
                        return None
                    entries.append(entry)
            receipts: list[Path] = []
            for entry in entries:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                tag = entry.name
                if self._safe_tag(tag) != tag:
                    return None
                tag_root = self._validated_existing_directory(safe_root / tag)
                receipt = tag_root / "official-root-artifact.romverse"
                try:
                    details = receipt.lstat()
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(details.st_mode):
                    continue
                receipts.append(receipt)
            return tuple(sorted(receipts))
        except (OSError, ProjectError, LocalStoreError):
            return None

    def _validated_existing_directory(self, directory: Path) -> Path:
        root = self.workspace.resolve(strict=True)
        candidate = Path(os.path.abspath(directory))
        try:
            relative = candidate.relative_to(root)
        except ValueError as exc:
            raise LocalStoreError("Root manager vault escapes the workspace") from exc
        current = root
        for part in relative.parts:
            if part in {"", ".", ".."}:
                raise LocalStoreError("Root manager vault path is invalid")
            current /= part
            details = current.lstat()
            is_junction = bool(getattr(current, "is_junction", lambda: False)())
            if not stat.S_ISDIR(details.st_mode) or current.is_symlink() or is_junction:
                raise LocalStoreError("Root manager vault directory is unsafe")
        return candidate

    @classmethod
    def _valid_receipt_shape(cls, payload: dict[str, object], schema: object) -> bool:
        if type(schema) is not int or schema not in {1, 2}:
            return False
        expected_keys = cls.RECEIPT_KEYS if schema == 2 else cls.RECEIPT_KEYS - {"receipt_digest"}
        if set(payload) != expected_keys:
            return False
        release = payload.get("release")
        if not isinstance(release, dict) or set(release) != cls.RELEASE_KEYS:
            return False
        asset = release.get("asset")
        structure = payload.get("apk_structure")
        identity = payload.get("apk_identity")
        if (
            not isinstance(asset, dict)
            or set(asset) != cls.ASSET_KEYS
            or not isinstance(structure, dict)
            or set(structure) != cls.APK_STRUCTURE_KEYS
            or not isinstance(identity, dict)
            or set(identity) != cls.APK_IDENTITY_KEYS
        ):
            return False
        string_values = (
            payload.get("retrieved_at"),
            payload.get("workspace_path"),
            payload.get("scope"),
            payload.get("execution_authority"),
            release.get("provider"),
            release.get("repository"),
            release.get("tag"),
            release.get("published_at"),
            release.get("source_url"),
            asset.get("provider"),
            asset.get("repository"),
            asset.get("tag"),
            asset.get("published_at"),
            asset.get("name"),
            asset.get("sha256"),
            asset.get("download_url"),
            identity.get("package_name"),
            identity.get("signer_sha256"),
            identity.get("signer_subject"),
        )
        if any(type(value) is not str for value in string_values):
            return False
        if (
            not 0 < len(payload["retrieved_at"]) <= 80
            or not 0 < len(payload["workspace_path"]) <= 500
            or payload["scope"] != "verified-online-root-preparation-only"
            or payload["execution_authority"] != "none"
            or payload.get("device_modified") is not False
            or type(asset.get("size_bytes")) is not int
            or type(structure.get("entry_count")) is not int
            or type(structure.get("dex_count")) is not int
            or structure["entry_count"] < 0
            or structure["dex_count"] < 0
            or type(structure.get("manifest_present")) is not bool
            or type(structure.get("legacy_signature_present")) is not bool
            or type(structure.get("valid")) is not bool
            or type(identity.get("signature_verified")) is not bool
            or len(identity["signer_subject"]) > 1000
        ):
            return False
        return schema == 1 or (
            type(payload.get("receipt_digest")) is str
            and bool(re.fullmatch(r"[0-9a-f]{64}", payload["receipt_digest"]))
        )

    @staticmethod
    def _make_private_file(path: Path) -> bool:
        if os.name == "nt":
            return True
        try:
            path.chmod(0o600)
            return stat.S_IMODE(path.stat().st_mode) == 0o600
        except OSError:
            return False

    @staticmethod
    def _receipt_digest(payload: dict[str, object]) -> str:
        unsigned = dict(payload)
        unsigned.pop("receipt_digest", None)
        return hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _failure_detail(error: OSError) -> str:
        detail = " ".join(str(error).split())[:240]
        return detail or "connection unavailable"

    @staticmethod
    def _clean_text(value: object, label: str, maximum: int) -> str:
        text = str(value or "").strip()
        if not text or len(text) > maximum or any(ord(char) < 32 for char in text):
            raise ProjectError(f"Official {label} is invalid")
        return text

    @staticmethod
    def _safe_filename(name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
        if not safe or len(safe) > 180:
            raise ProjectError("Official artifact filename is unsafe")
        return safe

    @staticmethod
    def _safe_tag(tag: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", tag) or ".." in tag:
            raise ProjectError("Official release tag is unsafe")
        return tag

    @classmethod
    def _sha256(cls, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(cls.CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()
