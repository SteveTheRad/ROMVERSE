# ROMVERSE Build Status

## Authoritative checkpoint

- Product Assurance authorization/base: `9ca297b4ad048fee89bb7686128f40d35b441456`
  (`Approve final signed candidate binding`).
- Source commit packaged: `9ca297b4ad048fee89bb7686128f40d35b441456`.
- Exact Git source tree: `963cd9a481efe44df33053c89ea4be2864bb9955`.
- Final handoff checkpoint: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, one consolidated unsigned Fedora internal-development
  artifact containing the approved Linux journey through final-signed candidate preparation.
- Source working tree before and after packaging: clean.

## Runnable Fedora development artifact

- Local artifact:
  `dist/ROMVERSE-Desktop-0.2.0-alpha.1-fedora44-x86_64-9ca297b-unsigned-internal.zip`.
- Classification: **unsigned internal development build**; not a release candidate, signed build,
  publication or production-trusted package.
- Platform built and launched: Fedora Linux 44, x86-64, kernel 7.1.13, Python 3.14.7.
- Locked packaging environment: `build 1.6.0`, `hatchling 1.32.0`, PyInstaller 6.22.2 and
  PySide6 6.11.2.
- Archive SHA-256: `096d15bad7518fafe74074dd92b7e27ed9609e36ba5cf1b3c06044f8655505a4`.
- Archive size: 150,953,773 bytes; mode 0644.
- Exact verified archive tree: 460 regular members, 360,259,562 expanded bytes.
- Exact member/content tree SHA-256:
  `b717d572fee377e7d3e2ba950d0598d96964586d60a3aaa5ccb86eb6860c8cf9`.
- Runnable binary after extraction: `ROMVERSE/ROMVERSE`.
- Frozen binary SHA-256: `2972216e8683cd73e3d9810da253d6571b595fb8d0fe7b46e17c9eea550a8fb5`.

The artifact remains local and ignored by Git. Its identity is recorded here; the 151 MB archive
was not committed, uploaded or published.

## Source and included checkpoint identity

- The wheel intermediary was built once from the clean authoritative source, contained 308 members
  and all 22 indexed Device Packs, and passed exact runtime-source byte comparison.
- Wheel SHA-256:
  `b6b5c74c3f5e7fe90833057130843e1d38c268665b5ca4c75731ae8005fce058`.
- The frozen application was built exactly once from that same checkout. The final archive was then
  packaged once from the frozen directory.
- Exact source commit `9ca297b` includes the approved implementation checkpoints for the retained
  unfamiliar-firmware journey:
  - `41580a949689087618a08fb0930422f45dfeba7d` — unfamiliar firmware intake handoff;
  - `b77ee3c03aac1746a8e8f18acd370ddcb3094360` — durable local-build completion;
  - `14de58e376bbd5cf14369f605bdfd6355f892cca` — artifact verification/offline-signing boundary;
  - `5319ee61f0324b0bb4d1c45e178b308defbced90` — durable signing-ready state;
  - `4a4c61c027790954655e584a07d38ed54650dcf6` — durable candidate preparation identity;
  - `b174803639e0d5a5d2aa6c3be470e03d691eba53` — exact final-signed installation-byte binding.
- All ancestors of `9ca297b` are source history; only runtime package files and assets selected by
  the existing locked packaging scripts are present in the executable bundle. Repository-only
  status/review documents are not runtime payloads.

## Verification and no-phone startup

- Actual wheel source/runtime verification: passed, 308 members and 22 Device Packs.
- Actual frozen build: completed successfully on Fedora with no corrective rebuild.
- Actual archive verification: passed, including CRC, safe member paths, file count, expanded-size
  bound and required executable.
- Independent exact-tree verification re-enumerated the frozen directory and proved every one of
  the 460 archive names and byte streams identical; source and archive tree digests matched.
- Unsigned classification check: passed. The artifact is explicitly named `unsigned-internal`, no
  signature sidecar was produced, and no signing or release-manifest command ran.
- Focused packaging contract regression: **9/9 unique tests passed in 0.37 seconds**.
- Exactly one frozen-app startup was run through the existing bounded `--release-smoke` path using:
  - a fresh disposable workspace and isolated empty configuration;
  - the default persisted experience contract (`GUIDED`);
  - an intentionally empty tool path, so no ADB, Fastboot or Device Engine target existed;
  - the production startup path that constructs the initial `Command Deck` and its truthful
    no-device/Guardian-first state;
  - automatic clean shutdown after 250 ms.
