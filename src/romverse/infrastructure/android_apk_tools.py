from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
import zipfile
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from romverse.infrastructure.local_store import (
    atomic_write_bytes,
    atomic_write_json,
    ensure_private_directory,
)

AAPT2_VERSION = "9.4.0-15978811"
AAPT2_SOURCE = (
    "https://dl.google.com/dl/android/maven2/com/android/tools/build/aapt2/"
    f"{AAPT2_VERSION}/aapt2-{AAPT2_VERSION}-linux.jar"
)
AAPT2_ARCHIVE_SHA256 = "f5bebd466ecf14d341fd465f2756a16d86052f29eb4532003d5ff7bcffd08de5"
AAPT2_PACKAGE_DIRECTORY = "android-aapt2"

APKSIG_VERSION = "9.4.0"
APKSIG_JAR = f"apksig-{APKSIG_VERSION}.jar"
APKSIG_SOURCE = (
    "https://dl.google.com/dl/android/maven2/com/android/tools/build/apksig/"
    f"{APKSIG_VERSION}/{APKSIG_JAR}"
)
APKSIG_ARCHIVE_SHA256 = "7ae2e5980c77d853e3513074ee7c822bbdcdcde1668889d17faa7fe8bc8aa821"
APK_VERIFIER_PACKAGE_DIRECTORY = "android-apk-verifier"
APK_VERIFIER_SOURCE_FILE = "RomverseApkVerifier.java"
APK_VERIFIER_LAUNCHER_FILE = "apksigner"

MAX_GOOGLE_MAVEN_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_GOOGLE_MAVEN_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_GOOGLE_MAVEN_ENTRIES = 2_048
MAX_RECEIPT_BYTES = 64 * 1024
DownloadProgress = Callable[[int, int], None]

APK_VERIFIER_LAUNCHER = f'''#!/usr/bin/env python3
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
command = (
    "java",
    "--class-path",
    str(root / "{APKSIG_JAR}"),
    str(root / "{APK_VERIFIER_SOURCE_FILE}"),
    *sys.argv[1:],
)
try:
    os.execvp(command[0], command)
except OSError:
    sys.stderr.write("Java 11 or newer is required for APK signature verification.\\n")
    raise SystemExit(127)
'''.encode()

APK_VERIFIER_JAVA = f'''import com.android.apksig.ApkVerifier;
import java.io.File;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;

public final class RomverseApkVerifier {{
    private static final String VERSION = "{APKSIG_VERSION}";

    private RomverseApkVerifier() {{}}

    public static void main(String[] args) {{
        if (args.length == 1 && "version".equals(args[0])) {{
            System.out.println("ROMVERSE APK Signature Verifier " + VERSION + " (official apksig; verification-only)");
            return;
        }}
        File apk = parseVerify(args);
        if (apk == null) {{
            System.err.println("Usage: apksigner verify [--verbose] [--print-certs] <apk>");
            System.exit(2);
            return;
        }}
        try {{
            ApkVerifier.Result result = new ApkVerifier.Builder(apk).build().verify();
            System.out.println(result.isVerified() ? "Verifies" : "DOES NOT VERIFY");
            System.out.println("Verified using v1 scheme (JAR signing): " + result.isVerifiedUsingV1Scheme());
            System.out.println("Verified using v2 scheme (APK Signature Scheme v2): " + result.isVerifiedUsingV2Scheme());
            System.out.println("Verified using v3 scheme (APK Signature Scheme v3): " + result.isVerifiedUsingV3Scheme());
            System.out.println("Verified using v3.1 scheme (APK Signature Scheme v3.1): " + result.isVerifiedUsingV31Scheme());
            int index = 1;
            for (X509Certificate certificate : result.getSignerCertificates()) {{
                System.out.println("Signer #" + index + " certificate DN: " + certificate.getSubjectX500Principal().getName());
                System.out.println("Signer #" + index + " certificate SHA-256 digest: " + sha256(certificate.getEncoded()));
                index++;
            }}
            if (!result.isVerified()) {{
                System.err.println("ERROR: APK signature verification failed (" + result.getErrors().size() + " verified issue(s))");
                System.exit(1);
            }}
        }} catch (Exception failure) {{
            System.err.println("ERROR: APK signature verification could not complete (" + failure.getClass().getSimpleName() + ")");
            System.exit(1);
        }}
    }}

    private static File parseVerify(String[] args) {{
        if (args.length < 2 || !"verify".equals(args[0])) {{
            return null;
        }}
        File apk = null;
        for (int index = 1; index < args.length; index++) {{
            String argument = args[index];
            if ("--verbose".equals(argument) || "--print-certs".equals(argument)) {{
                continue;
            }}
            if (argument.startsWith("-") || apk != null) {{
                return null;
            }}
            apk = new File(argument);
        }}
        return apk != null && apk.isFile() ? apk : null;
    }}

    private static String sha256(byte[] payload) throws Exception {{
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(payload);
        StringBuilder encoded = new StringBuilder(digest.length * 2);
        for (byte value : digest) {{
            encoded.append(String.format("%02x", value & 0xff));
        }}
        return encoded.toString();
    }}
}}
'''.encode()


