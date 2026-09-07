# ROMVERSE Build Status

## Authoritative checkpoint

- Implementation commit: `1300dde1b79304149b8acfafe0e3f272d800cd37`
- Title: `Assemble runnable Fedora recovery journey`
- Branch: `linux/stage1-desktop-readiness`
- Approved base: `fdb1692b0a5056cce0992b9045cd6f3a55cabf97`
- Stage: Stage 1 — v0.2 Golden Foundation tangible Fedora product assembly
- Milestone: runnable Fedora development build plus one complete inert Guided Recovery journey
- Build status: implementation and full Linux regression complete; stop for Product Assurance review
- Working tree target state: clean after this handoff commit. The separate original checkout's protected
  Companion changes and Windows launcher drafts were not edited, staged, discarded, or committed.

## Exact changes

- Added `docs/FEDORA-DEVELOPMENT-BUILD.md` with source-launch, offscreen smoke, wheel, one-folder
  executable, portable ZIP, and inert Guided Recovery commands for Fedora. The workflow installs
  nothing system-wide and makes no release claim.
- Added `scripts/simulate_guided_recovery.py`, a product-level simulation that imports no test code
  and traverses the production Recovery boundaries:
  **Scan → Match → Prepare → Consent → Result → Reassessment → Verification**.
- The simulator uses a new disposable workspace, tiny synthetic evidence, an in-memory device
  transport, a strict machine-readable adapter response, and an ephemeral Ed25519 test-only trust
  identity. It invokes no ADB/Fastboot executable, subprocess adapter, physical phone, production
  adapter, or existing ROMVERSE workspace.
- Added `tests/test_guided_recovery_simulation.py` to prove the journey reaches exact verified
  same-incident Recovery, keeps the Result boundary explicitly unverified, reopens the project,
  persists the report, retains no raw simulated serial, permits no retry, and contains no relock.
- No `src/romverse` application runtime, approved asset, Companion source, Windows launcher source,
  schema, Device Pack, production adapter, or release behavior changed.

## Runnable Fedora artifacts

- Source launcher: `python -m romverse --workspace <development-workspace> --skip-onboarding`
- Wheel: `build/wheel/romverse-0.1.0-py3-none-any.whl`
  - SHA-256: `df40c6ca9da96154050f07dd4fa8a336b035ff394c68bf56c52d41b6c0cdddcc`
  - Verified inventory: 308 members and 22 bundled Device Packs.
- One-folder executable: `build/frozen/ROMVERSE/ROMVERSE`
  - SHA-256: `b94dc7788b4cce09d4a30e5aff44d6bf1104c717bac9bf843267538c5e1a68ea`
- Portable development ZIP: `dist/ROMVERSE-Desktop-0.1.0-linux-x86_64.zip`
  - SHA-256: `dd73842d1de7c18f545b6a4cba7141f758ad3802c8e98877a54de81cdc3afed2`
  - Verified inventory: 460 files; 360,241,874 expanded bytes; no extracted symbolic links.
- Artifacts are local ignored build outputs and are deliberately not committed, signed, published,
  installed system-wide, or represented as releases.

## Demonstrated workflow

- Fedora source startup and controlled shutdown: passed offscreen through the real app entry point.
- Isolated wheel installation/startup/shutdown/uninstall: passed in a disposable virtual
  environment; project manifest remained byte-exact after uninstall.
- Frozen executable startup/shutdown: passed from the build directory and again after extracting
  the portable ZIP.
- Navigation: all 19 canonical Desktop routes opened through the installed application smoke.
- Project opening and persistence: a populated workspace reopened byte-exact; the Guided Recovery
  simulator also reopened its project and exact incident from durable storage.
- Guided/Expert shared state: the application-owned Recovery session remained the same session
  across a Guided-to-Expert mode change and continued to verification in the final full suite.
- Inert Guided Recovery: one exact simulated device was scanned and matched; a three-step
  source-bound preparation was consented once; three durable successes produced an unverified
  aggregate Result; same-incident Reassessment entered `VERIFYING`; only a fresh stable exact-device
  boot observation advanced the existing incident to `RECOVERED` and verified reboot.

## Classification

- Implemented: Fedora development build/launch documentation, reproducible inert Guided Recovery
  assembly, durable JSON demonstration report, and regression coverage.
- Simulated/Tested: the complete Guided Recovery journey and every phone/adapter observation in it.
  Simulation uses production services but is not hardware proof or production execution authority.
- Hardware Verified: no Android hardware operation occurred. Genuine Fedora host build and process
  launch were verified; this is host-platform verification, not phone verification.
- Released: no. The artifacts are unsigned local development outputs only.

## Verification evidence

- Final full Linux Python regression: **2,881/2,881 passed** in 920.49 seconds.
- Focused affected Recovery/UI/state regression: **79/79 passed**. This is a subset of the full
  2,881 and is not added to it.
- Earlier focused Fedora Desktop/build/package regression: **240/240 passed**. This is also a
  subset of the final full result and is not added to it.