- The frozen process returned zero, initialized the disposable workspace and logged
  `runtime started` followed by `runtime closed cleanly` with no runtime fault.
- The smoke was offscreen and bounded. It proves startup/construction and clean shutdown, not a
  human visual-layout review, interactive workflow replay or hardware behavior.
- The prior Product Assurance-approved journey evidence was reused. The intake, build, AVB,
  signing, candidate preparation and 117-node affected suite were not rerun or double-counted.

## Packaging findings and limitations

- No product or platform defect was exposed; no application source or behavior changed.
- PyInstaller emitted its normal Linux warning that executable icon embedding is supported only on
  Windows/macOS. The approved ROMVERSE icons remain packaged runtime assets, but Linux shell icon
  integration still depends on a later installer/desktop-entry boundary and is not claimed here.
- The PyInstaller warning inventory listed optional or cross-platform imports (for example Windows,
  Java, proxy and optional bcrypt modules). The actual frozen Fedora startup completed cleanly; no
  missing import blocked this bounded launch.
- The archive has not been tested on another Fedora machine, installed system-wide, integrated with
  a desktop menu, visually inspected in this checkpoint or exercised with real firmware/hardware.
- No production recovery adapter or device-changing execution capability was enabled.

## Result classification

- Implemented: no new product behavior. Existing approved source was assembled into one portable
  Fedora internal-development archive.
- Simulated/Tested: packaging checks and one actual offscreen frozen-process launch passed. Prior
  firmware journey evidence remains bounded synthetic/inert evidence.
- Hardware Verified: no phone or target hardware was used. Host packaging was genuinely performed
  on Fedora x86-64.
- Released: no. The artifact is unsigned, local and unpublished.

## Guided friction and remaining boundaries

- The package itself exposed no startup dead end. With isolated default settings and no tool path,
  startup reaches the existing Guided Command Deck and truthfully has no connected device or
  device-changing authority.
- This checkpoint did not repeat the prior Guided journey, open a phone-selection dialog or advance
  past the no-target state.
- Fresh target observation remains queued. Consent, execution, durable result, Recovery
  reassessment and independent verification remain separate closed boundaries.

## Guardian, Recovery and safety implications

- Packaging creates no evidence or authority for Guardian, Recovery, installation or release.
- Guardian remains the sole execution gate. Exact-device identity, exact-incident attribution,
  UNKNOWN-on-uncertainty, no blind retry and independent post-operation verification are unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform, freeze and version-gate status

- Fedora/Linux: one real frozen build, archive and clean offscreen launch verified.
- Windows: unchanged and not exercised; no Windows claim is made.
- Physical Android: not used. The separately authorized future read-only checkpoint remains queued
  until a phone is available and Product Assurance authorizes that boundary.
- Protected Companion, Windows launcher, Knowledge/Adaptive, website, logo and unrelated user work:
  untouched.
- 5 September 2026 feature freeze: compliant. Packaging assembled existing approved behavior and
  introduced no new feature or application change.
- v0.2 Golden Foundation remains **CLOSED**.

## External actions

- Physical phone/emulator operation, ADB/Fastboot target, APK transfer/install, consent, execution,
  Recovery, flash, private-key use, production trust enrollment, publication and release: none.
- System-wide install, dependency installation, merge, history rewrite and force-push: none.
- Local files created: one wheel intermediary, one frozen application directory, one final unsigned
  ZIP and disposable no-phone smoke workspace.
- Remote action: normal push of the documentation-only handoff commit to the existing
  `linux/stage1-desktop-readiness` branch only. The binary artifact is not pushed.

## Next proposed Build task

Stop for Product Assurance. If this local Fedora development artifact is approved and a phone is
available, Product Assurance may authorize one bounded read-only fresh exact-device observation.
Do not cross into consent, execution, installation, Recovery or another consequential slice without
that review.

## Product Assurance Review Requested

- Confirm the recorded source/tree/archive identities and unsigned internal-only classification.
- Confirm the offscreen clean launch with isolated Guided defaults and no tool path is sufficient
  for this bounded packaging checkpoint, while recognizing it is not visual or hardware evidence.
- Confirm the next authorized boundary, when hardware is available, remains one read-only fresh
  exact-device observation ending before consent.
