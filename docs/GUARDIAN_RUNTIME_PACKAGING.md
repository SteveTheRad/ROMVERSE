# Guardian runtime packaging

ROMVERSE defines a verifiable delivery contract for a future separately built Guardian runtime.
This contract does not provide a runtime binary, enroll a key, open a phone, or grant execution
authority. It allows a release process and the Desktop to agree on the exact runtime identity before
any later consent or execution integration is considered.

## Trust boundary

The signed package document binds:

- one regular runtime executable by filename, byte length, and SHA-256;
- Linux x86-64 or Windows x86-64 as the intended host platform;
- the Guardian runtime protocol and signed-result schema versions;
- the exact adapter identity and version;
- the runtime's Ed25519 public key and its SHA-256 identity; and
- an invariant forward-only safety policy with recovery, wipe, bootloader unlock/relock, device
  access, phone change, and execution authority all disabled at package-verification time.

An independent Ed25519 release key signs the canonical manifest with ROMVERSE's runtime-package
domain separator. The release signature does not replace the runtime key: the release key authenticates
the distributed package identity, while the runtime key later authenticates runtime-session and result
records. Neither private key belongs in the repository, Desktop bundle, package manifest, logs, or
support material.

The verifier requires the expected release key ID and public key from a separate trusted channel. It
validates the exact schema and safety policy, rejects symbolic links, checks the intended platform,
and rehashes the local executable. It returns a verified identity that can be bound to one already
validated Guardian gateway. Verification never launches the executable and never enrolls it.

## Release workflow

Use an isolated release environment. Generate and protect the production release/runtime keys under
an approved RadForge Labs key ceremony; do not use ad-hoc repository keys for a real release.

Prepare the unsigned manifest beside the final runtime artifact:

```bash
python scripts/prepare_guardian_runtime_package.py \
  --runtime-version 0.1.0-rc.1 \
  --platform linux-x86_64 \
  --artifact release/ROMVERSE-Guardian-Runtime \
  --runtime-signer-key-id guardian-runtime-2026 \
  --runtime-public-key secure/runtime-public.pem \
  --adapter-id romverse.fastboot.forward \
  --adapter-version 1 \
  --output release/guardian-runtime-unsigned.json
```

Sign only after independently comparing the unsigned manifest to the final artifact and approved
release record:

```bash
python scripts/sign_guardian_runtime_package.py \
  release/guardian-runtime-unsigned.json \
  --private-key secure/runtime-release-private.pem \
  --key-id romverse-runtime-release-2026 \
  --output release/guardian-runtime-signed.json
```

The signer optionally accepts `--password-env NAME`; the named environment variable is read only for
loading an encrypted PEM and is not written to the manifest. The private key path must be a bounded
regular file rather than a symbolic link.

Verify the delivered document and artifact with the separately obtained release public key:

```bash
python scripts/verify_guardian_runtime_package.py \
  release/guardian-runtime-signed.json \
  --release-public-key trusted/runtime-release-public.pem \
  --release-key-id romverse-runtime-release-2026 \
  --package-directory release \
  --platform linux-x86_64
```

Windows packages use `windows-x86_64` and an `.exe` artifact. A successful verification proves only
the release signature, manifest invariants, and current artifact bytes. It does not prove process
isolation, physical device behavior, a flash-certified Device Pack, recovery, or consent.

## Desktop candidate inspection

Guardian Core's **Runtime Candidate Inspector** exposes the same verification boundary without a
command line. Select the signed package document, select the release public key received through an
independent trusted channel, and enter that key's expected release ID. The check runs on a managed
background worker and shows the exact release-key fingerprint, manifest digest, runtime signer,
adapter, platform, protocol, result schema, executable name, size, and digest.

The Desktop does not remember either selected path and does not copy, open, execute, or enroll the
runtime. Success is deliberately labelled **CHECK PASSED • NOT ENROLLED**. It creates no approval,
final consent, device access, runtime session, or execution authority and changes no phone.

## Remaining release gates

Before ROMVERSE may expose final consent or execution, the project still needs a real reviewed
runtime binary, protected production keys and revocation policy, explicit Desktop enrollment,
process isolation, exact-device identity continuity across Fastboot and ADB transitions, separately
consented recovery/wipe paths, hostile-runner review, and physical validation against flash-certified
Device Packs. Until those gates exist, `execution_authority` remains `none`.
