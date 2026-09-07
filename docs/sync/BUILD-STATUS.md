# ROMVERSE Build Status

## Authoritative checkpoint

- Linux implementation commit: `7ea47d24fab13a4df43745dc95954f425ca3a890`.
- Linux Product Assurance base: `87af66065ea679919d603e056d40dce7b6ee07b5`.
- Approved Windows source reference: `a5527a04fe4b6183b903b209206b4eab40220f11`.
- Windows Product Assurance approval reference: `3c7b265`.
- Handoff checkpoint: the commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, cross-platform internal-alpha source convergence.
- Working tree: clean apart from ignored local build output after the handoff commit is created.

## Exact implementation change

- `VersionedToolchainStore` now creates its unique unpublished snapshot directory as
  `.stage-<32-hex UUID>` instead of embedding both the 64-character tool digest and UUID in that
  temporary path component.
- The immutable destination slot still contains and binds the complete tool SHA-256. Source bytes,
  exact size/hash checks, private-directory enforcement, atomic publication, receipt validation,
  verified-slot reuse and cleanup semantics are unchanged.
- This is the exact approved platform-neutral product-source hunk from Windows commit `a5527a0`.
- No Windows ACL/test adaptation, Windows branch history or other Windows-specific change was
  imported.

## Result classification

- Implemented: yes — bounded platform-neutral staging-path convergence.
- Simulated/Tested: yes — deterministic Linux-hosted focused toolchain isolation and local-build
  contract regression.
- Hardware Verified: no.
- Released: no.

## Non-double-counted verification

- Final focused regression: **22/22 passed** across:
  - `tests/test_toolchain_versions.py`;
  - `tests/test_build_contracts.py`.
- Ruff: **PASS** for the changed source and both exercised test modules.
- Git whitespace checks: **PASS** before the implementation commit and handoff.
- No broad/full suite, Guided journey, Recovery simulation, artifact rebuild or startup smoke was
  run. Previously accepted Fedora and Windows alpha artifact evidence is not recounted here.

## Blockers, failures and Guided friction

- No focused regression failure remains.
- The shorter unpublished staging name removes a known Windows path-pressure source without changing
  the visible Guided experience or adding any decision, dialog, route or dead end.
- No new blocker was discovered in this bounded convergence slice.

## Guardian, Recovery and safety implications

- The changed directory is host-only temporary evidence staging. It grants no Guardian, device,
  flash, Recovery, installation, signing, publication or release authority.
- UNKNOWN-on-uncertainty, no blind retry, exact-device evidence, consent separation, same-incident
  Recovery and independent verification remain unchanged.
- Production Recovery execution remains disabled and was not exercised.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora/Linux: the converged staging behavior is genuinely focused-regression verified on Linux.
- Windows: the source hunk originated from the separately tested and Product-Assurance-approved
  Windows checkpoint; no new Windows execution claim is made by this Linux checkpoint.
- Physical Android: not used; no hardware claim is made.
- 5 September 2026 feature freeze: compliant. This is only the approved minimum portability
  correction required to converge existing v0.2.0-alpha.1 source.
- v0.2 Golden Foundation remains **CLOSED**. No release gate changed.

## External actions

- Physical phone, USB target, ADB, Fastboot, Recovery, flash, install, APK transfer and device
  operation: none.
- Fedora or Windows artifact rebuild, package/dependency/system installation, signing, publication,
  release, merge and force-push: none.
- Remote action: only the normal push of the scoped Linux implementation and handoff commits to the
  existing Linux working branch is intended.
- The three protected Companion files, original-checkout Windows launcher drafts, website, assets
  and unrelated user work were untouched.

## Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice.

## Product Assurance Review Requested

- Confirm `7ea47d2` is byte-for-byte equivalent to the approved platform-neutral source hunk from
  Windows `a5527a0`, without importing Windows-specific adaptations.
- Confirm the focused 22-case Linux result is sufficient for source convergence and that neither
  platform artifact needs rebuilding for this temporary-path-only correction.