def install_pinned_aapt2(
    destination: Path,
    opener=None,
    *,
    boundary: Path | None = None,
    progress: DownloadProgress | None = None,
) -> tuple[Path, str]:
    """Install Google's exact stable standalone Linux AAPT2 with an integrity receipt."""

    trust_boundary = _prepare_destination(destination, boundary)
    staging, target, previous = _package_paths(destination, AAPT2_PACKAGE_DIRECTORY)
    _clear_staging(staging)
    ensure_private_directory(staging, boundary=trust_boundary)
    artifact = staging / f"aapt2-{AAPT2_VERSION}-linux.jar"
    try:
        artifact_bytes = _download_pinned_file(
            AAPT2_SOURCE,
            artifact,
            AAPT2_ARCHIVE_SHA256,
            opener=opener,
            progress=progress,
        )
        with zipfile.ZipFile(artifact) as package:
            members = package.infolist()
            names = {member.filename for member in members}
            if (
                len(members) > 16
                or names != {"META-INF/", "META-INF/MANIFEST.MF", "aapt2", "NOTICE"}
                or sum(member.file_size for member in members) > MAX_GOOGLE_MAVEN_EXPANDED_BYTES
                or package.testzip() is not None
            ):
                raise ValueError("official AAPT2 artifact failed structural validation")
            executable_bytes = package.read("aapt2")
            notice_bytes = package.read("NOTICE")
        if (
            not executable_bytes.startswith(b"\x7fELF")
            or b"Apache License" not in notice_bytes[:32_000]
        ):
            raise ValueError("official AAPT2 artifact contents are invalid")
        artifact.unlink()
        executable = staging / "aapt2"
        notice = staging / "NOTICE"
        atomic_write_bytes(
            executable,
            executable_bytes,
            boundary=trust_boundary,
            maximum_bytes=MAX_GOOGLE_MAVEN_EXPANDED_BYTES,
        )
        executable.chmod(0o700)
        atomic_write_bytes(
            notice,
            notice_bytes,
            boundary=trust_boundary,
            maximum_bytes=MAX_GOOGLE_MAVEN_EXPANDED_BYTES,
        )
        executable_digest = _file_sha256(executable)
        sidecar = staging / "aapt2.romverse"
        atomic_write_json(
            sidecar,
            {
                "format": "romverse.managed-tool",
                "schema_version": 1,
                "name": "AAPT2",
                "version": AAPT2_VERSION,
                "source": AAPT2_SOURCE,
                "sha256": executable_digest,
                "executable": "aapt2",
            },
            boundary=trust_boundary,
            maximum_bytes=MAX_RECEIPT_BYTES,
        )
        files = _file_manifest(executable, notice, sidecar)
        atomic_write_json(
            staging / "managed-package.romverse",
            {
                "format": "romverse.managed-package",
                "schema_version": 1,
                "name": "Android AAPT2",
                "version": AAPT2_VERSION,
                "source": AAPT2_SOURCE,
                "license": "Apache-2.0",
                "archive_sha256": AAPT2_ARCHIVE_SHA256,
                "archive_bytes": artifact_bytes,
                "files": files,
            },
            boundary=trust_boundary,
            maximum_bytes=MAX_RECEIPT_BYTES,
        )
        _replace_package(staging, target, previous)
        return target / "aapt2", AAPT2_ARCHIVE_SHA256
    finally:
        _clear_staging(staging)


