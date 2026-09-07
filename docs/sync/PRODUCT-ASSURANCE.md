# ROMVERSE Product Assurance

## Reviewed checkpoint: 99c961e — simulated Fedora Guided Forge boundary

- Handoff commit: `99c961e`
- Implementation commit: `392b21eb90966b09f089ed9b8f3dac29e5fedf8d`
- Product Assurance authorization: `15092ce`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — GUIDED FORGE PAUSE IS TRUTHFUL**

### Decision

The ordinary-user simulation found one real presentation defect and corrected only that defect.
Genesis now names Forge Control when the local build/sign stage pauses and retains Guardian review
only for the optional phone-install stage. The consequential chain, evidence requirements, and all
authority boundaries are unchanged.

Stopping at missing exact Partition Atlas inputs and verified Fakeroot is the correct result for the
minimal sanitized OTA fixture. The product did not turn incomplete synthetic evidence into a build,
signature, consent, Recovery result, reassessment, or verification claim. No additional work is
required for this exact fixture.

### Independent repository evidence

- `392b21e` changes seven lines in `guided_mission.py` and the exact focused ROM Studio regression;
  `99c961e` changes only the Build handoff.
- The stage ID selects the user-facing review-surface name without changing stage selection,
  readiness, modal ownership, automatic advancement, or live-console authority.
- The focused regression requires `paused at Forge Control` and excludes the stale Guardian label.
- Build recorded one pre-fix discovery run, one post-fix affected rerun, and one focused test pass;
  no broad suite or duplicated milestone was claimed. `git diff --check 15092ce..99c961e` passes.
- The production-UI report remains explicitly `SIMULATED`, records
  `production_execution_authority: none`, and contains no physical target or phone operation.

### Safety and acceptance result

- Correct build-stage surface and no false Guardian direction: **PASS**
- Truthful stop on missing source-derived partition/build evidence: **PASS**
- Feature freeze and existing Guided flow: **PRESERVED**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification, and permanent no-relock: **UNCHANGED**
- Phone, ADB/Fastboot target, Recovery, install, flash, signing, publication, release: **NONE**

### Approved next bounded task

Continue one new, non-duplicative Fedora production-UI **SIMULATED** journey from the Forge Control
boundary toward a verified local candidate. Use a disposable workspace and only the smallest
sanitized source-derived partition/image fixtures and injected non-consequential build adapters
already supported by the repository. Do not inject completed internal state, forge receipts, weaken
image/tool/evidence validation, or reuse the 722-byte source to claim progress it cannot support.

Exercise existing Partition Atlas, Fakeroot/toolchain, build-plan, candidate preparation, AVB and
Guardian handoff behavior only as far as valid evidence permits. Identify the first concrete
user-facing dead end or correctness defect after the now-approved Forge pause and implement only its
minimum freeze-safe correction. Rerun only the affected segment and focused tests. If the supported
production services correctly stop on evidence that cannot be represented safely by sanitized
fixtures, record that exact boundary without inventing completion. Label all results `SIMULATED`;
they grant no hardware, production, signing, release, Recovery, or execution authority. Commit and
push the handoff, then stop for Product Assurance.

### Gate status

- Fedora protected-source through Forge Control Guided journey: **SIMULATED AND VERIFIED**
- Source-derived local candidate through Guardian handoff: **NEXT SIMULATED INTEGRATION SLICE**
- v0.2 Golden Foundation: **CLOSED**
- Physical execution, production trust/signing, publication, and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 27538d8

- Handoff commit: `27538d8`
- Product implementation: unchanged at `f61cbc54c203283e457a346bd327a99bec29d880`
- Physical authorization: `c4043b871d7029ffd513bdda33d8e7a1fb5de103`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — LINUX PHYSICAL READ-ONLY DEVICE ENGINE VERIFIED**

### Decision

The bounded real Fedora Device Engine / First Light observation is accepted. The production UI
retained one exact authorized physical USB target, rendered privacy-safe Device DNA truthfully,
kept Guardian and First Light fail-closed, and shut down cleanly. The phone is released and this
authorization is exhausted; no further physical-device action is implied.

The automatic repair-research presentation remained guidance-only, did not block navigation, sent no
raw serial or private evidence, and granted no authority. It is acceptable for this checkpoint. Its
calmness and relevance should be observed during the next ordinary-user simulated journey rather
than opening a separate audit loop.

