# ROMVERSE Desktop release process

ROMVERSE Desktop release candidates are prepared locally and tested on Linux and Windows. The
release pipeline uses a PyInstaller one-folder build so the extracted application does not require
a separate Python installation. A wheel, portable ZIP, or manifest is not a public release merely
because it builds or passes CI.

## Trust boundary

The release manifest binds the product, version, channel, release identity, publication time, every
artifact filename, platform, kind, byte length, and SHA-256. It also fixes these update rules:

- installation is never automatic;
- the user must explicitly confirm an update;
- the existing workspace must be preserved;
- release metadata has no execution or device-changing authority; and
- rollback is unavailable unless the manifest names an exact included artifact and earlier version.

Manifests and envelopes use exact schema-one fields, bounded JSON, duplicate-field rejection, safe
base filenames, and Ed25519 signatures. Verification rejects a changed manifest, wrong or unknown
key identity, malformed signature, linked file, missing artifact, and size or SHA-256 mismatch.

ROMVERSE does not generate, ingest, or store a production private key in the repository or normal
application workspace. The release owner supplies an externally held Ed25519 key only during an
offline signing ceremony. The corresponding public key and stable key identity must be pinned in
the distribution channel before any update can be described as trusted.

The installed application now contains the matching runtime update verifier and safe staging layer.
Stable and Preview channels are explicit settings. A check accepts only the packaged publisher key,
the exact direct HTTPS channel, a non-future signed manifest, a newer semantic version, and exactly
one archive or installer for the running platform. Staging streams no more than the signed size,
recomputes SHA-256, writes and independently reloads a private digest-bound receipt, preserves the
workspace, and grants no installation or Android-device authority. Settings requires explicit
confirmation before that cancellable background download, reports byte-derived progress below 100
until the receipt is verified, removes incomplete files, and exposes only an **Open verified download
folder** action afterward. It never launches the artifact. Redirects, partial trust configuration,
wrong channels, ambiguous platform artifacts, changed bytes, links, forged in-memory completions,
cancelled transfers, and re-digested authority-bearing receipts fail closed.

`romverse/assets/desktop_update_trust.json` deliberately remains unconfigured in the alpha source.
During the first production signing ceremony, replace it with the stable key identity, raw public key
and final Stable/Preview manifest URLs before building the public binaries. Never place the private
key in that file. Until that happens, Settings truthfully disables online update checks while keeping
the local verification/staging implementation testable.

## Build the self-contained platform bundles

Build each bundle on its target operating system; do not cross-label one host's executable as the
other platform. The builder collects all ROMVERSE modules and packaged assets. The release smoke
opens the frozen application against a disposable workspace and exits through the normal Qt event
loop. The archive verifier rejects missing executables, unsafe members, escaping links, CRC errors,
excessive file counts, and excessive expanded size. Safe internal Linux library links are
materialized as regular archive files so extraction does not depend on symlink privileges.

```bash
python -m pip install -e '.[release]'
python scripts/build_desktop_executable.py \
  --output-directory build/frozen \
  --work-directory build/pyinstaller
python scripts/smoke_frozen_desktop.py \
  build/frozen/ROMVERSE/ROMVERSE /tmp/romverse-frozen-smoke
python scripts/package_desktop_bundle.py \
  build/frozen/ROMVERSE \
  --platform linux-x86_64 \
  --output dist/ROMVERSE-Desktop-0.1.0-linux-x86_64.zip
```

Use `ROMVERSE.exe` and `windows-x86_64` for the native Windows build. CI performs both target-host
builds and joins their exact verified ZIPs only after both jobs pass.

## Prepare an unsigned candidate

After both native bundles pass, create the candidate manifest:

```bash
python scripts/prepare_desktop_release.py \
  --version 0.1.0 \
  --release-id romverse-desktop-0.1.0-rc.1 \
  --artifact linux-portable:linux-x86_64:archive:dist/ROMVERSE-Desktop-0.1.0-linux-x86_64.zip \
  --artifact windows-portable:windows-x86_64:archive:dist/ROMVERSE-Desktop-0.1.0-windows-x86_64.zip \
  --output dist/romverse-desktop-0.1.0-unsigned.json
python scripts/verify_unsigned_desktop_release.py \
  dist/romverse-desktop-0.1.0-unsigned.json \
  --artifact-directory dist
```

The unsigned verifier deliberately prints that it grants no signing trust or update authority.
Linux and Windows CI each build, install, launch, inspect, and upload their native bundle; the final
CI job emits the combined unsigned candidate only when both platform jobs pass.

## Offline signing and independent verification

On the offline signing host, use the production Ed25519 private key and a stable public key identity:

```bash
python scripts/sign_desktop_release.py \
  dist/romverse-desktop-0.1.0-unsigned.json \
  --private-key /secure/offline/romverse-release.pem \
  --key-id romverse-release-2026 \
  --password-env ROMVERSE_RELEASE_KEY_PASSWORD \
  --output dist/romverse-desktop-0.1.0-signed.json
```

On a separate verification host, use only the pinned public key:

```bash
python scripts/verify_desktop_release.py \
  dist/romverse-desktop-0.1.0-signed.json \
  --public-key /trusted/romverse-release-public.pem \
  --key-id romverse-release-2026 \
  --artifact-directory dist
```

Do not publish when the expected key identity, pinned public key, signature, manifest digest, or any
artifact check fails. Do not substitute a development or CI test key for the production identity.

## Update and rollback release gate

Before publishing an update:

1. Pass the full Linux repository quality gate, the dedicated Windows portability suite, and the
   installed-wheel plus native frozen-application smoke on Linux and Windows.
2. Open a fresh workspace and a disposable copy of an existing workspace on each platform; prove
   manifests, immutable originals, working files, and Time Machine snapshots remain byte-identical.
3. Sign the final manifest offline and independently verify every artifact from the publication
   directory.
4. Install the candidate over the prior signed version while keeping the prior signed installer.
5. Launch and verify the existing workspace without migration loss.
6. If rollback is supported, include the exact prior artifact in the manifest and test the rollback
   on a disposable workspace copy. If no prior signed public release exists, keep rollback explicitly
   unavailable and explain why.
7. Publish the signed envelope, artifacts, checksums, release notes, supported platforms, and known
   locked capabilities together. Never publish an unsigned manifest as trusted.

The current `0.1.0` candidate has no earlier signed public ROMVERSE Desktop release, so its generated
manifest correctly reports rollback unavailable. Workspace preservation is independently required;
rollback metadata never authorizes file restoration, flashing, rooting, unlocking, wiping, or
bootloader relocking.
