# ROMVERSE 0.1.0 release-candidate report

## Decision

ROMVERSE 0.1.0 is a verified **unsigned release candidate** for Linux x86-64 and Windows
x86-64, accompanied by a verified **debug-signed Companion test APK**. The packaged Desktop is
self-contained and does not require a separate Python installation. This report covers the
Windows/Linux PySide6 app, its local ROM workflows, the Android Companion build, and their current
offline/Link contracts. Public hosted services remain outside this candidate.

The exact application-source commit is
`fe0f1521f656e0595ddbab855882262109fe37c4`.

## Release artifacts

The CI artifacts were independently downloaded into an isolated temporary verification directory.

| Platform or role | File | Bytes | SHA-256 | Entrypoint or identity |
| --- | --- | ---: | --- | --- |
| Linux x86-64 | `ROMVERSE-Desktop-0.1.0-linux-x86_64.zip` | 156,193,599 | `3e8d1c0d87eb1e714e258f99d3e4428f63eb136d74dda61f9e8a148873bea237` | `ROMVERSE/ROMVERSE` |
| Windows x86-64 | `ROMVERSE-Desktop-0.1.0-windows-x86_64.zip` | 73,034,151 | `4902a17a47d43f454aaff2b01422e6a84030e773c92653e533e20c6eda1bae14` | `ROMVERSE/ROMVERSE.exe` |
| Unsigned Desktop manifest | `romverse-desktop-0.1.0-unsigned.json` | 1,185 | `27c5658661a6b81f255b0ff4107a4d9daaa4be7f44a700e6a39ac10baf15d848` | Not executable |
| Android Companion test build | `app-debug.apk` | 8,171,670 | `c711a4fe69203eb693ee11a4c1c9d26eb9e3315d0956a277fcc5ba6d1c0becc2` | `com.radforge.romverse.companion` |

The Desktop manifest release identity is
`romverse-desktop-0.1.0-fe0f1521f656e0595ddbab855882262109fe37c4`. It binds both archives,
229,227,750 total artifact bytes, explicit-update consent, workspace preservation, no execution
authority, and unavailable rollback because no earlier signed public release exists. The separate
per-platform CI copies are byte-identical to the copies in the combined candidate.

## Passing evidence