### Independent evidence

- `27538d8` changes only `docs/sync/BUILD-STATUS.md`; product source, tests, packages, assets,
  Companion, Windows work, and protected unrelated changes are untouched.
- Product Assurance visually inspected the retained Command Deck and ROM Studio captures. They show
  the named phone, `CONNECTED • READ ONLY`, Android 17, the protected-firmware prerequisite, no
  active project, `NOT YET VERIFIED`, and Guardian `NOT YET READY` without a false success state.
- The screenshot and sanitized-JSON SHA-256 values exactly match the handoff:
  `f3968b87acb810cb4bdb340cc616b988f11280360071c0d8e5bb05753bca6f0c`,
  `d120386c0ae344119e93bfec0c771f47760c1b598aedb8fdd950dd5a96215e33`, and
  `43f624c2e8c07fdca292898232f4d2364bf8f0fe1489f3ddb320179d3f772827`.
- Sanitized evidence records one USB target, zero device errors, Guardian unverified, execution
  authority `none`, and First Light `NOT STARTED`.
- A direct byte search found zero raw-serial occurrences in the retained workspace/evidence scope.
- No repeated suite was needed because the unchanged product journey exposed no implementation
  defect. Existing 2,881-test Fedora and focused Companion evidence remains non-double-counted.

### Safety and gate result

- Exact physical USB observation: **PASS**
- Privacy-safe Device DNA and raw-serial exclusion: **PASS**
- Guardian no-authority and First Light fail-closed truthfulness: **PASS**
- ROM Studio protected-original prerequisite: **PASS**
- Phone mutation, APK install, mode change, Recovery/Fastboot, flashing, signing, release, relock:
  **NONE**
- v0.2 Golden Foundation: **CLOSED; physical read-only discovery gap now verified on one device**

### Approved next bounded task

Run one ordinary-user, production-UI **SIMULATED** Fedora ROM Studio journey in a disposable isolated
workspace. Use only sanitized synthetic firmware/Device DNA fixtures and injected non-consequential
ADB/Fastboot/Recovery adapters; no real phone may be connected or targeted. Exercise the existing
flow from project creation and protected-original import through evidence-derived Device DNA,
Matrix/Nexus/Pathfinder presentation, candidate build/preparation, Guardian gating, and inert
Recovery/result presentation as far as the current product truthfully supports.

The purpose is to identify the first concrete user-facing dead end or correctness defect in an
existing pre-v1.0 flow. If one appears, implement only its minimum freeze-safe correction and rerun
only the affected segment. If the product correctly stops at a prerequisite, record that truthful
boundary instead of inventing completion. Label all evidence `SIMULATED`; it grants no hardware,
production, signing, release, or execution claim. Do not run broad suites, repeat accepted journeys,
or create a general architecture/audit task. Commit and push the Build handoff, then stop for
independent Product Assurance review.

## Creator-authorized physical checkpoint: 2026-09-08

- Base checkpoint: `c415391`
- Branch: `linux/stage1-desktop-readiness`
- Authorization status: **APPROVED — ONE CONTROLLED READ-ONLY PHYSICAL ANDROID JOURNEY**

### Decision

Steve connected a phone to the Linux host immediately after Product Assurance requested explicit
authorization for controlled read-only physical Android verification. Read-only preflight observed
exactly one authorized ADB target with explicit `usb:3-1` transport evidence, product/device identity
`popsicle`, and model `2509FPN0BC`. The raw serial is intentionally not recorded here.

This authorizes one bounded real-product Device Engine / First Light observation journey on Linux.
It does not authorize a build, flash, wipe, unlock, reboot, Recovery or Fastboot transition, APK
installation, root action, production trust enrollment, signing, publication, release, or relock.

### Approved next bounded task

Using the existing approved Fedora development build and a fresh isolated workspace, exercise the
production Device Engine / First Light read-only discovery path against the one current physical USB
target. Require one unambiguous authorized target throughout. Capture only product-generated,
privacy-safe evidence for target classification, observable mode/identity, Device DNA/First Light
state, Guardian authority state, and any truthful actionable blocker. Do not persist the raw serial.

