"""Curated Android-wide reference seeds for the local ROMVERSE Archives.

The records in this module are intentionally data-only.  Archives applies its
normal validation and search rules before exposing them in the desktop app.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReferenceSourceSeed:
    label: str
    authority: str
    url: str
    reviewed_on: str = "2026-09-03"


@dataclass(frozen=True, slots=True)
class ReferenceArticleSeed:
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
    source_id: str


SOURCES = {
    "build": ReferenceSourceSeed(
        "Android Build identity fields",
        "OFFICIAL ANDROID",
        "https://developer.android.com/reference/android/os/Build",
    ),
    "catalog": ReferenceSourceSeed(
        "Google Play supported Android device catalog",
        "OFFICIAL GOOGLE • IDENTITY ONLY",
        "https://storage.googleapis.com/play_public/supported_devices.csv",
    ),
    "adb": ReferenceSourceSeed(
        "Android Debug Bridge (adb)",
        "OFFICIAL ANDROID",
        "https://developer.android.com/tools/adb",
    ),
    "hardware": ReferenceSourceSeed(
        "Run apps on a hardware device",
        "OFFICIAL ANDROID",
        "https://developer.android.com/studio/run/device",
    ),
    "oem_usb": ReferenceSourceSeed(
        "Install OEM USB drivers",
        "OFFICIAL ANDROID",
        "https://developer.android.com/studio/run/oem-usb",
    ),
    "platform_tools": ReferenceSourceSeed(
        "SDK Platform Tools release notes",
        "OFFICIAL ANDROID",
        "https://developer.android.com/tools/releases/platform-tools",
    ),
    "ota_tools": ReferenceSourceSeed(
        "Build OTA packages",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/core/ota/tools",
    ),
    "ab": ReferenceSourceSeed(
        "A/B seamless system updates",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/core/ota/ab",
    ),
    "nonab": ReferenceSourceSeed(
        "Non-A/B system updates",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/core/ota/nonab",
    ),
    "sign_builds": ReferenceSourceSeed(
        "Sign Android builds and OTA packages",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/core/ota/sign_builds",
    ),
    "update_engine": ReferenceSourceSeed(
        "Android update_engine error codes",
        "AOSP SOURCE",
        "https://android.googlesource.com/platform/system/update_engine/+/refs/heads/main/common/error_code.h",
    ),
    "fastbootd": ReferenceSourceSeed(
        "AOSP fastboot and userspace fastbootd",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/core/architecture/bootloader/fastbootd",
    ),
    "partitions": ReferenceSourceSeed(
        "Android partitions overview",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/core/architecture/partitions",
    ),
    "dynamic": ReferenceSourceSeed(
        "Android dynamic partitions",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/core/ota/dynamic_partitions",
    ),
    "gsi": ReferenceSourceSeed(
        "Android Generic System Images",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/core/tests/vts/gsi",
    ),
    "compatibility": ReferenceSourceSeed(
        "Android compatibility program overview",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/compatibility/overview",
    ),
    "cts": ReferenceSourceSeed(
        "Android Compatibility Test Suite",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/compatibility/cts",
    ),
    "vts": ReferenceSourceSeed(
        "Android Vendor Test Suite",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/core/tests/vts",
    ),
    "avb": ReferenceSourceSeed(
        "Android Verified Boot",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/security/features/verifiedboot/avb",
    ),
    "boot_flow": ReferenceSourceSeed(
        "Android Verified Boot flow",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/security/features/verifiedboot/boot-flow",
    ),
    "unlock": ReferenceSourceSeed(
        "Lock and unlock the Android bootloader",
        "OFFICIAL AOSP",
        "https://source.android.com/docs/core/architecture/bootloader/locking_unlocking",
    ),
    "apksigner": ReferenceSourceSeed(
        "Android apksigner verification",
        "OFFICIAL ANDROID",
        "https://developer.android.com/tools/apksigner",
    ),
    "package_manager": ReferenceSourceSeed(
        "Android PackageManager install status definitions",
        "AOSP SOURCE",
        "https://android.googlesource.com/platform/frameworks/base/+/android16-qpr2-release/core/java/android/content/pm/PackageManager.java",
    ),
    "backup": ReferenceSourceSeed(
        "Back up or restore data on Android",
        "OFFICIAL ANDROID SUPPORT",
        "https://support.google.com/android/answer/2819582",
    ),
    "pixel_factory": ReferenceSourceSeed(
        "Factory images for Google Pixel devices",
        "OFFICIAL GOOGLE • PIXEL-SCOPED",
        "https://developers.google.com/android/images",
    ),
    "pixel_ota": ReferenceSourceSeed(
        "Full OTA images for Google Pixel devices",
        "OFFICIAL GOOGLE • PIXEL-SCOPED",
        "https://developers.google.com/android/ota",
    ),
    "xiaomi": ReferenceSourceSeed(
        "Xiaomi HyperOS update guidance",
        "OFFICIAL XIAOMI • MODEL/REGION-SCOPED",
        "https://www.mi.com/global/support/faq/details/KA-483292/",
    ),
    "motorola": ReferenceSourceSeed(
        "Motorola Software Fix rescue update",
        "OFFICIAL MOTOROLA • MODEL-SCOPED",
        "https://en-ca.support.motorola.com/app/answers/detail/a_id/167770/",
    ),
    "reddit": ReferenceSourceSeed(
        "Reddit Android community reports",
        "COMMUNITY • REPORTS REQUIRE CORROBORATION",
        "https://www.reddit.com/r/AndroidQuestions/",
    ),
    "stackexchange": ReferenceSourceSeed(
        "Android Enthusiasts questions and accepted answers",
        "COMMUNITY • ACCEPTED ANSWERS REQUIRE SCOPE CHECK",
        "https://android.stackexchange.com/",
    ),
    "xda": ReferenceSourceSeed(
        "XDA device forums and development reports",
        "COMMUNITY • DEVICE/BUILD-SCOPED",
        "https://xdaforums.com/",
    ),
    "github": ReferenceSourceSeed(
        "Upstream tool and ROM project issue trackers",
        "MAINTAINER/COMMUNITY • REPOSITORY-SCOPED",
        "https://github.com/",
    ),
}


def _article(
    key: str,
    title: str,
    category: str,
    source_id: str,
    meaning: str,
    *,
    checks: tuple[str, ...],
    fix_steps: tuple[str, ...],
    verification: tuple[str, ...],
    tags: tuple[str, ...],
    route: str,
    evidence: str,
    automation: str = "GUIDANCE AND READ-ONLY EVIDENCE ONLY • NO DEVICE WRITE AUTHORITY",
) -> ReferenceArticleSeed:
    return ReferenceArticleSeed(
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
        source_id,
    )


ANDROID_REFERENCE_SEEDS = (
    _article(
        "android-identity-field-meanings",
        "Android device identity fields: brand, manufacturer, model, device, and product",
        "DEVICE IDENTITY & COMPATIBILITY",
        "build",
        "Android exposes several identity fields that describe different layers. Model is a user-visible model value; device and product identify the product implementation; brand and manufacturer identify branding and maker. Similar-looking values are not interchangeable.",
        checks=(
            "Collect every field in one read-only Device DNA scan instead of relying on the Settings name.",
            "Keep the original spelling and also build normalized aliases for comparison.",
        ),
        fix_steps=(
            "Match firmware against the strongest intersection of model, device/codename, product, region, and current build evidence.",
            "If fields disagree, label the identity ambiguous and stop compatibility escalation.",
        ),
        verification=(
            "The Device DNA receipt preserves each field separately with its evidence source.",
        ),
        tags=("android device id", "model codename product brand manufacturer", "build device"),
        route="device_atlas",
        evidence="The Android Build API defines these as distinct build-time identity values; no single value proves firmware compatibility.",
    ),
    _article(
        "android-build-fingerprint-meaning",
        "Read an Android build fingerprint without guessing",
        "DEVICE IDENTITY & COMPATIBILITY",
        "build",
        "A build fingerprint identifies one software build lineage and usually contains brand, product, device, release, build id, incremental value, build type, and tags. OEM formatting varies, so ROMVERSE stores both the complete fingerprint and parsed fields.",
        checks=(
            "Capture the complete ro.build.fingerprint and the related product/system/vendor fingerprints.",
            "Compare the current incremental, build id, release, SDK, and security patch independently.",
        ),
        fix_steps=(
            "Use exact equality where an OTA declares a required pre-build; use aliases only for target-device matching.",
        ),
        verification=("Every parsed value can be traced back to the unchanged raw fingerprint.",),
        tags=("build fingerprint", "ro build fingerprint", "incremental build id release tags"),
        route="device_atlas",
        evidence="Android documents FINGERPRINT as a string that uniquely identifies the build; ROMVERSE does not treat it as a retail model name.",
    ),
    _article(
        "android-version-sdk-patch",
        "Android release, SDK level, build date, and security patch are different",
        "DEVICE IDENTITY & COMPATIBILITY",
        "build",
        "The marketing release, numeric SDK level, build timestamp, incremental version, and security patch date answer different questions. A higher-looking marketing label alone does not prove that firmware is a safe upgrade.",
        checks=(
            "Compare current and proposed SDK levels, security patch dates, build timestamps, and OEM incrementals.",
            "Check the package's own signed metadata rather than its filename.",
        ),
        fix_steps=(
            "Report each comparison separately and leave uncomparable OEM versions unknown.",
        ),
        verification=("The upgrade assessment cites the exact current and proposed values.",),
        tags=("sdk int android version security patch", "upgrade version compare"),
        route="device_atlas",
        evidence="The Android Build.VERSION API exposes SDK_INT, RELEASE, SECURITY_PATCH, and incremental data as separate properties.",
    ),
    _article(
        "google-device-catalog-authority",
        "What the official Google Play device ID catalog can and cannot prove",
        "DEVICE IDENTITY & COMPATIBILITY",
        "catalog",
        "Google's public supported-device catalog maps retail branding, marketing name, device code, and model. It is excellent naming evidence, but it does not publish partition layouts, firmware hashes, bootloader rules, recovery routes, or flash compatibility.",
        checks=(
            "Require an integrity-checked local catalog receipt and an exact brand/device match.",
            "Treat multiple matching retail variants as ambiguous until model evidence resolves them.",
        ),
        fix_steps=("Use Device Atlas to add a sourced Device Pack after identity recognition.",),
        verification=(
            "The match remains labelled identity-only with build and flash authority set to none.",
        ),
        tags=("google play supported devices csv", "device ids names catalog", "retail name"),
        route="device_atlas",
        evidence="ROMVERSE mirrors the bounded official CSV, verifies its digest and receipt, and never converts a name match into execution authority.",
    ),
    _article(
        "android-serial-is-not-model",
        "A USB or ADB serial is not a phone model or firmware target",
        "DEVICE IDENTITY & COMPATIBILITY",
        "adb",
        "ADB uses a transport serial to select one connected target. That identifier can distinguish transports, but it does not name the retail model and must not be sent to public knowledge sources.",
        checks=(
            "Use the serial only for exact local target selection.",
            "Collect model, device/codename, product, and build properties from the selected authorized device.",
        ),
        fix_steps=(
            "Mask the serial in the interface and redact it from error fingerprints and uploads.",
        ),
        verification=(
            "Logs and online lookup receipts contain a masked identifier, never the raw serial.",
        ),
        tags=("adb serial device id privacy", "usb serial model"),
        route="command_deck",
        evidence="ADB documents serial-based target selection; ROMVERSE applies a stricter privacy boundary to that identifier.",
    ),
    _article(
        "fastboot-identity-limit",
        "Fastboot product identity is useful but incomplete",
        "DEVICE IDENTITY & COMPATIBILITY",
        "fastbootd",
        "Bootloader Fastboot and userspace fastbootd can expose product, slot, lock state, and mode. They normally cannot provide the same Android runtime, health, package, or storage evidence as an authorized ADB scan.",
        checks=(
            "Read getvar product, current-slot, unlocked, secure, and is-userspace only through the bounded identity probe.",
            "Do not infer missing Android properties from an old scan of another boot state.",
        ),
        fix_steps=(
            "Combine current Fastboot evidence with an exact Device Pack and protected firmware metadata.",
        ),
        verification=(
            "Unavailable facts remain UNKNOWN and no reboot or write command is issued.",
        ),
        tags=("fastboot getvar product current slot", "fastbootd identity incomplete"),
        route="device_atlas",
        evidence="AOSP defines getvar and is-userspace for identity and mode discovery; these values do not describe the entire Android software contract.",
    ),
    _article(
        "regional-carrier-variant-boundary",
        "Region and carrier variants must not inherit firmware compatibility",
        "DEVICE IDENTITY & COMPATIBILITY",
        "xiaomi",
        "An OEM can ship different builds for the same marketing name by region, carrier, radio configuration, or sales channel. A matching retail name therefore does not prove that another region's package is compatible.",
        checks=(
            "Collect region/carrier evidence, model suffix, product code, current fingerprint, and firmware channel.",
            "Confirm the OEM source explicitly lists the same variant or that signed package metadata matches it.",
        ),
        fix_steps=(
            "Keep the result UNKNOWN or KNOWN INCOMPATIBLE when the region contract conflicts.",
        ),
        verification=("The compatibility report names the exact matched variant and source.",),
        tags=("region carrier variant firmware channel", "cn global eea india mismatch"),
        route="device_atlas",
        evidence="Xiaomi's official update guidance states that eligibility and rollout can depend on model and region; other OEMs may apply their own variant rules.",
    ),
    _article(
        "unknown-versus-incompatible",
        "Unknown compatibility is not the same as known incompatible",
        "DEVICE IDENTITY & COMPATIBILITY",
        "compatibility",
        "UNKNOWN means evidence is missing or ambiguous. KNOWN INCOMPATIBLE means trusted evidence directly conflicts, such as a target-device mismatch, unsupported partition route, required pre-build mismatch, or explicit OEM restriction.",
        checks=(
            "Identify which exact fact is absent for UNKNOWN, or which source proves the conflict for KNOWN INCOMPATIBLE.",
            "Never convert UNKNOWN into compatible merely because no failure has been reported.",
        ),
        fix_steps=(
            "Collect the missing Device DNA, package metadata, Device Pack, or recovery evidence.",
        ),
        verification=(
            "Every status has a human-readable reason and at least one evidence reference where applicable.",
        ),
        tags=("compatible not compatible unknown", "known incompatible compatibility status"),
        route="nexus",
        evidence="Android platform compatibility and ROMVERSE device/firmware compatibility are different scopes; ROMVERSE makes uncertainty explicit.",
    ),
    _article(
        "romverse-compatibility-statuses",
        "ROMVERSE compatibility statuses: Verified, Strong Match, Limited, Unknown, and Incompatible",
        "DEVICE IDENTITY & COMPATIBILITY",
        "compatibility",
        "Verified requires exact protected-source and Device Pack evidence. Strong Match has multiple high-quality sources but lacks exact physical proof. Limited Evidence means a route may be technically possible. Unknown lacks enough evidence. Known Incompatible has a direct conflict.",
        checks=(
            "Review confidence, freshness, scope, warnings, and every evidence source.",
            "Check that the decision is bound to current Device DNA rather than a prior scan.",
        ),
        fix_steps=(
            "Refresh stale evidence and resolve exact-device gaps before raising confidence.",
        ),
        verification=(
            "A regenerated matrix changes digest when its Device DNA or decisions change.",
        ),
        tags=(
            "verified strong match limited evidence unknown known incompatible",
            "compatibility matrix",
        ),
        route="nexus",
        evidence="ROMVERSE's local compatibility matrix is conservative, evidence-bound, advisory-only, and never permits bootloader relocking.",
    ),
    _article(
        "device-pack-authority-levels",
        "Device Pack identity, build, recovery, and flash authority are separate",
        "DEVICE IDENTITY & COMPATIBILITY",
        "compatibility",
        "A broad OEM Device Pack can explain tools and naming while still having no exact build or flash authority. Exact identity, build contract, recovery artifacts, and physical flash/first-boot attestations are separate evidence levels.",
        checks=(
            "Inspect Pack scope, patterns, sources, build contract, recovery contract, and attestations.",
            "Confirm the Pack digest still matches the packaged index.",
        ),
        fix_steps=("Draft a new exact Pack instead of widening a generic wildcard Pack.",),
        verification=(
            "Device Atlas shows explicit readiness gaps rather than an inherited capability.",
        ),
        tags=("device pack authority exact build recovery flash", "generic pack limited"),
        route="device_atlas",
        evidence="ROMVERSE validates each Device Pack and derives capability state from the evidence actually present.",
    ),
    _article(
        "android-cdd-cts-scope",
        "CDD and CTS compatibility does not prove a firmware file fits one phone",
        "DEVICE IDENTITY & COMPATIBILITY",
        "cts",
        "Android-compatible devices must meet the Compatibility Definition and pass CTS. That establishes platform and application behavior, not whether a downloaded OEM image belongs to one hardware variant.",
        checks=(
            "Separate Android ecosystem compatibility from firmware target compatibility.",
            "Require the device's exact package target, partition, signing, and recovery contracts.",
        ),
        fix_steps=("Use CTS evidence as a post-build quality signal, not as a flashing shortcut.",),
        verification=(
            "The report labels CTS scope separately from Device Pack and package scope.",
        ),
        tags=("cdd cts android compatible firmware compatibility", "compatibility test suite"),
        route="nexus",
        evidence="AOSP defines the CDD as requirements and CTS as the compatibility mechanism; neither maps arbitrary firmware to a device.",
    ),
    _article(
        "android-vts-vendor-scope",
        "VTS checks vendor and kernel interfaces, not an arbitrary firmware download",
        "DEVICE IDENTITY & COMPATIBILITY",
        "vts",
        "The Vendor Test Suite exercises kernel and hardware abstraction layer behavior on a device. Passing evidence is valuable for a built image, but does not authenticate an unrelated firmware archive.",
        checks=(
            "Bind VTS results to the exact device, build fingerprint, test version, and date.",
        ),
        fix_steps=(
            "Use fresh VTS results to support build validation after source and target identity are proven.",
        ),
        verification=(
            "The result receipt includes device/build identity and complete test outcome.",
        ),
        tags=("vts vendor test suite hal kernel compatibility",),
        route="nexus",
        evidence="AOSP documents VTS as device-side kernel and HAL testing managed from a host.",
    ),
    _article(
        "android-gsi-scope",
        "A GSI-capable device is not automatically compatible with every ROM",
        "DEVICE IDENTITY & COMPATIBILITY",
        "gsi",
        "A Generic System Image is an AOSP system image used with Treble/VTS compatibility testing. Architecture, launch version, vendor interfaces, partition layout, boot image, AVB, and OEM restrictions still matter.",
        checks=(
            "Confirm Treble support, CPU architecture/bitness, launch Android version, dynamic partition layout, and the intended GSI target.",
            "Keep OEM factory firmware and GSI compatibility as separate routes.",
        ),
        fix_steps=(
            "Use an exact GSI test plan and recovery route; do not rename an OEM image as a GSI.",
        ),
        verification=(
            "The compatibility record cites matching GSI/VTS evidence for the same device build.",
        ),
        tags=("gsi treble generic system image phh", "gsi compatible rom"),
        route="nexus",
        evidence="AOSP defines GSI configurations and CTS-on-GSI/VTS testing; it does not claim that every image works on every Treble device.",
    ),
    _article(
        "android-apk-abi-compatibility",
        "APK CPU ABI compatibility: arm64, armeabi-v7a, x86, and x86_64",
        "DEVICE IDENTITY & COMPATIBILITY",
        "cts",
        "Native APK libraries must include an ABI the device supports. A 64-bit device can have different 32-bit compatibility, and a package containing only the wrong native architecture fails even when its Android version is high enough.",
        checks=(
            "Compare the device ABI list with every native library directory in the APK or split set.",
            "Check minimum SDK, required features, and signing identity separately.",
        ),
        fix_steps=("Choose the developer's matching ABI build or complete universal split set.",),
        verification=(
            "APK preflight reports at least one matching ABI and no missing required split.",
        ),
        tags=(
            "apk abi arm64-v8a armeabi-v7a x86_64 incompatible",
            "INSTALL_FAILED_NO_MATCHING_ABIS",
        ),
        route="app_launchpad",
        evidence="Android compatibility testing covers every ABI mode a device claims; ROMVERSE compares package and device evidence before installation review.",
    ),
    _article(
        "ota-full-versus-incremental",
        "Full OTA and incremental OTA packages have different upgrade requirements",
        "FIRMWARE INTAKE",
        "ota_tools",
        "A full OTA contains the data needed to build the target partitions from a wider set of starting states. An incremental OTA is generated from one source build to one target build and normally requires the declared source state to match exactly.",
        checks=(
            "Inspect package metadata and payload properties for incremental preconditions.",
            "Record the current device fingerprint and incremental build before calling a package an upgrade.",
        ),
        fix_steps=(
            "Use a full package when the exact incremental source requirement cannot be proven.",
        ),
        verification=(
            "The intake report labels the package full or incremental and cites the evidence used.",
        ),
        tags=("full ota incremental ota difference", "delta ota source build"),
        route="rom_studio",
        evidence="AOSP OTA tooling distinguishes full and incremental generation and requires a source target-files build for incremental packages.",
    ),
    _article(
        "ota-target-device-metadata",
        "OTA target device metadata must match Device DNA",
        "FIRMWARE INTAKE",
        "ota_tools",
        "Standard OTA metadata can declare pre-device target aliases. At least one normalized alias must intersect trusted device/codename/product evidence, and an empty or ambiguous identity must not be accepted.",
        checks=(
            "Read metadata from the package itself, not the download page or filename.",
            "Compare every declared pre-device alias with current Device DNA and the selected Device Pack.",
        ),
        fix_steps=("Reject a direct conflict and keep missing identity evidence UNKNOWN.",),
        verification=(
            "The report shows the declared aliases, observed aliases, and exact intersection.",
        ),
        tags=("pre-device target device ota metadata", "firmware wrong device target mismatch"),
        route="rom_studio",
        evidence="AOSP OTA tooling emits device assertions/metadata; ROMVERSE applies an exact, normalized identity intersection before upgrade classification.",
    ),
    _article(
        "ota-prebuild-preincremental",
        "Incremental OTA pre-build and pre-incremental values must match exactly",
        "FIRMWARE INTAKE",
        "ota_tools",
        "An incremental update is tied to its source build. A matching model is insufficient when the package requires a different pre-build fingerprint or pre-build-incremental value.",
        checks=(
            "Compare the complete current fingerprint with pre-build when present.",
            "Compare the current incremental with pre-build-incremental when present.",
        ),
        fix_steps=(
            "Obtain the correct incremental for the installed source build or use the correct full OTA.",
        ),
        verification=("Every declared incremental precondition is an exact match.",),
        tags=("pre-build pre-build-incremental mismatch", "incremental ota wrong source"),
        route="rom_studio",
        evidence="AOSP OTA metadata records source build properties for incremental packages so clients can refuse the wrong update path.",
    ),
    _article(
        "ota-version-ordering",
        "Determine whether firmware is an upgrade using comparable signed metadata",
        "FIRMWARE INTAKE",
        "ota_tools",
        "An upgrade decision needs a matching target plus a supported update path and comparable version evidence. Higher SDK, target timestamp, security patch, and OEM incremental data can support an upgrade; filenames and marketing version numbers cannot prove it alone.",
        checks=(
            "Confirm target identity and incremental source conditions first.",
            "Compare post-sdk-level, post-timestamp, post-security-patch-level, post-build, and post-build-incremental when supplied.",
        ),
        fix_steps=("Return UNKNOWN when no trustworthy ordering field can be compared.",),
        verification=(
            "The decision explains which exact field proved newer, equal, older, or incomparable.",
        ),
        tags=("firmware upgrade newer higher version", "post timestamp post sdk ota"),
        route="nexus",
        evidence="AOSP-generated OTA metadata supplies target build properties; ROMVERSE requires package-derived evidence and does not trust names alone.",
    ),
    _article(
        "update-engine-code-9",
        "update_engine error 9: download transfer error",
        "FIRMWARE INTAKE",
        "update_engine",
        "Error 9 is kDownloadTransferError: update_engine could not complete the payload transfer. It is a transport/download failure, not proof that the package is compatible or incompatible.",
        checks=(
            "Preserve the exact error, URL/source receipt, byte count, and network state.",
            "Verify local free space and whether the payload download was complete.",
        ),
        fix_steps=(
            "Retry the download from the verified source after resolving the evidenced transport issue.",
        ),
        verification=("The complete downloaded payload matches its expected digest and size.",),
        tags=("update engine error 9", "kDownloadTransferError", "ota download failed"),
        route="recovery_bay",
        evidence="The current AOSP update_engine error enumeration assigns 9 to kDownloadTransferError.",
    ),
    _article(
        "update-engine-codes-10-12",
        "update_engine errors 10, 11, and 12: payload integrity or size failure",
        "FIRMWARE INTAKE",
        "update_engine",
        "Error 10 is payload hash mismatch, 11 is payload size mismatch, and 12 is payload verification failure. These are integrity failures; repeated installation attempts cannot repair changed or incomplete bytes.",
        checks=(
            "Compare the local package digest and byte length with the trusted source.",
            "Confirm no proxy, transfer tool, filesystem, or extraction step changed the payload.",
        ),
        fix_steps=(
            "Quarantine the bad copy and download a fresh package from the trusted source.",
        ),
        verification=(
            "A new protected source passes size, digest, container, and metadata validation.",
        ),
        tags=("update engine error 10 11 12", "payload hash mismatch size verification"),
        route="recovery_bay",
        evidence="The AOSP update_engine error enumeration defines these payload validation failures explicitly.",
    ),
    _article(
        "update-engine-code-51",
        "update_engine error 51: payload timestamp rejected",
        "FIRMWARE INTAKE",
        "update_engine",
        "Error 51 is kPayloadTimestampError and indicates that the payload timestamp violates the device's accepted update ordering, commonly because it is treated as an older or otherwise disallowed payload.",
        checks=(
            "Compare the signed target timestamp and rollback evidence with the current device build.",
            "Confirm that the user did not select a package for another channel or region.",
        ),
        fix_steps=(
            "Use a newer, correctly targeted official package; do not bypass rollback protection.",
        ),
        verification=(
            "The replacement package passes the same timestamp and target checks before any action.",
        ),
        tags=("update engine error 51", "kPayloadTimestampError", "payload timestamp rollback"),
        route="recovery_bay",
        evidence="The current AOSP update_engine API and source assign 51 to payload timestamp rejection.",
    ),
    _article(
        "update-engine-codes-52-60-61",
        "update_engine errors 52, 60, and 61: inactive update, no space, or corruption",
        "FIRMWARE INTAKE",
        "update_engine",
        "Error 52 means updated but not active, 60 means not enough space, and 61 means device corrupted. They require different diagnosis; none should be collapsed into a generic flash failure.",
        checks=(
            "For 52, inspect active slot and reboot-pending state without changing slots.",
            "For 60, measure the relevant data/snapshot space; for 61, preserve corruption evidence and stop writes.",
        ),
        fix_steps=("Follow the exact code-specific recovery path and re-assess before retrying.",),
        verification=(
            "A fresh status reports the expected active slot, adequate space, and no integrity finding.",
        ),
        tags=(
            "update engine error 52 60 61",
            "updated not active not enough space device corrupted",
        ),
        route="recovery_bay",
        evidence="The AOSP update_engine error enumeration keeps these outcomes as separate codes.",
    ),
    _article(
        "ota-signature-boundary",
        "OTA sideloading keeps recovery trust checks active",
        "BOOT & SECURITY",
        "sign_builds",
        "Android recovery verifies an OTA package against trusted recovery keys. A correctly structured ZIP or matching target name is not enough when its signing key is not accepted by that device's recovery.",
        checks=(
            "Inspect the OTA signature and certificate chain without modifying the archive.",
            "Confirm the exact recovery trust source for the same device/build.",
        ),
        fix_steps=(
            "Use the properly signed official or explicitly supported build for that recovery trust contract.",
        ),
        verification=(
            "Offline signature inspection succeeds and the signer evidence is recorded.",
        ),
        tags=("ota signature verification failed", "adb sideload signature", "otacerts res keys"),
        route="guardian_core",
        evidence="AOSP states that sideloading retains recovery's normal signature-verification mechanism.",
    ),
    _article(
        "ab-slot-update-model",
        "A/B updates write the inactive slot and still require post-boot verification",
        "FILESYSTEMS & PARTITIONS",
        "ab",
        "A/B update_engine writes the unused slot, verifies it, and asks the bootloader to try it. Fallback improves resilience, but a moving boot animation or slot switch is not proof that the new build is healthy.",
        checks=(
            "Record current slot, slot-successful state, payload result, and reboot-pending state.",
            "Keep the prior slot recovery path and backup evidence available.",
        ),
        fix_steps=(
            "After the first boot, verify build identity, boot completion, services, and a clean reboot before declaring success.",
        ),
        verification=(
            "The new slot is active, booted, marked successful, and matches the intended build.",
        ),
        tags=("a b ota inactive slot fallback", "slot successful update engine"),
        route="recovery_bay",
        evidence="AOSP documents the A/B slot lifecycle, update_engine verification, and bootloader fallback behavior.",
    ),
    _article(
        "nonab-recovery-update-model",
        "Older non-A/B recovery updates have a different risk and log path",
        "FILESYSTEMS & PARTITIONS",
        "nonab",
        "Legacy non-A/B devices update active partitions from recovery and may use cache for packages and logs. They do not provide the same inactive-slot fallback model as A/B devices.",
        checks=(
            "Confirm the device truly lacks A/B and identify its recovery/update-binary package format.",
            "Verify backup, battery, storage, recovery keys, and the exact update package.",
        ),
        fix_steps=(
            "Use the device's supported recovery path; never apply A/B assumptions to a legacy layout.",
        ),
        verification=(
            "Recovery reports signature and installation success and the intended build boots cleanly.",
        ),
        tags=("non a b ota legacy recovery update-binary cache last_log",),
        route="recovery_bay",
        evidence="AOSP describes non-A/B as a deprecated legacy methodology with recovery-based writes and signature checks.",
    ),
    _article(
        "fastbootd-logical-partitions",
        "Dynamic logical partitions normally belong in userspace fastbootd",
        "FILESYSTEMS & PARTITIONS",
        "fastbootd",
        "Android moves dynamic-partition flashing support to userspace fastbootd. Bootloader Fastboot and fastbootd are different modes, and forcing a logical-partition write from the wrong mode is not a general compatibility solution.",
        checks=(
            "Read getvar is-userspace and is-logical for the intended partition.",
            "Compare the exact super layout, group sizes, slot scheme, and maximum download size.",
        ),
        fix_steps=(
            "Return to the documented device-specific route and regenerate the plan for the observed mode.",
        ),
        verification=(
            "The plan targets the correct mode and partition contract before Guardian review.",
        ),
        tags=("fastbootd logical partition wrong mode", "is-userspace is-logical super"),
        route="rom_studio",
        evidence="AOSP defines fastbootd as the userspace mode that supports logical partition operations and discourages force mode as a general developer route.",
    ),
    _article(
        "partition-name-is-not-universal",
        "Android partition names and layouts are not universal",
        "FILESYSTEMS & PARTITIONS",
        "partitions",
        "Modern Android can use boot, init_boot, vendor_boot, system, system_ext, product, vendor, odm, *_dlkm, vbmeta chains, super, and device-specific partitions. Presence and ownership vary by launch version and OEM design.",
        checks=(
            "Inventory the exact protected source and live read-only partition evidence.",
            "Record slot suffixing, logical/physical status, sizes, filesystem types, and AVB descriptors.",
        ),
        fix_steps=(
            "Build a device-specific partition contract; do not synthesize a missing partition name.",
        ),
        verification=(
            "Every planned image maps to one evidenced target partition with matching size and role.",
        ),
        tags=(
            "boot init_boot vendor_boot product system_ext odm_dlkm partition",
            "partition not found",
        ),
        route="rom_studio",
        evidence="AOSP's partition overview documents release-dependent partition roles while allowing product-specific implementations.",
    ),
    _article(
        "avb-green-orange-yellow-red",
        "Interpret green, orange, yellow, and red Verified Boot states",
        "BOOT & SECURITY",
        "boot_flow",
        "Green indicates a locked device using the normal trusted root, orange an unlocked bootloader, yellow a locked device using a custom root of trust, and red a verification or no-valid-OS failure. State meaning is evidence, not an instruction to relock.",
        checks=(
            "Capture ro.boot.verifiedbootstate and flash-lock evidence from the current boot.",
            "Correlate red states with AVB, dm-verity, slot, and partition evidence.",
        ),
        fix_steps=(
            "Stop device writes on red; assess the exact signed recovery route and rollback material.",
        ),
        verification=("The reported color and lock state agree across current evidence sources.",),
        tags=("verified boot green orange yellow red", "dm verity corrupt no valid os"),
        route="recovery_bay",
        evidence="AOSP defines the Verified Boot user-visible states and their bootloader meaning.",
    ),
    _article(
        "bootloader-unlock-erases-data",
        "Bootloader unlocking normally erases user data and requires physical confirmation",
        "BOOT & SECURITY",
        "unlock",
        "AOSP's unlock flow requires a warning, physical user interaction, and a factory data reset to protect existing data. OEM eligibility and account waiting rules can add further restrictions.",
        checks=(
            "Confirm the OEM's exact model/region unlock policy and complete backup verification.",
            "Treat OEM unlocking availability and current lock state as separate facts.",
        ),
        fix_steps=(
            "Do not begin an unlock from a knowledge article; create a separately reviewed destructive-operation plan.",
        ),
        verification=(
            "Backup, identity, recovery, wipe acknowledgement, and physical confirmation are all explicit.",
        ),
        tags=("fastboot flashing unlock wipes data", "oem unlocking factory reset"),
        route="guardian_core",
        evidence="AOSP requires the user-confirmed bootloader unlock transition to reset the device; vendor policy may be stricter.",
        automation="DESTRUCTIVE OPERATION KNOWLEDGE ONLY • ROMVERSE DOES NOT AUTO-UNLOCK OR RELOCK",
    ),
    _article(
        "avb-rollback-index-boundary",
        "AVB rollback protection can reject an otherwise valid older image",
        "BOOT & SECURITY",
        "avb",
        "Android Verified Boot can store minimum rollback indices in tamper-evident storage. A valid signature and matching device name do not guarantee that an older signed image remains bootable.",
        checks=(
            "Inspect AVB descriptors, rollback index locations, security patch/timestamp evidence, and OEM advisories.",
            "Preserve the device's current bootable path before any update planning.",
        ),
        fix_steps=("Use a permitted newer image; never attempt to bypass rollback protection.",),
        verification=("No planned image has an evidenced rollback-index conflict.",),
        tags=("avb rollback index anti rollback older image", "downgrade blocked"),
        route="guardian_core",
        evidence="AOSP AVB provides rollback protection and bootloader-managed rollback metadata.",
    ),
    _article(
        "apk-signature-before-install",
        "Verify APK signing identity before an install or update",
        "APPS & PACKAGES",
        "apksigner",
        "Android requires package signatures and an update must preserve the accepted signing lineage. File names and package names cannot prove signer continuity.",
        checks=(
            "Verify the APK or complete split set with apksigner and print certificate digests.",
            "Compare the proposed signer with the installed package signer and trusted publisher source.",
        ),
        fix_steps=(
            "Use the correctly signed release or uninstall only through a separate data-loss-aware plan.",
        ),
        verification=("Signature verification succeeds for the device's supported SDK range.",),
        tags=("apksigner certificate digest signature update incompatible", "apk signer verify"),
        route="app_launchpad",
        evidence="Android's apksigner verifies whether signatures are valid for supported platform versions and can expose signer certificates.",
    ),
    _article(
        "apk-split-set-completeness",
        "Base APK and configuration splits must form one complete signed set",
        "APPS & PACKAGES",
        "package_manager",
        "Modern apps can require a base APK plus ABI, density, language, or feature splits. Installing one extracted file may fail as missing split or produce an incomplete app even when every file looks like an APK.",
        checks=(
            "Inventory base and split names, package/version identity, signer lineage, ABI, and required features.",
            "Reject mixed versions or mixed signing certificates.",
        ),
        fix_steps=("Obtain the complete matching set from the trusted publisher source.",),
        verification=(
            "Preflight reports one package/version/signer identity and no missing required split.",
        ),
        tags=("INSTALL_FAILED_MISSING_SPLIT", "split apk apks base config", "bundle incomplete"),
        route="app_launchpad",
        evidence="Android PackageManager defines missing-split and update/signature installation outcomes; ROMVERSE inspects before requesting install approval.",
    ),
    _article(
        "android-usb-host-checklist",
        "Android USB connection checklist for Windows, Linux, macOS, and ChromeOS",
        "CONNECTIVITY & ADB",
        "hardware",
        "USB debugging requires Developer options, a data-capable connection, and user authorization. Windows can require an OEM ADB driver; Linux can require plugdev membership and udev rules; macOS and ChromeOS normally do not need an OEM driver.",
        checks=(
            "Confirm the cable carries data, the phone is unlocked, and USB debugging is enabled.",
            "Check the host-specific driver or permission requirement before restarting tools.",
        ),
        fix_steps=(
            "Correct one evidenced host problem, reconnect once, accept the RSA prompt, and rescan.",
        ),
        verification=("adb devices and ROMVERSE show the same authorized target consistently.",),
        tags=("windows oem usb driver linux udev plugdev mac adb", "phone not detected"),
        route="forge_arsenal",
        evidence="Android's hardware-device guide documents host-specific setup and connection troubleshooting.",
    ),
    _article(
        "android-oem-usb-driver-source",
        "Download Windows Android USB drivers only from the OEM route",
        "TOOLS & HOST",
        "oem_usb",
        "Windows drivers bind the host to the USB interface and should come from the device maker or the official Android OEM-driver index. A generic third-party driver bundle adds supply-chain and compatibility risk.",
        checks=(
            "Match the USB vendor/device identity and Windows architecture before choosing a driver.",
        ),
        fix_steps=(
            "Follow the official Android OEM-driver link to the manufacturer and verify the publisher signature.",
        ),
        verification=(
            "Windows reports the expected signed driver provider and adb lists the authorized phone.",
        ),
        tags=("adb windows driver oem usb", "android usb driver download"),
        route="forge_arsenal",
        evidence="Android publishes an OEM-driver index and installation guidance for Windows hardware-device connections.",
    ),
    _article(
        "android-backup-limitations",
        "An Android cloud backup is useful but not a complete flash rollback image",
        "RECOVERY & GUARDIAN",
        "backup",
        "Android account backup can preserve supported app data, call history, contacts, settings, and messages, but apps choose what they back up and restoration varies by device and Android version. It does not capture every partition or guarantee a pre-flash rollback.",
        checks=(
            "Open the phone's Backup details and confirm the latest completed state for each needed data class.",
            "Keep separate copies of irreplaceable media and exact recovery firmware where lawful and available.",
        ),
        fix_steps=("Build a layered backup and test access to it before destructive work.",),
        verification=(
            "The recovery plan lists what is backed up, what is excluded, and how each item was tested.",
        ),
        tags=("android backup restore limitations", "google one backup flash rollback"),
        route="time_machine",
        evidence="Google's Android backup documentation states that not every app backs up all data and that restore behavior depends on Android version and device.",
    ),
    _article(
        "pixel-ota-versus-factory",
        "Pixel full OTA and factory images are different recovery routes",
        "RECOVERY & GUARDIAN",
        "pixel_factory",
        "Google describes full OTA sideload as generally easier and safer than a factory image. Factory-image installation normally requires bootloader unlocking and erases data, while full OTA sideload can preserve data and keep the bootloader locked.",
        checks=(
            "Confirm the exact Pixel codename/model, build, carrier note, anti-rollback advisory, and published checksum.",
            "Read any build-specific special instructions before choosing a route.",
        ),
        fix_steps=(
            "Prefer the applicable signed full OTA route when it satisfies the recovery objective.",
        ),
        verification=(
            "The downloaded artifact checksum, device target, and route-specific prerequisites all match.",
        ),
        tags=("pixel full ota factory image difference", "pixel flash data wipe"),
        route="recovery_bay",
        evidence="Google's Pixel image pages distinguish full OTA sideload from factory images and publish build-specific warnings.",
        automation="PIXEL-SCOPED GUIDANCE ONLY • NO AUTOMATIC DOWNLOAD, UNLOCK, SIDELOAD, OR FLASH",
    ),
    _article(
        "xiaomi-phased-regional-updates",
        "Xiaomi HyperOS updates can be model-, region-, and rollout-phase-specific",
        "DEVICE IDENTITY & COMPATIBILITY",
        "xiaomi",
        "Xiaomi states that update availability can depend on the exact model, region, and release phase. A package that is newer for one channel must not be treated as an upgrade for another channel from its version label alone.",
        checks=(
            "Match exact model/codename, region/channel, current build, and package metadata.",
            "Check the current Xiaomi support notice for that model and region.",
        ),
        fix_steps=(
            "Wait for the correct channel or obtain the exact official package without altering its contents.",
        ),
        verification=("The update assessment names the matched Xiaomi region/channel evidence.",),
        tags=("xiaomi hyperos update region rollout", "miui cn global eea firmware"),
        route="device_atlas",
        evidence="Xiaomi's official support guidance says HyperOS update eligibility and timing can vary by model and region.",
    ),
    _article(
        "motorola-rescue-identity-and-wipe",
        "Motorola Software Fix matches firmware by device identity and erases data during Rescue",
        "RECOVERY & GUARDIAN",
        "motorola",
        "Motorola's official Rescue workflow reads device identity to match firmware and warns that a rescue software update resets the phone to factory defaults. That OEM workflow is separate from ROMVERSE and remains user-controlled.",
        checks=(
            "Confirm the exact Motorola/Lenovo model is supported by the current official tool.",
            "Verify a complete backup and account credentials before any Rescue action.",
        ),
        fix_steps=(
            "Use Motorola's current official Software Fix release when the OEM route is chosen.",
        ),
        verification=(
            "The OEM tool identifies the exact phone and matched software before the user starts Rescue.",
        ),
        tags=("motorola rescue smart assistant software fix", "motorola firmware imei wipe"),
        route="recovery_bay",
        evidence="Motorola documents identity-based firmware matching and a factory reset as part of its Rescue software update.",
        automation="OEM RECOVERY GUIDANCE ONLY • ROMVERSE DOES NOT CONTROL MOTOROLA SOFTWARE FIX",
    ),
    _article(
        "community-report-evidence-levels",
        "Community reports: reported, corroborated, locally verified, and retired",
        "ROMVERSE WORKFLOWS",
        "reddit",
        "A community fix can be useful evidence. ROMVERSE labels one report as reported, raises confidence when independent sources describe the same scoped outcome, promotes it only after a matching typed local verification, and retires it when later evidence fails or drifts.",
        checks=(
            "Record source URL, publication/retrieval dates, exact device, build, tool version, error, action, and outcome.",
            "Separate the author's claim from what ROMVERSE reproduced locally.",
        ),
        fix_steps=(
            "Search for independent corroboration and official constraints before applying the idea.",
        ),
        verification=(
            "The evidence card shows authority, freshness, scope match, corroboration count, and local outcome state.",
        ),
        tags=("community report valid evidence", "reported corroborated locally verified retired"),
        route="archives",
        evidence="ROMVERSE preserves community value while keeping claims, corroboration, and reproducible local results as distinct evidence states.",
    ),
    _article(
        "community-exact-scope",
        "Match a community fix to the exact device, build, tool, and failure",
        "ROMVERSE WORKFLOWS",
        "xda",
        "A fix that worked on the same marketing name can still fail across codenames, regions, storage sizes, Android releases, security patches, partition layouts, or tool versions. Exact scope is the difference between useful evidence and unsafe folklore.",
        checks=(
            "Compare model, codename, region, build fingerprint/incremental, package digest, partition/slot state, and tool version.",
            "Read the full thread for edits, failures, prerequisites, and later reversals.",
        ),
        fix_steps=(
            "Reproduce only through a bounded ROMVERSE workflow with rollback and verification.",
        ),
        verification=(
            "The local result is attached only to the same normalized error fingerprint and scope.",
        ),
        tags=("xda community fix exact device build", "same model different codename"),
        route="archives",
        evidence="XDA device forums are valuable model-specific records, but thread instructions and outcomes remain community claims until independently checked.",
    ),
    _article(
        "community-accepted-answer-boundary",
        "An accepted Android Enthusiasts answer is strong context, not universal proof",
        "ROMVERSE WORKFLOWS",
        "stackexchange",
        "Accepted answers are useful because the question, revisions, votes, and resolution are visible. Acceptance still proves only that the answer helped that question's context, not every device or Android release.",
        checks=(
            "Check question date, Android/OEM version, exact symptoms, comments, answer revisions, and whether links remain authoritative.",
            "Prefer answers that cite official documentation or reproducible diagnostics.",
        ),
        fix_steps=(
            "Use the accepted answer to form a testable hypothesis, then verify it against current Device DNA.",
        ),
        verification=(
            "ROMVERSE records the source as community and the reproduced outcome separately.",
        ),
        tags=("android stackexchange accepted answer community fix", "android enthusiasts"),
        route="archives",
        evidence="Android Enthusiasts exposes durable question/answer context; ROMVERSE does not equate acceptance with device-wide compatibility.",
    ),
    _article(
        "maintainer-issue-evidence",
        "Tool maintainer issues can explain version-specific failures",
        "ROMVERSE WORKFLOWS",
        "github",
        "An upstream issue can reveal regressions, supported versions, patches, and maintainer-confirmed workarounds. It is strongest when it belongs to the actual tool repository and matches the installed release and exact error.",
        checks=(
            "Confirm repository ownership, issue state, affected/fixed versions, linked commits/releases, and reproducible logs.",
            "Reject copied binaries or commands from unrelated forks unless independently verified.",
        ),
        fix_steps=("Prefer the maintainer's signed fixed release or documented safe workaround.",),
        verification=(
            "Forge Arsenal verifies the resulting tool bytes and version before activation.",
        ),
        tags=("github issue maintainer bug fixed version", "tool regression workaround"),
        route="forge_arsenal",
        evidence="Repository issue trackers provide version-scoped maintainer/community evidence; ROMVERSE still verifies installed artifacts locally.",
    ),
)