[GitHub Actions run 33790777149](https://github.com/SteveTheRad/ROMVERSE/actions/runs/33790777149)
completed successfully for the exact source commit:

- Linux Python 3.12 and 3.14 each passed all 1,468 tests, complete Ruff checking, and the complete
  formatting gate.
- Windows Python 3.12 and 3.14 each passed all 313 portability tests, including Device Pack schema,
  build-readiness, Guardian inert execution-plan/gateway/result-verifier contracts, and signed Desktop update
  coverage, plus both complete Ruff gates.
- Both native packaging jobs built and verified the 232-member wheel and all 21 integrity-indexed
  Device Packs, installed the wheel outside the checkout, launched fresh and populated workspaces,
  launched the frozen app, and verified the complete portable archive.
- Existing-workspace smoke preserved the project manifest, protected original, working copy, and
  Time Machine snapshot byte-for-byte across restart on both operating systems.
- The Linux archive contains 442 regular files and 385,629,855 expanded bytes.
- The Windows archive contains 297 regular files and 170,567,550 expanded bytes.
- The final CI stage downloaded both native archives and independently accepted the combined
  unsigned manifest only after both packaging jobs passed.
- Companion `testDebugUnitTest` and `assembleDebug` completed successfully using Java 17, Gradle
  8.11.1, Android setup v4, and Gradle setup v6. The Kotlin test source contains 25 test files and
  138 `@Test` declarations; the Android unit-test task executed rather than being skipped.

Subsequent source commit `898bd04d87fba52690a330d09eeb61c4275c3649` adds the exact
runtime-bound final-consent-v1 verifier/issuer and its deliberately locked Desktop explanation.
[GitHub Actions run 33797435368](https://github.com/SteveTheRad/ROMVERSE/actions/runs/33797435368)
is fully green for that exact commit: both Linux versions passed all 1,489 tests and both complete
Ruff gates across 359 files; both Windows versions passed the 334-test portability selection and
both Ruff gates; Companion unit/build, both installed/frozen/native package jobs, and the combined
unsigned candidate all passed. Each CI wheel contains 234 members and all 21 Device Packs. A fresh
isolated Fedora wheel build has SHA-256
`1614f04ba2df4a3a41f31624ef049cbeace99b09757a8c4f204eb3119269ff78`; its verifier found the
same 234 members/21 Packs, and an isolated install loaded final-consent schema one with execution
authority `none` and no execute or token-consumption method. This is later source/build evidence; it
does not silently replace the exact artifact hashes listed above.

Independent Fedora verification on 2026-09-04 reproduced the manifest's two artifact sizes and
SHA-256 values, checked every ZIP member and CRC, and confirmed both duplicate CI copies were
byte-identical. The Linux bundle has the expected executable, and the Windows bundle has the
expected `.exe` entrypoint. A fresh isolated local build produced the expected 232-member wheel with
SHA-256 `6ac8de9f74345804d5a7a8a7c08e9277d11a1f98440ed7e7a9c92c84c68750cf`.
That exact wheel passed all 19 top-level route checks, loaded 194 packaged guides with 144 known
fixes and all 21 Device Packs, rendered the Time Machine empty state with the shared dark theme, and
reopened a populated test workspace without changing tracked bytes.

The downloaded Companion APK passed complete ZIP CRC validation. Android Build Tools 35.0.0
identified package `com.radforge.romverse.companion`, version code 3/version 0.1.0, minimum API 26,
and target API 35. `apksigner` independently verified one APK Signature Scheme v2 signer with
certificate SHA-256
`c9d0ab3106a266484a0240545a5765eccdf7f12386c489346dc3038918cd5fb7`. Its certificate identity is
`Android Debug`, so this proves artifact integrity for testing, not production publisher identity.

The protected Xiaomi 17 Pro Max candidate was previously read through the bounded standard-metadata
path: target `popsicle`, OTA type `AB`, post SDK 37, security patch `2026-08-01`, post timestamp
`1787328761`, and post-build incremental
`17OS4.0.260821.223347094.QCPECN.S` were present. A physical read-only scan later confirmed that
exact incremental against the live system partition and classified the protected source as the same
installed OTA build. No phone was connected or changed while downloading or verifying the artifacts
in this report.

## Supported candidate behavior

- Self-contained native portable Desktop applications for Linux x86-64 and Windows x86-64.
- Local project creation with a protected immutable original and separately managed working copy.
- Source inspection, extraction, integrity-bound evidence, Time Machine snapshots, and local
  recovery planning without silently altering source material.
- Exact project/source handoffs between ROM Studio, Device Atlas, Forge Arsenal, Forge Control,
  Guardian, Archives, and Time Machine, including visible refusal for stale or mismatched evidence.
- Integrity-indexed Device Pack lookup, Compatibility Matrix, Device DNA, ROM DNA, Nexus planning,
  Recipe design, local toolchain preparation, diagnostics, and evidence-bound Guardian review.
- Conservative Xiaomi HyperOS and standards-conforming Android OTA comparison using live/source
  codename, region, branch, incremental, SDK, fingerprint, security-patch, and timestamp evidence.
  Upgrade, same-version, downgrade, incompatible, and unconfirmed states remain distinct and grant
  no flash authority.
- Multiple detected transports require an explicit Command Deck selection. Every action page binds
  to that session-only choice and remains unbound until a device is selected.
- Detection-only state is now preserved independently from action authority. Genesis and ROMVERSE
  Link distinguish no visible device, failed scan, authorization required, ADB offline, recovery,
  sideload, fastboot/bootloader/fastbootd, unknown mode, and multiple-device selection instead of
  incorrectly telling the user to connect an already detected phone.
- Archives contains a separately sourced recovery/sideload identity guide, and Genesis routes
  recovery, sideload, Fastboot, and authorized ADB states to their exact relevant guides rather than
  treating every visible transport as normal authorized Device DNA.
- Guardian can compile a strict, private, deterministic and fully revalidated **inert** Fastboot
  command preview from the current device-bound manifest and signed partition-write contract. A
  schema-2 contract can additionally bind exact SHA-256 Fastboot readback rules and bounded,
  allowlisted post-boot identity and verified-boot checks from the same source build and physical
  attestation. A separate typed gateway contract then expands that exact plan into precondition,
  write, immediate per-partition readback and post-boot result obligations, with only redacted
  target/workspace/output placeholders. Both private records regenerate from current evidence,
  store no raw serial, grant no phone authority, and invoke no runtime.
- Partition-write schema 3 now adds an exact signed, source-bound mode/slot/recovery contract. It
  requires a contiguous transport-correct transition chain, exact slot activation where applicable,
  one final system transition, a bounded stock-recovery adapter/action chain bound to the exact stock
  package digest, external backup, explicit wipe disclosure, separate final consent, no automatic
  wipe, no relock and zero execution authority. Guardian binds that evidence into its inert plan and
  a separate transition-aware gateway/result template. The gateway interleaves only signed
  mode/slot transitions at their exact write boundaries, requires resulting-mode or active-slot
  evidence, and binds the exact command-free recovery contingency. It invokes no runner.
- ROM Studio now carries that entire inert chain through its managed Guardian review operation with
  one monotonic byte-derived progress scale across each required artifact rehash. The review dialog
  presents readable dark scroll cards for the exact binding, partition intent, preconditions,
  signed transitions, immediate readback hashes, recovery actions and possible-wipe warning,
  first-boot Device DNA and blockers, then hands the same exact identities into Guardian Core.
  Changed, mismatched or authority-bearing cached context is discarded, and both screens expose no
  execute, flash, consent, transition or reboot control.
- Guardian live-target check v1 now implements the missing read-only target re-identification boundary.
  It requires a complete previously reviewed Android build identity, the exact gateway device pseudonym,
  one Fastboot device and no competing ADB target, three identical discovery passes around two identical
  product/unlocked/mode probe rounds, and any entry-stage signed slot requirements. Its private receipt
  expires after two minutes, binds the exact gateway/plan/manifest/artifact/Pack scope, hashes the prior
  build identity, stores no raw serial/fingerprint/tool output, grants no consent or authority, and is
  explicitly not cryptographic device attestation. Fixture tests cover target swap, ambiguity, wrong
  product/unlock/mode, probe failure/drift, incomplete prior build evidence, expiry, tampering, duplicate
  fields and linked files. The exact Guardian review now offers this check only when the gateway,
  reviewed Android build identity and both verified tools are present; it runs off the UI thread and
  shows pass/fail, expiry and explicit zero-authority status. Real-device validation remains required.
- Guardian final consent v1 is now defined as a strict runtime-bound source boundary rather than a
  generic approval. It requires the exact schema-three gateway and plan, the still-current stored
  target receipt, the same reviewed phone, an externally pinned runtime public key/adapter, every
  dynamic consequence acknowledgement, and a typed phrase containing the exact product, plan digest
  segment and keep/erase action. It records every ordered forward and recovery consequence, expires
  with the target receipt, stores only an ephemeral-token digest, and leaves recovery and possible
  wipe separately unconsented. It grants no execution authority and contains no signer, token
  consumer, runner or device command. The Desktop visibly explains this boundary after the read-only
  target card but offers no consent button because no production runtime trust is enrolled.
- Guardian runtime-session v1 now defines the next separately identified boundary: a 45-second exact
  challenge must receive a domain-separated Ed25519 response from the pinned runtime key, with the
  runtime accepting only the exact forward gateway and explicitly denying automatic recovery, wipe,
  relock, opened device access and phone change. One boundary-anchored exclusive claim prevents two
  concurrent responses from winning. A create-once consent-capability reservation can then bind the
  in-memory grant's digest to that exact verified session; it stores no raw token and explicitly
  records that runtime consumption and execution authority remain absent. These are verifier/local
  reservation source boundaries only: no production runtime, signer, launcher, device runner or
  Android command has been added.
- A persistent user-supplied firmware responsibility notice and explicit import acknowledgement,
  without attempting to exclude rights or obligations that cannot legally be excluded.
- Signed Desktop update checking and explicit, cancellable staging with measured progress, strict
  receipt reload, boundary-anchored artifact hashing, linked/replaced-file rejection, partial-file
  cleanup, workspace preservation, and zero installer or Android-device authority.
- Companion local diagnostics, Lifeline guidance, Activity/Galaxy/optimizer history, privacy curtain,
  Guided/Expert presentation, encrypted Link credentials, pinned-TLS Desktop telemetry, Device DNA,
  Live Console, and Ascension status display under the tested local contracts. Desktop visibly
  restores a genuine remembered Link session after restart, reports its remaining lifetime, copies
  only a live one-time code, and provides explicit replacement and immediate wireless reset controls.
- A pinned Fedora launcher runs the installed wheel from the recovered data-drive source and opens
  the preserved recovered workspace.

## Intentionally locked or unavailable

- The Desktop candidate is unsigned. It has no production trust or update authority and must not be
  presented as a signed public release.
- The Companion artifact uses the Android Debug certificate. It is a test APK, not a production
  Android release or proof that an upgrade over a future production signing identity will work.
- Production publication awaits externally held Desktop and Android signing keys, pinned public
  trust, offline signing, independent verification, and explicit release-owner approval.
- Desktop rollback is unavailable because there is no prior signed public ROMVERSE Desktop artifact.
  This is represented explicitly rather than simulated.
- Flashing, rooting, bootloader unlocking, wiping, relocking, and other phone-changing operations
  remain locked unless their exact typed contract, recovery evidence, explicit user consent, and
  independent physical validation genuinely exist. The current Guardian preview is intentionally
  inert: it never infers mode transitions, slot activation, reboot, wipe, rollback or recovery; it
  represents them only when an exact signed schema-three Pack declares them. No built-in Device Pack
  currently carries the required signed schema-two or schema-three contracts. Both gateway variants
  are inert result templates—not execution receipts. A domain-separated Ed25519 result verifier is
  now defined and tested, but it has no signer, runner or execution method and no production runtime
  trust is enrolled. The read-only live-target receipt issuer and runtime-bound final-consent receipt
  verifier/issuer are implemented but not physically validated; no consent can be created in the
  production Desktop without enrolled trust, and atomic token consumption, separately consented
  recovery/wipe, a governed runtime adapter, physical validation, and an actual signed result remain
  unavailable.
- Physical-device and broad multi-OEM claims remain limited to the hardware evidence actually
  collected. Samsung Download Mode, Qualcomm EDL, MediaTek preloader, OEM unlock services, recovery
  signing, and other vendor-specific write paths still need separately reviewed adapters and signed
  Device Pack contracts.
- Public Synapse, production Members/billing, Galaxy synchronization, community services, and other
  hosted services are not part of this offline candidate.

## Production-release handoff

1. Keep every production private key outside the repository and normal ROMVERSE workspace.
2. Sign the exact Desktop manifest through the documented offline Ed25519 ceremony and sign the
   Companion release with the separately protected Android production identity.
3. Verify the signed Desktop envelope, both exact archives, and the release APK on separate hosts
   using only the pinned public identities.
4. Install the production-signed Companion over the preceding production candidate on representative
   Android versions and prove private-data migration before publication.
5. Complete the remaining physical-device, recovery, hostile-network, and supported-distribution
   gates listed in `docs/RELEASE_READINESS.md` without changing these candidate bytes.
6. Publish only after explicit release-owner approval, with artifacts, signed metadata, checksums,
   release notes, privacy statement, supported platforms, rollback status, and locked-capability
   statement together.

Until those steps are complete, these files remain verified candidate artifacts rather than trusted
public updates.