Do not issue a state-changing device command, install the Companion APK, enter another device mode,
or manufacture execution readiness. If the target changes, multiplies, disconnects, becomes
unauthorized, or any evidence is uncertain, classify the result as `UNKNOWN` or specifically blocked
and stop. Reuse existing accepted tests; run only a focused check if the journey exposes a concrete
defect. Commit and push the Build handoff, then stop for independent Product Assurance review.

### Acceptance criteria

- Exactly one explicit physical USB target remains unambiguous: **REQUIRED**
- Production UI truthfully identifies the observable target and mode: **REQUIRED**
- First Light / Device DNA evidence is read-only, bounded, and privacy-safe: **REQUIRED**
- Guardian grants no execution authority: **REQUIRED**
- Uncertainty, disconnect, authorization loss, or identity change fails closed: **REQUIRED**
- No APK, reboot, mode transition, flashing, Recovery, trust enrollment, signing, release, or relock:
  **REQUIRED**

## Reviewed checkpoint: 1ecb0d1

- Handoff commit: `1ecb0d1`
- Implementation commit: `f61cbc54c203283e457a346bd327a99bec29d880`
- Product Assurance authorization: `44a3332d975583747e576bfa2967c1bb0bfb0014`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — COMPANION STALE-RESULT INVALIDATION VERIFIED**

### Decision

The minimum Companion correctness repair is accepted. A reset, newer request, or Activity teardown
now invalidates the older pairing generation before that worker can update current presentation,
persist a token, or restore pairing preferences. The direct product Link milestone remains verified,
and its retained evidence count is now stated exactly as 13 observations total / 12 authenticated.

This repair adds no user decision, retry, network authority, execution authority, or feature. It
closes the observed `APPROVAL TIMEOUT • TRY AGAIN` overwrite without repeating the product journey.

### Independent repository and verification evidence

- `f61cbc5` changes only `MainActivity.kt` and one new local unit test. `1ecb0d1` changes only the
  Build handoff. Desktop source, Windows work, protocol, assets, and protected original-checkout
  changes are untouched.
- The synchronized generation gate gives each submitted request one current identity. Reset calls
  invalidate before clearing session state, a newer begin supersedes the older identity, and
  `onDestroy` closes the gate.
- Initial request presentation, polling, telemetry/transfer collection, token-vault persistence,
  paired preferences, late failure, and timeout all require the same current generation. A stale
  worker exits or its main-thread action is rejected.
- The deterministic regression proves stale timeout and stale approval cannot replace reset state or
  restore token/preferences; only the newer attempt can apply; teardown rejects its pending result.
- Product Assurance independently read the generated JUnit XML: the new gate test passed 1/1 and the
  retained Link security tests passed 7/7, with zero failure, error, or skip. Android lint produced no
  blocking error. Git whitespace and remote ancestry are clean.
- Automatic retrieval of SDK Platform 35 revision 2 and Build-Tools 34.0.0 occurred only inside the
  already dedicated removable-data Android toolchain. It did not change repository dependencies,
  Fedora packages, user-wide SDK state, host security, or application behavior. Removing and
  redownloading those valid components would add risk and waste, so no cleanup or follow-up is
  required.

### Safety, freeze, and Guided-friction review

- Certificate pinning, exact safety-code comparison, Companion confirmation, separate Desktop
  approval, remembered-session behavior, revocation, and privacy-filtered telemetry are preserved.
- Link still grants no flash, wipe, root, unlock, relock, Recovery, command, or Guardian authority.
- UNKNOWN-on-uncertainty, no blind retry, exact-device evidence, and permanent no-relock are unchanged.
- No additional dialog, confirmation, route, or technical dead end was introduced.
- The feature freeze is preserved: this is a bounded correctness repair to an existing Link flow.

### Acceptance criteria result

- Stale reset/new-attempt/teardown result rejection: **PASS**
- Stale token/preference restoration prevention: **PASS**
- Focused Android unit and security regression: **8/8 PASS**
- Android compile/lint admission: **PASS; zero blocking lint errors**
- Evidence wording: **CORRECTED — 13 total / 12 authenticated**
- Emulator/full-journey/broad-suite repetition: **NOT PERFORMED; NOT REQUIRED**
- Physical, Recovery, signing, publication, release, or relock action: **NONE**

