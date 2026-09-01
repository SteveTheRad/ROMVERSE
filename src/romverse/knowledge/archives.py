"""Structured ROMVERSE Archives catalog, validation, and bounded local retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

ALL_CATEGORIES = "ALL KNOWLEDGE"
CATEGORIES = (
    "CONNECTIVITY & ADB",
    "TOOLS & HOST",
    "FIRMWARE INTAKE",
    "FILESYSTEMS & PARTITIONS",
    "BUILD & RECIPES",
    "BOOT & SECURITY",
    "APPS & PACKAGES",
    "RECOVERY & GUARDIAN",
    "DIAGNOSTICS & HEALTH",
    "ROMVERSE WORKFLOWS",
)

CANONICAL_ROUTES = frozenset(
    {
        "command_deck",
        "rom_studio",
        "quantum_optimizer",
        "device_atlas",
        "recovery_bay",
        "guardian_core",
        "app_launchpad",
        "time_machine",
        "activity_center",
        "archives",
        "live_console",
        "nexus",
        "forge_arsenal",
        "companion_link",
        "about",
    }
)


@dataclass(frozen=True, slots=True)
class ArchiveSource:
    label: str
    authority: str
    url: str = ""
    reviewed_on: str = "2026-09-01"


@dataclass(frozen=True, slots=True)
class ArchiveArticle:
    key: str
    title: str
    category: str
    meaning: str
    checks: tuple[str, ...]
    fix_steps: tuple[str, ...]
    verification: tuple[str, ...]
    tags: tuple[str, ...]
    route: str
    evidence: str
    automation: str
    source: ArchiveSource

    @property
    def plain_text(self) -> str:
        sections = [f"WHAT IT MEANS\n{self.meaning}"]
        if self.checks:
            sections.append("CHECK FIRST\n" + "\n".join(f"• {item}" for item in self.checks))
        if self.fix_steps:
            sections.append("KNOWN SAFE FIX\n" + "\n".join(f"• {item}" for item in self.fix_steps))
        if self.verification:
            sections.append(
                "VERIFY THE RESULT\n" + "\n".join(f"• {item}" for item in self.verification)
            )
        sections.extend(
            (
                f"EVIDENCE\n{self.evidence}",
                f"AUTOMATION BOUNDARY\n{self.automation}",
                f"SOURCE\n{self.source.label}  •  {self.source.authority}"
                + (f"\n{self.source.url}" if self.source.url else ""),
            )
        )
        return "\n\n".join(sections)

    @property
    def search_document(self) -> str:
        return " ".join(
            (
                self.title,
                self.category,
                self.meaning,
                *self.checks,
                *self.fix_steps,
                *self.verification,
                *self.tags,
                self.evidence,
                self.automation,
                self.source.label,
            )
        )


@dataclass(frozen=True, slots=True)
class ArchiveMatch:
    article: ArchiveArticle
    score: int


ADB_SOURCE = ArchiveSource(
    "Android Debug Bridge (adb)",
    "OFFICIAL ANDROID",
    "https://developer.android.com/tools/adb",
)
PACKAGE_SOURCE = ArchiveSource(
    "Android PackageManager install status definitions",
    "AOSP SOURCE",
    "https://android.googlesource.com/platform/frameworks/base/+/android16-qpr2-release/core/java/android/content/pm/PackageManager.java",
)
DYNAMIC_SOURCE = ArchiveSource(
    "AOSP dynamic partitions",
    "OFFICIAL AOSP",
    "https://source.android.com/docs/core/ota/dynamic_partitions",
)
SUPER_SIZE_SOURCE = ArchiveSource(
    "AOSP super partition sizing",
    "OFFICIAL AOSP",
    "https://source.android.com/docs/core/ota/dynamic_partitions/how_to_size_super",
)
AVB_SOURCE = ArchiveSource(
    "Android Verified Boot",
    "OFFICIAL AOSP",
    "https://source.android.com/docs/security/features/verifiedboot/avb",
)
BOOT_FLOW_SOURCE = ArchiveSource(
    "Verified Boot flow",
    "OFFICIAL AOSP",
    "https://source.android.com/docs/security/features/verifiedboot/boot-flow",
)
EROFS_SOURCE = ArchiveSource(
    "AOSP EROFS",
    "OFFICIAL AOSP",
    "https://source.android.com/docs/core/architecture/kernel/erofs",
)
SELINUX_SOURCE = ArchiveSource(
    "Build SELinux policy",
    "OFFICIAL AOSP",
    "https://source.android.com/docs/security/features/selinux/build",
)
BUILD_SOURCE = ArchiveSource(
    "Build Android",
    "OFFICIAL AOSP",
    "https://source.android.com/docs/setup/build/building",
)
ANDROID_BUILD_TOOLS_SOURCE = ArchiveSource(
    "Android SDK Build Tools",
    "OFFICIAL ANDROID",
    "https://developer.android.com/tools/releases/build-tools",
)
OTA_SOURCE = ArchiveSource(
    "Build OTA packages",
    "OFFICIAL AOSP",
    "https://source.android.com/docs/core/ota/tools",
)
ANDROID_NETWORK_SOURCE = ArchiveSource(
    "Fix internet connection problems on Android devices",
    "OFFICIAL ANDROID SUPPORT",
    "https://support.google.com/android/answer/2651367",
)
ANDROID_SCREEN_SOURCE = ArchiveSource(
    "Fix a screen that isn't working right on Android",
    "OFFICIAL ANDROID SUPPORT",
    "https://support.google.com/android/answer/7666942",
)
ANDROID_APP_SOURCE = ArchiveSource(
    "Find problem apps with Android safe mode",
    "OFFICIAL ANDROID SUPPORT",
    "https://support.google.com/android/answer/7665064",
)
ANDROID_STORAGE_SOURCE = ArchiveSource(
    "Free up storage on your Android device",
    "OFFICIAL ANDROID SUPPORT",
    "https://support.google.com/android/answer/7431795",
)
ANDROID_PERFORMANCE_SOURCE = ArchiveSource(
    "Speed up a slow Android device",
    "OFFICIAL ANDROID SUPPORT",
    "https://support.google.com/android/answer/7667018",
)
ANDROID_UPDATE_SOURCE = ArchiveSource(
    "Check and update the Android version",
    "OFFICIAL ANDROID SUPPORT",
    "https://support.google.com/android/answer/7680439",
)
PIXEL_BATTERY_SOURCE = ArchiveSource(
    "Google Pixel battery and heat safety guidance",
    "OFFICIAL GOOGLE • PIXEL-SCOPED",
    "https://support.google.com/pixelphone/answer/6090612",
)
GOOGLE_DEVICE_CATALOG_SOURCE = ArchiveSource(
    "Google Play supported Android device catalog",
    "OFFICIAL GOOGLE • IDENTITY ONLY",
    "https://storage.googleapis.com/play_public/supported_devices.csv",
)
ROMVERSE_SOURCE = ArchiveSource(
    "ROMVERSE tested safety and evidence contracts",
    "ROMVERSE VERIFIED",
)
FIELD_SOURCE = ArchiveSource(
    "Recorded ROMVERSE HyperOS reference workflow",
    "FIELD VERIFIED • MODEL/BUILD SCOPED",
)


def _fix(
    key: str,
    title: str,
    category: str,
    meaning: str,
    *,
    checks: tuple[str, ...],
    fix_steps: tuple[str, ...],
    verification: tuple[str, ...],
    tags: tuple[str, ...],
    route: str,
    evidence: str,
    automation: str,
    source: ArchiveSource,
) -> ArchiveArticle:
    return ArchiveArticle(
        key,
        title,
        category,
        meaning,
        checks,
        fix_steps,
        verification,
        tags,
        route,
        evidence,
        automation,
        source,
    )


KNOWN_FIXES = (
    _fix(
        "adb-multiple-targets",
        "ADB error: more than one device or emulator",
        "CONNECTIVITY & ADB",
        "ADB found multiple transports and the request did not identify one exact target.",
        checks=(
            "Open Device Portal and identify every listed physical device and emulator.",
            "Confirm the intended phone is authorized; do not choose by list position alone.",
        ),
        fix_steps=(
            "Disconnect or stop unrelated transports, then rescan.",
            "Let ROMVERSE bind read-only work to the selected device identity instead of issuing an unscoped adb command.",
        ),
        verification=("The fresh Device Portal scan shows one intended authorized target.",),
        tags=("adb more than one device emulator", "multiple devices", "more than one device"),
        route="command_deck",
        evidence="The official adb contract requires an exact target when multiple transports exist.",
        automation="READ-ONLY RESCAN AVAILABLE • NO AUTOMATIC TARGET SELECTION",
        source=ADB_SOURCE,
    ),
    _fix(
        "adb-unauthorized",
        "ADB authorization is pending on the phone",
        "CONNECTIVITY & ADB",
        "The USB transport exists, but Android has not accepted this computer's debugging identity.",
        checks=(
            "Unlock the phone and keep its screen awake while the cable remains connected.",
            "Confirm the host entry is unauthorized rather than offline or missing.",
        ),
        fix_steps=(
            "Accept the RSA fingerprint prompt on the phone, then run a fresh read-only Device Portal scan.",
            "If no prompt appears, revoke stale USB debugging authorizations on the phone, reconnect once, and review the new fingerprint before accepting it.",
        ),
        verification=(
            "Device Portal reports the same phone identity in the authorized device state.",
        ),
        tags=("adb unauthorized", "device unauthorized", "rsa prompt", "usb debugging approval"),
        route="command_deck",
        evidence="The official adb workflow requires the user to acknowledge the computer's RSA key on the device.",
        automation="PHONE APPROVAL IS MANUAL • READ-ONLY RESCAN AVAILABLE",
        source=ADB_SOURCE,
    ),
    _fix(
        "adb-device-offline",
        "ADB device stays offline after reconnect",
        "CONNECTIVITY & ADB",
        "ADB remembers a transport, but that transport is not currently responding to host requests.",
        checks=(
            "Unlock the phone and inspect whether its USB connection is repeatedly reconnecting.",
            "Use one known data cable and a direct USB port before changing host software.",
        ),
        fix_steps=(
            "Reconnect once and perform a fresh read-only scan.",
            "Use Recovery Bay's bounded host-daemon repair only when the collected evidence identifies the host daemon as the fault.",
        ),
        verification=("Consecutive scans keep the same device identity in the authorized state.",),
        tags=("adb device offline", "adb offline", "device offline after reconnect"),
        route="recovery_bay",
        evidence="ADB distinguishes an offline transport from an unauthorized or absent transport.",
        automation="SAFE RESCAN • HOST REPAIR REQUIRES EXACT REVIEW",
        source=ADB_SOURCE,
    ),
    _fix(
        "adb-no-device",
        "ADB cannot find a connected device",
        "CONNECTIVITY & ADB",
        "The host has no usable Android debugging transport to identify or inspect.",
        checks=(
            "Confirm USB debugging, data mode, a data-capable cable, and an unlocked phone.",
            "On Linux inspect udev access; on Windows inspect the Android/OEM USB driver.",
        ),
        fix_steps=(
            "Correct the evidenced cable, mode, driver, or host-permission problem, then reconnect once.",
            "Verify Platform Tools in Forge Arsenal if adb itself is unavailable.",
        ),
        verification=("adb and Device Portal independently show the intended phone identity.",),
        tags=("adb no devices", "no devices attached", "device not found", "adb empty list"),
        route="command_deck",
        evidence="A missing transport cannot be safely inferred as a particular phone or failure cause.",
        automation="HOST TOOL CHECK AND READ-ONLY RESCAN ONLY",
        source=ADB_SOURCE,
    ),
    _fix(
        "adb-server-version-mismatch",
        "ADB server and client version mismatch",
        "CONNECTIVITY & ADB",
        "Different adb copies are competing, so the client and background server cannot share one protocol version reliably.",
        checks=(
            "Inspect Forge Arsenal for the exact active adb path and version.",
            "Check whether Android Studio, a system package, and a downloaded Platform Tools copy are all on PATH.",
        ),
        fix_steps=(
            "Choose one verified current Platform Tools installation and remove stale PATH precedence.",
            "Use Recovery Bay's typed ADB host recovery to restart only the host daemon after Guardian review.",
        ),
        verification=(
            "A fresh tool inventory and adb scan use the same verified executable path.",
        ),
        tags=("adb server version mismatch", "daemon version mismatch", "client server mismatch"),
        route="recovery_bay",
        evidence="ROMVERSE verifies the active executable and has a bounded host-only daemon repair.",
        automation="TYPED HOST REPAIR • EXACT GUARDIAN REVIEW REQUIRED",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "adb-transport-timeout",
        "ADB transport timeout or broken connection",
        "CONNECTIVITY & ADB",
        "The host saw a transport but a bounded probe did not complete before its deadline.",
        checks=(
            "Keep the phone unlocked and inspect its current authorized/offline state.",
            "Remove USB hubs and try a known data-capable cable and direct port.",
            "Check for a reconnect loop before repeating any operation.",
        ),
        fix_steps=(
            "Reconnect once and run a fresh read-only scan.",
            "If the host daemon is the evidenced fault, use the bounded Recovery Bay host repair.",
        ),
        verification=(
            "Several consecutive read-only scans retain the same authorized device identity.",
        ),
        tags=("adb timeout", "transport failed", "broken pipe", "device disconnected"),
        route="recovery_bay",
        evidence="ROMVERSE treats probe timeouts as failed evidence and never assumes success from elapsed time.",
        automation="SAFE RESCAN • HOST DAEMON REPAIR REQUIRES REVIEW",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "usb-charge-only",
        "USB cable connects power but no ADB data",
        "CONNECTIVITY & ADB",
        "A charge-only cable, wrong USB mode, damaged port, or host permission can provide power without an adb transport.",
        checks=(
            "Confirm the phone exposes USB debugging and a data/file-transfer mode.",
            "Try a known data cable and a direct motherboard port.",
            "On Linux inspect udev access; on Windows inspect the OEM/Android USB driver.",
        ),
        fix_steps=(
            "Correct the physical/driver issue, reconnect, unlock, and accept the RSA prompt.",
        ),
        verification=("adb devices and Device Portal show the same authorized phone.",),
        tags=("charge only cable", "usb no data", "adb no device cable"),
        route="command_deck",
        evidence="ADB cannot diagnose a transport the operating system never exposes.",
        automation="MANUAL HOST/USB FIX • READ-ONLY RESCAN AVAILABLE",
        source=ADB_SOURCE,
    ),
    _fix(
        "linux-udev-permission",
        "Linux ADB USB permission denied",
        "TOOLS & HOST",
        "The host can see the USB device but the current account lacks permission to open it.",
        checks=(
            "Confirm the vendor/product USB identity and that adb is not being run as root.",
            "Inspect the distribution's Android udev rules and current group membership.",
        ),
        fix_steps=(
            "Install or correct the distribution/OEM udev rule, reload rules, then reconnect the phone.",
            "Keep ROMVERSE under the normal user account so workspace ownership remains consistent.",
        ),
        verification=("The normal user can run a read-only adb devices scan without sudo.",),
        tags=("udev", "insufficient permissions for device", "usb permission denied linux"),
        route="forge_arsenal",
        evidence="Host permission is distinct from Android's RSA authorization state.",
        automation="OPERATING-SYSTEM AUTHORIZATION IS VISIBLE AND MANUAL",
        source=ADB_SOURCE,
    ),
    _fix(
        "managed-tool-receipt-mismatch",
        "Managed tool changed after verification",
        "TOOLS & HOST",
        "A managed executable no longer matches the content digest in its activation receipt.",
        checks=(
            "Preserve the changed tool and receipt for review.",
            "Confirm no linked binary or unexpected file entered the managed package directory.",
        ),
        fix_steps=(
            "Deactivate the changed tool immediately.",
            "Use Forge Arsenal to download and validate a fresh approved package; never bless the changed bytes in place.",
        ),
        verification=(
            "A fresh inventory rehashes every required executable and activates only the matching receipt.",
        ),
        tags=("tool hash mismatch", "managed receipt invalid", "executable changed"),
        route="forge_arsenal",
        evidence="ROMVERSE's managed toolchain is content-addressed and reverified before activation.",
        automation="SAFE DEACTIVATION • VERIFIED REPROVISIONING ONLY",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "payload-dumper-missing",
        "payload.bin found but Payload Dumper is missing",
        "TOOLS & HOST",
        "The OTA structure is recognized, but no receipt-verified payload extraction tool is active.",
        checks=("Confirm the protected source really contains one bounded payload.bin.",),
        fix_steps=(
            "Choose Resolve partition tools in ROM Studio.",
            "Let Forge Arsenal select the approved host asset, require its published digest, and validate the archive before activation.",
        ),
        verification=(
            "ROM Studio freshly verifies Payload Dumper and only then re-enters Partition Atlas.",
        ),
        tags=("payload dumper missing", "payload.bin tool unavailable", "extract ota payload"),
        route="forge_arsenal",
        evidence="ROMVERSE implements a scoped resolver tied to the current OTA workflow.",
        automation="VERIFIED TOOL RESOLUTION AVAILABLE • NO FIRMWARE CHANGE",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "filesystem-reader-missing",
        "EXT4 or EROFS filesystem reader is missing",
        "TOOLS & HOST",
        "The partition image format is known, but the corresponding receipt-verified reader is not active.",
        checks=(
            "Confirm Partition Atlas reports the detected filesystem and exact required tool profile.",
        ),
        fix_steps=(
            "Resolve only the format-scoped filesystem tools through Forge Arsenal, then retry expansion.",
        ),
        verification=(
            "The complete tool inventory passes and Partition Atlas reads the image without changing it.",
        ),
        tags=("erofs tool missing", "ext4 reader missing", "filesystem unavailable", "fsck erofs"),
        route="forge_arsenal",
        evidence="ROMVERSE resumes only after the required reader is freshly verified.",
        automation="VERIFIED TOOL RESOLUTION AVAILABLE • IMAGE REMAINS READ-ONLY",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "android-sdk-build-tools-not-discovered",
        "Android SDK is installed but AAPT2 or APK Signer is still missing",
        "TOOLS & HOST",
        "App Launchpad needs AAPT2 to decode package identity and a cryptographic verifier for "
        "APK signing evidence. On Linux x86-64, ROMVERSE can install exact Apache-licensed "
        "Google Maven artifacts for both inspection capabilities without accepting an Android "
        "SDK license. Full Android SDK Build Tools remain a separate requirement for creating "
        "APK signatures, and an existing complete SDK revision is still discovered automatically.",
        checks=(
            "Decide whether the workflow needs package inspection and signature verification only, or the full SDK capability to create an APK signature.",
            "For the managed Linux route, confirm Java 11 or newer is ready and allow only the pinned Google Maven AAPT2 and apksig sources shown by Forge Arsenal.",
            "For an installed SDK, confirm one stable build-tools revision contains aapt2, apksigner, and lib/apksigner.jar together.",
            "Check ANDROID_SDK_ROOT, ANDROID_HOME, and the standard Android Studio SDK folder; run each tool's version interface rather than trusting a filename.",
        ),
        fix_steps=(
            "Choose Install and verify requirements in Forge Arsenal. On supported Linux hosts ROMVERSE downloads the exact pinned stable AAPT2 binary and official apksig library, preserves their Apache notices, and activates them only while every receipt hash matches.",
            "Use the managed verification-only apksig launcher for App Launchpad and official root-manager inspection; it cannot sign an APK or handle a private key.",
            "When signing is genuinely required, use Android Studio SDK Manager or sdkmanager to install one complete stable Build Tools revision and accept its license in that user-controlled flow.",
            "Keep an installed SDK directory intact, then choose Re-scan toolchain; ROMVERSE prefers complete stable revisions and falls back when a newer revision cannot start.",
        ),
        verification=(
            "Forge Arsenal reports the exact managed versions and labels apksig verification-only, or reports paired paths from one complete installed Build Tools revision.",
            "App Launchpad decodes package identity and validates the signer certificate SHA-256 before Guardian review.",
            "Changing the managed executable, library, Java source, notice, sidecar, or receipt removes its directory from activation on the next scan.",
            "ROMVERSE never claims the managed verifier can sign, never accepts an Android SDK license, and never creates or stores a private signing key.",
        ),
        tags=(
            "aapt2 missing",
            "apksigner missing",
            "apksig verification only",
            "managed aapt2",
            "google maven apk tools",
            "android sdk build tools",
            "android studio sdk not detected",
            "ANDROID_SDK_ROOT",
            "ANDROID_HOME",
            "app launchpad package identity",
        ),
        route="forge_arsenal",
        evidence="ROMVERSE pins the stable Google Maven artifact URLs and SHA-256 values, validates their Apache notices and required structures, receipts every activated file, and also discovers complete paired Build Tools revisions from official SDK locations.",
        automation="PINNED APACHE-LICENSED INSPECTION-TOOL DOWNLOAD OR READ-ONLY SDK DISCOVERY • NO SDK LICENSE ACCEPTANCE, APK SIGNING, PRIVATE KEY, BUILD, OR PHONE ACTION",
        source=ANDROID_BUILD_TOOLS_SOURCE,
    ),
    _fix(
        "tool-download-digest-mismatch",
        "Downloaded tool archive digest mismatch",
        "TOOLS & HOST",
        "Downloaded bytes do not match the approved publisher digest, so authenticity and completeness are unconfirmed.",
        checks=(
            "Preserve the URL, expected digest, observed digest, and receipt failure without opening the archive.",
        ),
        fix_steps=(
            "Discard the staged candidate and retry only from the approved official source after checking current release metadata.",
        ),
        verification=(
            "The exact archive digest and every extracted executable digest match before activation.",
        ),
        tags=("sha256 mismatch download", "archive digest mismatch", "tool verification failed"),
        route="forge_arsenal",
        evidence="A mismatched artifact is never activated merely because its filename is expected.",
        automation="FAIL-CLOSED STAGING CLEANUP • NO EXECUTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "firmware-source-changed",
        "Firmware source changed during import",
        "FIRMWARE INTAKE",
        "The selected source identity changed while ROMVERSE was copying or hashing it.",
        checks=(
            "Compare the source's device/inode, size, timestamps, and complete digest captured across the import boundary.",
        ),
        fix_steps=(
            "Discard the incomplete staging copy, preserve the original source, and start a new import from stable bytes.",
        ),
        verification=(
            "The protected original's saved SHA-256 re-verifies after atomic publication.",
        ),
        tags=("source changed during copy", "firmware hash race", "import source mismatch"),
        route="rom_studio",
        evidence="ROMVERSE binds import completion to the same source identity observed before copying.",
        automation="SAFE STAGING DISCARD • USER RESELECTS THE SOURCE",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "firmware-encrypted-archive",
        "Encrypted firmware archive cannot be inspected safely",
        "FIRMWARE INTAKE",
        "Archive metadata indicates encrypted members, so ROMVERSE cannot prove bounded contents before extraction.",
        checks=(
            "Confirm the file came from an authoritative OEM or maintainer source and was not renamed.",
        ),
        fix_steps=(
            "Obtain an unencrypted, hash-published source or inspect it in an isolated manual workflow; do not enter passwords into an unverified extractor path.",
        ),
        verification=(
            "A fresh source passes bounded metadata inspection before any tree is materialized.",
        ),
        tags=("encrypted zip", "password protected firmware", "archive encrypted"),
        route="rom_studio",
        evidence="ROMVERSE rejects encrypted entries because expanded scope cannot be verified first.",
        automation="BLOCKED • MANUAL AUTHORITATIVE SOURCE REQUIRED",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "firmware-unsafe-entry",
        "Firmware archive contains traversal, link, or special entries",
        "FIRMWARE INTAKE",
        "An archive member could escape the contained working tree or materialize an unsafe filesystem object.",
        checks=("Inspect the rejected normalized member name and type without extracting it.",),
        fix_steps=(
            "Reject the archive and obtain a clean authoritative copy; never rewrite unsafe paths and continue as if provenance were unchanged.",
        ),
        verification=(
            "Every accepted member remains a regular file or directory beneath private staging.",
        ),
        tags=("zip slip", "path traversal", "archive symlink", "special file firmware"),
        route="rom_studio",
        evidence="ROMVERSE's bounded extractor rejects traversal, links, and special files before publication.",
        automation="FAIL-CLOSED • NO EXTRACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "firmware-unsupported-container",
        "Firmware container is unsupported or ambiguous",
        "FIRMWARE INTAKE",
        "The bytes and bounded structure do not establish one supported OTA, factory archive, or raw-image route.",
        checks=(
            "Keep the original filename, size, hash, and first structure report.",
            "Confirm the exact device/build source and whether an outer vendor container is expected.",
        ),
        fix_steps=(
            "Use an authoritative source in a supported format or add a reviewed detector fixture; never guess from the extension.",
        ),
        verification=(
            "Automatic Detection selects one route from bytes and structure with no conflicting finding.",
        ),
        tags=("unknown firmware format", "unsupported archive", "ambiguous container"),
        route="rom_studio",
        evidence="Format detection is evidence-backed and cannot be overridden by renaming a file.",
        automation="GUIDANCE ONLY • DETECTOR UPDATE REQUIRES REVIEWED FIXTURES",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "payload-bin-missing",
        "OTA package has no usable payload.bin",
        "FIRMWARE INTAKE",
        "The source was expected to follow an A/B OTA payload route, but the bounded archive inventory did not find one unambiguous payload.bin.",
        checks=(
            "Confirm whether the package is a full OTA, incremental OTA, recovery package, or vendor wrapper.",
        ),
        fix_steps=(
            "Return to Automatic Detection or obtain the correct full package; do not fabricate an empty payload or reuse one from another build.",
        ),
        verification=(
            "The protected source report binds exactly one contained payload.bin to the package hash.",
        ),
        tags=("payload.bin missing", "no payload bin", "ota payload not found"),
        route="rom_studio",
        evidence="AOSP OTA tooling treats package structure and target metadata as part of the update contract.",
        automation="BLOCKED • CORRECT SOURCE REQUIRED",
        source=OTA_SOURCE,
    ),
    _fix(
        "sparse-image-conversion",
        "Android sparse image needs conversion before byte inspection",
        "FILESYSTEMS & PARTITIONS",
        "The image uses Android sparse chunks, so its file size is not the raw partition extent and direct filesystem tools may reject it.",
        checks=("Verify the sparse header and calculated expanded size before allocating space.",),
        fix_steps=(
            "Use a receipt-verified sparse converter in private staging, then inspect the raw result without replacing the protected source.",
        ),
        verification=(
            "The raw size and content digest are recorded and the sparse source remains unchanged.",
        ),
        tags=("simg2img", "android sparse image", "invalid sparse file format"),
        route="rom_studio",
        evidence="AOSP super sizing guidance requires calculations from unsparsed image sizes.",
        automation="SAFE LOCAL CONVERSION AFTER SPACE PREFLIGHT",
        source=SUPER_SIZE_SOURCE,
    ),
    _fix(
        "erofs-read-only-image",
        "EROFS image is read-only by design",
        "FILESYSTEMS & PARTITIONS",
        "EROFS is a compressed read-only filesystem; treating it like a writable EXT4 tree is an invalid workflow.",
        checks=("Confirm the detected filesystem and compressor/pcluster metadata.",),
        fix_steps=(
            "Extract into an isolated working tree, apply reviewed changes there, and rebuild a new EROFS image with the source contract preserved.",
        ),
        verification=(
            "Reinspect the rebuilt image, size, compression settings, tree metadata, and AVB descriptors.",
        ),
        tags=("erofs read only", "erofs extraction", "cannot mount erofs rw", "mkfs erofs"),
        route="rom_studio",
        evidence="AOSP defines EROFS as read-only and documents its Android build/compression contract.",
        automation="LOCAL EXTRACT/REBUILD ONLY • NEVER MODIFY SOURCE IN PLACE",
        source=EROFS_SOURCE,
    ),
    _fix(
        "filesystem-image-overflow",
        "Rebuilt filesystem image exceeds its partition budget",
        "FILESYSTEMS & PARTITIONS",
        "The candidate filesystem cannot fit the exact logical partition or dynamic-group allocation.",
        checks=(
            "Compare unsparsed image size, filesystem free space, logical partition size, group maximum, and super overhead.",
        ),
        fix_steps=(
            "Reduce reviewed content or rebuild with contract-compatible settings; never truncate an image or silently enlarge a partition.",
        ),
        verification=(
            "The complete candidate fits with the required metadata overhead and all unchanged partitions retain their source extents.",
        ),
        tags=(
            "image too large",
            "partition size exceeded",
            "not enough space super",
            "lpmake overflow",
        ),
        route="rom_studio",
        evidence="Dynamic partitions share super capacity; every group and physical bound must remain valid.",
        automation="BLOCKED UNTIL A NEW REVIEWED BUILD PLAN EXISTS",
        source=SUPER_SIZE_SOURCE,
    ),
    _fix(
        "dynamic-super-layout-mismatch",
        "Dynamic super metadata or group layout mismatch",
        "FILESYSTEMS & PARTITIONS",
        "Candidate metadata slots, groups, A/B attributes, or logical partition extents differ from the protected source contract.",
        checks=(
            "Compare LP Dump results for source and candidate, including metadata slots, group maxima, attributes, and extents.",
        ),
        fix_steps=(
            "Regenerate lpmake inputs from the exact source layout; do not reuse another model/build's command line.",
        ),
        verification=(
            "LP Dump and LP Unpack reproduce every expected logical partition and unchanged bytes match their originals.",
        ),
        tags=(
            "lpmake failed",
            "super metadata mismatch",
            "dynamic partition group mismatch",
            "lp metadata",
        ),
        route="rom_studio",
        evidence="Dynamic partition metadata is device/build specific and controls shared super allocation.",
        automation="LOCAL REBUILD GUIDANCE • NO FLASH AUTHORITY",
        source=DYNAMIC_SOURCE,
    ),
    _fix(
        "logical-partition-byte-mismatch",
        "Unchanged logical partition differs after super rebuild",
        "FILESYSTEMS & PARTITIONS",
        "A partition that was outside the approved change scope no longer matches its protected source bytes.",
        checks=(
            "Unpack both source and candidate super images and hash every logical partition independently.",
        ),
        fix_steps=(
            "Reject the candidate, rebuild from the known-good source layout, and include only the intended changed image.",
        ),
        verification=(
            "Every out-of-scope partition is byte-identical and the intended partition has a reviewed provenance delta.",
        ),
        tags=("lp unpack mismatch", "partition hash changed", "unchanged image mismatch"),
        route="rom_studio",
        evidence="This comparison was required by the field-verified HyperOS reference workflow.",
        automation="AUTOMATIC REJECTION IS SAFE • REBUILD REQUIRES REVIEW",
        source=FIELD_SOURCE,
    ),
    _fix(
        "avb-footer-mismatch",
        "AVB footer, salt, root digest, or descriptor mismatch",
        "BOOT & SECURITY",
        "The rebuilt image no longer matches the AVB metadata contract bound to the protected source and candidate plan.",
        checks=(
            "Compare algorithm, key identity, salt, rollback index, hashtree root digest, footer size, and chained descriptors.",
        ),
        fix_steps=(
            "Stop readiness, restore the correct source metadata inputs, and rebuild the descriptor chain; never disable verification as a generic fix.",
        ),
        verification=(
            "Fresh AVB inspection deterministically matches every expected descriptor and candidate image digest.",
        ),
        tags=("avb digest mismatch", "hashtree error", "avb footer", "root digest mismatch"),
        route="rom_studio",
        evidence="AVB defines signed partition metadata and rollback protection as part of the boot chain.",
        automation="FAIL-CLOSED VERIFICATION • NO AUTOMATIC BYPASS",
        source=AVB_SOURCE,
    ),
    _fix(
        "vbmeta-chain-mismatch",
        "vbmeta descriptor chain does not match rebuilt partitions",
        "BOOT & SECURITY",
        "A top-level or chained vbmeta image describes different partition bytes, keys, or rollback metadata than the candidate contains.",
        checks=(
            "Inspect all descriptors recursively and bind each to the corresponding exact image digest.",
        ),
        fix_steps=(
            "Regenerate only the approved subordinate metadata using the exact device/build policy; preserve signed top-level metadata unless a verified contract explicitly says otherwise.",
        ),
        verification=(
            "The full descriptor graph resolves without missing, duplicate, or stale partition bindings.",
        ),
        tags=("vbmeta mismatch", "descriptor chain", "avbtool verify image failed"),
        route="rom_studio",
        evidence="Historical topology from one build is reference-only and cannot authorize another build.",
        automation="GUIDANCE AND VERIFICATION ONLY • NO SIGNING/FLASH AUTHORITY",
        source=AVB_SOURCE,
    ),
    _fix(
        "verified-boot-red",
        "Verified Boot red state or dm-verity corruption",
        "BOOT & SECURITY",
        "The boot chain found no valid OS or detected verified data that does not match its expected cryptographic metadata.",
        checks=(
            "Preserve the exact boot warning, slot, build identity, and most recent signed operation receipt.",
        ),
        fix_steps=(
            "Stop repeated boots and use the exact OEM/device recovery route backed by a known-good image and tested rollback plan.",
        ),
        verification=(
            "Recovery evidence and a fresh boot observation confirm a consistent exact build; never relock as a verification shortcut.",
        ),
        tags=("verified boot red", "dm verity corruption", "no valid os", "verity error"),
        route="recovery_bay",
        evidence="AOSP documents red boot states for corruption or no valid OS and requires recovery.",
        automation="DEVICE RECOVERY REQUIRES EXACT GUARDIAN PLAN AND APPROVAL",
        source=BOOT_FLOW_SOURCE,
    ),
    _fix(
        "selinux-neverallow",
        "SELinux neverallow or policy compilation failure",
        "BUILD & RECIPES",
        "A policy rule conflicts with an enforced platform security invariant or the combined policy cannot compile.",
        checks=(
            "Read the first concrete compiler violation and identify the source/vendor policy fragment that introduced it.",
        ),
        fix_steps=(
            "Correct the domain/type design and least-privilege rule; do not delete or bypass upstream neverallow rules.",
        ),
        verification=(
            "The full combined policy compiles and the intended service works under enforcing mode in a controlled test.",
        ),
        tags=(
            "neverallow check failed",
            "sepolicy compile error",
            "avc denied build",
            "selinux policy",
        ),
        route="rom_studio",
        evidence="AOSP compiles merged policy and treats neverallow rules as security invariants.",
        automation="DIAGNOSIS ONLY • SECURITY POLICY CHANGES REQUIRE HUMAN REVIEW",
        source=SELINUX_SOURCE,
    ),
    _fix(
        "file-contexts-missing",
        "Wrong ownership, mode, or SELinux file context after rebuild",
        "BUILD & RECIPES",
        "Materialized files no longer carry the metadata Android services expect, which can cause access denials or userspace boot loops.",
        checks=(
            "Compare source and candidate path ownership, modes, capabilities, xattrs, and file_contexts mapping.",
        ),
        fix_steps=(
            "Restore metadata from the protected baseline or an explicit reviewed recipe; never solve broad denials by making the device permissive.",
        ),
        verification=(
            "Rebuilt metadata inventory matches the plan and enforcing-mode boot logs show no new relevant denial.",
        ),
        tags=(
            "wrong selinux context",
            "file_contexts",
            "permission denied after rebuild",
            "boot loop contexts",
        ),
        route="rom_studio",
        evidence="The field-verified ROM workflow preserved ownership, modes, and SELinux context as build evidence.",
        automation="LOCAL METADATA COMPARISON SAFE • CHANGES REQUIRE RECIPE REVIEW",
        source=FIELD_SOURCE,
    ),
    _fix(
        "aosp-wrong-jdk",
        "Android build uses the wrong Java version",
        "BUILD & RECIPES",
        "The selected platform branch expects a different JDK than the one currently first on PATH.",
        checks=(
            "Capture the branch/API target, reported required Java version, java -version output, and active PATH.",
        ),
        fix_steps=(
            "Install/select the branch-compatible JDK and restart the build environment; do not patch version checks blindly.",
        ),
        verification=(
            "A clean environment reports the expected JDK and the build advances beyond toolchain validation.",
        ),
        tags=("wrong java version", "jdk mismatch", "javac version", "android build error"),
        route="forge_arsenal",
        evidence="AOSP's build guide identifies incompatible JDK selection as a known build failure.",
        automation="HOST TOOLCHAIN SELECTION MAY BE ASSISTED • BUILD RETRY IS EXPLICIT",
        source=BUILD_SOURCE,
    ),
    _fix(
        "soong-ninja-first-error",
        "Soong or Ninja build failure: diagnose the first real error",
        "BUILD & RECIPES",
        "Parallel build output often contains many downstream failures after one earlier compiler, generator, dependency, or space error.",
        checks=(
            "Preserve the complete log and locate the earliest concrete failed command, not only the final ninja summary.",
        ),
        fix_steps=(
            "Correct one evidenced root cause, keep the same target, and rerun the smallest affected module before a full rebuild.",
        ),
        verification=(
            "The original first error disappears and no unrelated source or target inputs changed.",
        ),
        tags=("ninja failed", "soong error", "build stopped subcommand failed", "m failed"),
        route="rom_studio",
        evidence="AOSP provides module-scoped builds and a parse-only target to separate configuration from compilation.",
        automation="LOG RANKING SAFE • SOURCE CHANGES REQUIRE REVIEW",
        source=BUILD_SOURCE,
    ),
    _fix(
        "recipe-target-changed",
        "Recipe target changed after preview",
        "BUILD & RECIPES",
        "A target's identity or content no longer matches the exact file reviewed in the Recipe plan.",
        checks=("Compare project, relative path, file type, source digest, and current digest.",),
        fix_steps=(
            "Cancel the stale execution, inspect the new content, and generate a fresh preview and approval.",
        ),
        verification=(
            "The new immutable preview binds every target and conflict to the current working tree.",
        ),
        tags=("recipe stale", "target changed", "recipe digest mismatch", "preview mismatch"),
        route="rom_studio",
        evidence="ROMVERSE revalidates recipe identities immediately before applying a change.",
        automation="AUTOMATIC CANCELLATION • NEVER AUTO-APPROVE THE NEW TARGET",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "recipe-overlap-conflict",
        "Recipe targets overlap or conflict",
        "BUILD & RECIPES",
        "Two steps address the same path or a parent/child scope in an order that could hide the resulting change.",
        checks=(
            "Review normalized targets, operation order, and each step's expected source digest.",
        ),
        fix_steps=(
            "Split the intent into smaller recipes or explicitly reorder and regenerate the preview; never rely on incidental filesystem order.",
        ),
        verification=(
            "The new preview has one unambiguous owner for every target and rollback entry.",
        ),
        tags=("recipe conflict", "overlapping targets", "duplicate recipe path"),
        route="rom_studio",
        evidence="ROMVERSE detects overlaps before execution and keeps protected originals out of scope.",
        automation="CONFLICT DETECTION SAFE • RESOLUTION REQUIRES USER INTENT",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "apk-invalid",
        "APK install error: INSTALL_FAILED_INVALID_APK",
        "APPS & PACKAGES",
        "Android Package Manager rejected the package as invalid rather than accepting an install session.",
        checks=(
            "Re-run bounded APK structure, manifest, signer, and ZIP integrity inspection on the unchanged file.",
        ),
        fix_steps=(
            "Obtain a complete correctly signed APK from the authoritative publisher; do not repair or resign unknown bytes automatically.",
        ),
        verification=(
            "App Launchpad produces a fresh inspection receipt for the exact replacement hash before any install review.",
        ),
        tags=("install failed invalid apk", "INSTALL_FAILED_INVALID_APK", "parse failed not apk"),
        route="app_launchpad",
        evidence="PackageManager defines invalid-package failures separately from transport failures.",
        automation="INSPECTION ONLY • REPLACEMENT AND INSTALL REQUIRE USER REVIEW",
        source=PACKAGE_SOURCE,
    ),
    _fix(
        "apk-signature-conflict",
        "APK update error: INSTALL_FAILED_UPDATE_INCOMPATIBLE",
        "APPS & PACKAGES",
        "The installed package and candidate update do not share the required signing identity or update lineage.",
        checks=(
            "Compare package name, installed signer evidence when available, candidate signer, version, and source.",
        ),
        fix_steps=(
            "Use an update signed by the same trusted publisher; do not silently uninstall the existing app because that may delete its data.",
        ),
        verification=(
            "The replacement's signer/update lineage is compatible before a new Guardian install plan is created.",
        ),
        tags=(
            "INSTALL_FAILED_UPDATE_INCOMPATIBLE",
            "signatures do not match",
            "apk signer mismatch",
        ),
        route="app_launchpad",
        evidence="Android reports update signing conflicts as an installation conflict.",
        automation="NO AUTOMATIC UNINSTALL • EXACT APK INSTALL REVIEW REQUIRED",
        source=PACKAGE_SOURCE,
    ),
    _fix(
        "apk-insufficient-storage",
        "APK install error: INSTALL_FAILED_INSUFFICIENT_STORAGE",
        "APPS & PACKAGES",
        "Package Manager could not allocate enough device storage for the install.",
        checks=(
            "Inspect current /data usage and package size; do not infer available space from host storage.",
        ),
        fix_steps=(
            "Free user-approved device space outside ROMVERSE, then create a fresh install plan for the unchanged APK.",
        ),
        verification=("A fresh read-only storage probe shows sufficient headroom before retry.",),
        tags=(
            "INSTALL_FAILED_INSUFFICIENT_STORAGE",
            "apk no space",
            "insufficient storage install",
        ),
        route="quantum_optimizer",
        evidence="PackageManager classifies this as a storage failure.",
        automation="DIAGNOSIS ONLY • ROMVERSE DOES NOT DELETE PHONE DATA",
        source=PACKAGE_SOURCE,
    ),
    _fix(
        "apk-abi-incompatible",
        "APK install error: INSTALL_FAILED_NO_MATCHING_ABIS",
        "APPS & PACKAGES",
        "The package's native libraries do not support the device's reported CPU ABI set.",
        checks=(
            "Compare APK lib/ directories and splits with the device's read-only ABI evidence.",
        ),
        fix_steps=(
            "Obtain the correct architecture or universal package from the same trusted publisher.",
        ),
        verification=(
            "App Launchpad inspection confirms at least one compatible ABI before review.",
        ),
        tags=("INSTALL_FAILED_NO_MATCHING_ABIS", "CPU_ABI_INCOMPATIBLE", "apk abi mismatch"),
        route="app_launchpad",
        evidence="PackageManager defines incompatible native-code and no-matching-ABI failures.",
        automation="READ-ONLY COMPATIBILITY CHECK • NO BINARY REPACKING",
        source=PACKAGE_SOURCE,
    ),
    _fix(
        "apk-version-downgrade",
        "APK install error: INSTALL_FAILED_VERSION_DOWNGRADE",
        "APPS & PACKAGES",
        "The candidate version code is older than the installed package and Android blocked the downgrade.",
        checks=(
            "Compare installed/candidate versions, signer, device policy, and why a downgrade was requested.",
        ),
        fix_steps=(
            "Prefer a same-signer newer build; a deliberate downgrade needs a separate explicit policy and data-risk review that ROMVERSE v0.1 does not provide.",
        ),
        verification=(
            "A new candidate passes inspection with a non-downgrade version relationship.",
        ),
        tags=("INSTALL_FAILED_VERSION_DOWNGRADE", "apk downgrade", "older version code"),
        route="app_launchpad",
        evidence="PackageManager explicitly rejects version downgrades.",
        automation="BLOCKED • NO DOWNGRADE BYPASS",
        source=PACKAGE_SOURCE,
    ),
    _fix(
        "apk-missing-split",
        "APK install error: INSTALL_FAILED_MISSING_SPLIT",
        "APPS & PACKAGES",
        "A split package requires one or more companion splits that were not provided.",
        checks=(
            "Inventory base APK, configuration splits, feature splits, package names, versions, and signer consistency.",
        ),
        fix_steps=(
            "Obtain the complete matching split set or an official universal APK; never combine splits from different releases.",
        ),
        verification=(
            "The complete set has one package/version/signer identity and every declared required split.",
        ),
        tags=("INSTALL_FAILED_MISSING_SPLIT", "missing split apk", "split install failed"),
        route="app_launchpad",
        evidence="PackageManager defines missing required split as a distinct install failure.",
        automation="INSPECTION ONLY • MULTI-APK INSTALL NOT AUTHORIZED IN V0.1",
        source=PACKAGE_SOURCE,
    ),
    _fix(
        "apk-user-restricted",
        "APK install error: INSTALL_FAILED_USER_RESTRICTED",
        "APPS & PACKAGES",
        "Android user, work-profile, parental, enterprise, or installer policy denied installation.",
        checks=(
            "Read the device-visible policy prompt and identify the active user/profile without attempting a bypass.",
        ),
        fix_steps=(
            "Ask the device owner or administrator to change the legitimate policy, or stop the install.",
        ),
        verification=(
            "Android's own confirmation permits the install for the intended user/profile.",
        ),
        tags=(
            "INSTALL_FAILED_USER_RESTRICTED",
            "user restricted install",
            "device policy blocked apk",
        ),
        route="app_launchpad",
        evidence="PackageManager exposes user restriction as an explicit failure.",
        automation="BLOCKED • ROMVERSE NEVER BYPASSES DEVICE POLICY",
        source=PACKAGE_SOURCE,
    ),
    _fix(
        "apk-test-only",
        "APK install error: INSTALL_FAILED_TEST_ONLY",
        "APPS & PACKAGES",
        "The manifest marks the APK test-only and a normal production install rejected it.",
        checks=(
            "Confirm the package source, signer, build type, and whether a test build is genuinely intended.",
        ),
        fix_steps=(
            "Use a publisher-provided non-test build; ROMVERSE does not silently add adb install flags to weaken the reviewed plan.",
        ),
        verification=(
            "The replacement manifest and exact install plan no longer require a test-only exception.",
        ),
        tags=("INSTALL_FAILED_TEST_ONLY", "testOnly apk", "adb install -t"),
        route="app_launchpad",
        evidence="Official adb documentation and PackageManager identify test-only installation behavior.",
        automation="BLOCKED • INSTALL FLAGS CANNOT CHANGE AFTER APPROVAL",
        source=ADB_SOURCE,
    ),
    _fix(
        "device-battery-low",
        "Device battery is below the safe maintenance threshold",
        "DIAGNOSTICS & HEALTH",
        "The read-only battery sample is low enough that a long maintenance or recovery workflow has avoidable interruption risk.",
        checks=(
            "Confirm the percentage with a fresh scan and check whether the level is still falling while connected.",
            "Inspect the cable, charger, port, and charging indicator before planning long work.",
        ),
        fix_steps=(
            "Pause long-running, privileged, build-transfer, or recovery work and charge the phone.",
            "Use a compatible known-good charger and follow the exact manufacturer's guidance.",
        ),
        verification=("A fresh scan shows a stable charge above the workflow threshold.",),
        tags=("battery low", "low charge", "battery level is low", "battery safety threshold"),
        route="quantum_optimizer",
        evidence="ROMVERSE treats charge as a readiness signal, never proof that a battery is healthy.",
        automation="READ-ONLY RESCAN ONLY • CHARGING IS USER CONTROLLED",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "device-temperature-elevated",
        "Device battery temperature is elevated",
        "DIAGNOSTICS & HEALTH",
        "The reported temperature exceeds ROMVERSE's conservative review threshold and may reflect load, charging, environment, battery condition, or inaccurate telemetry.",
        checks=(
            "Stop heavy use, disconnect charging when safe, move away from heat, and observe whether temperature falls.",
            "Inspect for swelling, damage, odor, smoke, liquid exposure, or heat that remains extreme while idle.",
        ),
        fix_steps=(
            "Let the phone cool naturally in a ventilated place; do not puncture, open, crush, externally heat, or rapidly chill the battery.",
            "For damage, swelling, smoke, odor, or persistent extreme heat, stop using it and follow qualified manufacturer service guidance.",
        ),
        verification=(
            "Several fresh idle samples return below the warning threshold without missing evidence.",
        ),
        tags=("battery temperature elevated", "phone overheating", "device hot", "battery heat"),
        route="recovery_bay",
        evidence="Google Pixel guidance confirms heat can accelerate drain; exact limits and service steps remain model/OEM scoped.",
        automation="ALERT AND READ-ONLY TREND ONLY • NO AUTOMATIC THERMAL OR CHARGING CHANGE",
        source=PIXEL_BATTERY_SOURCE,
    ),
    _fix(
        "device-storage-nearly-full",
        "Android device storage is nearly full",
        "DIAGNOSTICS & HEALTH",
        "Very low free user-data space can prevent app installs, updates, cameras, downloads, and Android services from completing.",
        checks=(
            "Confirm the affected mount and free-space reading with a fresh scan.",
            "Review Android's storage categories and preserve important files before removing anything.",
        ),
        fix_steps=(
            "Back up important data, then remove or move user-selected large files or unused apps through Android's normal UI.",
            "Clear only an identified app's cache first; never delete unknown system or partition files.",
        ),
        verification=(
            "A fresh scan shows sufficient free space and the original failing action completes.",
        ),
        tags=(
            "device storage nearly full",
            "storage capacity",
            "low free space android",
            "out of space phone",
        ),
        route="quantum_optimizer",
        evidence="Official Android support distinguishes user-controlled unused-app cleanup from deleting unknown system data.",
        automation="READ-ONLY CAPACITY ANALYSIS • PHONE FILE DELETION REQUIRES USER CHOICE",
        source=ANDROID_STORAGE_SOURCE,
    ),
    _fix(
        "security-patch-aging",
        "Android security patch is aging",
        "DIAGNOSTICS & HEALTH",
        "The reported patch date is older than ROMVERSE's review window; availability still depends on exact model, region, carrier, and OEM support.",
        checks=(
            "Confirm patch date, Android version, model, region/carrier, and current OEM update channel.",
            "Review exact OEM release notes rather than assuming another model's package is compatible.",
        ),
        fix_steps=(
            "Check for a normal system update through the device and its authoritative OEM support page.",
            "Do not sideload, downgrade, unlock, or flash a package selected only by a similar model name.",
        ),
        verification=(
            "The device reports the expected signed build and newer patch after its normal update path.",
        ),
        tags=(
            "security patch aging",
            "old security patch",
            "android update old",
            "security patch age",
        ),
        route="device_atlas",
        evidence="Official Android support documents how to check version/update state; the OEM supplies exact availability.",
        automation="UPDATE DISCOVERY ONLY • INSTALLATION AND FIRMWARE CHANGES ARE NOT AUTOMATIC",
        source=ANDROID_UPDATE_SOURCE,
    ),
    _fix(
        "bootloader-unlocked-review",
        "Bootloader is reported unlocked: verify the intended state",
        "BOOT & SECURITY",
        "An unlocked bootloader may be intentional for development, but changes the trust boundary and must not trigger an automatic relock.",
        checks=(
            "Confirm the observation against the exact device, active build, Verified Boot state, and recovery plan.",
            "Determine whether unlock was intentional and whether data or keys depend on the current state.",
        ),
        fix_steps=(
            "Record the state in Device DNA and use only workflows designed for that exact model/build contract.",
            "Never relock merely to clear a warning; a mismatched relock can prevent boot or recovery.",
        ),
        verification=(
            "Fresh Device DNA and boot evidence agree and keep relocking explicitly prohibited.",
        ),
        tags=("bootloader unlocked", "unlocked bootloader", "security bootloader"),
        route="device_atlas",
        evidence="AOSP Verified Boot describes trust outcomes; ROMVERSE permanently forbids inferred relocking.",
        automation="READ-ONLY REVIEW ONLY • BOOTLOADER RELOCK NEVER AUTOMATIC",
        source=BOOT_FLOW_SOURCE,
    ),
    _fix(
        "verified-boot-state-review",
        "Verified Boot reports orange, yellow, or red",
        "BOOT & SECURITY",
        "The device reports a non-green Verified Boot state. Exact meaning and recovery behavior remain device-specific.",
        checks=(
            "Record the exact state, bootloader observation, build identity, slot, and recent firmware changes.",
            "Distinguish an expected development state from a new red verification failure.",
        ),
        fix_steps=(
            "If unexpected or red, stop modification work, preserve evidence, and use the exact model's supported recovery path.",
            "Do not disable verification or relock the bootloader as a generic fix.",
        ),
        verification=(
            "The intended signed build and boot chain produce the expected state after a clean reboot and scan.",
        ),
        tags=(
            "verified boot non green",
            "verified boot orange",
            "verified boot yellow",
            "verified boot red",
        ),
        route="guardian_core",
        evidence="AOSP defines distinct Verified Boot states; ROMVERSE treats them as evidence, not change authority.",
        automation="READ-ONLY EVIDENCE ONLY • NO VERIFICATION OR LOCK-STATE CHANGE",
        source=BOOT_FLOW_SOURCE,
    ),
    _fix(
        "root-signal-review",
        "Root signal or Root Manager candidate needs identity review",
        "BOOT & SECURITY",
        "A root-capable ADB identity, package candidate, or conflicting Manager evidence was observed; none alone proves the intended root configuration.",
        checks=(
            "Separate active ADB root evidence from a merely installed Manager package candidate.",
            "Verify exact Manager identity, signer, build source, target image, and device/build scope.",
        ),
        fix_steps=(
            "Record evidence in Device DNA and use Ascension only for an exact supported source-bound route.",
            "Do not request elevation, patch, uninstall, hide, or change root from a generic finding.",
        ),
        verification=(
            "Fresh evidence consistently identifies state without treating package presence as root proof.",
        ),
        tags=(
            "root detected",
            "root manager candidate",
            "security root",
            "magisk kernelsu conflict",
        ),
        route="rom_studio",
        evidence="ROMVERSE's typed root-identity review separates active signals from candidate metadata.",
        automation="CLASSIFICATION ONLY • ROOT AND PACKAGE CHANGES REQUIRE SEPARATE EXACT WORKFLOWS",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "android-app-crash-triage",
        "Android app crashes or behaves unpredictably",
        "APPS & PACKAGES",
        "A repeatable crash can come from one app, damaged local state, low storage, an update, a dependency, or a wider Android problem; the symptom alone does not identify the cause.",
        checks=(
            "Record the exact package, action, time, repeatability, available storage, and recent app or system updates.",
            "Compare the affected app with a trusted stock app and note whether the problem follows one user profile or the whole device.",
        ),
        fix_steps=(
            "Use normal app and system updates, restart once, and clear only the identified app's cache before considering its data or removal.",
            "Use the manufacturer's safe-mode guidance to isolate downloaded apps; back up important app data before any clear-data, uninstall, or reset step.",
        ),
        verification=(
            "Repeat the exact failing action after one controlled change and confirm other core apps remain stable.",
        ),
        tags=("app crash", "application keeps stopping", "android instability", "safe mode app"),
        route="recovery_bay",
        evidence="Official Android support describes safe mode as an isolation step; it does not identify or remove an app automatically.",
        automation="EVIDENCE CORRELATION ONLY • APP DATA AND PACKAGE CHANGES REQUIRE USER CHOICE",
        source=ANDROID_APP_SOURCE,
    ),
    _fix(
        "android-screen-touch-triage",
        "Android display or touch is not working correctly",
        "DIAGNOSTICS & HEALTH",
        "Display, touch, accessory, software, liquid, impact, or hardware faults can look similar and must be separated before a recovery action is chosen.",
        checks=(
            "Inspect for cracks, liquid, contamination, a lifting screen, and accessories such as cases or protectors without opening the device.",
            "Determine whether the image, touch response, one screen region, or the entire interface is affected and whether screenshots appear normal elsewhere.",
        ),
        fix_steps=(
            "Clean and dry the exterior safely, remove interfering accessories, restart once, and follow the exact manufacturer's supported display diagnostics.",
            "Use manufacturer safe mode only to isolate software; back up important data before any reset and use qualified service for damage or persistent hardware symptoms.",
        ),
        verification=(
            "Test the same gestures and affected regions repeatedly after one controlled step.",
        ),
        tags=("screen not working", "touchscreen failure", "display touch", "ghost touch"),
        route="recovery_bay",
        evidence="Official Android support separates basic screen checks, safe-mode isolation, reset, and manufacturer service.",
        automation="GUIDED CHECKS ONLY • NO AUTOMATIC RESET, CALIBRATION, OR HARDWARE ACTION",
        source=ANDROID_SCREEN_SOURCE,
    ),
    _fix(
        "android-network-triage",
        "Android Wi-Fi, Bluetooth, or mobile network problem",
        "DIAGNOSTICS & HEALTH",
        "A connection failure may belong to one radio, location, router, accessory, carrier, account, or software state; resetting every network setting can erase useful evidence and saved connections.",
        checks=(
            "Identify the exact radio, location, network or accessory, signal state, and whether another device works on the same connection.",
            "Test Wi-Fi, mobile data, and Bluetooth separately and record carrier or router messages before changing settings.",
        ),
        fix_steps=(
            "Restart the affected connection and device once, then follow the router, carrier, accessory, or phone manufacturer's exact supported checks.",
            "Record credentials and configuration before forgetting a network or performing a reviewed network reset; never invent APN values.",
        ),
        verification=(
            "Reconnect to the original target and verify the exact failing service, not only an icon.",
        ),
        tags=("wifi problem", "bluetooth problem", "mobile network", "no internet android"),
        route="recovery_bay",
        evidence="Official Android support recommends isolating Wi-Fi and mobile-data causes before broader reset steps.",
        automation="READ-ONLY CORRELATION ONLY • NETWORK RESET AND CREDENTIAL CHANGES ARE USER CONTROLLED",
        source=ANDROID_NETWORK_SOURCE,
    ),
    _fix(
        "android-camera-audio-triage",
        "Android camera, microphone, or speaker problem",
        "DIAGNOSTICS & HEALTH",
        "Camera and audio symptoms can originate in one component, app, permission, privacy control, accessory, obstruction, routing state, or hardware fault.",
        checks=(
            "Identify the exact camera, microphone, speaker, app, permission state, accessory, and conditions that reproduce the fault.",
            "Compare the stock camera or recorder with one other trusted app and inspect exterior openings without inserting tools.",
        ),
        fix_steps=(
            "Review Android privacy controls and app permissions, remove an interfering case or accessory, and restart once.",
            "Preserve important media and use exact manufacturer diagnostics or qualified service when the fault crosses apps or follows impact, liquid, or damage.",
        ),
        verification=(
            "Record a fresh test with the same component and confirm playback or capture through a second trusted path.",
        ),
        tags=("camera failure", "microphone not working", "speaker problem", "camera audio"),
        route="recovery_bay",
        evidence="ROMVERSE separates observable component, app, permission, routing, and physical evidence before recommending a route.",
        automation="GUIDED EVIDENCE ONLY • NO AUTOMATIC PERMISSION, MEDIA, OR HARDWARE CHANGE",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "android-performance-freezing",
        "Android is slow, freezing, or repeatedly unresponsive",
        "DIAGNOSTICS & HEALTH",
        "Slowness can reflect heat, low storage, recent updates, one app, background work, short uptime, or a wider system fault; indiscriminately killing or removing software hides the cause.",
        checks=(
            "Correlate the symptom with temperature, free storage, recent apps or updates, uptime resets, and whether one action consistently triggers it.",
            "Allow declared post-update optimization to settle and compare behavior in a trusted stock app.",
        ),
        fix_steps=(
            "Restart once, cool the phone if needed, and review user-selected storage before changing one suspected app at a time.",
            "Use the manufacturer's safe-mode guidance to isolate downloaded apps and back up important data before any clear-data, uninstall, or reset step.",
        ),
        verification=(
            "Repeat the same measured task after one change and confirm the improvement survives another normal restart.",
        ),
        tags=("slow performance", "android freezing", "phone lag", "system unresponsive"),
        route="recovery_bay",
        evidence="Official Android performance guidance uses update, storage, app, and safe-mode checks without treating one signal as proof.",
        automation="TREND AND EVIDENCE ANALYSIS ONLY • NO AUTOMATIC TASK KILL, REMOVAL, OR RESET",
        source=ANDROID_PERFORMANCE_SOURCE,
    ),
    _fix(
        "boot-loop-first-triage",
        "Boot loop after a ROM change: first safe triage",
        "RECOVERY & GUARDIAN",
        "Repeated boots after a change can come from framework, permissions, SELinux, AVB, filesystem, slot, kernel/vendor, or data compatibility failures; a moving animation is not proof of progress.",
        checks=(
            "Record the exact change set, active slot, elapsed boot pattern, and last known-good rollback artifact.",
            "Preserve available recovery/boot logs and do not stack additional changes.",
        ),
        fix_steps=(
            "Return to the immutable known-good baseline or exact tested rollback route, then reintroduce one reviewed change set at a time.",
        ),
        verification=(
            "Require stable boot evidence plus core service checks; never relock merely because one boot completes.",
        ),
        tags=("bootloop", "boot loop", "stuck boot animation", "userspace reboot"),
        route="recovery_bay",
        evidence="The field-verified workflow separated boot stability from complete first-boot verification.",
        automation="RECOVERY GUIDANCE ONLY • DEVICE CHANGE REQUIRES EXACT APPROVAL",
        source=FIELD_SOURCE,
    ),
    _fix(
        "active-slot-mismatch",
        "Active A/B slot differs from the reviewed target",
        "RECOVERY & GUARDIAN",
        "The phone's current slot no longer matches the slot identity captured in the plan or recovery evidence.",
        checks=(
            "Refresh read-only slot, boot-control, build, and rollback evidence for the exact device.",
        ),
        fix_steps=(
            "Cancel the stale plan and build a new slot-aware assessment; never assume _a or _b from a filename.",
        ),
        verification=(
            "The newly reviewed plan and fresh evidence bind the same exact active/target slot.",
        ),
        tags=(
            "current slot mismatch",
            "slot a b",
            "active slot changed",
            "fastboot getvar current-slot",
        ),
        route="recovery_bay",
        evidence="Slot identity is part of Device DNA and every high-consequence readiness decision.",
        automation="AUTOMATIC CANCELLATION • NO AUTOMATIC SLOT CHANGE",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "guardian-approval-expired",
        "Guardian approval expired before execution",
        "RECOVERY & GUARDIAN",
        "The short-lived approval is no longer valid, even if the visible plan appears unchanged.",
        checks=("Revalidate the exact plan, target, evidence, tool identity, and current time.",),
        fix_steps=("Request a fresh review and approval; never extend or rewrite the old record.",),
        verification=(
            "The gateway consumes one current approval bound to the unchanged exact operation.",
        ),
        tags=("approval expired", "guardian token expired", "stale approval"),
        route="guardian_core",
        evidence="ROMVERSE approvals expire and are reverified immediately before use.",
        automation="BLOCKED UNTIL NEW EXPLICIT APPROVAL",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "guardian-target-changed",
        "Approved target or plan changed before execution",
        "RECOVERY & GUARDIAN",
        "The current operation, file hash, device identity, arguments, or evidence no longer matches what the user approved.",
        checks=(
            "Compare the complete current manifest with the approval-bound digest and target.",
        ),
        fix_steps=(
            "Reject the stale approval, show the change, and request a new review only if the new intent is legitimate.",
        ),
        verification=(
            "The gateway receives a byte-for-byte matching current plan and one unconsumed approval.",
        ),
        tags=("plan changed after approval", "target mismatch", "approval digest mismatch"),
        route="guardian_core",
        evidence="Guardian binds approval to exact purpose, target, arguments, effects, and evidence.",
        automation="AUTOMATIC REJECTION • NEVER AUTO-APPROVE CHANGES",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "backup-verification-failed",
        "Backup completed but verification evidence failed",
        "RECOVERY & GUARDIAN",
        "Copied bytes or folders cannot be called a verified backup because integrity, scope, or receipt persistence did not complete.",
        checks=(
            "Preserve the destination, measured bytes, child approval, and exact failed verification stage.",
        ),
        fix_steps=(
            "Do not overwrite the candidate; correct the host/storage issue and run a fresh bounded plan to a distinct destination.",
        ),
        verification=(
            "Every planned item and digest verifies and the private receipt reloads successfully.",
        ),
        tags=(
            "backup verification failed",
            "receipt save failed",
            "incomplete backup",
            "adb pull failed",
        ),
        route="time_machine",
        evidence="ROMVERSE separates copy completion from receipt-backed verified completion.",
        automation="FAILED EVIDENCE STATE • NO AUTOMATIC RESTORE",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "workspace-no-space",
        "Workspace is out of space",
        "TOOLS & HOST",
        "The Data-drive workspace cannot safely hold staging, expanded images, rollback material, and final output at the same time.",
        checks=(
            "Measure free bytes against the operation's bounded source, expansion, staging, rollback, and output budget.",
        ),
        fix_steps=(
            "Free or select verified host storage without deleting protected originals, then recreate the plan so its space evidence is current.",
        ),
        verification=("Fresh preflight shows the required safety margin before writing starts.",),
        tags=("no space left on device", "ENOSPC", "workspace full", "disk full"),
        route="rom_studio",
        evidence="ROMVERSE performs free-space preflight before materializing large firmware trees.",
        automation="BLOCKED • USER CONTROLS HOST FILE DELETION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "unknown-is-not-healthy",
        "Unknown diagnostic evidence is not a healthy result",
        "DIAGNOSTICS & HEALTH",
        "A missing, failed, stale, or unsupported probe cannot contribute a green health claim or a zero-valued metric.",
        checks=(
            "Inspect evidence coverage, probe errors, freshness, and which facts were actually measured.",
        ),
        fix_steps=(
            "Restore the read-only evidence path and scan again; keep the status Unconfirmed until genuine data arrives.",
        ),
        verification=(
            "Every displayed health claim links to present accepted evidence and missing metrics remain dashes.",
        ),
        tags=("unknown health", "unconfirmed evidence", "missing diagnostic", "false green"),
        route="quantum_optimizer",
        evidence="ROMVERSE's safety vocabulary never maps absence of evidence to healthy.",
        automation="READ-ONLY RESCAN AVAILABLE • NO FABRICATED DEFAULT",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "diagnostic-history-tampered",
        "Saved diagnostic snapshot failed integrity checks",
        "DIAGNOSTICS & HEALTH",
        "A snapshot is malformed, linked, oversized, stale, or no longer matches its content fingerprint.",
        checks=(
            "Preserve the rejected file and review the visible reason without loading it into trends.",
        ),
        fix_steps=(
            "Run a fresh read-only scan and explicitly save a new snapshot; never silently rewrite the damaged history.",
        ),
        verification=(
            "The new snapshot reloads with its exact pseudonymous device binding and digest.",
        ),
        tags=("diagnostic snapshot tampered", "health history corrupt", "snapshot digest mismatch"),
        route="quantum_optimizer",
        evidence="Health Timeline excludes unverified records and explains every rejection.",
        automation="SAFE EXCLUSION • USER-REQUESTED FRESH SNAPSHOT",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "cache-preview-changed",
        "Cache file changed after cleanup preview",
        "DIAGNOSTICS & HEALTH",
        "A temporary file no longer matches the identity reviewed for bounded cleanup.",
        checks=(
            "Compare path containment, regular-file type, age, size, and modification identity.",
        ),
        fix_steps=("Preserve the changed file and clean only unchanged previewed candidates.",),
        verification=(
            "The cleanup receipt reports removed and preserved counts and reloads with a valid digest.",
        ),
        tags=("cache changed after preview", "cleanup skipped changed file", "safe cleanup"),
        route="quantum_optimizer",
        evidence="ROMVERSE's cache optimizer revalidates every candidate immediately before deletion.",
        automation="BOUNDED HOST CLEANUP AFTER EXPLICIT CONFIRMATION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "android-device-identity-catalog",
        "Recognize an Android model without guessing build or flash support",
        "ROMVERSE WORKFLOWS",
        "A retail phone name is useful context, but only the exact on-device Build.BRAND plus "
        "Build.DEVICE pair identifies a Google Play device model. Marketing names, codenames, "
        "and model strings can each be shared across variants and cannot prove a firmware or "
        "partition contract.",
        checks=(
            "Run a fresh read-only Device Engine scan and confirm Build.BRAND, Build.DEVICE, and model are present.",
            "Check that Device Atlas accepted a current private catalog receipt and an exact brand/device match.",
            "Separate the identity result from the active Device Pack, protected firmware digest, build contract, and physical recovery evidence.",
        ),
        fix_steps=(
            "Use Device Atlas to sync the official Android device IDs in the background, then rescan the connected phone.",
            "If the official pair has multiple retail names, preserve the result as ambiguous until the exact model narrows it; never choose by popularity or list order.",
            "Review the automatically selected Device Pack roadmap and prepare a review-only exact-model draft for any missing contract.",
        ),
        verification=(
            "Device Atlas shows the exact retail identity and source digest as read-only evidence.",
            "ROM Studio names the same phone while build and flash readiness remain locked unless their independent exact contracts pass.",
            "Unknown, stale, malformed, redirected, linked, oversized, or altered catalog evidence never becomes a device identity claim.",
        ),
        tags=(
            "android device id",
            "Build.BRAND Build.DEVICE",
            "official device catalog",
            "unknown phone model",
            "device codename",
            "automatic device recognition",
        ),
        route="device_atlas",
        evidence="Google defines a device model by the OEM-reported retail brand and device properties and warns that device or marketing name alone is not unique.",
        automation="BOUNDED OFFICIAL CATALOG SYNC • READ-ONLY IDENTITY • BUILD/FLASH AUTHORITY NONE",
        source=GOOGLE_DEVICE_CATALOG_SOURCE,
    ),
    _fix(
        "device-build-requirements-blueprint",
        "Determine what a recognized Android device needs to build, compile, and flash",
        "ROMVERSE WORKFLOWS",
        "A model name is only the first requirement. ROMVERSE must independently bind retail "
        "identity, an exact protected-firmware build contract, the contract's ordered host "
        "toolchain, and physical flash/recovery evidence. The Requirements Blueprint keeps "
        "those four lanes separate so an official identity or installed compiler can never be "
        "mistaken for permission to build or write a phone.",
        checks=(
            "Confirm the blueprint is bound to the current model/codename, Device Pack id and SHA-256, and readiness-report digest.",
            "Read all four lane badges: Identity, Build Contract, Compile Toolchain, and Flash Contract can have different states.",
            "For a generic/OEM Pack, expect build, toolchain, and flash requirements to remain explicit unknowns even when Google's retail identity is verified.",
            "For an exact build Pack, compare declared tools and outputs with the Pack contract; host readiness and flash readiness still require separate verification.",
        ),
        fix_steps=(
            "Use the Identity lane to sync or review exact Build.BRAND / Build.DEVICE evidence without granting compatibility.",
            "Use the Build lane to resolve model scope, protected source hashes, partitions, editable images, and bounded allowed outputs.",
            "Use the Compile lane only after an exact contract exists; Forge Arsenal will verify or prepare that declared ordered subset rather than guessing a generic bundle.",
            "Use the Flash lane to prepare stock recovery and obtain signed exact-build AVB, physical-test, publisher, and partition-write evidence before Guardian review.",
        ),
        verification=(
            "Every lane route re-derives the same current blueprint before navigating and refuses a stale or substituted report.",
            "An exact build-ready Pack can open ROM Studio while a separate flash-locked lane remains visibly locked.",
            "An official generic identity names the phone but never creates required tools, allowed images, partition writes, approval, or flash authority.",
            "No blueprint button starts an approval, build worker, flash command, or device-changing operation.",
        ),
        tags=(
            "build compile flash requirements",
            "recognized android device requirements",
            "automatic device blueprint",
            "what tools does this phone need",
            "device build contract missing",
            "flash requirements unknown",
            "identity build toolchain flash",
        ),
        route="device_atlas",
        evidence="ROMVERSE derives each lane only from the current official identity match, integrity-checked Device Pack, deterministic validation rows, and exact report digest.",
        automation="DETERMINISTIC REQUIREMENTS AND SAFE ROUTING ONLY • NO APPROVAL, BUILD, FLASH, OR DEVICE-CHANGING AUTHORITY",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "device-pack-readiness-roadmap",
        "Device Pack roadmap is build-locked or flash-locked",
        "ROMVERSE WORKFLOWS",
        "Device Atlas separates identity, local build planning, and phone-writing readiness. A "
        "build lock means the exact model, firmware capability, partition descriptors, or bounded "
        "build contract is incomplete. A flash lock means the independent recovery, AVB, signed "
        "physical-test, or partition-write evidence is incomplete even when local building is ready.",
        checks=(
            "Read the first unresolved validation row and confirm whether it is labelled for build, flash, or public release.",
            "Confirm the roadmap still binds the connected model/codename and the integrity-checked active Device Pack digest.",
            "Keep official retail identity, Device Pack scope, protected firmware, host tools, and Guardian approval as separate evidence.",
        ),
        fix_steps=(
            "For an identity or build gate, open the exact guide selected by Next Safe Action and update only a reviewed Device Pack contract.",
            "For a missing stock route, use Time Machine to register and reverify exact local backup and stock-recovery evidence.",
            "For physical, AVB, publisher, or write-contract gates, export the privacy-safe challenge and import only a valid signed exact-build attestation.",
            "Continue to ROM Studio only after every build-labelled row passes; flash remains unavailable until every flash-labelled row independently passes.",
        ),
        verification=(
            "The same deterministic report reloads with the expected Pack/model binding and a valid report digest.",
            "Live Console records the genuine readiness result and returns to Device Atlas without starting a worker or phone action.",
            "No route, export, catalog match, or locally edited receipt changes readiness unless its originating verifier accepts the exact evidence.",
        ),
        tags=(
            "device pack build locked",
            "device pack flash locked",
            "validation roadmap",
            "build contract missing",
            "partition write contract",
            "physical recovery attestation",
            "next safe action",
        ),
        route="device_atlas",
        evidence="ROMVERSE derives every readiness row from the exact active Device Pack, connected hardware identity, and independently verified attestations.",
        automation="DETERMINISTIC GUIDANCE AND ROUTING ONLY • NO APPROVAL OR EXECUTION AUTHORITY",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "device-pack-build-toolchain",
        "Recognized device needs its exact build toolchain",
        "TOOLS & HOST",
        "A recognized phone and an integrity-checked Device Pack can declare the exact host "
        "programs needed to inspect and build its protected firmware. Tool availability proves "
        "only that those local programs freshly start and report correctly; it does not prove "
        "firmware compatibility, approve a build, unlock a bootloader, or authorize flashing.",
        checks=(
            "Confirm Device Atlas still binds the connected model/codename, Pack id, Pack SHA-256, and current readiness-report digest.",
            "Compare Forge Arsenal's highlighted requirements with the ordered required_tools list in that exact Device Pack build contract.",
            "Treat an absent, renamed, or failed verifier result as missing even if a similarly named executable exists elsewhere on the host.",
            "Read build-contract and flash-contract badges independently; a complete host toolchain cannot turn a flash lock into authority.",
        ),
        fix_steps=(
            "From the active Device Atlas roadmap, choose Inspect exact build tools so Forge Arsenal receives the current digest-bound contract.",
            "Use Set up missing requirements to review only the missing declared subset, its official sources, and ROMVERSE's managed, operating-system-authorized, or manual strategy.",
            "Approve only the visible plan you intend, then let Forge re-scan every requirement instead of trusting an installer exit message.",
            "Continue to ROM Studio only when every exact host requirement and the independent Device Pack build contract both verify.",
        ),
        verification=(
            "Forge Arsenal shows the same Pack id/hash and model/codename as the current Device Atlas report.",
            "Every required tool is highlighted and reports Ready from a fresh verifier result; missing names remain explicit.",
            "ROM Studio receives the refreshed tool inventory while flash authority remains none until Device Atlas and Guardian independently permit it.",
            "A changed report, Pack, device, or tool result stops the retained handoff without installing, building, or touching a phone.",
        ),
        tags=(
            "exact device toolchain",
            "device pack required tools",
            "recognized phone build tools",
            "forge arsenal device pack",
            "missing rom build dependency",
            "build compile requirements",
            "flash authority none",
        ),
        route="forge_arsenal",
        evidence="ROMVERSE resolves this list only from the current integrity-checked Device Pack required_tools contract and freshly verified host-tool statuses.",
        automation="EXACT TOOL INVENTORY AND USER-REVIEWED SETUP ONLY • NO BUILD, APPROVAL, OR PHONE-WRITE AUTHORITY",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "rom-studio-project-toolchain",
        "ROM Studio prerequisite route loses the exact project or does not refresh evidence",
        "ROMVERSE WORKFLOWS",
        "A Studio prerequisite control must carry one exact project id, protected-source SHA-256, "
        "and bounded purpose into Command Deck or Forge Arsenal. A navigation-only device refresh "
        "or a generic tool list can look successful while leaving Build & Proof with stale or "
        "unrelated evidence.",
        checks=(
            "Confirm the destination handoff names the same project id and protected-source fingerprint shown in ROM Studio.",
            "For Command Deck, confirm the expected model/codename is compared with a fresh authorized-device scan rather than a retained label.",
            "For Forge Arsenal, confirm required tools come from a source-matched Device Pack contract or are explicitly labelled structural/default guidance.",
            "Confirm returning to Studio revalidates the context digest and never starts a project worker, build, root, flash, wipe, or relock action.",
        ),
        fix_steps=(
            "Reopen the prerequisite from the exact ROM Studio project instead of using a generic sidebar destination.",
            "Use Scan exact target in Command Deck when device evidence is requested; Ascension refresh must start that read-only scan, not merely navigate.",
            "Use Re-check exact tools in Forge Arsenal, review any missing source-bound requirements, and return the fresh inventory to the same project.",
            "If the source, Pack, inspection, device expectation, or context digest changed, keep the destination open in a stopped state and reopen from Studio.",
        ),
        verification=(
            "Command Deck reports target match, mismatch, or scan needed and returns the same project/source identity.",
            "Forge Arsenal shows the exact project/source, derived required tools, and whether a source-matched build contract is bound.",
            "Studio's return banner reports the fresh evidence and explicitly confirms that no phone-changing or build action started.",
            "A forged or stale source/context digest disables the retained action and remains at the evidence destination.",
        ),
        tags=(
            "rom studio command deck handoff",
            "refresh device does not scan",
            "forge arsenal exact project",
            "stale project context",
            "source bound toolchain",
            "build readiness prerequisites",
        ),
        route="forge_arsenal",
        evidence="ROMVERSE binds each route to the persisted project, protected-source SHA-256, current inspection/Pack evidence, derived tool list, and fresh device or host verification result.",
        automation="READ-ONLY SCAN OR USER-REVIEWED HOST-TOOL SETUP ONLY • NO PROJECT WORKER, BUILD, ROOT, APPROVAL, OR PHONE-WRITE AUTHORITY",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "nexus-evidence-prerequisites",
        "Nexus cannot generate a plan because project evidence is missing",
        "ROMVERSE WORKFLOWS",
        "Nexus plans only from one protected ROM project with current Device DNA and a "
        "Compatibility Matrix. A connected phone or official catalog identity is useful context, "
        "but neither proves the protected firmware, partition layout, or compatibility decisions "
        "needed for an evidence-bound plan.",
        checks=(
            "Confirm ROM Studio contains the intended project and an integrity-verified protected firmware source.",
            "Confirm Device DNA belongs to that exact project, source digest, and active Device Pack context.",
            "Confirm the Compatibility Matrix was derived from the current Device DNA and protected source rather than an older project state.",
        ),
        fix_steps=(
            "Open ROM Studio and create or import the intended project without changing its protected source.",
            "Complete the read-only inspection so ROMVERSE can derive current Device DNA and the Compatibility Matrix from exact evidence.",
            "Return to Nexus, refresh evidence, review the selected project identity, and generate a plan only when both records report ready.",
        ),
        verification=(
            "Nexus selects the intended project and reports Evidence ready.",
            "Generate Nexus Plan is enabled, but no plan exists until the user explicitly chooses it.",
            "The evidence path grants no Guardian approval, execution authority, build worker, or phone action.",
        ),
        tags=(
            "nexus evidence missing",
            "nexus cannot generate plan",
            "device dna missing",
            "compatibility matrix missing",
            "no rom project",
            "nexus prerequisites",
        ),
        route="rom_studio",
        evidence="ROMVERSE re-derives Nexus decisions only from the exact current protected project, Device DNA, and Compatibility Matrix records.",
        automation="EXACT NAVIGATION AND EVIDENCE REFRESH ONLY • NO PLAN, APPROVAL, OR EXECUTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "about-live-evidence-unavailable",
        "About runtime evidence is stale or unavailable",
        "ROMVERSE WORKFLOWS",
        "The ROMVERSE Now panel is a read-only map of facts owned by Device Atlas, Archives, "
        "ROM Studio, Forge Arsenal, and Live Console. A warning means one owning service "
        "rejected, could not refresh, or has not yet collected its evidence; About never fills "
        "that gap with a demo counter or inferred success.",
        checks=(
            "Reopen About ROMVERSE so the panel recalculates from the current workspace rather than a previous screen state.",
            "Open the card's exact owning feature and read its bounded reason: Device Atlas for Pack/catalog identity, Forge Arsenal for host tools, or Live Console for ledger integrity.",
            "Keep official device identity separate from source-bound build, compile, flash, Guardian approval, and execution readiness.",
        ),
        fix_steps=(
            "For a stale official ID receipt, use Device Atlas's reviewed catalog refresh and wait for its integrity receipt before returning to About.",
            "For missing host tools, use the exact Device Pack handoff to Forge Arsenal; prepare only the declared missing subset, then run a fresh verifier scan.",
            "For a rejected Live Console ledger, preserve the file and use Live Console's visible integrity error; do not rewrite or count untrusted events.",
            "For zero projects or events, create work only through the owning ROM Studio or subsystem workflow. Zero is valid evidence and is not automatically repaired.",
        ),
        verification=(
            "Returning to About shows counts identical to the current owning feature without starting a scan, build, approval, or phone action.",
            "Every evidence card opens its registered canonical Desktop page and preserves the workspace state.",
            "A rejected catalog or ledger remains visibly unavailable and contributes no trusted row or event count.",
        ),
        tags=(
            "about runtime evidence",
            "romverse now stale",
            "about counters unavailable",
            "device catalog warning",
            "live ledger integrity",
            "desktop feature evidence map",
        ),
        route="about",
        evidence="ROMVERSE calculates the panel from current in-process service results and validated local records each time About is opened.",
        automation="READ-ONLY RECALCULATION AND EXACT FEATURE ROUTING ONLY • NO SCAN, BUILD, APPROVAL, OR DEVICE ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "live-console-light-table-contrast",
        "Live Console table is white or unreadable on a dark desktop",
        "ROMVERSE WORKFLOWS",
        "The host desktop's native item-view theme painted the event cells or header with a "
        "light background while ROMVERSE retained light text. This is a display-layer fault; "
        "it does not prove that the privacy-redacted event ledger is damaged or untrusted.",
        checks=(
            "Confirm the white or grey area is limited to the Live Console table while its surrounding cards remain dark.",
            "Confirm Live Console reports genuine event counts rather than a ledger-integrity warning, and preserve a screenshot of the affected desktop theme.",
        ),
        fix_steps=(
            "Install the current ROMVERSE Desktop build, which paints evidence cells, alternating rows, selection, state text, grid lines, and headers with its own bounded dark renderer.",
            "Restart ROMVERSE so the running window loads the renderer; do not rewrite the event ledger or reset the whole desktop theme to repair presentation.",
        ),
        verification=(
            "Normal and alternating rows remain dark navy, header labels remain readable, and the selected row uses a distinct purple-blue highlight.",
            "Refresh events and navigate away and back; the table remains readable without changing event counts, evidence, or device state.",
            "The rendered-pixel regression check rejects a light alternate row or header before a Desktop build can pass verification.",
        ),
        tags=(
            "live console white table",
            "unreadable event grid",
            "white text white background",
            "wayland table contrast",
            "fedora desktop theme",
            "live console header white",
        ),
        route="live_console",
        evidence="ROMVERSE reproduced the presentation fault and verifies the painted header and alternate-row pixels in the Desktop UI test suite.",
        automation="DISPLAY REPAIR AND NAVIGATION ONLY • NO LEDGER REWRITE, EVENT CHANGE, PHONE ACTION, OR EVIDENCE INFERENCE",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "archives-local-learning-boundary",
        "Local learned fix is missing or retired in Archives",
        "ROMVERSE WORKFLOWS",
        "Archives Local Learning accepts only privacy-scrubbed host-side or read-only outcomes "
        "produced by a built-in typed action with a verified action receipt. Research text, a "
        "successful command exit, an unverified phone change, or a plausible community answer "
        "cannot become learned knowledge. Retired records stay visible so ROMVERSE does not "
        "silently reuse evidence invalidated by failures or version drift.",
        checks=(
            "Confirm Settings allowed ROMVERSE to prepare private local Synapse contributions; no production upload service is implied or used.",
            "Confirm Forge Control first preserved an exact error fingerprint and source-attributed official or maintainer candidate.",
            "Confirm the matching built-in typed action produced a receipt digest and separate verification-evidence digest without changing a phone.",
            "Inspect the learned record's exact operation, source format, device codename, build family, tool name, and tool version scope.",
        ),
        fix_steps=(
            "If no local record exists, complete the typed host/read-only repair and its verification; do not manually create a knowledge record.",
            "If the cache is rejected, preserve it and review the visible integrity warning. ROMVERSE will not rewrite or count modified contributions.",
            "If the record is candidate-only, gather another locally verified success before relying on it as a reusable fix.",
            "If the record is retired, resolve the failed verification or version drift and create fresh exact-scope evidence instead of reviving the old record.",
        ),
        verification=(
            "Archives reloads the cache and shows the same compiled state, confidence, success/failure counts, source families, and exact scope.",
            "A new query can use only compatible non-retired knowledge; retired records remain inspection-only.",
            "The record remains guidance-only and cannot approve, build, install, flash, publish, upload, or execute remote instructions.",
        ),
        tags=(
            "local learning missing",
            "synapse fix retired",
            "learned outcome unavailable",
            "archives learned fixes",
            "verified repair memory",
            "tool version drift",
            "guidance only knowledge",
        ),
        route="archives",
        evidence="ROMVERSE compiles Local Learning only from the digest-verified private Synapse cache and its typed local action evidence contracts.",
        automation="PRIVATE READ-ONLY INDEXING AND COMPATIBLE-SCOPE QUERY ONLY • NO UPLOAD, APPROVAL, REMOTE TEXT EXECUTION, OR DEVICE ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "command-deck-exact-workflow-handoff",
        "Command Deck opens ROM Studio but not the requested workflow",
        "ROMVERSE WORKFLOWS",
        "Build ROM, Pre-Build Simulation, and Recipes share ROM Studio, but they are not the "
        "same intent. ROMVERSE preserves the selected card as an owner-controlled handoff: "
        "Genesis opens for Build ROM, Build & Proof is selected for a dry-run, and Recipe "
        "Forge is selected for contained customization. A route alone is not treated as a "
        "successful feature connection.",
        checks=(
            "Confirm the ROM Studio handoff banner names the exact Command Deck action you selected.",
            "For Pre-Build Simulation, confirm Build & Proof is selected and Plan build (dry-run) is the highlighted next control.",
            "For Recipes, confirm Recipe Forge is selected and its readiness text is bound to the current project and working tree.",
            "Treat a prerequisite badge as a safe stop; it must name the missing project, protected original, inspection, or working tree without starting work.",
        ),
        fix_steps=(
            "Return to Command Deck and select the intended card again so ROM Studio can compile a fresh handoff from its current project state.",
            "Complete only the prerequisite named in the handoff using Source Lab or Genesis Sequence, then re-open the original card.",
            "Use Plan build (dry-run) for an execution-locked input plan, or Recipe Forge for a previewed rollback-protected change; do not substitute one workflow for the other.",
            "If the exact banner does not appear, keep ROM Studio open and inspect Activity Center before retrying; navigation alone grants no execution authority.",
        ),
        verification=(
            "Build ROM opens Genesis Sequence at the current project's exact next safe stage without starting a build or phone action.",
            "Pre-Build Simulation selects Build & Proof and reports READY only when a contained working tree exists; the worker remains idle until the user chooses the dry-run control.",
            "Recipes selects Recipe Forge and reports READY only when contained targets can be designed; no recipe executes during the handoff.",
            "Missing, stale, or incomplete context remains visibly stopped in ROM Studio and changes no workspace file or connected device.",
        ),
        tags=(
            "command deck wrong workflow",
            "rom studio generic route",
            "pre-build simulation handoff",
            "recipes handoff",
            "build rom genesis",
            "workflow prerequisite",
            "feature connection",
        ),
        route="command_deck",
        evidence="ROMVERSE tests the three Command Deck actions against their exact ROM Studio owner state, selected command group, readiness copy, and zero-worker boundary.",
        automation="EXACT LOCAL NAVIGATION AND PREREQUISITE EXPLANATION ONLY • NO BUILD, RECIPE EXECUTION, APPROVAL, FLASH, OR PHONE ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "command-deck-current-evidence-handoff",
        "Command Deck owner page opens without current device evidence",
        "ROMVERSE WORKFLOWS",
        "Device DNA, Health Review, and Rescue & Backup each depend on a different current "
        "evidence owner. Opening the right page is not enough: Device Atlas must identify the "
        "active Device Pack report, Quantum Optimizer must summarize the current diagnostic "
        "report, and Time Machine must compile the current device, plan, tool, project, and "
        "snapshot recovery map. Missing evidence stays an explicit prerequisite.",
        checks=(
            "Confirm the destination shows COMMAND DECK HANDOFF and names Device DNA, current health evidence, or the current recovery map.",
            "For Device DNA, compare model/codename, Pack id/version, report digest, passed checks, and separate build/flash states with Device Atlas.",
            "For Health Review, compare the device name, health score, finding count, and highest-priority finding with the current read-only report.",
            "For Rescue & Backup, compare the connected device, Guardian plan integrity, Platform Tools state, ROM project count, and local snapshot count.",
        ),
        fix_steps=(
            "If the handoff says evidence needed, connect and authorize one phone and run a fresh read-only Device Engine scan; do not infer the missing state.",
            "If Device DNA is identity-only, review the official identity and add an integrity-checked exact Device Pack contract before expecting build or flash requirements.",
            "If Health Review has no report, use Refresh health data; the Command Deck handoff itself deliberately does not launch a scan or optimization.",
            "If recovery evidence is incomplete, record only the named Guardian plan, Platform Tools, project, or snapshot prerequisite from Time Machine.",
        ),
        verification=(
            "Each card opens its canonical owner and displays a fresh banner compiled from that owner's current in-memory or integrity-checked local evidence.",
            "A new device scan clears the previous handoff so stale model, health, or recovery claims are not retained.",
            "Ready evidence reveals exact next controls while missing evidence remains visibly stopped with no substitute claim.",
            "Opening any of the three handoffs leaves scan, optimization, cleanup, backup, copy, restore, build, flash, and phone workers idle.",
        ),
        tags=(
            "owner page missing evidence",
            "command deck current evidence",
            "device dna handoff",
            "health review handoff",
            "rescue backup handoff",
            "generic owner navigation",
            "stale dashboard context",
        ),
        route="command_deck",
        evidence="ROMVERSE tests prerequisite and connected-device states across Device Atlas, Quantum Optimizer, and Time Machine while asserting their execution workers remain idle.",
        automation="CURRENT EVIDENCE SUMMARY AND EXACT LOCAL NAVIGATION ONLY • NO SCAN, OPTIMIZATION, CLEANUP, BACKUP, RESTORE, BUILD, FLASH, OR PHONE ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "rom-studio-cross-feature-context",
        "Open ROM Studio loses the originating Pack, toolchain, or Nexus project",
        "ROMVERSE WORKFLOWS",
        "A cross-feature Continue or Open control must carry its verified reason into ROM "
        "Studio. Device Atlas contributes the current exact Device Pack report, Forge Arsenal "
        "adds the freshly verified ordered host toolchain, and ROMVERSE Nexus identifies the "
        "exact selected project and its Device DNA/Compatibility Matrix state. Generic page "
        "navigation is not accepted as a completed handoff.",
        checks=(
            "Read the ROM Studio handoff eyebrow and confirm it names DEVICE ATLAS, FORGE ARSENAL, or ROMVERSE NEXUS rather than Command Deck.",
            "For Pack handoffs, compare model/codename, Pack id/version, report digest, and separate build/flash state with the source page.",
            "For Forge handoffs, confirm every ordered required tool remains freshly available and the retained Device Atlas digest is still current.",
            "For Nexus handoffs, confirm the exact project id is selected and missing Device DNA or Compatibility Matrix evidence remains explicit.",
        ),
        fix_steps=(
            "Return to the originating feature and use its Continue/Open control again so ROMVERSE can revalidate the source identity at the boundary.",
            "If Device Atlas context changed, run a fresh read-only scan and reopen the current Requirements Blueprint before continuing.",
            "If a Forge context is stale or a required tool is missing, re-open it from Device Atlas and freshly verify the declared subset.",
            "If a Nexus project is missing, create or select the exact protected-source project; do not substitute another current Studio project.",
        ),
        verification=(
            "Device Atlas Continue opens Genesis with the current exact Pack report visible and does not start a build or phone action.",
            "A verified build/artifact lane selects Build & Proof, while Forge Arsenal continues only when every declared host tool remains ready.",
            "Nexus selects the exact project and reports its current evidence prerequisite without generating a plan or starting a project worker.",
            "Changed Pack, tool, report, or project identity leaves the source page visibly stopped instead of opening an unrelated Studio context.",
        ),
        tags=(
            "open rom studio loses context",
            "device atlas studio handoff",
            "forge arsenal studio handoff",
            "nexus project handoff",
            "wrong rom project selected",
            "stale build contract context",
            "continue button generic navigation",
        ),
        route="rom_studio",
        evidence="ROMVERSE revalidates the source owner immediately before navigation and tests the resulting Studio eyebrow, digest/project binding, selected command group, and idle-worker boundary.",
        automation="EXACT CONTEXT REVALIDATION, PROJECT SELECTION, AND WORKFLOW FOCUS ONLY • NO PROJECT WORKER, PLAN, BUILD, APPROVAL, FLASH, OR PHONE ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "rom-studio-outbound-evidence-context",
        "ROM Studio opens recovery, Device Atlas, or Guardian without the exact project",
        "ROMVERSE WORKFLOWS",
        "An outbound Studio control must carry the selected project and the evidence owned by "
        "that destination. Time Machine needs the exact project and its current snapshot records; "
        "Device Atlas needs the project Pack/source relationship; Guardian Core needs the exact "
        "command-free manifest plus current phone and readiness evidence. A page opening by itself "
        "does not prove that the handoff succeeded.",
        checks=(
            "Confirm the destination eyebrow names ROM STUDIO HANDOFF and shows the originating project id rather than whichever project was already selected there.",
            "In Time Machine, compare the protected-source prefix and selected snapshot with the current ROM Studio project.",
            "In Device Atlas, compare project Pack id and protected-source digest with the Pack build contract; identity match alone must not imply build or flash readiness.",
            "In Guardian Core, compare manifest, handoff, source, project, model/codename, data mode, blockers, and zero-authority invariants.",
        ),
        fix_steps=(
            "Return to the exact ROM Studio project and reopen the destination from its relevant recovery or readiness control.",
            "If Time Machine rejects the project, reload the project and create or verify a schema-two local baseline snapshot before relying on rollback.",
            "If Device Atlas reports a Pack/source/device mismatch, connect and scan the exact target; never substitute a similar model or generic Pack.",
            "If Guardian expires the manifest, return to Forge Control and compile a fresh review from current project, phone, readiness, handoff, and artifact evidence.",
        ),
        verification=(
            "Time Machine selects the exact project and snapshot while leaving every backup and restore worker idle.",
            "Device Atlas shows the project source/Pack relationship and reports EXACT MATCH only when the current report is genuinely ready.",
            "Guardian Core retains the exact manifest as persistent evidence and revalidates it whenever the page is revisited.",
            "Returning from Guardian selects the exact ROM project and Build & Proof group; stale project, phone, Pack, snapshot, or manifest evidence stops visibly in-page.",
        ),
        tags=(
            "rom studio loses project on navigation",
            "time machine wrong project",
            "device atlas wrong pack context",
            "guardian manifest only in dialog",
            "guardian context expired",
            "outbound project handoff",
            "cross feature evidence routing",
        ),
        route="rom_studio",
        evidence="ROMVERSE tests exact project selection, snapshot/source/Pack identity, persistent Guardian manifest identity, stale-context expiry, return routing, and idle worker/device boundaries.",
        automation="EXACT PROJECT, SNAPSHOT, PACK, SOURCE, AND COMMAND-FREE MANIFEST NAVIGATION ONLY • NO WORKER, BUILD, APPROVAL, RESTORE, FLASH, OR PHONE ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "desktop-legal-publication-boundary",
        "About shows Terms, but public legal terms are not published",
        "ROMVERSE WORKFLOWS",
        "ROMVERSE v0.1.0 is an internal development alpha. The source tree contains a "
        "proprietary development-snapshot licence, while the approved product commitments "
        "explicitly keep billing promises subject to production implementation and published "
        "terms. A link-like Terms label must therefore report the missing publication gate; it "
        "cannot imply that a reviewed public contract already exists.",
        checks=(
            "Confirm the installed build identifies itself as internal alpha rather than a public production release.",
            "Inspect the packaged/source LICENSE and distinguish source-use permission from customer terms of service.",
            "Confirm no public terms document has been packaged, versioned, and approved for this release.",
            "Treat membership prices and future-service promises as product direction until production billing and published terms exist.",
        ),
        fix_steps=(
            "Replace inert or misleading Terms text with a visible internal-alpha state and an exact explanatory record.",
            "Before public release, obtain the reviewed legal text, assign a version/effective date, package it immutably, and connect the UI to that exact artifact.",
            "Keep unavailable purchasing, renewal, cancellation, and public-account actions disabled until the production service and terms agree.",
        ),
        verification=(
            "About displays PUBLIC LEGAL PACK NOT ISSUED and opens this exact record.",
            "The destination retains a safe Return to About path and starts no account, browser, billing, or network action.",
            "No UI label claims that public legal terms were accepted, published, or approved in this internal build.",
        ),
        tags=(
            "terms not published",
            "terms link does nothing",
            "internal alpha legal status",
            "membership terms unavailable",
            "public legal pack",
            "terms of service missing",
        ),
        route="about",
        evidence="The current source contains a proprietary LICENSE and approved commitments that keep billing benefits subject to production implementation and published terms; no separate public terms artifact is packaged.",
        automation="STATUS AND EXACT LOCAL GUIDANCE ONLY • NO LEGAL ACCEPTANCE, ACCOUNT, BILLING, BROWSER, NETWORK, OR PUBLISH ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "desktop-local-privacy-boundary",
        "About Privacy must describe the real local and online data boundary",
        "ROMVERSE WORKFLOWS",
        "A generic Privacy label is not evidence of a privacy policy. The current Desktop is "
        "local-first: activity, diagnostics, projects, receipts, Galaxy topics, Device Atlas "
        "catalogs, and Synapse memory are stored in the selected workspace under bounded schemas. "
        "Online intelligence, community research, Members sign-in, and wireless Companion each "
        "have separate settings or explicit flows and must never be implied by opening About.",
        checks=(
            "Inspect Settings for online intelligence, community research, Synapse contribution, notifications, backup destination, and Members configuration.",
            "Confirm device serials are masked or pseudonymized in user-facing ledgers, exports, approvals, and repair memory.",
            "Distinguish local Galaxy topics from future public publishing and local Synapse memory from any remote contribution.",
            "Confirm an external service is shown as unavailable when it is not configured or cannot prove its response.",
        ),
        fix_steps=(
            "Keep data in the selected local workspace unless one named, enabled workflow explicitly requires a network service.",
            "Scrub paths, full hashes, raw serials, credentials, and unrelated device data before any permitted bounded contribution or export.",
            "Fail closed on malformed, oversized, linked, stale, redirected, or integrity-rejected local and remote evidence.",
            "Before public release, publish a reviewed privacy statement covering collection, retention, deletion, accounts, backups, diagnostics, research, Companion, and community services.",
        ),
        verification=(
            "Opening the About privacy control performs local navigation only and returns to About without changing settings.",
            "Private workspace files remain local and integrity-protected; online switches retain their current explicit values.",
            "No phone command, upload, contribution, account request, or public post starts from the About trust dock.",
        ),
        tags=(
            "privacy policy local workspace",
            "about privacy link",
            "local first data boundary",
            "serial masking",
            "online intelligence privacy",
            "community publishing locked",
        ),
        route="about",
        evidence="ROMVERSE stores typed bounded records in the selected workspace, uses pseudonymous device bindings, and exposes online/community capabilities behind explicit configuration and workflow boundaries.",
        automation="LOCAL GUIDANCE NAVIGATION ONLY • NO SETTING CHANGE, UPLOAD, CONTRIBUTION, ACCOUNT, PUBLISH, OR PHONE ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "desktop-licence-notice-inventory",
        "Open-source licences or third-party notices are incomplete",
        "TOOLS & HOST",
        "The ROMVERSE source snapshot is proprietary and includes its own LICENSE, but it also "
        "depends on Python, PySide6/Qt, cryptography, downloaded Android tools, host packages, and "
        "other components with separate licences. A source licence is not a complete third-party "
        "notice inventory, and a tool receipt naming Apache-2.0 does not cover every bundled or "
        "installed dependency.",
        checks=(
            "Confirm the ROMVERSE LICENSE is present and matches the package metadata's proprietary classification.",
            "Inventory every runtime, bundled asset, Python distribution, Qt component, managed Android artifact, and redistributed binary in the exact release artifact.",
            "Verify each notice against the exact installed version and source/publisher receipt rather than a package name alone.",
            "Separate host-only system tools from redistributed files and preserve required licence texts for bundled downloads.",
        ),
        fix_steps=(
            "Keep the About status honest while the complete notice bundle is not generated and reviewed.",
            "At release time, generate a deterministic dependency inventory from the final artifact, attach exact licence texts and attributions, and review incompatible or unknown entries.",
            "Bind the notice bundle digest to the signed Desktop release and keep managed-tool licence receipts independently verifiable.",
        ),
        verification=(
            "About opens this exact record instead of displaying inert Open-source licences or Third-party notices text.",
            "A public release remains blocked until its final artifact and complete reviewed notice bundle have matching provenance.",
            "Opening the record installs no dependency, accepts no SDK licence, downloads nothing, and changes no host or phone state.",
        ),
        tags=(
            "third party notices incomplete",
            "open source licences missing",
            "license inventory",
            "qt pyside cryptography notices",
            "about licences link",
            "release notice bundle",
        ),
        route="about",
        evidence="The repository contains a proprietary LICENSE and explicit dependency/tool licence evidence, but no complete deterministic public-release third-party notice bundle.",
        automation="LOCAL INVENTORY GUIDANCE ONLY • NO DOWNLOAD, INSTALL, LICENCE ACCEPTANCE, HOST CHANGE, OR RELEASE CLAIM",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "desktop-release-provenance",
        "Changelog or installed Desktop build cannot prove what is running",
        "ROMVERSE WORKFLOWS",
        "A version label or changelog sentence cannot prove the installed executable contains the "
        "reviewed changes. Release provenance needs the source revision, deterministic test result, "
        "wheel checksum and member validation, installed import path, protected brand-asset hashes, "
        "and a live process started from that exact environment. Signed update metadata remains a "
        "separate production release gate.",
        checks=(
            "Compare the source revision with the wheel built from that clean worktree.",
            "Verify the wheel ZIP, required members, SHA-256, installed module paths, and app entry point.",
            "Recheck the official ROMVERSE and RadForge logo hashes after build and install.",
            "Confirm one live Desktop process uses the pinned launcher environment and produces no startup error.",
        ),
        fix_steps=(
            "Do not publish an unbound changelog; record each verified milestone with its local revision and artifact checksum.",
            "Rebuild and reinstall after any source change, then rerun targeted installed-package checks and the full source suite.",
            "Before public updates, sign release artifacts and update metadata, publish checksums and limitations, and verify rollback instructions.",
        ),
        verification=(
            "About opens this exact provenance record and retains Return to About.",
            "The running Desktop imports from the installed wheel environment and its launcher remains pinned to that environment.",
            "No unsigned artifact or UI version string is represented as a signed public release.",
        ),
        tags=(
            "changelog build proof",
            "installed desktop provenance",
            "version label not enough",
            "wheel checksum",
            "source revision installed build",
            "signed update missing",
        ),
        route="about",
        evidence="ROMVERSE release gates already require source tests, wheel integrity, installed import verification, protected asset hashes, launcher identity, and a live runtime; signed update metadata is not implemented in this alpha.",
        automation="LOCAL EVIDENCE REVIEW ONLY • NO BUILD, INSTALL, UPDATE, SIGNING, PUBLISH, OR PROCESS ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "activity-exact-source-context",
        "Activity outcome cannot reopen its exact source evidence",
        "ROMVERSE WORKFLOWS",
        "Activity Center stores a bounded redacted outcome summary, not the producing record. "
        "Supported events can also carry a privacy-safe typed identifier that ROMVERSE "
        "revalidates before restoring the exact ROM project, Health Timeline snapshot, "
        "recovery-readiness plan, Time Machine snapshot, guided repair session, or APK install "
        "receipt, or private local Galaxy topic. Older and unsupported events honestly open "
        "only their canonical source page.",
        checks=(
            "Confirm the event shows EXACT CONTEXT READY before expecting an exact project or snapshot handoff.",
            "For ROM Studio, confirm the referenced project manifest still exists and passes the project store's validation.",
            "For Health Timeline, confirm the snapshot is integrity-enveloped and still passes its SHA-256 verification.",
            "For Time Machine, Recovery Bay, and App Launchpad, confirm the exact plan, snapshot, session, or receipt still passes its owning store's integrity checks.",
            "For Galaxy, confirm the private topic still exists in the integrity-checked local Community Lab store.",
            "Treat a page-level handoff as navigation only; it does not claim that a previous selection was restored.",
        ),
        fix_steps=(
            "Refresh Activity Center so it rereads the bounded local ledger and rejects modified or unsupported records.",
            "If exact context is available, use Open exact source evidence; ROMVERSE revalidates the identifier and owning record before leaving Activity Center.",
            "If the handoff stops, preserve the activity and source evidence, then open the canonical page and inspect its current verified records manually.",
            "Do not insert paths, device serials, credentials, or arbitrary routes into the ledger; the context contract rejects them.",
        ),
        verification=(
            "A valid ROM project handoff opens ROM Studio with that exact project selected.",
            "A valid diagnostic handoff opens Health Timeline with that exact verified snapshot selected.",
            "Valid Time Machine, Recovery Bay, and App Launchpad handoffs display their exact verified record without recreating approval or execution state.",
            "A valid Galaxy handoff opens the exact private local topic and never publishes or synchronizes it.",
            "Missing, legacy, tampered, incomplete, or unsupported context leaves Activity Center visible with a safe-stop reason and changes no workspace or phone state.",
        ),
        tags=(
            "activity exact source",
            "activity context unavailable",
            "open exact project evidence",
            "open diagnostic snapshot",
            "activity handoff stopped",
            "legacy activity event",
            "source evidence missing",
            "backup plan activity",
            "repair session activity",
            "apk receipt activity",
            "time machine snapshot activity",
            "galaxy topic activity",
        ),
        route="activity_center",
        evidence="ROMVERSE accepts only registered type-to-route pairs and path-free identifiers, then asks the owning validated store to reload the exact current record.",
        automation="LOCAL REVALIDATION AND EXACT NAVIGATION ONLY • NO APPROVAL, RESTORE, BUILD, INSTALL, FLASH, PUBLISH, OR DEVICE ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "activity-galaxy-topic-context",
        "Activity Center opens Galaxy but not the exact local topic",
        "ROMVERSE WORKFLOWS",
        "A Galaxy outcome is not fully connected when Activity Center can open only the general "
        "Community Lab. Topic creation and replies now carry a path-free local topic id. "
        "Activity Center validates that typed id, asks Galaxy's integrity-checking store to "
        "reload it, refreshes the destination, and verifies the same topic again before showing "
        "the handoff as complete.",
        checks=(
            "Confirm the Activity event says EXACT CONTEXT READY and identifies GALAXY TOPIC rather than offering a generic Galaxy route.",
            "Confirm the topic id is a 32-character lowercase hexadecimal local identifier, not a title, path, author, account, or device id.",
            "Check the Galaxy community record is a regular bounded local file and its SHA-256 integrity envelope still verifies.",
            "Confirm the topic still exists; a deletion outcome intentionally retains only page-level Galaxy navigation.",
        ),
        fix_steps=(
            "Refresh Activity Center so the private ledger and its registered type-to-route contract are reread.",
            "Use Open exact ROMVERSE Galaxy evidence; ROMVERSE clears any search filter and selects only the reloaded matching topic id.",
            "If the exact handoff stops, leave the activity record intact and inspect the current local Galaxy store; do not substitute a similarly named topic.",
            "For legacy or nonconforming topic ids, retain generic Galaxy navigation rather than dropping the entire activity outcome.",
        ),
        verification=(
            "A reply event recorded for one topic reopens that exact topic even when another topic was selected most recently.",
            "The destination reports integrity-checked local evidence and keeps online publishing locked.",
            "Deleting the referenced topic makes the same handoff stay in Activity Center with a visible safe-stop reason.",
            "The round trip starts no publish, synchronization, account, worker, build, approval, install, flash, or phone action.",
        ),
        tags=(
            "galaxy activity exact topic",
            "activity opens wrong galaxy topic",
            "community lab source context",
            "galaxy topic missing",
            "private topic activity handoff",
            "right page wrong local topic",
            "nothing published synchronized",
        ),
        route="activity_center",
        evidence="ROMVERSE regression tests record a typed Galaxy topic event, deliberately select another topic, restore the exact original id, and then prove a deleted source stops safely.",
        automation="LOCAL INTEGRITY REVALIDATION AND EXACT NAVIGATION ONLY • NO PUBLISH, SYNC, ACCOUNT, WORKER, BUILD, APPROVAL, INSTALL, FLASH, OR PHONE ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "cross-feature-return-loses-evidence",
        "Return button opens the right page but loses the exact evidence",
        "ROMVERSE WORKFLOWS",
        "A return control is not safe merely because it opens the expected page. Guardian Core, "
        "Time Machine, and Forge Arsenal must carry the exact plan, project, Pack, and report "
        "identity they originally received, then ask the owning feature to revalidate that "
        "identity immediately before navigation. A generic route can silently expose an unrelated "
        "current selection and is therefore treated as a failed handoff.",
        checks=(
            "Compare the source card's plan/report digest and project or Pack id with the destination's selected evidence.",
            "Confirm the return control was enabled by a retained exact context rather than by page availability alone.",
            "Re-read the owning store or current Device Atlas report; do not trust a digest retained only in a widget.",
            "Confirm the return does not create approval, execution authority, a worker, or a phone command.",
        ),
        fix_steps=(
            "Reopen the context from its owning feature so ROMVERSE can retain a fresh exact identity.",
            "For Guardian, regenerate or reopen the exact current Nexus or recovery-readiness plan when its digest changed.",
            "For Time Machine, reopen the current Device Atlas stock-recovery lane before creating or selecting its protected-source project.",
            "For Forge Arsenal, reopen the exact Requirements Blueprint compile lane after any phone, Pack, or report change.",
        ),
        verification=(
            "Guardian returns to the exact Nexus project/plan or Time Machine plan id and refuses superseded evidence in-page.",
            "Time Machine carries the same current Device Atlas report into ROM Studio and refuses a changed phone, Pack, or stock-recovery gate.",
            "Forge Arsenal returns to Device Atlas with the same Pack hash and report digest visibly restored.",
            "Every stale case leaves the source page visible with an explicit safe-stop reason and starts no worker or device action.",
        ),
        tags=(
            "return button loses context",
            "right page wrong evidence",
            "guardian return stale plan",
            "time machine device atlas report",
            "forge arsenal return device atlas",
            "generic navigation unsafe",
            "stale report refused",
            "exact reverse handoff",
        ),
        route="guardian_core",
        evidence="ROMVERSE tests both successful reverse routing and deliberate plan/report supersession while asserting exact destination identity and idle execution boundaries.",
        automation="EXACT IDENTITY REVALIDATION AND NAVIGATION ONLY • NO PLAN GENERATION, APPROVAL, WORKER, BUILD, RESTORE, FLASH, OR PHONE ACTION",
        source=ROMVERSE_SOURCE,
    ),
    _fix(
        "studio-continue-reloads-wrong-current-evidence",
        "ROM Studio opens with a different Nexus plan or Device Atlas report",
        "ROMVERSE WORKFLOWS",
        "A Continue/Open control can be wired to the correct page yet still be wrong if it sends "
        "no evidence identity. Nexus must send the selected project plus its current plan digest; "
        "Device Atlas must send its report id plus report digest. ROM Studio and MainWindow then "
        "independently reload the owning records before accepting the handoff, so a queued click "
        "cannot silently adopt evidence that changed after it was shown.",
        checks=(
            "In Nexus, compare the selected project id and displayed plan digest with the Studio handoff banner.",
            "In Device Atlas, compare the report id/digest, Pack id/version/hash, and model/codename with the Studio banner.",
            "Confirm a Nexus project-creation handoff carries two explicit empty identities rather than an unrelated selected project.",
            "Confirm the destination says no worker, plan, build, approval, flash, or phone action started.",
        ),
        fix_steps=(
            "Return to Nexus and reopen Studio from the freshly loaded selected project and plan; regenerate the plan if its evidence changed.",
            "Return to Device Atlas and reopen Studio from the current exact report after any phone, Pack, or attestation change.",
            "If no Nexus project exists, use the explicit protected-project creation handoff; do not reuse a previous Studio selection.",
            "Treat an in-page HANDOFF STOPPED message as evidence protection, then refresh the owning feature rather than bypassing it with sidebar navigation.",
        ),
        verification=(
            "A current Nexus plan opens its exact project and displays the same plan digest, objective, and status in ROM Studio.",
            "A superseded displayed Nexus plan leaves Nexus visible with a safe-stop explanation.",
            "A current Device Atlas report opens Genesis with the same report digest and exact Pack relationship.",
            "A mismatched report id/digest leaves Device Atlas visible and starts no Studio worker or phone action.",
        ),
        tags=(
            "studio wrong nexus plan",
            "studio wrong device atlas report",
            "continue button stale evidence",
            "queued signal current selection",
            "nexus plan digest handoff",
            "device atlas report id handoff",
            "rom studio context mismatch",
            "handoff stopped plan changed",
        ),
        route="rom_studio",
        evidence="ROMVERSE tests exact signal payloads, independent store reloading, successful destination rendering, superseded-plan refusal, mismatched-report refusal, and idle worker/device boundaries.",
        automation="EXACT PROJECT, PLAN, PACK, AND REPORT REVALIDATION ONLY • NO PLAN GENERATION, WORKER, BUILD, APPROVAL, FLASH, OR PHONE ACTION",
        source=ROMVERSE_SOURCE,
    ),
)


def _key_for(title: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:72]
    return f"guide-{key}"


def _legacy_route(title: str) -> str:
    lowered = title.casefold()
    if any(token in lowered for token in ("adb", "usb", "device engine", "windows setup")):
        return "command_deck"
    if any(token in lowered for token in ("time machine", "backup", "recovery checklist")):
        return "time_machine"
    if "app launchpad" in lowered:
        return "app_launchpad"
    if any(
        token in lowered
        for token in (
            "rom studio",
            "firmware source",
            "recipe",
            "rom inspection",
            "build plan",
            "ascension",
            "hyperos",
            "dynamic partition",
            "avb",
            "android auto",
            "first-boot",
            "debloat",
            "rom dna",
        )
    ):
        return "rom_studio"
    if any(token in lowered for token in ("diagnostic", "battery", "storage", "performance")):
        return "quantum_optimizer"
    if "recovery" in lowered or "scan fails" in lowered:
        return "recovery_bay"
    if "device atlas" in lowered or "another phone" in lowered:
        return "device_atlas"
    if "guardian" in lowered or "approval" in lowered:
        return "guardian_core"
    if "logs" in lowered or "history" in lowered:
        return "activity_center"
    if "companion" in lowered or "galaxy" in lowered:
        return "companion_link"
    return "archives"


def _legacy_category(title: str, route: str) -> str:
    lowered = title.casefold()
    if route == "command_deck" or "adb" in lowered or "usb" in lowered:
        return "CONNECTIVITY & ADB"
    if route == "app_launchpad":
        return "APPS & PACKAGES"
    if route in {"guardian_core", "recovery_bay", "time_machine"}:
        return "RECOVERY & GUARDIAN"
    if route == "quantum_optimizer":
        return "DIAGNOSTICS & HEALTH"
    if any(token in lowered for token in ("avb", "boot", "root")):
        return "BOOT & SECURITY"
    if any(token in lowered for token in ("partition", "filesystem")):
        return "FILESYSTEMS & PARTITIONS"
    if route == "rom_studio":
        return "BUILD & RECIPES"
    return "ROMVERSE WORKFLOWS"


def build_catalog(legacy_guides: tuple[tuple[str, str], ...]) -> tuple[ArchiveArticle, ...]:
    """Upgrade established guides and append structured, evidence-labelled known fixes."""

    established = []
    for title, body in legacy_guides:
        route = _legacy_route(title)
        established.append(
            ArchiveArticle(
                _key_for(title),
                title,
                _legacy_category(title, route),
                body,
                (),
                (),
                (),
                (title,),
                route,
                "Established ROMVERSE guidance; use exact live evidence before applying it.",
                "GUIDANCE ONLY UNLESS A TYPED ROMVERSE WORKFLOW STATES OTHERWISE",
                FIELD_SOURCE if "Verified HyperOS" in title else ROMVERSE_SOURCE,
            )
        )
    catalog = tuple(established) + KNOWN_FIXES
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: tuple[ArchiveArticle, ...]) -> None:
    if not catalog or len(catalog) > 256:
        raise ValueError("Archives catalog size is invalid")
    keys: set[str] = set()
    titles: set[str] = set()
    for article in catalog:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", article.key):
            raise ValueError(f"Archives key is invalid: {article.key}")
        if article.key in keys or article.title.casefold() in titles:
            raise ValueError(f"Archives article identity is duplicated: {article.title}")
        keys.add(article.key)
        titles.add(article.title.casefold())
        if article.category not in CATEGORIES or article.route not in CANONICAL_ROUTES:
            raise ValueError(f"Archives article classification is invalid: {article.title}")
        bounded = (
            (article.title, 140),
            (article.meaning, 1_600),
            (article.evidence, 600),
            (article.automation, 300),
            (article.source.label, 180),
            (article.source.authority, 100),
        )
        if any(not value.strip() or len(value) > limit for value, limit in bounded):
            raise ValueError(f"Archives article text is invalid: {article.title}")
        for collection in (article.checks, article.fix_steps, article.verification, article.tags):
            if len(collection) > 16 or any(
                not item.strip() or len(item) > 500 for item in collection
            ):
                raise ValueError(f"Archives article collection is invalid: {article.title}")
        if article.source.url:
            parsed = urlsplit(article.source.url)
            if (
                len(article.source.url) > 500
                or parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError(f"Archives source URL is invalid: {article.title}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", article.source.reviewed_on):
            raise ValueError(f"Archives source review date is invalid: {article.title}")


def _normalized(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


SEARCH_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "for",
        "in",
        "is",
        "not",
        "of",
        "on",
        "or",
        "real",
        "romverse",
        "the",
        "to",
        "topic",
        "with",
    }
)


def search_catalog(
    catalog: tuple[ArchiveArticle, ...],
    query: str,
    category: str = ALL_CATEGORIES,
    *,
    limit: int = 256,
) -> tuple[ArchiveMatch, ...]:
    """Rank a bounded local query without network access or execution authority."""

    bounded_limit = max(1, min(limit, 256))
    selected = (
        catalog
        if category == ALL_CATEGORIES
        else tuple(article for article in catalog if article.category == category)
    )
    normalized = _normalized(query[:160])
    if not normalized:
        return tuple(ArchiveMatch(article, 0) for article in selected[:bounded_limit])
    all_tokens = tuple(dict.fromkeys(normalized.split()))[:16]
    query_tokens = tuple(token for token in all_tokens if token not in SEARCH_STOP_WORDS)
    if not query_tokens:
        query_tokens = all_tokens
    exact: list[ArchiveMatch] = []
    partial: list[ArchiveMatch] = []
    for index, article in enumerate(selected):
        title = _normalized(article.title)
        tags = _normalized(" ".join(article.tags))
        document = _normalized(article.search_document)
        if normalized == title:
            score = 1_200
        elif normalized in title:
            score = 1_000
        elif normalized in tags:
            score = 900
        elif normalized in document:
            score = 700
        else:
            hits = sum(token in document for token in query_tokens)
            required_hits = 1 if len(query_tokens) == 1 else max(2, (len(query_tokens) + 1) // 2)
            if hits < required_hits:
                continue
            score = hits * 90
            if hits == len(query_tokens):
                score += 260
            score += sum(token in title for token in query_tokens) * 70
        match = ArchiveMatch(article, score * 1_000 - index)
        (exact if normalized in document else partial).append(match)
    matches = exact or partial
    matches.sort(key=lambda item: (-item.score, item.article.title.casefold()))
    return tuple(matches[:bounded_limit])


def catalog_metrics(catalog: tuple[ArchiveArticle, ...]) -> dict[str, int]:
    return {
        "guides": len(catalog),
        "categories": len({article.category for article in catalog}),
        "official_sources": sum(bool(article.source.url) for article in catalog),
        "known_fixes": len(KNOWN_FIXES),
    }
