# ROMVERSE Build Status

## Authoritative checkpoint

- Packaged-run correction commit: `64ad510532a18b5e26a6feec46791069aee0e8ec`.
- Approved onboarding implementation contained in the artifact: `eaa3d615912a4eefddd44ee3b032562047ddadc3`.
- Artifact build repository state and Product Assurance authorization/base:
  `b59c3d86a24fdc08d8531ac2414ff6f97b4ee498`.
- Handoff checkpoint: the commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, refreshed Fedora first-run alpha artifact.
- Working tree: clean apart from ignored local build/evidence output after the handoff commit is
  created.

## Refreshed Fedora development artifact

- The Fedora `0.2.0-alpha.1` artifact was rebuilt and packaged exactly once from the approved
  `b59c3d8` repository state.
- File: `dist/ROMVERSE-Desktop-0.2.0-alpha.1-linux-x86_64.zip`.
- SHA-256: `cc9f1c7df7b9147e4a2e8bc1a3ac4b8acb5441ece9fd495854f725322fee9ac0`.
- Archive size: `150947822` bytes; mode `0644`.
- Verified contents: `460` regular files, `360254930` expanded bytes, expected
  `ROMVERSE/ROMVERSE` executable present, safe member validation and CRC verification passed.
- Exactly one packaged `0.2.0-alpha.1` Fedora artifact exists in `dist`.
- Classification: **unsigned internal development artifact only**. It is not signed, published,
  released or production-authorized.

## Exact packaged first-run journey

- Launched the refreshed frozen executable without `--skip-onboarding`, using a new disposable
  config/workspace, Fedora's local Qt VNC display backend and an empty executable-search path.
- The real packaged onboarding visibly displayed `0.2.0-alpha.1 • INTERNAL DEVELOPMENT`, the
  no-phone/setup boundary and the exact `Continue in Guided Mode` action.
- Activated that real packaged Guided action. The same frozen process opened Command Deck with:
  - `GUIDED • ARCANA` visibly selected;
  - sidebar identity `ROMVERSE 0.2.0-alpha.1`;
  - `DEVICE: NOT CONNECTED`, no active project and `GUARDIAN: VERIFY REQUIRED`;
  - a visible `Resolve Platform Tools` host prerequisite;
  - `No Android device is connected. ROM Studio remains available for safe local firmware work.`
- No dead button or navigation loop prevented entry. The bounded process was terminated after the
  evidence capture; no Android executable was discoverable and no phone/device action started.
- Packaged onboarding screenshot SHA-256:
  `b537e2a8292a5308bca92024795a1526b3ee03c23e5560538ca809b31e31d258`.
- Packaged Command Deck screenshot SHA-256:
  `b4bc20a93ee6f49c479169ba882f160a392ad96f52afe6ad9e8e89e2b6ff1aa9`.

## First concrete packaged-run defect and correction

- Command Deck's static subtitle still claimed `One live device, one active project` while the
  authoritative cards correctly showed no device and no project. This was a misleading status claim
  visible only after the packaged Guided transition.
- `DeviceCenter` now uses the evidence-neutral subtitle `Current device, project, and
  evidence-derived next action at a glance.` and exposes that label for focused verification.
- One focused regression proves the empty Command Deck no longer claims a live device or active
  project.
- Per the exactly-once refresh instruction, the Fedora artifact was not rebuilt a second time after
  this minimum source correction. The artifact contains the approved onboarding correction but not
  the subsequent neutral subtitle; `64ad510` is the authoritative corrected source.

## Result classification

- Implemented: yes — minimum truthful Command Deck subtitle correction after the exact packaged run.
- Simulated/Tested: yes — real packaged first-run UI journey plus one source-level focused regression.
- Hardware Verified: no.
- Released: no.

## Non-double-counted verification

- Refreshed artifact build/package: **1/1 completed**.
- Real packaged first-run Guided/no-phone journey: **1/1 completed**.
- Focused subtitle regression: **1/1 passed**.
- Ruff: **PASS** for the changed source and focused test module.
- Git whitespace checks: **PASS** before the correction commit and handoff.
- Artifact integrity/tree verification: **PASS** with the exact digest, size and member counts above.
- No full suite, earlier journey replay, second artifact build/package or unrelated UI regression
  campaign was run.

## Guided friction and remaining boundaries

- Verified: corrected internal-alpha onboarding reaches Guided Command Deck without a dead button,
  false device readiness or technical loop.
- Fixed in authoritative source: the contradictory static `one live device / one active project`
  subtitle found by this packaged run.
- Remaining packaging boundary: the exactly-once refreshed ZIP predates only the one-line subtitle
  correction. It must not be represented as containing `64ad510` until a later authorized rebuild.

## Guardian, Recovery and safety implications

- Onboarding and Command Deck presentation grant no Guardian, build, device, flash, Recovery,
  installation, signing, publication or release authority.
- UNKNOWN-on-uncertainty, no blind retry, exact-device evidence, consent separation, same-incident
  Recovery and independent verification remain unchanged.
- Expert mode was not entered. Production Recovery execution was not invoked.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora/Linux: refreshed unsigned artifact and its exact first-run Guided/no-phone journey are
  genuinely software-verified on Fedora 44 x86-64; this is not hardware verification.
- Windows: unchanged; no new Windows claim is made.
- Physical Android: not used; no hardware claim is made.
- 5 September 2026 feature freeze: compliant. Only the first misleading packaged-run status string
  received its minimum focused correction.
- v0.2 Golden Foundation remains **CLOSED**. No signing, publication or release gate changed.

## External actions

- Physical phone, emulator, USB target, device-scoped ADB/Fastboot, Recovery, flash, install, APK
  transfer and device operation: none.
- Managed tool auto-install, package/dependency/system installation, signing, publication, release,
  merge and force-push: none.
- Fedora artifact refresh: exactly one authorized local build/package replacement; no distribution
  or installation occurred.
- Remote action: only the normal push of the scoped correction and handoff commits to the existing
  Linux working branch is intended.
- The three protected Companion files, original-checkout Windows launcher drafts, website, assets
  and unrelated user work were untouched.

## Next proposed Build task

Stop for independent Product Assurance review. Do not rebuild either platform artifact or begin
another consequential slice.

## Product Assurance Review Requested

- Confirm the refreshed artifact and real packaged first-run evidence satisfy the approved Fedora
  platform milestone.
- Confirm `64ad510` is the minimum freeze-safe correction for the first packaged-run defect.
- Decide when the one-line post-build subtitle correction should be incorporated into a later
  batched development artifact without violating this checkpoint's exactly-once refresh boundary.