### Approved next bounded task

Linux stops at this clean approved checkpoint. The remaining emulator-versus-physical-USB
classification defect is assigned to the Windows branch as the single owner because that branch now
contains the completed Desktop listener lifecycle correction in the same source subsystem. Linux must
not duplicate it or begin unrelated work merely to stay busy.

Further Linux Stage-1 product work now crosses a creator-controlled gate: controlled physical Android
verification and production Recovery trust/enrollment remain unauthorized. Product Assurance will
assign a Linux task only after a non-overlapping freeze-safe correction appears or Steve explicitly
authorizes the next physical/production boundary.

### Gate status

- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Companion standalone and direct Desktop Link: **VERIFIED**
- Companion stale-result invalidation: **VERIFIED**
- Emulator/physical-USB Desktop classification: **ASSIGNED TO WINDOWS NEXT**
- Windows Device Engine readiness: **listener correction complete; stale OS prompt still requires human dismissal**
- v0.2 Golden Foundation: **CLOSED pending physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: c4bcdfa

- Handoff commit: `c4bcdfa6b46e377c4947b8e5f1a9de52012edd45`
- Product Assurance authorization: `db6fcc14b8fd446ed06e4f31100f17ff0e1b37c8`
- Reviewed implementation: unchanged from `b86aca25e5cf2078fdcae375812e59f0327d89b5`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **CORRECTION REQUIRED — DIRECT PRODUCT LINK VERIFIED; MINIMUM PRESENTATION RACE REPAIR**

### Decision

The direct real Fedora Desktop-to-real Companion product Link milestone is accepted. The unchanged
applications completed the production TLS pairing path through both visible identity decisions,
delivered sustained authenticated telemetry, restored one remembered session, revoked it through the
visible Desktop control, and rejected the old credential after Companion restart. No fixture,
instrumentation hook, private-state injection, physical phone, or execution authority participated.

One observed Companion presentation race requires a minimum correction before Linux advances: after
a visible reset invalidated an in-flight request, that older request's eventual timeout overwrote the
current button copy with `APPROVAL TIMEOUT • TRY AGAIN`. The button still opened the correct safety
dialog and no stale credential or authority was restored, so this is not a pairing or Guardian failure.
It is nevertheless untruthful stale UI state and should be fixed in the existing flow.

Product Assurance also corrects two evidence/wording points without rejecting the milestone:

- The retained Desktop event log contains 13 snapshot observations total. The first is the expected
  unauthenticated waiting state and the following **12 are authenticated**, not 13 authenticated
  observations. Twelve still exceeds the required two.
- The Desktop described the sole API-35 emulator as `USB also connected` and later claimed USB
  read-only evidence remained. Repository inspection shows `DeviceEngine` classifies any ADB serial
  without a colon as `usb`, and `CompanionCenter.set_device_snapshot` sets `_usb_ready` for every
  normal `device` snapshot. This is a real connection-source classification defect, not physical-USB
  evidence. Its Desktop source overlaps the active Windows Companion lifecycle slice, so it is queued
  for one coordinated correction after that Windows checkpoint rather than duplicated now.

### Independent repository and runtime evidence

- Commit `c4bcdfa` changes only `docs/sync/BUILD-STATUS.md`; product source, tests, APK, Desktop
  artifacts, protected original-checkout files, and Windows work are unchanged.
- Product Assurance independently inspected the redacted 17-event Desktop log. Its SHA-256 is
  `082aa7090499f3f7ef565b47f86d24177ec68a8f1ee5814c9a06fb26e3c4fcfe`.
  The order is ready, approved, 13 observations, reconnected, reset; every event reports
  `execution_authority: none`.
- Observation one visibly says it is waiting for an authenticated phone snapshot; observations two
  through thirteen contain authenticated health state. No pairing code, bearer token, private key,
  or raw serial is present in the redacted log.
- Product Assurance independently matched the recorded hashes for the paired Desktop, authenticated
  Desktop snapshot, reconnect, reset, Companion safety dialog, paired screen, Live Console,
  remembered reopen, revoked reopen, and Android error log.
- The actual screens show the same certificate-derived code on both products. Companion's Live
  Console visibly retains `Execution authority: NONE` and `Bootloader relock: NEVER`; after revocation
  it requires a new Link code.