def install_pinned_apk_verifier(
    destination: Path,
    opener=None,
    *,
    boundary: Path | None = None,
    progress: DownloadProgress | None = None,
) -> tuple[Path, str]:
    """Install an exact official apksig library and ROMVERSE's verification-only launcher."""

    trust_boundary = _prepare_destination(destination, boundary)
    staging, target, previous = _package_paths(destination, APK_VERIFIER_PACKAGE_DIRECTORY)
    _clear_staging(staging)
    ensure_private_directory(staging, boundary=trust_boundary)
    artifact = staging / APKSIG_JAR
    try:
        artifact_bytes = _download_pinned_file(
            APKSIG_SOURCE,
            artifact,
            APKSIG_ARCHIVE_SHA256,
            opener=opener,
            progress=progress,
        )
        with zipfile.ZipFile(artifact) as package:
            members = package.infolist()
            names = {member.filename for member in members}
            required = {
                "LICENSE",
                "com/android/apksig/ApkVerifier.class",
                "com/android/apksig/ApkVerifier$Builder.class",
                "com/android/apksig/ApkVerifier$Result.class",
            }
            if (
                len(members) > MAX_GOOGLE_MAVEN_ENTRIES
                or not required.issubset(names)
                or sum(member.file_size for member in members) > MAX_GOOGLE_MAVEN_EXPANDED_BYTES
                or package.testzip() is not None
            ):
                raise ValueError("official apksig artifact failed structural validation")
            license_bytes = package.read("LICENSE")
        if b"Apache License" not in license_bytes[:32_000]:
            raise ValueError("official apksig license evidence is invalid")
        license_path = staging / "LICENSE.apksig"
        source_path = staging / APK_VERIFIER_SOURCE_FILE
        launcher = staging / APK_VERIFIER_LAUNCHER_FILE
        atomic_write_bytes(
            license_path,
            license_bytes,
            boundary=trust_boundary,
            maximum_bytes=MAX_GOOGLE_MAVEN_EXPANDED_BYTES,
        )
        atomic_write_bytes(
            source_path,
            APK_VERIFIER_JAVA,
            boundary=trust_boundary,
            maximum_bytes=MAX_GOOGLE_MAVEN_ARTIFACT_BYTES,
        )
        atomic_write_bytes(
            launcher,
            APK_VERIFIER_LAUNCHER,
            boundary=trust_boundary,
            maximum_bytes=MAX_GOOGLE_MAVEN_ARTIFACT_BYTES,
        )
        launcher.chmod(0o700)
        launcher_digest = _file_sha256(launcher)
        sidecar = staging / "apksigner.romverse"
        atomic_write_json(
            sidecar,
            {
                "format": "romverse.managed-tool",
                "schema_version": 1,
                "name": "APK Signer",
                "version": f"{APKSIG_VERSION} verification-only",
                "source": APKSIG_SOURCE,
                "sha256": launcher_digest,
                "executable": APK_VERIFIER_LAUNCHER_FILE,
            },
            boundary=trust_boundary,
            maximum_bytes=MAX_RECEIPT_BYTES,
        )
        files = _file_manifest(artifact, license_path, source_path, launcher, sidecar)
        atomic_write_json(
            staging / "managed-package.romverse",
            {
                "format": "romverse.managed-package",
                "schema_version": 1,
                "name": "Android APK Signature Verifier",
                "version": APKSIG_VERSION,
                "source": APKSIG_SOURCE,
                "capability": "verification-only",
                "license": "Apache-2.0",
                "artifact_sha256": APKSIG_ARCHIVE_SHA256,
                "artifact_bytes": artifact_bytes,
                "files": files,
            },
            boundary=trust_boundary,
            maximum_bytes=MAX_RECEIPT_BYTES,
        )
        _replace_package(staging, target, previous)
        return target / APK_VERIFIER_LAUNCHER_FILE, APKSIG_ARCHIVE_SHA256
    finally:
        _clear_staging(staging)


def _download_pinned_file(
    source: str,
    target: Path,
    expected_sha256: str,
    *,
    opener=None,
    progress: DownloadProgress | None = None,
) -> int:
    open_url = opener or urllib.request.urlopen
    digest = hashlib.sha256()
    total = 0
    with open_url(source, timeout=90) as response, target.open("xb") as stream:
        expected_bytes = _content_length(response)
        if expected_bytes > MAX_GOOGLE_MAVEN_ARTIFACT_BYTES:
            raise ValueError("official Google Maven artifact exceeds its size boundary")
        if progress is not None:
            progress(0, expected_bytes)
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_GOOGLE_MAVEN_ARTIFACT_BYTES:
                raise ValueError("official Google Maven artifact exceeds its size boundary")
            digest.update(chunk)
            stream.write(chunk)
            if progress is not None:
                progress(total, expected_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    if progress is not None:
        progress(0, 0)
    if total == 0 or digest.hexdigest() != expected_sha256:
        raise ValueError("official Google Maven artifact does not match ROMVERSE's pinned SHA-256")
    target.chmod(0o600)
    return total


def _prepare_destination(destination: Path, boundary: Path | None) -> Path:
    trust_boundary = Path(os.path.abspath(boundary or destination.parent))
    if boundary is None:
        while not trust_boundary.exists() and trust_boundary != trust_boundary.parent:
            trust_boundary = trust_boundary.parent
    ensure_private_directory(destination, boundary=trust_boundary)
    return trust_boundary


def _package_paths(destination: Path, name: str) -> tuple[Path, Path, Path]:
    return (
        destination / f".{name}.extracting",
        destination / name,
        destination / f".{name}.previous",
    )


def _replace_package(staging: Path, target: Path, previous: Path) -> None:
    with suppress(OSError):
        shutil.rmtree(previous)
    if target.exists() or target.is_symlink():
        os.replace(target, previous)
    try:
        os.replace(staging, target)
    except OSError:
        if previous.exists() and not target.exists():
            os.replace(previous, target)
        raise
    with suppress(OSError):
        shutil.rmtree(previous)


def _clear_staging(staging: Path) -> None:
    with suppress(OSError):
        shutil.rmtree(staging)


def _file_manifest(*paths: Path) -> dict[str, str]:
    return {path.name: _file_sha256(path) for path in paths}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _content_length(response: object) -> int:
    headers = getattr(response, "headers", None)
    if headers is None:
        return 0
    try:
        return max(0, int(headers.get("Content-Length", "0")))
    except (AttributeError, TypeError, ValueError):
        return 0
