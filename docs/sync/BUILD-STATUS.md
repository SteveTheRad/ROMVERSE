# ROMVERSE Build Status

## Authoritative checkpoint

- Product implementation remains unchanged at `f61cbc54c203283e457a346bd327a99bec29d880`.
- Physical-journey authorization and checkpoint base: `c4043b871d7029ffd513bdda33d8e7a1fb5de103`.
- Branch: `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation controlled physical Android verification.
- Milestone: production Fedora Device Engine / First Light read-only journey against one explicitly
  authorized physical USB target.
- This handoff is the only repository change in the checkpoint commit. Product source, tests,
  packaging, assets, Companion, Windows launcher work, and the protected original checkout are
  unchanged.

## Exact journey and observed product result

- Launched the existing production Fedora Desktop through `romverse.app.main` with
  `--skip-onboarding` and a fresh isolated `/tmp` workspace.
- The production UI's automatic reconnect-safe Device Engine path retained exactly one authorized
  target through its identity-stabilization and completed telemetry passes.
- The UI visibly reported `Connected via ADB`, `CONNECTED • READ ONLY`, `Xiaomi 17 Pro Max`,
  codename `popsicle`, and `Android 17`.
- Privacy-safe Device DNA evidence reported model `2509FPN0BC`, product/codename `popsicle`, API 37,
  build `CP2A.260605.016`, ROM `OS4.0.0.32.XPBCNXM`, security patch `2026-08-01`, boot complete,
  active slot `_a`, Verified Boot `orange`, bootloader unlocked, no active root evidence, Companion
  present, and zero probe errors.
- The production ROM Studio navigation control was activated through its visible Qt button. In the
  fresh workspace it truthfully showed `No ROM projects yet`, `AWAITING PROTECTED FIRMWARE`, and
  Device DNA awaiting an evidence-backed protected firmware import.
- First Light remained **NOT STARTED**. No exact project, successful Guardian execution, linked boot
  observation, or verified first boot existed, so ROMVERSE did not manufacture First Light or
  Recovery success.
- Guardian remained `unverified`; Guardian verification was false and execution authority remained
  `none`. Device Pack readiness separately remained flash-locked.
- ROMVERSE closed cleanly and no ROMVERSE or Fastboot process remained.

## Privacy-safe evidence

- Raw device serial was used only transiently in memory to enforce same-target continuity and was
  never printed into this handoff, evidence JSON, screenshots, or workspace records.
- A post-run byte-for-byte scan found **0 raw-serial occurrences** in the isolated workspace.
- The evidence uses only a one-way SHA-256 target token truncated to 24 hexadecimal characters:
  `e0e6a3bd1e06a7b52df30300`.
- External local evidence (not staged or published):
  - Command Deck screenshot SHA-256:
    `f3968b87acb810cb4bdb340cc616b988f11280360071c0d8e5bb05753bca6f0c`.
  - ROM Studio screenshot SHA-256:
    `d120386c0ae344119e93bfec0c771f47760c1b598aedb8fdd950dd5a96215e33`.
  - Sanitized UI evidence JSON SHA-256:
    `43f624c2e8c07fdca292898232f4d2364bf8f0fe1489f3ddb320179d3f772827`.
- The fresh workspace also recorded its normal redacted activity, Device Atlas readiness, offline
  archive matches, and guidance-only remediation receipts. Its activity ledger explicitly says
  `nothing uploaded` for the offline lookup.

## Result classification

- Implemented: no new implementation; this checkpoint verifies the existing product.
- Simulated/Tested: no simulator, emulator, fixture, or mocked device was used for this checkpoint.
- Hardware Verified: **yes, narrowly** — one real authorized Xiaomi 17 Pro Max was identified over
  explicit physical USB and its production read-only ADB telemetry was rendered by the Fedora UI.
- Not Hardware Verified: First Light, Guardian execution, Recovery execution/result/reassessment,
  flashing, reboot/mode transition, Companion installation, production trust, signing, or release.
- Released: no.

## Non-double-counted verification

- Current checkpoint: one completed production Fedora UI physical journey; no automated test suite
  was rerun because the journey exposed no correctness defect requiring a focused regression.
- The verification session used two short UI launches: the first captured only the expected bounded
  identity-stabilization snapshot and closed; the second completed that same reconnect-safe product
  journey and produced the evidence above. These are **not** counted as two completed journeys.
- The earlier creator-authorized read-only admission/preflight that established the one explicit USB
  target is already captured by Product Assurance in `c4043b8` and is not counted again.
- Retained prior accepted regression evidence remains unchanged and is not added here:
  - Full Fedora/Linux Python regression: **2,881/2,881 passed** at `1300dde`.
  - Companion focused unit/security result: **8/8 passed** at `f61cbc5`.

## Guided friction and dead ends

- Target identification and Device DNA presentation completed without a dialog or user decision
  after USB authorization was already present.
- The fresh workspace correctly stops at project creation/protected firmware import. This is an
  actionable prerequisite, not a circular route and not execution readiness.
- First Light is correctly unavailable until the exact project has a successful Guardian-linked
  execution and independently verified first boot. No extra confirmation or false success appeared.
- The Command Deck started its existing automatic repair-research presentation for the observed
  unlocked-bootloader security posture. It completed with two source-attributed, guidance-only
  candidates and `execution_authority: guidance-only`. This did not block navigation or grant phone
  authority, but Product Assurance should confirm whether this automatic presentation is the desired
  calm Guided behavior on first discovery.

## Guardian, Recovery, and safety implications

- Guardian granted no execution authority. The scan was read-only and Device Atlas explicitly kept
  flash locked despite matching the device to an existing Device Pack identity.
- No project/source/consent/preparation/executor/result/reassessment/verification chain was created.
- Exact-device continuity failed closed in the external observation harness if target count,
  authorization state, or the sealed one-way target identity changed.
- UNKNOWN-on-uncertainty, no blind retry, same-incident Recovery, independent verification, and
  Guardian-only authority were unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora production Desktop startup, read-only physical USB Device Engine, privacy masking, visible
  Command Deck state, ROM Studio navigation, and clean shutdown: **HARDWARE VERIFIED** for this one
  authorized phone and host only.
- Windows: unchanged; no Windows claim is made by this checkpoint.
- Companion hardware workflow: not exercised. The app only observed that the Companion package was
  present; it did not launch, pair, update, or install it.
- 5 September 2026 pre-v1.0 feature freeze: preserved. No product capability or UI was added.
- v0.2 Golden Foundation remains **CLOSED**. This closes only the bounded Linux read-only physical
  discovery evidence gap; production Recovery/trust, signing, Windows release readiness, packaging,
  publication, and release gates remain open.

## Blockers and remaining limitations

- First Light cannot be hardware-verified in a fresh empty workspace and must not be fabricated; it
  still requires an exact project, protected firmware, successful Guardian execution, linked boot
  evidence, reassessment, and independent verification.
- The observed phone/host result cannot be generalized to every Android device or Windows.
- Production Recovery execution, trust enrollment, physical flashing, signing, packaging,
  publication, and release remain outside this authorization.

## Next proposed Build task

Stop for independent Product Assurance review of this exact physical read-only checkpoint. Do not
start another hardware journey or consequential slice until repository review authorizes it.

## External actions

- Physical phone: read-only ADB identity and health-property probes only, through the production
  Device Engine. The phone was released immediately after the completed snapshot.
- Phone mutation: none — no APK install, reboot, mode transition, Fastboot/Recovery entry, flash,
  wipe, unlock, root, trust enrollment, signing, locking, or relocking.
- Automatic intelligence: the enabled existing product service evaluated source-attributed guidance
  for the unlocked-bootloader posture and wrote a guidance-only receipt in the isolated workspace.
  Its configured provider path attempted bounded public search GET requests to Reddit and Android
  Stack Exchange using non-serial device/error fingerprint text during the short launches. No raw
  serial, account credential, local file, private evidence, or command was sent; no candidate from
  those community searches was accepted into the resulting receipt. The resulting official-catalog
  guidance granted no action or execution authority.
- Host mutation: fresh isolated `/tmp` workspace and local evidence files only; no system-wide
  install, dependency change, firewall/SELinux change, or persistent settings change.
- Publication/release/merge/force-push: none.
- Remote action: only the normal push of this documentation-only Linux checkpoint is intended after
  repository verification.
- Protected Companion files, original-checkout Windows drafts, website, logos, and unrelated work:
  untouched.

## Product Assurance Review Requested

- Confirm the production UI evidence satisfies the authorized physical Device Engine / First Light
  boundary while correctly treating First Light as not started rather than successful.
- Confirm the two-launch stabilization disclosure is acceptable as one completed bounded journey.
- Review the automatic guidance-only repair-research presentation on first discovery for Guided
  calmness; no implementation change is requested by Build at this checkpoint.
- Confirm Linux may remain stopped with v0.2 closed pending the remaining platform, production-trust,
  signing, Recovery, packaging, and release gates.