- After the run ADB was empty and no emulator, ROMVERSE process, or port-8765 listener remained.
  SELinux stayed enforcing. No physical target, host-security change, dependency install, Recovery,
  signing, publication, or release action occurred.
- Repository inspection localizes the stale Companion copy to the in-flight polling thread in
  `MainActivity.kt`, which unconditionally writes the timeout label after the request is no longer
  approved. The visible reset can complete while that older thread is still pending.

### Vision, Guided friction, freeze, and safety review

- This proves the existing products can pair directly and sustain their intended read-only health
  channel. It is meaningful operability progress, not another fixture or broad-test checkpoint.
- Both identity decisions remain meaningful. Reset and revocation remain effective despite the stale
  label; no hidden approval, retry, or authority path was observed.
- Guardian-only execution, exact-device attribution, consent separation, UNKNOWN-on-uncertainty,
  no blind retry, independent reassessment/verification, and permanent no-relock remain unchanged.
- The feature freeze is preserved. The required change is a correctness repair to an existing
  asynchronous presentation boundary, not a new feature.

### Required minimum correction

Correct only the existing Companion Link request-generation/presentation lifecycle:

1. Give an in-flight Link request a bounded attempt identity, cancellation state, or equivalent
   existing-state check so a visible reset, a newer request, or Activity teardown makes an older
   request unable to update current UI or pairing preferences.
2. A late approval, rejection, network error, or timeout from an invalidated attempt must be ignored
   for presentation and authorization. Do not turn it into a retry, success, or replacement request.
3. Preserve certificate pinning, exact safety-code comparison, explicit confirmation, remembered
   session behavior, reset/revocation, read-only telemetry, and zero execution authority.
4. Add the smallest deterministic affected test proving reset followed by an older timeout cannot
   overwrite the reset/new-request state. Retain current Link assertions; do not weaken timing or
   safety checks.
5. Correct `docs/sync/BUILD-STATUS.md` to say 13 observations total / 12 authenticated.

Expected scope is the minimum relevant Companion Activity source, its directly affected test, and
the handoff wording. Do not change Desktop Companion source in this Linux task while the Windows
listener lifecycle correction is active. Do not rerun the full Fedora journey, broad Python suite,
or unrelated Android inventory.

### Acceptance criteria

- A deterministic focused test proves a reset/new attempt invalidates the old asynchronous
  presentation result and that no stale approval/token/preferences are restored.
- Directly affected Android compile/static/test gates pass. Rebuild only the affected development APK
  if the test requires it; do not repeatedly rebuild artifacts.
- If a bounded emulator check is necessary, use one emulator, reproduce only reset-versus-late-result,
  and shut it down afterward. Do not repeat the entire direct Link milestone.
- `BUILD-STATUS.md` truthfully records 13 total observations and 12 authenticated observations.
- No Desktop source, Windows branch, physical phone, mutating ADB/Fastboot command, Recovery,
  production trust/signing, firewall policy, publication, release, or relock action occurs.
- Commit and push the exact correction/handoff, then stop for independent Product Assurance review.

### Approved next bounded task

Implement only the minimum Companion stale-result invalidation correction above. This keeps the Linux
track on functioning product behavior while Windows independently finishes its already-active Desktop
listener lifecycle correction. The queued emulator-versus-physical-USB classification defect must not
be started by Linux until Product Assurance has reviewed that Windows checkpoint and assigned one
owner.

### Gate status

- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Companion standalone API-35 runtime: **VERIFIED**
- Contained fixture-backed Companion Link: **VERIFIED**
- Direct Fedora Desktop-to-Companion product Link: **VERIFIED**
- Companion reset-versus-late-result presentation: **MINIMUM CORRECTION REQUIRED**
- Emulator/physical-USB Desktop classification: **QUEUED; SINGLE OWNER AFTER WINDOWS CHECKPOINT**
- Windows optional-listener lifecycle: **SEPARATE ACTIVE CORRECTION**
- v0.2 Golden Foundation: **CLOSED pending remaining Windows, physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: e091a55