- New product simulation executed directly and completed all seven requested stages with three
  strict adapter actions, no external process, no raw serial persistence, and final exact-incident
  verification.
- Wheel validation, installed-app smoke, frozen-app smoke, extracted-portable smoke, isolated
  uninstall preservation check, Ruff over `src`, `scripts`, and `tests`, and Git whitespace check:
  all passed.
- No failed, skipped, or xfailed item appeared in the final Linux run.

## Blockers and remaining limitations

- No production-signed Recovery adapter is enrolled and physical Recovery execution remains
  disabled. This is an intentional release gate, not a Guided loop.
- No Android physical device was used for Recovery or post-repair verification.
- The Fedora artifact is not an RPM, Flatpak, signed installer, or published release; native desktop
  entry/install/uninstall integration remains outside this development-build checkpoint.
- PyInstaller reported a missing optional `xxsubtype` hidden-import warning and that its executable
  icon option is Windows/macOS-specific. Neither caused a Fedora launch or bundled-asset failure;
  native package-shell icon integration is not claimed here.
- The separate Windows branch has genuine approved Windows trusted-launcher verification, but its
  broader repository portability baseline is incomplete and is not claimed by this Linux checkpoint.
- Companion Android instrumentation and hardware behavior were not exercised.

## Guided friction and dead ends

- No dead end or circular gate occurred in the demonstrated inert journey.
- Guided retains one consequential consent decision. Result and Reassessment remain calm,
  non-authoritative continuation boundaries rather than additional confirmations.
- A completed adapter sequence does not claim repair. The session waits for the exact phone and
  only continues after fresh stable verification evidence.
- Wrong, missing, stale, or ambiguous identity still fails closed. FAILED and UNKNOWN still stop
  without a retry offer.
- Real Recovery cannot proceed until separately authorized production-adapter and physical-hardware
  gates exist; ROMVERSE must continue to present that limitation truthfully.

## Guardian, Recovery, and safety implications

- Guardian remains the only execution gate. Convenience, UI state, consent, preparation, adapter
  text, and historical identity grant no execution authority.
- Preparation and consent explicitly retain `execution_authority: none`.
- The aggregate Result explicitly retains `recovery_verified: false`; independent boot evidence is
  required before the incident becomes recovered.
- Exact-device and same-incident attribution are preserved through every stage.
- UNKNOWN remains durable and cannot trigger a blind or automatic retry.
- Bootloader locking/relocking remains permanently prohibited with no override. The simulation
  Device Pack, adapter allowlist, report, and assertions all retain `bootloader_relock_allowed: false`.
- The test-only signing private key exists only in memory and is never written to the workspace,
  fixtures, report, source, or logs.

## Platform status

- Fedora/Linux: genuinely built, launched, shut down, packaged, extracted, reopened, and fully
  regressed on Fedora. Local development readiness checkpoint complete.
- Windows: the trusted-launcher contract is genuinely Windows-verified on the separate authoritative
  Windows branch and Product Assurance approved it. The full Windows repository baseline remains
  incomplete; no Windows work was duplicated here.
- Android physical hardware: not run and not claimed.

## Feature-freeze and version-gate impact

- 5 September 2026 pre-v1.0 feature freeze: compliant. This assembles and demonstrates the already
  approved Stage 1 chain and fixes no unrelated behavior; it adds no product feature, vendor,
  firmware format, Device Pack, production adapter, execution authority, or release surface.
- v0.2 Golden Foundation: remains **CLOSED** as recorded by the latest Product Assurance verdict.
  This checkpoint supplies tangible Fedora development-build evidence and does not reopen a safety
  or architecture boundary.
- Release gate: unchanged. Production adapter enrollment and controlled physical Android
  verification remain mandatory separate gates.

## Next proposed Build task

Stop for Product Assurance review of this runnable Fedora checkpoint. Do not begin another
consequential slice or merge a platform branch. After approval, choose only the next bounded task
that Product Assurance and the creator authorize from repository truth.

## External actions

- Physical phone operation: none.
- ADB/Fastboot command against hardware: none.
- APK installation: none.
- System-wide package installation: none.
- Disposable virtual-environment action: the locally built wheel was installed, launched, then
  uninstalled inside an isolated temporary venv; no user/system environment was changed.
- Production Recovery execution: none.
- Publication/release: none.
- Website change: none.
- Companion source change: none.
- Windows launcher source change: none.
- Remote action: normal push of only `linux/stage1-desktop-readiness` for checkpoint review; no
  force-push and no unrelated branch push.

## Product Assurance Review Requested

- Confirm the local wheel, one-folder executable, portable ZIP, and documented source launcher are
  sufficient for the requested runnable Fedora development-build milestone.
- Confirm the product-level inert journey faithfully demonstrates the existing Stage 1 Guided
  chain without misclassifying simulation as hardware verification or broadening the feature freeze.
- Confirm that native RPM/Flatpak/desktop-entry integration and production adapter/hardware work
  remain later, separately authorized release gates rather than defects in this checkpoint.
