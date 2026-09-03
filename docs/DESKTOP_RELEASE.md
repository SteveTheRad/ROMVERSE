# ROMVERSE Desktop release process

ROMVERSE Desktop release candidates are prepared locally and tested on Linux and Windows. A wheel
or manifest is not a public release merely because it builds or passes CI.

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

## Prepare an unsigned candidate

Build and verify the wheel first, then create the candidate manifest:

```bash
python -m build --wheel
python scripts/verify_wheel.py dist/romverse-0.1.0-py3-none-any.whl
python scripts/prepare_desktop_release.py \
  --version 0.1.0 \
  --release-id romverse-desktop-0.1.0-rc.1 \
  --artifact current-python-wheel:python-any:wheel:dist/romverse-0.1.0-py3-none-any.whl \
  --output dist/romverse-desktop-0.1.0-unsigned.json
python scripts/verify_unsigned_desktop_release.py \
  dist/romverse-desktop-0.1.0-unsigned.json \
  --artifact-directory dist
```

The unsigned verifier deliberately prints that it grants no signing trust or update authority.
Linux and Windows CI each build, install, launch, inspect, and upload this unsigned candidate.

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

1. Pass the full repository quality gate and installed-wheel smoke on Linux and Windows.
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