- Handoff commit: `e091a555c8ad95d79c4969b6ce77b492d5f7f600`
- Implementation commit: `b86aca25e5cf2078fdcae375812e59f0327d89b5`
- Product Assurance authorization: `a015b2fdd7e7cc2c23cd1ad5f44ed8e8ddcb8f0a`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — CONTAINED COMPANION LINK RUNTIME VERIFIED**

### Decision

The stale instrumentation interaction is corrected without changing the application. The complete
API-35 Companion inventory now passes through the current visible safety-code confirmation, performs
the real ephemeral TLS exchange, observes fresh health state, and reconnects its encrypted remembered
session while retaining zero execution authority.

This closes the contained fixture milestone. It does not claim a physical-phone result or prove that
the two independently runnable ROMVERSE applications can yet pair directly without the fixture. The
next bounded task therefore moves to a real-product integration journey instead of another unit,
packaging, architecture, or broad-regression loop.

### Independent repository and runtime evidence

- The implementation commit changes only
  `companion/app/src/androidTest/kotlin/com/radforge/romverse/companion/MainActivityInstrumentedTest.kt`.
  No production Activity, navigation, transport, Desktop source, dependency, Gradle file, asset, or
  protected original-checkout file changed.
- The test explicitly opens Link, fills the existing endpoint/fingerprint/code fields, proves the old
  checkbox remains disabled and non-clickable, and confirms through the visible accessibility action
  `YES • CODE MATCHES`. It contains no reflection, private hook, preference mutation, or direct-state
  bypass.
- Product Assurance independently read the raw runner log: 12 success status codes, zero failure or
  assumption-skip status, and `OK (12 tests)`. Its SHA-256 is
  `4490e6b7199de0e36c477528823a3083cae4237caba24717bbe269fa2e1a9a45`.
- The fixture log independently shows the exact order `ready → approved → first-health-snapshot →
  complete`, reports `execution_authority: none` at admission and completion, and finishes at
  `OPTIMAL`. Its SHA-256 is
  `9ddcbda1f97f062772239f89cc92a36b9387b7ed21921b8d2701378a95f8072b`.
- Product Assurance independently inspected the captured confirmation frame. It visibly presents the
  exact certificate-derived code, affirmative and decline choices, and the statement that Link grants
  no flash, root, wipe, unlock, relock, or command authority.
- Product Assurance also inspected the captured Live Console and bounded sequence sheet. The UI is
  readable and the sequence shows the unpaired state while the confirmation is present, followed by
  the Link/Console journey. Transient paired/Device-DNA/Ascension pages are supported by passing
  runtime assertions and are not overstated as separately captured frames.
- Product Assurance independently rehashed both artifacts. The unchanged application APK remains
  `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`; the corrected instrumentation
  APK is `5239d6d7efc4b4ce574cc3c9c84cc62783c8e22bfccee306921108711949df5c`.
  ZIP integrity passed; the instrumentation package targets SDK 35, uses the AndroidJUnitRunner, and
  has one Android Debug signer with a verified v2 signature.
- After the bounded run, ADB was empty and no emulator or Link listener remained. SELinux stayed
  enforcing; no package/environment, firewall, host-security, or physical-device change occurred.

### Guided friction and safety review

- One meaningful identity decision is retained; the retired direct-checkbox shortcut is unusable.
- Companion remains a structured, read-only mission view. Pairing and telemetry confer no Recovery or
  command authority.
- Guardian-only execution, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent reassessment/verification, and permanent no-relock remain intact.
- The short-lived listener's LAN bind/discovery behavior is described honestly. This approval is for
  the previously authorized ephemeral, zero-authority emulator run, not a network-isolation claim.
- The feature freeze is preserved: this is a test correction and runtime proof, not a new feature.

### Approved next bounded task

Prove one direct **real Fedora Desktop application ↔ real Companion application** development journey,
using the existing production Link surfaces rather than `companion_link_emulator_fixture.py`:

1. Use the current approved Fedora development source/application and unchanged approved Companion
   debug APK in isolated temporary workspaces. Do not rebuild or rerun broad suites merely for this
   checkpoint.
2. Launch exactly one clean API-35 emulator with no physical Android target present, then launch the
   real Fedora ROMVERSE Desktop application and open their existing ROMVERSE Link screens.
