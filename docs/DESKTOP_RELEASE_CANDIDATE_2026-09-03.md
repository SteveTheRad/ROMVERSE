# ROMVERSE Desktop 0.1.0 release-candidate report

## Decision

ROMVERSE Desktop 0.1.0 is a verified **unsigned release candidate** for Linux x86-64 and
Windows x86-64. The packaged application is self-contained and does not require a separate Python
installation. This report covers the Windows/Linux PySide6 desktop and its local ROM workflows.
Android Companion and public online services are outside this candidate.

The candidate application source is commit
`7096c8c46e6b85adfd8cfad0779da790d08e414c`. The documentation-only evidence commit is
`0367858750a78c7768df9b2fabccb4fd1dee780a`.

## Release artifacts

All files are in `dist/github-candidate-7096c8c/`.

| Platform or role | File | Bytes | SHA-256 | Entrypoint |
| --- | --- | ---: | --- | --- |
| Linux x86-64 | `ROMVERSE-Desktop-0.1.0-linux-x86_64.zip` | 156,007,370 | `27f6f507ec9a2e79f774c6955acf9ec3d156229aef9a597edd98ed3b4613c4e6` | `ROMVERSE/ROMVERSE` |
| Windows x86-64 | `ROMVERSE-Desktop-0.1.0-windows-x86_64.zip` | 72,845,873 | `dc726bb11dcf13bb2fdca237b44a9c29120233e2fcd8fda70396c26bc0f34da7` | `ROMVERSE/ROMVERSE.exe` |
| Unsigned manifest | `romverse-desktop-0.1.0-unsigned.json` | 1,185 | `d3b0a10c3120818d5d20fba001eb39f9f5e04746d20646dba0e83e4d0ba5b6d6` | Not executable |

The manifest release identity is
`romverse-desktop-0.1.0-7096c8c46e6b85adfd8cfad0779da790d08e414c`. It binds both archives,
228,853,243 total artifact bytes, explicit-update consent, workspace preservation, no execution
authority, and unavailable rollback because no earlier signed public release exists.

## Passing evidence

GitHub Actions run `33729703131` completed successfully for the exact application-source commit:

- Linux Python 3.12 and 3.14: 1,323 tests on each version, complete Ruff check, and complete Ruff
  formatting check.
- Windows Python 3.12 and 3.14: 154 dedicated portability tests on each version, complete Ruff
  check, and complete Ruff formatting check.
- Both native packaging jobs: verified 224-member wheel, all 21 integrity-indexed Device Packs,
  installation from the wheel outside the checkout, fresh-workspace launch, populated-workspace
  reopen, frozen-app launch, and complete portable-archive verification.
- Existing-workspace smoke: the project manifest, protected original, working copy, and Time
  Machine snapshot remained byte-identical across restart on both target operating systems.
- Linux portable archive: 441 regular files and 385,445,509 expanded bytes.
- Windows portable archive: 296 regular files and 170,381,593 expanded bytes.
- Final CI stage: independently downloaded both platform artifacts, reverified them, and prepared
  the combined unsigned manifest only after both native jobs passed.

The downloaded archives and combined manifest were independently reverified on Fedora on
2026-09-03. The local installed wheel also passed all 19 top-level route checks, loaded 101 packaged
known fixes and all 21 Device Packs, rendered the Time Machine empty state with the shared dark
theme, and reopened the populated test workspace without changing tracked bytes.

## Supported desktop behavior

- Self-contained native portable application for Linux x86-64 and Windows x86-64.
- Local project creation with a protected immutable original and separately managed working copy.
- Source inspection, extraction, integrity-bound evidence, Time Machine snapshots, and local
  recovery planning without silently altering source material.
- Exact project/source handoff from ROM Studio to Device Atlas and Forge Arsenal, including visible
  refusal when retained context is stale or belongs to another project.
- Integrity-indexed Device Pack lookup, Compatibility Matrix, ROM DNA, build planning, Recipe
  design, local toolchain preparation, diagnostics, Archives guidance, and evidence-bound Guardian
  review.
- Explicit, non-automatic desktop update policy that preserves the existing workspace and grants
  release metadata no device-changing or execution authority.
- A pinned Fedora launcher currently runs the installed 0.1.0 wheel from the recovered source and
  opens the preserved recovered workspace.

## Intentionally locked or unavailable

- The candidate is unsigned. It has no production trust or update authority and must not be
  presented as a signed public release.
- Production publication awaits an externally held Ed25519 private key, a pinned distribution
  public key and stable key identity, offline signing, and independent verification.
- Rollback is unavailable because there is no prior signed public ROMVERSE Desktop artifact. This
  is represented explicitly rather than simulated.
- Flashing, rooting, bootloader unlocking, wiping, relocking, and other phone-changing operations
  remain locked unless their exact typed contract, recovery evidence, explicit user consent, and
  independent physical validation genuinely exist.
- Physical-device and broad multi-OEM claims remain limited to the hardware evidence actually
  collected; passing desktop simulation or CI is not represented as phone-write certification.
- Android Companion, public Synapse, production Members/billing, Galaxy backend, public community
  services, and other hosted services are not part of this desktop candidate.

## Production-release handoff

1. Keep the production private key outside the repository and normal ROMVERSE workspace.
2. Sign this exact manifest through the documented offline Ed25519 ceremony.
3. Verify the signed envelope and both exact archives on a separate host using only the pinned
   public key and expected key identity.
4. Optionally perform a final hands-on launch on the intended Windows and Linux distribution
   machines without changing the candidate bytes.
5. Publish only after explicit release-owner approval, with both archives, the signed envelope,
   hashes, release notes, supported platforms, and the locked-capability statement together.

Until those steps are complete, these files remain verified candidate artifacts rather than a
trusted public update.
