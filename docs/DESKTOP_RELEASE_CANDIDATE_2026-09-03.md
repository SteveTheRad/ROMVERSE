# ROMVERSE Desktop 0.1.0 release-candidate report

## Decision

ROMVERSE Desktop 0.1.0 is a verified **unsigned release candidate** for Linux x86-64 and
Windows x86-64. The packaged application is self-contained and does not require a separate Python
installation. This report covers the Windows/Linux PySide6 desktop and its local ROM workflows.
Android Companion and public online services are outside this candidate.

The candidate application source is commit
`5b5b9f6678dff3e9f3f9d7d6aba60ed6432d9f2f`.

## Release artifacts

All files are in `dist/github-candidate-5b5b9f6/`.

| Platform or role | File | Bytes | SHA-256 | Entrypoint |
| --- | --- | ---: | --- | --- |
| Linux x86-64 | `ROMVERSE-Desktop-0.1.0-linux-x86_64.zip` | 156,027,666 | `6845ae6e94fa85ee6bdff377c4d3dd4bc1984f78f5297ab9bc0f9da598a4237d` | `ROMVERSE/ROMVERSE` |
| Windows x86-64 | `ROMVERSE-Desktop-0.1.0-windows-x86_64.zip` | 72,869,049 | `b571dc5dc6c3ffdd489e231c9da581432b935a94b46ce16afb5012b36bbbcf7d` | `ROMVERSE/ROMVERSE.exe` |
| Unsigned manifest | `romverse-desktop-0.1.0-unsigned.json` | 1,185 | `294683367768878a0edeb5ee59bcd8ea5d1ddc97239a43d437efdc6306e9e563` | Not executable |

The manifest release identity is
`romverse-desktop-0.1.0-5b5b9f6678dff3e9f3f9d7d6aba60ed6432d9f2f`. It binds both archives,
228,896,715 total artifact bytes, explicit-update consent, workspace preservation, no execution
authority, and unavailable rollback because no earlier signed public release exists.

## Passing evidence

GitHub Actions run `33741631099` completed successfully for the exact application-source commit:

- Linux Python 3.12 and 3.14: 1,347 tests on each version, complete Ruff check, and complete Ruff
  formatting check.
- Windows Python 3.12 and 3.14: 154 dedicated portability tests on each version, complete Ruff
  check, and complete Ruff formatting check.
- Both native packaging jobs: verified 226-member wheel, all 21 integrity-indexed Device Packs,
  installation from the wheel outside the checkout, fresh-workspace launch, populated-workspace
  reopen, frozen-app launch, and complete portable-archive verification.
- Existing-workspace smoke: the project manifest, protected original, working copy, and Time
  Machine snapshot remained byte-identical across restart on both target operating systems.
- Linux portable archive: 441 regular files and 385,465,493 expanded bytes.
- Windows portable archive: 296 regular files and 170,401,664 expanded bytes.
- Final CI stage: independently downloaded both platform artifacts, reverified them, and prepared
  the combined unsigned manifest only after both native jobs passed.

The downloaded archives and combined manifest were independently reverified on Fedora on
2026-09-03. The local installed wheel also passed all 19 top-level route checks, loaded 101 packaged
known fixes and all 21 Device Packs, rendered the Time Machine empty state with the shared dark
theme, and reopened the populated test workspace without changing tracked bytes.
The protected Xiaomi 17 Pro Max candidate was also read through the new bounded standard-metadata
path: target `popsicle`, OTA type `AB`, post SDK 37, security patch `2026-08-01`, post timestamp
`1787328761`, and post-build incremental
`17OS4.0.260821.223347094.QCPECN.S` were present. The phone was not connected during this final
verification, so comparison with a freshly scanned live build timestamp remains a hands-on test and
no phone-changing command was attempted.

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
- Conservative Xiaomi HyperOS upgrade-candidate identification from live/source codename, region,
  firmware branch, and numeric version evidence. Same-version, downgrade, incompatible, and
  unconfirmed inputs remain distinct, and no relationship label grants installation authority.
- Generic Android identity passports now include product/vendor device aliases, hardware SKU,
  build fingerprint/incremental/timestamp, SDK, security, A/B and dynamic-partition evidence. A
  standards-conforming Android OTA ZIP is checked through its bounded
  `META-INF/com/android/metadata` target, update-path, post-build, SDK and timestamp records.
- Multiple detected transports now require one explicit Command Deck selection. Diagnostics,
  repair, Device Atlas, ROM Studio, APK, backup, terminal and Companion context all bind to that
  same session-only choice and remain unbound until it is made.
- A persistent user-supplied firmware responsibility notice and an explicit import acknowledgement,
  while preserving rights and obligations that cannot legally be excluded.
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
  ADB/standard OTA identification is generic, but Samsung Download Mode, Qualcomm EDL, MediaTek
  preloader, OEM unlock services, recovery signing and other vendor-specific write paths still need
  separately reviewed adapters and signed Device Pack contracts.
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