3. Generate the short-lived code in Desktop, enter the exact endpoint/fingerprint/code in Companion,
   compare the same derived safety code on both visible applications, and exercise every existing
   affirmative/decline decision required by the production flow. Do not bypass either UI or inject
   pairing state.
4. Demonstrate a genuine authenticated paired state and at least two fresh bounded health/mission
   snapshots delivered by the real Desktop transport, with the Companion Live Console remaining
   structured/privacy-filtered and `execution_authority: none`.
5. Restart/reopen the presentation only where the existing product supports it and demonstrate that
   remembered-session reconnection neither duplicates the session nor grants authority. Exercise the
   existing reset/revoke control and prove the old credential no longer reconnects.
6. Capture readable evidence from both applications and retain exact hashes/logs while redacting the
   short-lived pairing code. Shut down Desktop, Companion/emulator, listener, and ADB target at the end.

This is an integration/operability milestone, not authorization to implement or redesign Link. If the
unchanged products cannot complete the journey, preserve the smallest reproducible product blocker,
commit only the evidence/handoff, and stop for Product Assurance. Do not edit application source,
weaken pairing, add a fixture/test hook, install dependencies, connect a phone, merge platform
branches, enable Recovery, sign, publish, or release.

### Acceptance criteria

- Both actual development applications visibly complete the existing pairing journey without the
  fixture or private-state injection.
- Desktop and Companion display the same safety code and retain their meaningful approval boundaries.
- Two fresh authenticated snapshots, structured Live Console state, zero execution authority,
  remembered-session reconnection, and explicit revocation are demonstrated truthfully.
- No physical target, mutating ADB/Fastboot command, Recovery execution, relock, blind retry,
  production trust, or release action occurs.
- Update `docs/sync/BUILD-STATUS.md`, commit and push the bounded checkpoint, and stop for independent
  review. A genuine failure stops the run; do not loop or silently change source.

### Gate status

- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Companion standalone API-35 runtime: **VERIFIED**
- Contained fixture-backed Companion Link: **VERIFIED**
- Direct Fedora Desktop-to-Companion product Link: **NEXT BOUNDED MILESTONE**
- Windows runnable development readiness: separate one-test portability correction in progress
- v0.2 Golden Foundation: **CLOSED pending remaining Windows, physical, production, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: 1e0d4fe

- Handoff commit: `1e0d4fec65d9b2affc4174e8b40e5a6865187df3`
- Prior Product Assurance authorization:
  `1bc798bbca7a0f6a88dfa2514a25f130245c3d33`
- Title: `Record contained Link instrumentation failure`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **CORRECTION REQUIRED — STALE TEST INTERACTION; APPLICATION SAFETY FLOW RETAINED**

### Decision

The environment correction worked exactly: clean-worktree ROMVERSE source and the existing verified
dependency environment were separated correctly, the exact emulator and APK admission passed, and
the committed fixture reached a genuine TLS-ready state with `execution_authority: none`.

The remaining failure is independently localized to an outdated instrumentation interaction. The
test still searches for and directly checks a checkbox whose text begins
`I confirmed the Link safety code`. The current application intentionally no longer exposes that
bypass. Its internal confirmation checkbox is disabled and the real user journey requires the
visible `CONFIRM DESKTOP IDENTITY` dialog and affirmative `YES • CODE MATCHES` action.

The application behavior is the safer and authoritative contract. Do not weaken or alter it. The
minimum correction is confined to the existing Link instrumentation test so it navigates through
and asserts the current meaningful safety confirmation before pairing.

### Independent evidence

- Commit `1e0d4fe` changes only `docs/sync/BUILD-STATUS.md`; the worktree is clean and matches the
  remote branch.
- The fixture log hash and runner log hash independently match the handoff:
  `07d6cbdb23d72d8b22e98841a9afcd579e81016ac742eb1d142dfc95b0d19632` and
  `ca19e7914c5ef971c1080697c6f62aa132e513e7e307370fc80d78f1c8fae7bd`.
- The raw runner records 11 success completions, one failure, zero assumption skips, and
  `FAILURES!!!` for 12 tests.
- The one failure is a `NoSuchElementException` inside
  `tlsPinnedLinkCarriesLiveConsoleAndReconnectsAfterRecreation`, before any pairing request.
- The committed test directly searches for the retired checkbox text and sets `isChecked = true`.
- The committed application instead renders `Safety code confirmation is waiting`, keeps the
  checkbox disabled/non-clickable, and exposes a dialog containing the derived safety code, an
  explicit no-device-command explanation, a decline action, and `YES • CODE MATCHES`.
- The three pairing inputs and the Link route remain present; no evidence supports an application
  navigation or TLS defect at this boundary.

### Fixture containment classification

The fixture uses the production local-network transport, which binds a short-lived TLS listener to
all local interfaces and emits the existing discovery broadcast. It is therefore contained by
ephemeral identity, short-lived code, explicit approval, bounded duration, and zero execution
authority—not by a private network namespace or loopback-only bind.

That behavior must be described honestly. It does not require a production transport change in
this correction: no external request was observed, no reusable token existed, the unapproved
fixture accepted no telemetry, and the process/listener closed immediately after failure. The next
run must retain the same brief bounded lifetime, never expose its code externally, and verify no
unexpected request appears before the explicit in-emulator confirmation.

### Required minimum correction

Modify only
`companion/app/src/androidTest/kotlin/com/radforge/romverse/companion/MainActivityInstrumentedTest.kt`
within the clean Linux worktree:

1. In the existing TLS-pinned Link test, explicitly open the existing Link destination before
   interacting with its fields.
2. Populate only the fixture endpoint, certificate fingerprint, and six-digit pairing code.
3. Remove the stale direct-checkbox mutation.
4. Activate the existing `CONNECT WIRELESSLY` action and require the real confirmation dialog.
5. Assert the displayed safety code exactly matches the code derived from the supplied certificate
   fingerprint and assert the dialog retains its read-only/no-command authority explanation.
6. Select `YES • CODE MATCHES` through the visible/accessibility UI surface. Do not use reflection,
   private-field access, test-only application hooks, preference mutation, or another bypass.
7. Confirm the fixture receives no pairing request before that explicit affirmative action.
8. Preserve all existing post-pairing assertions: TLS pin, two fresh health snapshots, encrypted
   remembered-session storage/reconnection, schema-six Live Console, Device DNA, Ascension,
   `Execution authority: NONE`, and permanent bootloader-relock prohibition.

Do not modify `MainActivity.kt`, navigation, production transport, fixture behavior, protocol,
dependencies, Gradle configuration, or any protected original-checkout file. This is a correctness
repair to stale test interaction only, not a feature change.

### Acceptance criteria

- The exact test-source diff is limited to the interaction/assertion changes above.
- The instrumentation APK is rebuilt from the unchanged approved application source; its new hash,
  package/target/runner identities, debug signer and certificate are recorded and independently
  verified. The application APK must remain byte-identical at its approved hash.
- Relevant compile/static gates pass without weakening or removing an assertion.
- One clean API-35 host-GPU runtime uses the same exact-target, SELinux-enforcing, verified Python
  environment, ephemeral fixture, and artifact admission boundaries.
- The complete 12-test suite passes 12/12 with zero failure and zero skip.
- The fixture emits `ready`, then no request before explicit visible confirmation, then `approved`,
  two fresh health snapshots, and `complete`, always with `execution_authority: none`.
- Bounded readable evidence shows the paired Link state and current confirmation path; Live Console,
  Device DNA, and Ascension evidence remain truthful.
- Fixture and emulator are shut down; ADB is empty; no unexpected client or listener remains.

Any failure ends the task without another source change or retry.

### Approved next bounded task

Implement only the minimum test correction above, rebuild only what is required for the debug
instrumentation artifact, and perform its one exact contained integration run. Update
`docs/sync/BUILD-STATUS.md`, commit and push the exact checkpoint on
`linux/stage1-desktop-readiness`, then stop for independent Product Assurance review.

No physical phone, application behavior change, production Recovery, production trust/signing,
platform merge, publication, or release is authorized.

### Gate status

- v0.2 Golden Foundation: **CLOSED pending remaining release gates**
- Fedora runnable build and inert Guided journey: **VERIFIED**
- Companion standalone API-35 emulator runtime: **VERIFIED**
- Contained Desktop/Companion Link integration: **MINIMUM TEST CORRECTION REQUIRED**
- Windows runnable development build: separate correction track in progress
- Physical hardware, production Recovery, signing, publication, and release: not authorized
