# ROMVERSE Product Assurance

## Current authorization — converge verified Linux core into Windows

- Windows base: `35f7baf22874bf842041592e449d05907ee4d93e`
- Verified shared-core source: `c0de9b2ab491120276f640628d159b51ab1dbcb6` on
  `origin/linux/stage1-desktop-readiness`
- Branch: `windows-launcher-authorized-work`
- Status: **AUTHORIZED — CONTROLLED CROSS-PLATFORM CONVERGENCE**

### Reason

Windows is stopped only because the trusted interactive app-control service is unavailable. Waiting
or rebuilding the same `f52dfff` artifact would add no value. The Windows line now has 72 unique
commits and the verified Linux/shared-core line has 98 unique commits after their common base. A
repository-level dry merge identifies only three textual conflicts:
`docs/sync/PRODUCT-ASSURANCE.md`, `tests/test_build_contracts.py` and
`tests/test_desktop_bundle.py`. This is a bounded, necessary integration milestone and does not
depend on interactive UI control or a phone.

### Exact bounded task

Preserve the current untracked
`0001-Preserve-local-build-completion-across-restart.patch` byte-for-byte. Its source change is
already represented by committed Windows history, so do not apply, delete, rewrite, stage or commit
it. Confirm the Windows working tree otherwise contains no user change, fetch the two exact refs and
fast-forward to this verdict. Create a normal non-rebase merge of
`c0de9b2ab491120276f640628d159b51ab1dbcb6` into `windows-launcher-authorized-work`; never reset,
rewrite or force-push either history.

Resolve only the three predicted conflicts. For Product Assurance, retain both platforms' complete
chronological verdicts and place the current Windows convergence authorization at the top. For the
two test files, preserve the semantic union of Linux/shared-core and Windows-specific assertions;
do not choose one side wholesale, weaken a bound, lower an expected count without accounting for
the new cases, or remove a Windows path/identity assertion. If another conflict appears, stop at the
first one and report it rather than improvising a wider rewrite.

Run the directly affected Windows tests first, including build contracts, desktop bundle,
local-device transition, external firmware intake/inspection, build-control UI and Windows launcher
identity/runner coverage. Resolve only genuine integration failures. If that set passes, run one
complete Windows Desktop/Python suite to detect cross-platform regressions introduced by converging
the shared core. Do not loop or rerun a passing group. Run whole-source lint/format verification and
whitespace checks once at the final tree.

If verification passes, commit one merge/integration checkpoint and update
`docs/sync/BUILD-STATUS.md` with the exact parents, conflict resolution, unique test totals and
genuine Windows evidence. Do not build or package yet; that becomes the next Product Assurance
decision because the existing Windows artifact remains valid for its old source but is superseded
for the converged source. Push normally and stop for independent review.

### Boundaries

- This task integrates already reviewed functionality; it adds no new feature or execution route.
- Interactive packaged UI evidence remains outstanding, not failed or fabricated.
- Do not install system-wide dependencies, use guessed-coordinate/keystroke automation, or attempt
  to repair the unavailable app-control service inside ROMVERSE source.
- No phone/emulator, ADB/Fastboot target, Companion/Adaptive change, firmware execution, consent,
  Guardian dispatch, Recovery action, signing, publication, release, destructive Git action or
  bootloader relock.
- Preserve exact-device evidence, Guardian-only authority, consent separation,
  UNKNOWN-on-uncertainty, no blind retry and permanent no-relock.

### Gate status

- Existing Windows artifact at `f52dfff`: **APPROVED FOR ITS RECORDED SOURCE**
- Windows/shared-core convergence: **AUTHORIZED NOW**
- Rebuilt converged artifact: **NOT YET AUTHORIZED**
- Interactive Windows packaged journey: **OUTSTANDING; MUST NOT BLOCK THIS TASK**

## Reviewed checkpoint: f52dfff — refreshed Windows signing/preparation alpha

- Handoff commit: `f52dfff`
- Product Assurance authorization/source: `f75b9f6db9e9aec06df1918495d9153f049fa27a`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — ARTIFACT VERIFIED; INTERACTIVE UI EVIDENCE OUTSTANDING**

### Decision and independent evidence

Exactly one refreshed unsigned Windows `0.2.0-alpha.1` bundle was built from the approved source.
The canonical ZIP passed the recorded safe-tree/CRC checks and contains the expected executable.
Product Assurance independently re-read the Legion files over the established authenticated SSH
channel: the executable is 6,285,439 bytes with SHA-256
`84eb54a8934e982a6660c6f09f5a65517e94934384fc7f4858546404eb7a7194`; the ZIP is 73,469,641
bytes with SHA-256 `bdf144fb716a6193a5d9a910a244c8d9363b66731c43c61dd7827efd3b04cc8a`.
Windows reports the executable as `NotSigned`, which is the required internal-development state.

Packaged startup, clean close and restart passed with a stable disposable-workspace manifest. The
interactive Guided journey is not claimed: the Windows task's trusted app-control RPC service is
not configured, and Build correctly refused to substitute guessed keystrokes or fabricate visual
evidence. This is an environment evidence limitation, not a demonstrated ROMVERSE defect.

### Approved next bounded task

Do not rebuild or repackage. When trusted Windows app control is available, run exactly one bounded
interactive journey against the already verified artifact in a new disposable no-phone workspace:
Guided entry, Command Deck, Platform Tools remediation presentation, one offline Knowledge/Device
DNA lookup, signing/preparation presentation and one clean restart. Commit evidence only if clean;
if a concrete defect appears, apply only its minimum correction with one focused regression and at
most one corrective rebuild.

Until app control becomes available, Windows remains at a clean approved artifact boundary and may
only fetch/read new repository verdicts. Do not replace UI evidence with more test loops. Do not use
a phone/emulator, ADB/Fastboot target, system-wide installation, consent/admission, execution,
Recovery, production signing/trust, publication, release, force-push, Companion/Adaptive/Linux
changes or relock. Preserve the existing untracked patch.

### Gate status

- Refreshed Windows unsigned alpha artifact: **VERIFIED**
- Packaged startup/restart: **VERIFIED**
- Interactive packaged Guided journey: **OUTSTANDING — APP-CONTROL SERVICE UNAVAILABLE**
- Physical execution, production signing/publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 88f0b16 — Windows stable same-file identity

- Handoff commit: `88f0b16`
- Correction commit: `7b79a4b077bf62ae1b2c669b1ed631f18d282696`
- Product Assurance authorization: `c4adb738b5daddcc82dd5388ff8270901f2fa3f2`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — WINDOWS PORTABILITY CORRECTION VERIFIED**

### Decision and evidence

The correction is the exact minimum requested. On Windows only, both same-file helpers compare the
stable descriptor/path fields: device/file identity, inode/file index, size and modification time.
Other platforms retain creation/change time. Fresh content hashes, descriptor-before/after checks,
path containment, no-follow/symlink rejection, expected receipt/path binding, size checks and
replacement detection remain unchanged.

Product Assurance inspected the four-file correction/handoff diff. The five new Windows tests prove
that a ctime-only descriptor/path discrepancy is accepted, file-identity replacement is rejected
even with preserved size/mtime, and same-size byte drift with restored mtime produces a different
fresh hash. Build reran only the 24 formerly failing nodes and the five new nodes: **29/29 passed**.
Ruff and whitespace passed. The earlier 95 passing nodes were not needlessly repeated.

### Approved next bounded task

This is the next normal user-facing Windows artifact milestone. Fast-forward the clean Legion
checkout to this verdict while preserving the existing untracked patch. Build exactly one refreshed
unsigned Windows `0.2.0-alpha.1` internal-development bundle from the approved source. Verify the
exact executable/archive identities, safe archive tree and unsigned classification, then run one
bounded no-phone packaged user journey covering Guided entry, Command Deck, platform-tool status/
remediation presentation, one offline Knowledge/Device DNA lookup, candidate/signing-preparation
state truthfulness, and clean durable restart.

Reuse the already passing source evidence. Do not run a broad suite or repeat the build. If the one
journey exposes a concrete Windows runtime/Guided defect, apply only its minimum freeze-safe fix,
add one focused regression and rebuild at most once. Commit/push the handoff and stop for review.

Do not use a phone/emulator, target ADB/Fastboot, install system-wide, sign, enroll production trust,
create consent/admission, execute, enter Recovery, publish/release, alter the preserved patch or
Companion/Knowledge/Linux work, force-push, unlock, lock or relock.

### Gate status

- Windows signing/preparation source convergence: **VERIFIED**
- Windows same-file identity correction: **VERIFIED**
- Next Windows milestone: **ONE REFRESHED UNSIGNED ALPHA AND PACKAGED USER JOURNEY**
- Physical execution, production signing/trust, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 3bd3d07 — Windows signing/preparation convergence

- Handoff commit: `3bd3d07`
- Synchronized source commits: `fa088e6`, `7efceb0`, `f7340b7`, `6d15156`
- Product Assurance base: `88c8edf2351ab35bc96d70deab1c9ea263d575fe`
- Branch: `windows-launcher-authorized-work`
- Review status: **CORRECTION REQUIRED — WINDOWS SAME-FILE IDENTITY PORTABILITY**

### Decision and repository evidence

The four synchronized platform-neutral changes match the already approved Linux
artifact-verification, signing-ready, durable preparation and final-signed-byte binding work. The
batch is feature-freeze compliant and its two Build-Control regressions pass on Windows. Ruff and
whitespace also pass. No Windows executable rebuild was required or performed.

The decisive short-path Windows run exposed one bounded portability defect rather than a safety
failure: 24 nodes stop on unchanged files because `os.fstat()` and `Path.stat()` can report
different `st_ctime_ns` values for the same Windows file. The affected comparisons are
`candidate_avb._fingerprint()` and Guardian private-staging `_file_identity()`. Device/inode, size
and modification time remain equal, and the existing content hashes remain separately checked.
Every failure is fail-closed; none created signing, target, consent, admission, execution or
Recovery authority.

### Minimum exact correction

On Windows only, compare the stable same-file fields available consistently from descriptor and
path observations: device/file identity, inode/file index, size and modification time. Preserve the
current `st_ctime_ns` comparison on platforms where it is stable. Do not remove fresh content
hashing, descriptor-before/after comparison, path containment, no-follow/symlink rejection,
expected path/receipt binding, size checks, or replacement detection.

Add focused Windows regressions proving all three conditions:

1. the same unchanged file is accepted when only descriptor/path `st_ctime_ns` differs;
2. a path replacement/file-identity change is rejected even if size and mtime are preserved;
3. byte drift is rejected through the existing fresh hash boundary.

Rerun only the 24 previously failing nodes plus the new focused regressions, Ruff and whitespace.
If green, update BUILD-STATUS.md, commit/push and stop for independent review. Do not rerun the 95
passing nodes unless the touched dependency graph requires them, and do not rebuild the executable
until this source correction is approved and included in the next normal user-facing Windows
artifact milestone.

### Safety and gate status

- Cross-platform signing/preparation source synchronization: **ACCEPTED PENDING PORTABILITY FIX**
- Windows unchanged-file identity validation: **CORRECTION REQUIRED**
- Feature freeze and Guardian/Recovery separation: **PRESERVED**
- Exact hashes, UNKNOWN/no-blind-retry and permanent no-relock: **PRESERVE IN CORRECTION**
- Phone, execution, production signing/trust, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 5e4a43f — durable local-build completion synchronization

- Handoff commit: `5e4a43fb`
- Windows synchronization commit: `f5521c4a`
- Approved Linux source: `b77ee3c03aac1746a8e8f18acd370ddcb3094360`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — DURABLE LOCAL-BUILD SOURCE CONVERGED**

### Decision and independent evidence

The Windows two-file source/test patch has the exact stable patch ID of the approved Linux
correction: `664f2435f3ed483e4c029cd9a0891c369e7c70ae`. It truthfully preserves an unsigned local candidate
across reload and routes to artifact verification rather than installation. Build's genuine Windows
focused test, Ruff and whitespace evidence are proportional. Product Assurance independently
inspected the exact diff and reran the focused production-widget regression against the reviewed
source: **1/1 passed**.

The pre-existing untracked patch in the Windows checkout remains user/build-owned and was not
altered, staged or committed. No artifact rebuild, phone, Recovery, signing, publication or release
activity occurred. Guardian-only authority, exact-device evidence, UNKNOWN/no-blind-retry and
permanent no-relock remain unchanged.

### Approved next bounded task

Remain clean until Linux Product Assurance approves the current final-signed-installation-byte
binding checkpoint. Then synchronize, in one Windows source batch, only the approved
platform-neutral artifact-verification, signing-ready presentation, durable preparation and final
signed-byte binding commits that apply cleanly to `windows-launcher-authorized-work`. Preserve all
Windows launcher, ACL, packaging and toolchain corrections; do not copy Linux handoff history or
Adaptive Online Device DNA work.

Run only the focused Windows tests for the synchronized product paths plus Ruff/whitespace. Do not
rebuild the Windows executable merely for source convergence; include the batch in the next normal
user-facing Windows artifact milestone. Do not touch the preserved untracked patch, use a phone,
perform Recovery/installation, sign, publish, release, force-push or relock. Update BUILD-STATUS.md,
commit/push and stop for Product Assurance.

### Gate status

- Windows runnable internal alpha: **VERIFIED AT THE PRIOR APPROVED ARTIFACT**
- Durable local-build source convergence: **VERIFIED**
- Next Windows milestone: **ONE BATCHED SIGNING/PREPARATION SOURCE CONVERGENCE**
- Physical execution, production signing/publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 6cb22cf — Windows Command Deck truthfulness convergence

- Handoff commit: `6cb22cf`
- Windows synchronization commit: `0f64dd3b`
- Approved upstream correction: Linux `64ad510532a18b5e26a6feec46791069aee0e8ec`
- Product Assurance authorization: Linux `292cd09`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — COMMAND DECK SOURCE CONVERGED**

### Decision and evidence

The Windows correction has the exact stable patch ID of the approved Linux source,
`f43ea1fd1e6402522f15a53c941450718ed88e44`. It removes the false pre-device/pre-project claim and
adds only the focused presentation regression. Build's Windows **1/1 passed**, Ruff success and Git
whitespace success are sufficient for this exact two-file synchronization.

No artifact rebuild is required or authorized. Both current internal alpha artifacts retain their
truthfully documented prior subtitle; the corrected neutral text will enter the next normal
cross-platform artifact batch after additional useful product work, avoiding a packaging loop.

### Safety and gate result

- Cross-platform Command Deck source truthfulness: **PASS**
- Feature freeze: **PASS — exact approved presentation correction only**
- Guardian authority, exact-device evidence, UNKNOWN/no-blind-retry and permanent no-relock:
  **UNCHANGED**
- Phone, Recovery, Companion, signing, publication and release activity: **NONE**

### Approved next bounded task

Windows should remain at this clean approved source baseline while the authorized Linux task runs
the single Companion first-run/offline journey. Do not rebuild or retest Windows again until a new
cross-platform source change or user-facing milestone creates material evidence to collect.

## Reviewed checkpoint: 14328a0 — refreshed Windows Guided alpha

- Handoff commit: `14328a0`
- Windows synchronization commit: `74064de`
- Approved upstream implementation: Linux `eaa3d615912a4eefddd44ee3b032562047ddadc3`
- Product Assurance authorization: Linux `b59c3d8`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — WINDOWS GUIDED ALPHA REFRESH VERIFIED**

### Decision and independent evidence

The Windows source patch has the exact stable patch ID of the approved Linux onboarding correction,
`e12aa36177cdccfc2d26942ee0f64bee79880c22`. No Linux handoff history or unrelated source was
merged. Build's focused **5/5 passed**, Ruff success and whitespace success are proportional to this
three-file synchronization.

Product Assurance independently rehashed the refreshed executable and canonical ZIP on the Windows
host. The executable is `6,281,239` bytes with SHA-256
`7ee304d55731fa6ca291f8e9d780246642e37c79c6331ce3ba8ee6718a1532c1` and Authenticode status
`NotSigned`. The ZIP is `72,689,076` bytes with SHA-256
`17eb961d8022d0b0774bb1cc616b9a9746961c0805552d4210430df39069b863`; it contains 262 entries,
162,253,374 expanded bytes, exactly one expected executable and no absolute or parent-traversal
member.

The split first-run evidence is accepted. The refreshed executable remained alive and responsive at
the fresh unapplied onboarding boundary with no ADB/Fastboot on its host path. The packaged
PyInstaller module contains the required internal-alpha, Guided/no-phone and accessible-action text;
the focused production-widget test proves the exact Guided-to-Command-Deck interaction. Because the
SSH-launched process has no interactive desktop automation surface, no unobserved visible-window
claim is made.

### Vision, freeze and safety result

- Windows internal-alpha artifact and corrected onboarding payload: **PASS**
- Guided friction and truthful no-phone prerequisite state: **PASS**
- Feature freeze: **PASS — exact approved platform-neutral correction and one artifact refresh**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification and permanent no-relock: **PRESERVED**
- Phone, Recovery, production signing/trust, publication and release activity: **NONE**

### Approved next bounded task

Do not rebuild or retest the Windows alpha again. Await the matching Fedora refresh review, then use
the two approved artifacts as the cross-platform baseline for the next single user-facing milestone.
Until that handoff is committed, Windows may perform only read-only synchronization checks; it must
not begin physical-device, Recovery, signing, publication or release work.

### Gate status

- Windows v0.2.0-alpha.1 onboarding-corrected development artifact: **VERIFIED**
- Matching Fedora refresh: **IN PROGRESS ON THE AUTHORIZED LINUX BRANCH**
- Cross-platform public release, production trust/signing and physical Recovery: **NOT AUTHORIZED**

## Reviewed checkpoint: 785bb02 — Windows v0.2.0-alpha.1 development build

- Handoff commit: `785bb0208e0f44dbe49b38b64d3d891e5ac8432e`
- Synchronized source commits: `fc11d38`, `3654646`, `ae2c91b`, `dd1572d`
- Windows portability correction: `a5527a04fe4b6183b903b209206b4eab40220f11`
- Product Assurance authorization/base: `018d07cbae87f4afb472ca8abff8ddaf6d636c15`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — WINDOWS v0.2.0-alpha.1 DEVELOPMENT ARTIFACT VERIFIED**

### Decision

The Windows branch now contains the approved durable local-build resume and alpha identity changes,
retains the accepted Windows launcher and pinned Platform Tools work, and produces a coherent
unsigned `0.2.0-alpha.1` development artifact. This completes the intended cross-platform internal
alpha milestone; it does not open signing, publication, production Recovery or physical execution.

The Windows portability correction is accepted. The full digest remains in the final versioned-tool
slot and receipt; shortening only the unpublished random staging directory removes an ordinary
Windows path-limit failure without changing source, hash, isolation or atomic-publication checks.
The focused receipt assertions now use the previously approved owner-only Windows ACL contract
instead of POSIX mode bits.

### Independent repository and artifact evidence

- `fc11d38`, `3654646` and `dd1572d` have stable patch IDs identical to approved Linux commits
  `3475b45`, `dcd73cc` and `9e6762a`. `ae2c91b` contains the approved alpha source/test identity
  while correctly omitting the Fedora-only guide and preserving the existing Windows PyInstaller
  test import.
- `a5527a0` changes only the staging component in `toolchain_versions.py` and portable assertions in
  the directly affected build-contract test. It does not weaken exact tool identity or filesystem
  privacy.
- Final focused Windows result: **48/48 passed**. Ruff and Git whitespace checks passed. No broad
  suite or duplicate Guided journey was run.
- Executable: `6,280,733` bytes, SHA-256
  `bcd30985ca8590e323039ea3e037cbb382d6147b2a63f3e592d5b9233e13aa60`, Authenticode
  `NotSigned` as required.
- ZIP: `72,428,464` bytes, SHA-256
  `11aac7b0425417abda5049d26ebbb1c601649dcd49cf111ab7170751abaf9ccd`; exact safe-tree
  verification passed for 262 files / 162,252,868 expanded bytes.
- One fresh frozen no-device startup smoke passed with no ADB/Fastboot discoverable. No phone,
  emulator or Recovery action was involved.

### Vision, freeze and safety result

- Windows runnable alpha identity and packaging: **PASS**
- Durable resume, Windows ACL privacy and ordinary-path portability: **PASS**
- Feature freeze: **PASS — approved milestone and directly exposed portability correction**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification and permanent no-relock: **PRESERVED**
- Signing, publication, release, phone mutation and production Recovery: **NONE**

### Approved next bounded task

On Linux, synchronize only the platform-neutral product-source hunk from `a5527a0` that shortens the
unpublished versioned-tool staging directory. Do not import the Windows ACL/test adaptations or
Windows branch history. Run the existing focused toolchain-version and local-build contract tests,
lint/whitespace, commit the tiny convergence correction and return for Product Assurance. Do not
rebuild either alpha artifact; their exact committed source identities remain recorded truthfully.

After that no-op-equivalent convergence, Product Assurance will select the next existing user-facing
pre-v1.0 workflow rather than opening packaging/test loops. No phone, Recovery, Companion change,
signing, publication, release, force-push or relock.

### Gate status

- Fedora v0.2.0-alpha.1 internal development build: **VERIFIED**
- Windows v0.2.0-alpha.1 internal development build: **VERIFIED**
- Cross-platform internal alpha milestone: **ACHIEVED**
- Production/public v0.2 release: **NOT CLAIMED OR AUTHORIZED**
- Physical hardware and production Recovery/trust/signing: **OUTSTANDING**

## Authorized synchronization: v0.2.0-alpha.1 consolidated Windows build

- Linux Product Assurance approval: `87af660`
- Approved Linux handoff: `679b0d8`
- Approved source commits, in order: `3475b45`, `dcd73cc`, `07b5b17`, `9e6762a`
- Windows base approval: `06e9dea`
- Branch: `windows-launcher-authorized-work`
- Authorization status: **APPROVED NEXT BOUNDED WINDOWS MILESTONE**

### Exact task

Synchronize only the four approved platform-neutral source/test commits above without copying Linux
handoff/assurance history or merging/rewriting either branch. Retain the accepted Windows launcher,
Platform Tools pin and all Windows-specific correctness work. Run only the focused local-resume,
version-identity and prerelease-parser checks plus lint/whitespace.

Produce exactly one consolidated unsigned Windows `0.2.0-alpha.1` development build and one matching
ZIP. Verify their hashes and exact archive tree, then run one bounded no-phone startup/no-device
smoke. Record the result in the Windows Build handoff, commit and push, and stop for Product
Assurance. Do not repeat the broad suite or Guided journey; do not target a phone/emulator, invoke
device-scoped ADB/Fastboot or Recovery, change Companion, drivers, firewall or global PATH, sign,
publish, release, force-push or relock.

### Gate status

- Fedora v0.2.0-alpha.1 internal development build: **VERIFIED AT `87af660`**
- Windows v0.2.0-alpha.1 consolidated development build: **AUTHORIZED NOW**
- Public release, production trust/signing and physical Recovery: **NOT AUTHORIZED**

## Reviewed checkpoint: 7c52c02 — Windows Guided/Forge synchronization

- Handoff commit: `7c52c02bb6bc2be77ae1d9cfb39d27730f8aaba0`
- Synchronized implementation commits: `ab2c650b6391c4f1f369df712c0d5258452ca5f6`,
  `e73f72dd36f975fd504b2f6b2663cc42e3e8f869`
- Approved upstream commits: `392b21eb90966b09f089ed9b8f3dac29e5fedf8d`,
  `37e2ee27d9373d90e6a3cd71cb31fcadb64f415b`
- Previous Windows approval: `a0740bd0d718d82e1c3c649aee86aec1564652e2`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — PLATFORM-NEUTRAL GUIDED/FORGE CORRECTIONS SYNCHRONIZED**

### Decision

The Windows branch now contains the two already approved platform-neutral correctness fixes without
copying Linux-only handoff history or broadening product scope. The Guided build-stage pause names
Forge Control truthfully, and exact source-derived inputs are refrozen only after successful
preparation and before the worker reports completion. Both patches are byte-independent but
patch-identical to their approved Linux sources.

### Independent repository evidence

- Stable patch ID `f0de2e4427782bafaa91d1b0d62e5a306f56b560d` matches for `ab2c650` and
  `392b21e`; stable patch ID `13bb12c29e7e442ae67f4ccfaf562f5084fb2cac` matches for
  `e73f72d` and `37e2ee2`.
- `ab2c650` changes only `guided_mission.py` and its exact focused UI regression. `e73f72d`
  changes only `build_control.py` and its exact final-tree regression. `7c52c02` changes only the
  Build handoff. Protected Companion files and all launcher, Device Engine, Guardian, Recovery,
  packaging, signing and release source remain untouched.
- Product Assurance inspected the exact diffs and confirmed the build-stage/optional-install label
  distinction and the successful-preparation ordering. The later exact planner verification remains
  present; failure still exits through the existing managed error path.
- Build's Windows focused result: **2/2 passed**. Ruff and Git whitespace checks passed. One bounded
  source-level production-UI affected segment also passed and remained explicitly `SIMULATED` with
  zero physical targets, zero ADB/Fastboot commands and no execution authority.

### Vision, freeze and safety result

- Approved vision and Guided friction: **PASS** — the user is directed to the surface that actually
  owns the blocked build requirement.
- Evidence integrity: **PASS** — the plan binds the final prepared source-derived tree rather than a
  stale pre-preparation snapshot.
- Feature freeze: **PASS** — these are previously approved correctness fixes, not a new feature.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification and permanent no-relock: **PRESERVED**.
- Physical phone, Recovery, production trust/signing, publication and release activity: **NONE**.

### Approved next bounded task

Do not duplicate the Linux track's active local-build interruption/resume journey. Keep this clean
Windows checkpoint ready and monitor the authoritative `linux/stage1-desktop-readiness` branch for
that journey's Product Assurance verdict. When it is approved, synchronize only any resulting
platform-neutral source/test correction onto Windows and run its exact focused Windows acceptance
check. If the Linux checkpoint contains no product source change, do not manufacture a Windows
change or rebuild; record the no-op comparison and return for the next material cross-platform
slice. Do not merge Linux documentation history, run a broad suite, rebuild the executable, target
a phone/emulator, invoke Recovery, change Companion, sign, publish, release, force-push or relock.

### Gate status

- Pinned Windows runnable development build and no-device readiness: **VERIFIED**
- Approved platform-neutral Guided/Forge fixes on Windows: **VERIFIED**
- Linux interruption/restart truthfulness: **ACTIVE INDEPENDENT TRACK; WINDOWS MUST NOT DUPLICATE**
- Next consolidated unsigned Windows artifact: **DEFERRED UNTIL THE NEXT MATERIAL SOURCE MILESTONE**
- v0.2 Golden Foundation: **CLOSED**
- Physical hardware, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 61efda1 — pinned Windows development build readiness

- Handoff commit: `61efda1`
- Approved source checkpoint: `6dbe7ef`
- Platform Tools pin implementation: `1908689733771a97dc1ec6e845adc4f169cb943f`
- Product Assurance authorization: `a561c1f`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — PINNED WINDOWS BUILD READY WITHOUT A DEVICE**

### Decision

The first runnable Windows artifact containing the approved Platform Tools pin is accepted. One
fresh visible setup acquired exactly the approved 37.0.1 archive, activated the workspace-local
ADB/Fastboot pair, reached a truthful ready/no-device Command Deck, and retained that state after one
normal restart. This closes the Windows no-phone toolchain-readiness slice without broadening device
or Recovery authority.

### Independent evidence and acceptance

- `61efda1` changes only the Build handoff. Application source remains the already approved
  `1908689`; protected Companion and unrelated source are untouched.
- Product Assurance independently rehashed the new executable as
  `dded5c0daa92a280349e931e7138cb2d63113ef2f9f94327a6c29fe03010c22b`.
- Independent Windows rehashes match the recorded managed components: ADB
  `b4a6b455702684652cccf7b46258b29e653538904359a58fd4931cf3ef286b3f` and Fastboot
  `b2d9cbff4ce9ae7eb448cfc831bafc867935f50f5be38f8f81057fd7eb3b8d86`.
- The runtime log contains exactly two starts and two clean closes with no recorded fault. The second
  launch reused the verified receipt and did not reopen setup or redownload.
- Exactly one unsigned development build and one affected setup/restart journey: **PASS**
- Approved archive source/size/digest/version and canonical receipt: **PASS**
- Ready/no-device truthfulness with only host-targeted empty discovery: **PASS**
- Phone/emulator/device-scoped operation, Recovery, driver/firewall/global PATH, signing, release,
  destructive action, force-push, or relock: **NONE**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  feature freeze, and permanent no-relock: **PRESERVED**

### Approved next bounded task

Synchronize only the two already Product-Assurance-approved platform-neutral Linux correctness
commits into the Windows branch: `392b21e` (truthful Forge Control pause label) followed by
`37e2ee2` (refreeze exact source-derived inputs before planning). The branch comparison shows these
are the only missing commits affecting the four relevant Guided/Forge source and test files after the
shared base `fdb1692`; do not copy documentation histories or unrelated Linux work.

Integrate without rewriting either branch, resolve only genuine context differences, and run the two
exact focused regressions on Windows plus lint/whitespace. Then run one source-level, no-phone,
production-UI `SIMULATED` affected-segment check proving the Windows Guided label and final-tree plan
behavior. Do not rebuild the executable yet; batch the next artifact build with a later material
Windows milestone. No phone/emulator target, ADB/Fastboot device command, Recovery, Companion change,
driver/firewall/global PATH change, signing, publication, release, force-push, or relock. Update the
Build handoff, commit and push, then stop for Product Assurance.

### Gate status

- Pinned Windows runnable development build and no-device readiness: **VERIFIED**
- Approved platform-neutral Linux Guided/Forge fixes on Windows: **NEXT SYNC SLICE**
- Physical hardware, production Recovery/trust, signing, publication, and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 6dbe7ef — Windows Platform Tools archive pin

- Handoff commit: `6dbe7ef`
- Implementation commit: `1908689733771a97dc1ec6e845adc4f169cb943f`
- Product Assurance authorization: `08826543ace12b621828f86e74877dcdd20e8e0c`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — WINDOWS PLATFORM TOOLS ACQUISITION IS DIGEST-PINNED**

### Decision

The Windows managed acquisition route now binds the official archive to the separately approved
Platform Tools 37.0.1 SHA-256 before ZIP parsing, extraction, receipt publication, or replacement of
a prior package. The verifier independently requires the same digest from retained receipts. A
moving upstream `latest` response can therefore no longer approve itself or silently replace the
reviewed bytes.

The implementation remains within the exact frozen-feature safety correction. Linux acquisition is
unchanged, and the existing verified Windows workspace remains accepted without receipt mutation or
redownload.

### Independent repository and verification evidence

- `1908689` changes only the managed-tool source and two focused test files; `6dbe7ef` changes only
  the Build handoff. Protected Companion, Device Engine, Guardian, Recovery, launcher, and release
  code are untouched.
- Product Assurance inspected the exact download, worker, and receipt-verifier paths and
  independently reran the submitted Windows selection: **36/36 passed**. Ruff passed for all three
  affected files and `git diff --check 0882654..6dbe7ef` passed.
- The exact approved source is bound to SHA-256
  `45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99`.
  Product Assurance independently retrieved the official bytes for the preceding approval and
  confirmed that digest, 8,044,989-byte size, and `Pkg.Revision=37.0.1`.
- Wrong content fails before extraction/publication, removes the partial file, retains the prior
  package, and reports that a reviewed ROMVERSE pin update is required. It does not learn the
  received digest.
- A receipt naming the approved Windows source cannot activate with a different archive digest even
  if its per-file hashes are internally consistent. Existing canonical/legacy path, exact file-set,
  hash, containment, and link/junction gates remain active.

### Safety and acceptance result

- Pre-extraction approved digest enforcement: **PASS**
- Receipt revalidation against the independent pin: **PASS**
- Wrong digest preserves prior package and fails closed: **PASS**
- Windows-only scope; no Linux policy leak: **PASS**
- Existing workspace retained without mutation or download: **PASS**
- Phone/device action, Recovery, signing, release, destructive change, blind retry, relock: **NONE**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, feature freeze, and
  permanent no-relock: **UNCHANGED**

### Approved next bounded task

Produce exactly one new unsigned Windows development build from this approved source so the runnable
artifact contains the archive pin. In one fresh disposable no-phone workspace, exercise only the
existing visible Platform Tools setup once, allowing one official Windows archive acquisition. The
artifact must accept only the approved digest, reach the truthful ready/no-device Command Deck state,
and retain that state after one normal restart. If the upstream bytes changed, capture the clear
fail-closed update-required result and do not change the pin.

Reuse the accepted focused tests and do not run another broad suite or repeat unrelated Guided,
Companion, Recovery, or packaging work. Do not connect, request, or target a phone or emulator; do
not run device-scoped ADB/Fastboot, change drivers/firewall/global PATH, produce an installer/ZIP,
sign, publish, release, force-push, or relock. Record the exact artifact hash and truthful runtime
result in `docs/sync/BUILD-STATUS.md`, commit and push, then stop for Product Assurance.

### Gate status

- Windows managed receipt persistence and pinned Platform Tools source: **VERIFIED**
- Current runnable artifact containing the new pin: **NEXT BOUNDED WINDOWS BUILD**
- Physical hardware, production Recovery/trust, signing, publication, and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 894f588 — Windows managed receipt persistence

- Handoff commit: `894f588d0e488654332e9feb088b943293b44428`
- Implementation commit: `b881d5ac128bc4e6f3d03be1781ec200037ef00a`
- Product Assurance correction: `a556d7da7b4d3525bc5fb1a516cbcdcedaaed799`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — WINDOWS MANAGED RECEIPT PERSISTENCE VERIFIED**

### Decision

The Windows receipt self-invalidation defect is corrected within the exact approved boundary. New
managed-package receipts use canonical forward-slash paths. The compatibility path accepts
backslashes only for the exact official Windows Platform Tools package/source and still applies the
strict schema, bounded receipt, exact file-set, per-component `lstat`, no-link/no-junction,
regular-file, resolved-containment, and exact-hash gates. It does not reinterpret arbitrary Windows
paths as trusted.

The already-downloaded ADB/Fastboot pair was accepted without editing its receipt or downloading it
again. The corrected unsigned development build reached a truthful ready/no-device state and retained
that state after one normal restart. This is a frozen-feature portability correction, not a new
feature or an expansion of execution authority.

### Independent repository and runtime evidence

- `b881d5a` changes only `src/romverse/ui/toolchain_center.py` and
  `tests/test_toolchain_download.py`; `894f588` changes only the Build handoff. Protected Companion,
  Device Engine, Guardian, Recovery, launcher, and release source are untouched.
- Product Assurance inspected the exact parser/verifier path and independently reran the focused
  suite on the Windows host: **31/31 passed**. Ruff passed for both changed files and
  `git diff --check a556d7d..894f588` passed.
- Coverage includes canonical creation, exact legacy Windows activation, idempotent PATH activation,
  drive/root/UNC/empty/dot/traversal/mixed-form rejection, hash tamper, and linked-component
  rejection. Existing archive containment, candidate bounds, schema/source, and exact-file-set
  coverage remains in the same focused file.
- Build evidence records one successful Windows 11 x64 unsigned development build, genuine Command
  Deck readiness before and after restart, exact workspace-local ADB/Fastboot `37.0.1-15733141`, and
  zero phone/device operations.
- Product Assurance independently fetched the declared official Windows archive on 8 September
  2026. It matched the retained receipt exactly: 8,044,989 bytes, SHA-256
  `45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99`, and
  `Pkg.Revision=37.0.1`.

### Safety, freeze, and Guided-friction review

- A failed receipt, unsafe path, link/junction, unexpected file set, or file mutation still produces
  no managed activation. No uncertainty becomes success.
- The user-facing failure was repaired without requiring a second download, global PATH change,
  system installation, or manual receipt surgery.
- No real phone, ADB/Fastboot target command, Recovery action, production adapter/trust, signing,
  release, destructive action, force-push, blind retry, or relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty,
  independent reassessment/verification, feature freeze, and permanent no-relock remain intact.

### Acceptance criteria result

- Canonical deterministic new receipt paths: **PASS**
- Exact legacy Windows receipt recovered through bounded compatibility: **PASS**
- Drive/root/UNC/traversal/link/hash-tamper rejection: **PASS**
- Existing package activated without redownload: **PASS**
- Device Engine ready before and after one restart: **PASS**
- Focused tests/lint/whitespace and genuine Windows evidence: **PASS**

### Retained provenance gate

The current archive URL contains `latest`. The receipt proves exact download-to-install consistency,
and Product Assurance independently reproduced its current bytes, but the downloader does not compare
those bytes with a pre-approved digest before extraction. Therefore this checkpoint proves Windows
development readiness only. It must not be treated as independently pinned tool provenance for a
physical Recovery/execution or public-release claim.

### Approved next bounded task

Add only the missing Windows Platform Tools archive pin to the existing managed acquisition route.
Bind the approved Windows package to SHA-256
`45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99` (Platform Tools 37.0.1),
compare the completed archive before extraction/publication, and require the verifier to match the
same approved digest already present in the receipt. Preserve the current official source, strict
path/file/hash gates, existing legacy receipt, and ready workspace. If Google changes the moving
archive, fail closed with a clear update-required message; do not learn or approve a new digest from
the download itself. Add only focused correct-digest/wrong-digest/preserve-prior-package tests, run
the directly affected Windows tests and lint, and reuse the current build/runtime evidence unless the
source change strictly requires one new unsigned build. No phone, device command, driver/firewall
change, broad suite, duplicate user journey, signing, publication, release, or relock. Commit and
push the exact checkpoint, then stop for Product Assurance.

### Gate status

- Windows runnable build and Device Engine no-device readiness: **VERIFIED FOR DEVELOPMENT**
- Windows managed receipt persistence: **VERIFIED**
- Windows Platform Tools independently pinned acquisition: **NEXT BOUNDED SAFETY CORRECTION**
- Physical hardware, production Recovery/trust, signing, publication, and release: **NOT AUTHORIZED**

## Runtime checkpoint: 6bbb86a — Windows managed-tool restart persistence

- Repository tip under test: `6bbb86a8cad296a88392b808f0a9787c0c661afd`
- Approved Build handoff continued: `bd5dd95f7e1308dff917713f9549f09ef93cf2a4`
- Branch: `windows-launcher-authorized-work`
- Review status: **CORRECTION REQUIRED — WINDOWS RECEIPT SELF-INVALIDATES AFTER INSTALL**

### Decision

Steve cleared the stale Windows Security prompt and exercised the approved frozen `Resolve Platform
Tools` journey. The acquisition itself succeeded: ROMVERSE downloaded the official Windows Platform
Tools package into its workspace, wrote its managed-package receipt, and both `adb.exe` and
`fastboot.exe` start and report Platform Tools `37.0.1-15733141`. No phone was connected or targeted.

The Device Engine nevertheless remains in `ERROR` after closing and reopening the exact workspace.
This is a reproducible product correctness defect, not a user setup failure. On Windows,
`install_managed_archive` records `Path.relative_to(...)` with backslash-separated file names, while
`_contained_receipt_file` rejects every receipt entry containing a backslash. The production
verifier therefore returns no verified directories and activates no managed tools for the receipt
that the same executable just created.

### Independent evidence

- Frozen executable under test:
  `C:\Work\ROMVERSE-Windows\build\windows-dev-frozen\ROMVERSE\ROMVERSE.exe`.
- Exact workspace under test: `C:\Work\ROMVERSE-Link-Lazy-Frozen-20260907`.
- Receipt source:
  `https://dl.google.com/android/repository/platform-tools-latest-windows.zip`.
- Receipt archive SHA-256:
  `45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99`.
- Receipt entries are `platform-tools\\adb.exe` and `platform-tools\\fastboot.exe`; their recorded
  hashes match the installed files.
- Direct read-only execution reports ADB `37.0.1-15733141` and Fastboot
  `37.0.1-15733141` from the workspace-local paths.
- Direct execution of the repository's production receipt/activation functions against that exact
  workspace returns `verified=()` and `activated=()`.
- No global PATH, system package, driver, firewall rule, phone, ADB/Fastboot target operation,
  Recovery action, signing, publication, release, or relock action occurred.

### Minimum exact correction

1. Emit new managed-package receipt file names in one platform-neutral canonical relative form.
2. Preserve the existing containment, regular-file, no-link, exact-hash, schema, and bounded-read
   gates. Do not make backslashes generally trustworthy path syntax.
3. Add a narrowly bounded, fail-closed compatibility path or migration for receipts already emitted
   by ROMVERSE on Windows. It may accept only demonstrably relative Windows path components, must
   reject drive-qualified, rooted, UNC, empty, dot, parent-traversal, linked, and escaping paths, and
   must still verify every declared file hash before activation. The existing verified download must
   not be trusted merely because ROMVERSE previously wrote it.
4. Add focused tests proving canonical new receipts survive Windows-style creation/restart, the exact
   legacy receipt shape is recoverable without redownloading, and traversal/link/hash-tamper cases
   remain rejected.
5. Run only the affected receipt/download/activation tests plus lint and whitespace checks. One new
   unsigned Windows development build is authorized after those checks; do not rebuild the ZIP or
   repeat unrelated suites and journeys.
6. Reuse the existing workspace and already-downloaded package. Confirm Device Engine recognizes the
   exact ADB/Fastboot pair, then close and reopen once to prove persistence. Commit the Build handoff
   and stop for independent review.

This is a frozen-feature correctness correction. It adds no capability, decision, execution route,
or authority and must not weaken Guardian, Recovery, or managed-tool provenance.

### Acceptance criteria

- New receipt paths are platform-neutral and deterministic: **REQUIRED**
- Existing Windows receipt is accepted only through bounded safe normalization/migration: **REQUIRED**
- Drive/root/UNC/traversal/link/hash-tamper rejection remains fail-closed: **REQUIRED**
- Existing package activates without another download: **REQUIRED**
- Device Engine ready state and one restart persistence check: **REQUIRED**
- No phone, global installation, production trust, Recovery, signing, release, or relock: **REQUIRED**

### Approved next bounded task

Perform only the minimum Windows managed-package receipt portability correction above, verify it with
the focused security and persistence tests, make one unsigned development build, and resume the exact
existing workspace without redownloading Platform Tools. Record the truthful ready or newly specific
blocked result in `docs/sync/BUILD-STATUS.md`, commit and push, then stop for Product Assurance.

## Reviewed checkpoint: bd5dd95

- Handoff commit: `bd5dd95`
- Implementation commit: `efeb854e9203ee39f8849a2b7bd2f5ee6a4a7197`
- Product Assurance correction: `47b3262945fb2738e02c98b78d5cfd8ce9e3da59`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — ANDROID CONNECTION-SOURCE TRUTHFULNESS VERIFIED**

### Decision

The fail-closed transport default is corrected exactly. Device Engine now calls a target physical USB
only when the current parsed ADB discovery row contains explicit `usb:` evidence. Standard emulator,
fresh QEMU, and network evidence retain their distinct classifications; a local-looking serial with
none of those signals remains non-authorizing `adb` evidence.

Companion Center already treats every non-`usb` classification as read-only development telemetry,
with no retained USB serial, USB assist, physical-cable copy, or `USB also connected` state. The
original false emulator/USB evidence from the direct Fedora journey can no longer recur through this
boundary.

### Independent repository and verification evidence

- `efeb854` changes one Device Engine helper and the two exact focused test files: 18 additions and
  three deletions. `bd5dd95` changes only the Build handoff. No Companion Android, Link transport,
  Windows launcher, Guardian, Recovery, artifact, packaging, or asset source changed.
- `_adb_transport` now uses explicit discovery `usb` evidence after network, standard-emulator, and
  positive QEMU checks; its only remaining fallback is stable `adb`, not `usb`.
- The physical test fixture now provides `usb:1-2.3`. A new `LOCALADB` case proves that absence of
  USB/emulator/QEMU evidence produces `adb` and an unconfirmed read-only connection note.
- Companion tests include that unconfirmed case before wireless pairing, after pairing, and after
  reset. It never gains `_usb_ready`, `_usb_serial`, USB assist, or physical-USB copy.
- Product Assurance independently reproduced six focused test nodes covering the complete submitted
  cases; all passed. Ruff and whitespace passed. The Build handoff's broader focused selection reports
  10/10 passed and is consistent with the inspected changes.
- The correction required no Windows-native rerun: it is deterministic parsing/presentation logic,
  introduces no Windows API or artifact difference, and the changed source was independently executed
  from the exact pushed worktree. Repeating it solely for platform labeling would add no decisive
  evidence.
- No app, prompt, emulator, network target, cable, phone, ADB/Fastboot command, artifact, Recovery,
  signing, publication, release, or relock action occurred.

### Safety, freeze, and Guided-friction review

- Absence of evidence now remains unconfirmed instead of becoming a cable claim or capability.
- Genuine explicit USB behavior remains available; virtual and network development remain useful and
  read-only.
- Guardian-only authority, exact-device evidence, consent separation, durable UNKNOWN, no blind
  retry, same-incident reassessment/verification, and permanent no-relock remain intact.
- No new user decision, route, retry, or feature was introduced. The feature freeze is preserved.

### Acceptance criteria result

- Explicit `usb:` evidence is required for physical USB: **PASS**
- Unproven local ADB is stable, unconfirmed, and non-authorizing: **PASS**
- Unproven local ADB cannot enable or claim USB assist: **PASS**
- Emulator, QEMU, network, explicit USB, and disconnect behavior retained: **PASS**
- Focused tests/lint/whitespace: **PASS**
- Duplicate build, journey, broad suite, or hardware execution: **NONE**

### Approved next bounded task

Resume the already-approved real Windows Device Engine/toolchain readiness journey only after Steve
manually chooses **Cancel** on the stale pre-correction Windows Security prompt. Reuse the corrected
frozen executable and existing fresh readiness workspace; do not rebuild again. Exercise only the
existing `Resolve Platform Tools` flow, accepting only its declared workspace-local, pinned,
integrity-checked tool acquisition. Capture the truthful ready or specific actionable blocked result
and restart persistence, then commit the handoff and stop for review.

Until the human prompt dismissal occurs, Windows must remain idle at this clean checkpoint. Linux is
also clean at its current approved gate; its remaining Stage-1 work requires separate explicit
physical-device or production-trust authorization. Do not manufacture another test/source loop merely
to keep either task busy.

### Gate status

- Fedora runnable build, inert Guided journey, and direct Companion Link: **VERIFIED**
- Companion stale-result invalidation: **VERIFIED**
- Windows runnable build, inert Guided journey, and intent-bound optional Link: **VERIFIED**
- Android connection-source truthfulness: **VERIFIED**
- Windows Device Engine/toolchain readiness: **WAITING FOR STEVE TO CANCEL STALE OS PROMPT**
- v0.2 Golden Foundation: **CLOSED pending physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: f23ac64

- Handoff commit: `f23ac64`
- Implementation commit: `e685eee873c170821f876c049d14625961c9bf40`
- Product Assurance authorization: `a27b1858f53fe41a81e50354b88703561cf6a825`
- Branch: `windows-launcher-authorized-work`
- Review status: **CORRECTION REQUIRED — UNPROVEN LOCAL ADB STILL DEFAULTS TO PHYSICAL USB**

### Decision

The correction successfully separates standard `emulator-*`, confirmed QEMU, network ADB, and
explicit `usb:` discovery evidence throughout Device Engine and Companion Center. Virtual/network
targets no longer enable USB assist or display physical-cable claims, and genuine explicit USB
evidence preserves the existing route.

One remaining default prevents approval: `_adb_transport` still returns `usb` for every local-looking
ADB serial that is not network and does not expose emulator/QEMU evidence—even when the discovery row
contains no `usb:` evidence. The implementation test reinforces that assumption by expecting the
original `SERIAL123` fixture, whose row has no `usb:` field, to be physical USB.

A serial shape and absence of emulator evidence do not prove a cable. This can still recreate the
exact false `Physical USB`, USB-assist, and `USB also connected` claims for a nonstandard local
virtual/forwarded transport. The required adjustment is small and stays within the approved source
boundary: unproven local ADB must remain explicitly unconfirmed, while an observed `usb:` field keeps
the physical route unchanged.

### Independent evidence

- `e685eee` changes only Device Engine, Companion Center, and their two focused test files;
  `f23ac64` changes only the Build handoff. Companion Android, Windows launcher, Link protocol,
  Guardian, Recovery, artifacts, and protected files are untouched.
- `_adb_transport` correctly prioritizes network serials, standard emulator serials, and positive
  QEMU properties, but its final unconditional `return "usb"` converts absence of evidence into a
  physical claim.
- `parse_adb_devices` retains the discovery row's `usb` field. The new explicit-USB fixture already
  supplies `usb:1-2.3`, so the product has a direct evidence signal available without new probing.
- Companion Center's `_usb_ready` and USB-assist boundary are correctly restricted to
  `device.transport == "usb"`; correcting Device Engine's last default therefore closes the path
  without redesigning the UI.
- Product Assurance independently reproduced six focused test nodes covering physical, emulator,
  QEMU, network, fail-closed UI, and disconnect cases; all passed. Ruff and whitespace passed. This
  confirms the submitted behavior while also showing the missing no-USB/no-QEMU case is not tested.
- No Windows app, prompt, emulator, network target, cable, phone, ADB/Fastboot command, artifact,
  Recovery, signing, publication, release, or relock action participated.

### Required minimum correction

1. In `_adb_transport`, return physical `usb` only when current ADB discovery contains a non-empty
   `usb` field. Retain network precedence, `emulator-*`, and positive QEMU/virtual-device evidence.
2. A local-looking serial with neither explicit USB nor emulator evidence must return one stable
   non-authorizing value such as `adb` or `unknown`, never `usb`.
3. Companion Center must present that value as an unconfirmed ADB transport, retain read-only
   telemetry, keep `_usb_ready` false, retain no USB serial, disable USB assist, and make no cable or
   physical-USB claim before or after wireless pairing/reset.
4. Update the original Device Engine fixture to include explicit `usb:` evidence if that case is
   intended to prove physical USB. Add one focused no-USB/no-QEMU case proving fail-closed unknown
   classification and Companion presentation.
5. Retain current emulator, QEMU, network, explicit-USB, multiple, unauthorized, offline, Link,
   Guardian, Recovery, UNKNOWN, no-retry, and no-relock behavior.

Run only the directly affected focused tests and lint. Do not run a broad suite, start an app or
target, rebuild artifacts, interact with the stale Windows Security prompt, or modify any other
subsystem. Commit and push the exact correction/handoff, then stop for independent review.

### Acceptance criteria

- Explicit discovery `usb:` evidence maps to `usb`; unproven local ADB does not.
- Unproven local ADB never enables or describes physical USB/USB assist.
- Existing standard emulator, QEMU, network, and explicit USB focused cases remain passing.
- No duplicate journey, build, broad regression, platform interaction, or hardware operation occurs.

### Approved next bounded task

Implement only the evidence-default correction above. The temporarily assigned local Build worker
remains the single owner; Linux application/Companion work stays untouched.

### Gate status

- Windows intent-bound optional listener: **VERIFIED**
- Emulator/network versus physical USB: **PARTIAL; ONE FAIL-CLOSED DEFAULT CORRECTION REQUIRED**
- Windows Device Engine readiness: **PAUSED FOR HUMAN CANCEL OF STALE OS PROMPT**
- v0.2 Golden Foundation: **CLOSED pending physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: ddd9714

- Handoff commit: `ddd9714402f59a4a521aa725d535c173e4b5ad3d`
- Implementation commit: `c0b140bbebe7b8fd107819c911703ac9a07e2954`
- Product Assurance authorization: `b0ba30681623e0fc97617f607fbb24dfa7d3cf73`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — COMPANION LINK LISTENER IS INTENT-BOUND**

### Decision

The optional Companion Link no longer binds, listens, or advertises during a fresh unpaired Windows
startup. One existing explicit pairing action starts the endpoint once; a valid remembered session
may resume it; failure remains bounded and unavailable. The corrected source and rebuilt frozen
application reached Command Deck with zero TCP listeners and zero UDP endpoints before Link intent.

The still-visible Windows Security notification is the original pre-correction `PickerHost.exe`
instance, not a new prompt created by either corrected launch. Product Assurance cannot automate or
dismiss an operating-system security decision. Steve should choose **Cancel** when present so the
Device Engine readiness journey can resume without granting unnecessary inbound access.

That stale prompt does not block the next source-only correctness task. To prevent duplicate platform
work, this Windows branch is now the single owner of the already-recorded emulator-versus-physical-USB
classification defect in the same Desktop subsystem.

### Independent repository and verification evidence

- `c0b140b` changes only Companion transport/center source and their directly affected tests;
  `ddd9714` changes only the Build handoff. Companion Android source and protected files are untouched.
- `CompanionTransport` now creates its TLS identity without constructing a server. Its locked
  `start()` performs one bounded bind/TLS/thread transition, reuses an existing live endpoint, and
  records a terminal unavailable result after failure rather than looping.
- `CompanionCenter` resumes only a valid approved session. Fresh/unpaired construction keeps Generate
  available and the endpoint idle; explicit generation starts Link before producing a pairing code.
- Windows Build reports 21 focused tests passed with one pre-existing layout test deliberately outside
  this lifecycle slice; Ruff and whitespace checks passed.
- Product Assurance independently reproduced the exact selected transport/center group on Fedora
  against the pushed source: **21 passed, 1 deselected**, followed by a clean Ruff result. The initial
  reproduction accidentally resolved an older editable install; it was discarded and rerun with the
  current worktree explicitly first on the import path. Only the current-source result is accepted.
- Source and the once-rebuilt frozen application each owned zero inbound TCP and zero UDP endpoints
  before Link intent. The frozen executable is unsigned development evidence at SHA-256
  `0d54ed4588c6337a7bee194ee9b3541593fe3e8ab9222f35489d339a5eae6cc9`.
- The retained stale prompt process predates both corrected launches by hours; no new prompt process
  appeared. No firewall rule, Allow/Cancel choice, global PATH, system package, phone, device command,
  Recovery, signing, publication, release, or relock action occurred.

### Safety, freeze, and Guided-friction review

- Optional Link no longer interrupts an unrelated offline Device Engine journey at application start.
- TLS identity, exact safety-code comparison, separate approval, read-only telemetry, revocation,
  shutdown, privacy filtering, and `execution_authority: none` remain intact.
- One terminal start failure is explained in the existing UI and is not retried automatically.
- Guardian-only execution, exact-device evidence, UNKNOWN-on-uncertainty, no blind retry, and the
  permanent no-relock rule are unchanged.
- This is a lifecycle correctness repair within the existing Link feature and preserves the freeze.

### Acceptance criteria result

- Fresh unpaired construction owns no listener/discovery endpoint: **PASS**
- Explicit intent starts one endpoint; repeated intent does not duplicate it: **PASS**
- Bounded fail-closed start and clean shutdown: **PASS**
- Valid remembered-session resume: **PASS**
- Windows focused verification: **21 PASS / 1 unrelated deselected**
- Independent Fedora reproduction: **21 PASS / 1 unrelated deselected**
- Fresh corrected source/frozen startup without a new firewall prompt: **PASS**
- Device Engine readiness completion: **WAITING FOR HUMAN DISMISSAL OF STALE OS PROMPT**

### Approved next bounded task

Correct only the Desktop's existing connection-source truthfulness on
`windows-launcher-authorized-work`; do not interact with the stale Windows Security prompt:

1. Classify a local Android emulator distinctly from physical USB using current ADB discovery and
   read-only device evidence. Treat `emulator-*`/confirmed QEMU evidence conservatively as virtual;
   never promote it to physical USB evidence. Preserve network ADB as non-USB.
2. In Companion Center, set physical-USB readiness and enable USB-assisted pairing only for a normal
   Android target whose observed transport is genuinely `usb`.
3. An emulator or network ADB snapshot may still provide read-only development telemetry, but it must
   never render `USB connected`, `USB also connected`, `USB read-only evidence remains available`, or
   another physical-cable claim.
4. Preserve the current genuine physical-USB path, multiple/unauthorized/offline fail-closed states,
   wireless Link behavior, and all Guardian/Recovery boundaries.
5. Add only focused Device Engine and Companion Center tests covering emulator, network ADB, and
   physical USB. Run the smallest affected tests and lint. Do not rebuild the executable/ZIP, rerun
   the Guided or Link journeys, or launch the app while the stale OS prompt remains.

Commit and push the exact source/test/handoff checkpoint, then stop for independent review. Linux is
explicitly not authorized to duplicate this correction.

### Gate status

- Fedora runnable build and direct Companion Link: **VERIFIED**
- Windows runnable development build and inert Guided journey: **VERIFIED**
- Optional Link listener lifecycle: **VERIFIED**
- Emulator/physical-USB classification: **WINDOWS NEXT BOUNDED CORRECTION**
- Windows Device Engine/toolchain readiness: **PAUSED FOR HUMAN CANCEL OF STALE OS PROMPT**
- v0.2 Golden Foundation: **CLOSED pending physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: f8413bf

- Handoff commit: `f8413bfe465e8bfd33d62a0a6cd92d3aa6572167`
- Evidence commit: `ae13356696915189ad73e9b3cd9bfdfcefa11b3b`
- Product Assurance authorization: `f5a06a7664c67c35d14a20286c1acc9ee1b6ba2e`
- Branch: `windows-launcher-authorized-work`
- Review status: **CORRECTION REQUIRED — OPTIONAL LINK LISTENER BLOCKS UNRELATED WINDOWS STARTUP**

### Decision

Build stopped at the correct boundary. The real frozen application starts with a truthful missing-
Platform-Tools state, but a Windows Security firewall dialog for inbound `ROMVERSE.exe` networking
appears before the user can select `Resolve Platform Tools`. Automating that operating-system security
decision or silently changing firewall policy is not acceptable.

Repository inspection identifies the product cause: every `CompanionCenter` construction immediately
constructs, binds, listens on, and starts the wireless `CompanionTransport` plus LAN discovery even in
a fresh workspace with no remembered Companion session and before the user opens or requests Link.
ROMVERSE Link is optional. It must not open an inbound network surface—or trigger a system permission
prompt—while the user is pursuing an unrelated offline Device Engine action.

This is a minimum Guided-friction and least-authority lifecycle correction within the existing Link
feature, not a new feature and not a request to weaken Windows security.

### Independent evidence

- `ae13356` contains only the blocker screenshot; `f8413bf` contains only the Build handoff. The
  application, frozen artifact, tests, host policy, and protected Companion files are unchanged.
- Product Assurance independently verified the screenshot hash
  `85a2e6fcfde4f4c0742eb8aaa795cbe2d05cec7d996ea2114e262d05f60b3e7e` and visually confirmed the
  real Command Deck's `Device Engine needs attention` / `Resolve Platform Tools` state beneath the
  modal Windows Security prompt.
- The fresh isolated workspace had no Android tool bytes or receipts; host PATH contained neither
  `adb` nor `fastboot`. No tool acquisition began, so no false readiness claim exists.
- Source inspection confirms `CompanionCenter.__init__` unconditionally calls
  `self.transport.start()`. `CompanionTransport` has already created and activated an
  `0.0.0.0` HTTP server socket during construction, and `start()` launches both the HTTPS serving
  thread and broadcast discovery thread.
- The product was closed, no ROMVERSE process remained, and no firewall choice, global PATH change,
  download, driver, phone, ADB/Fastboot device command, or Recovery action occurred.

### Required minimum correction

Correct only the existing Desktop Companion-Link network lifecycle:

1. In a fresh workspace with no remembered approved session, constructing/opening ROMVERSE must not
   bind or listen on an inbound Companion socket, start LAN discovery, or request firewall access.
2. Start the existing Link endpoint only after the user invokes an existing pairing action such as
   `Generate wireless code` or an eligible USB-pairing action. The UI must remain able to present that
   action before a socket is opened and must surface a bounded unavailable result if startup fails.
3. Preserve legitimate remembered-session reconnection. A previously explicit, still-valid approved
   Link may resume according to the existing contract; fresh/unpaired startup may not manufacture that
   authorization.
4. Preserve TLS identity, short-lived code, exact safety-code comparison, Desktop approval,
   read-only telemetry, revocation/reset, shutdown, fixed bounded listener behavior, privacy filtering,
   and `execution_authority: none`.
5. Add/update only directly affected lifecycle tests proving no fresh-start listener/discovery, one
   explicit start on pairing intent, fail-closed startup error, remembered-session behavior, and clean
   shutdown. Do not redesign Link or Device Engine.

Expected scope is the minimum relevant Desktop Companion transport/center source and its focused
tests, plus required build/handoff evidence. Do not alter Windows Firewall, add an exemption, suppress
the system prompt, use a different port as a workaround, disable TLS, change Companion Android source,
or touch Guardian/Recovery authority.

### Acceptance criteria

- A focused deterministic test proves a fresh unpaired `CompanionCenter` owns no listening socket or
  discovery thread until an existing explicit pairing action is invoked.
- The directly affected Companion transport/center tests pass on Windows and Linux; no broad suite is
  required.
- One Windows source launch in a fresh isolated workspace reaches the visible Command Deck and
  `Resolve Platform Tools` without an unsolicited firewall dialog or Companion listener.
- Rebuild the unsigned frozen development executable once from the corrected source, then repeat that
  same fresh-workspace startup. Do not rebuild/repackage repeatedly and do not rerun the inert Guided
  journey.
- Resume the already approved real Device Engine/toolchain readiness journey in that corrected frozen
  application. If a new genuine product blocker appears, preserve it and stop; do not loop or broaden
  the change.
- No firewall/security policy change, system-wide install, global PATH mutation, phone, driver,
  ADB/Fastboot device operation, Recovery execution, relock, production signing, publication, or
  release occurs.
- Update `docs/sync/BUILD-STATUS.md`, commit and push the exact correction/result, and stop for
  independent review.

### Approved next bounded task

Implement only the lazy, intent-bound Companion listener lifecycle correction above and use the
single corrected frozen build to continue the interrupted Windows Device Engine readiness journey.
Testing is acceptance evidence for that product outcome, not a new test campaign.

### Gate status

- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Windows runnable development build and inert Guided journey: **VERIFIED**
- Windows Device Engine/toolchain operability: **BLOCKED BY MINIMUM OPTIONAL-NETWORK LIFECYCLE DEFECT**
- Windows Firewall/security change: **NOT AUTHORIZED OR REQUIRED**
- Companion Android source: separate Linux integration track; unchanged here
- v0.2 Golden Foundation: **CLOSED pending physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: 7642cad

- Handoff commit: `7642cad98d2501588d9b6829b132c01c1f8798b7`
- Test correction: `7353b0df797f37354864ace65b889e488c7a9b56`
- Product Assurance authorization: `8a4461d21be1a9a7d45cf4420b132a0b3dd90cf7`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — WINDOWS DEVELOPMENT READINESS VERIFIED**

### Decision

The final portability defect is corrected exactly as authorized. The raw unsafe ZIP member remains
constructed and asserted through `ZipInfo.orig_filename`, and the cross-platform production boundary
still rejects it. Only the irrelevant host-specific `ZipInfo.filename` expectation was removed.

Combined with the previously verified native trusted launcher, readable frozen UI, private Windows
ACLs, exact development archive, source/frozen startup, and inert Guided journey, this closes the
Windows unsigned development-readiness gate. It does not authorize production signing, release,
physical Android operation, or Recovery execution.

### Independent evidence

- `7353b0d` deletes exactly one assertion from
  `tests/test_source_installation.py`; `7642cad` changes only the Build handoff. Production source,
  accepted-path validation, application, launcher, ACLs, artifacts, and protected Companion files
  are unchanged.
- Windows Build ran the corrected regression (**1 passed**) and the directly affected complete source-
  installation file (**32/32 passed**); its worktree and remote matched at the handoff.
- Product Assurance independently ran the exact previously failing Linux-focused group at the pushed
  checkpoint: **81 passed, 2 Windows-host skips, 0 failures**. The unsafe raw backslash member is
  still rejected on Linux without conditionalizing or skipping its safety contract.
- Previously accepted evidence remains applicable because no product or artifact byte changed:
  - native exact Windows launcher identity: **100/100 fresh processes** and focused launcher pass;
  - frozen visible window: readable, no square glyphs;
  - owner/SYSTEM-only private-file ACL contract;
  - unsigned development ZIP SHA-256
    `747d5b40dbc76f5fab3e777f40bbd3d586bcfb72eaeccadd6647df57996af239`;
  - source and frozen startup smoke;
  - simulation-only full Guided
    `Scan → Match → Prepare → Consent → Result → Reassessment → Verification` journey with no phone,
    wipe, relock, retry, or physical command.

### Vision, freeze, and safety review

- The correction is test-only and removes no safety assertion that belongs to the product contract.
- Guardian-only authority, exact-device evidence, one meaningful consent, durable UNKNOWN, no blind
  retry, independent reassessment/verification, and permanent no-relock remain preserved.
- Guided friction is unchanged; no extra user decision or technical dead end was introduced.
- The pre-v1.0 feature freeze is preserved. The artifact remains an unsigned local development build,
  not a release candidate or production package.

### Approved next bounded task

Prove the real Windows application's existing **Device Engine / toolchain readiness** journey on the
Legion host, so the runnable UI advances from its current “needs attention” state to a truthful usable
development state without a phone:

1. Use the already verified frozen Windows development application and a fresh isolated workspace.
   Do not rebuild the executable or ZIP and do not rerun the Guided journey or broad regression.
2. Open the existing Device Engine/Forge Arsenal readiness surface and record the actual missing,
   detected, or conflicting Android tool state before any action.
3. Exercise only existing product behavior. If tools are already available, verify their exact paths,
   versions, integrity/provenance receipts, and restart persistence. If the product's existing pinned,
   integrity-checked, workspace-local acquisition flow is required, it may obtain only those declared
   development tools into its isolated workspace. Do not perform an unverified/manual download.
4. Demonstrate that the real frozen UI reaches a truthful ready—or specific actionable blocked—state
   for its existing Android development toolchain and that reopening the app preserves the evidence.
5. Capture readable before/after Windows evidence and the exact local receipts. Keep all claims scoped:
   no connected-device, USB-driver, Fastboot communication, or physical-hardware verification claim
   is permitted without a phone.

This is a real Windows operability milestone, not authorization to implement a new tool manager. Do
not edit application source, install system-wide software or drivers, change global PATH/security,
connect or operate a phone, enable Recovery, sign, publish, or release. If the unchanged product cannot
complete its own existing readiness journey, commit the smallest reproducible blocker and handoff,
then stop for Product Assurance rather than modifying code or looping tests.

### Acceptance criteria

- The real frozen Windows application visibly and truthfully completes its existing host-toolchain
  readiness journey, or preserves one precise product blocker for review.
- Any acquired bytes are declared by the existing product manifest, integrity verified, and confined
  to the isolated ROMVERSE workspace; no broad host mutation occurs.
- Restarted UI state agrees with exact executable/version/provenance receipts.
- No phone, driver installation, ADB/Fastboot device operation, Recovery execution, relock, blind
  retry, production signing, publication, or release occurs.
- Update `docs/sync/BUILD-STATUS.md`, commit and push the bounded checkpoint, and stop for independent
  review. Do not substitute more tests for the actual visible product journey.

### Gate status

- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Windows unsigned frozen build and inert Guided journey: **VERIFIED**
- Windows native launcher, archive, visible UI, and private ACL readiness: **VERIFIED**
- Windows Device Engine/toolchain operability: **NEXT BOUNDED MILESTONE**
- Companion API-35 and fixture-backed Link runtime: **VERIFIED on Linux track**
- v0.2 Golden Foundation: **CLOSED pending physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: 20e0c33

- Handoff commit: `20e0c3312ef5d995694f66119295007d1f8d2dac`
- Correction implementation: `0e2f895dfcb3507fdbda5c1a3f74096361aedf3d`
- Previous Product Assurance correction: `a924b2067b83d797be3742b3bdb81f02ac06a045`
- Branch: `windows-launcher-authorized-work`
- Review status: **CORRECTION REQUIRED — WINDOWS READINESS FUNCTIONALLY VERIFIED; ONE CROSS-PLATFORM TEST ASSERTION REMAINS**

### Decision

The four requested Windows readiness corrections are materially complete and independently verified.
The real Windows launcher is stable across 100 fresh processes, the visible frozen application is
readable, the private project artifacts have a Windows-native owner/SYSTEM-only ACL, and the source
parser rejects a ZIP member whose raw name contains a literal backslash.

Approval is held only because the new ZIP regression contains one Windows-specific expectation about
Python's normalized `ZipInfo.filename`. On Linux, `ZipInfo.orig_filename` and `ZipInfo.filename` both
retain the literal backslash; the production parser still correctly rejects the raw unsafe member.
This is a test portability defect, not an application defect. The exact minimum correction below does
not authorize any product-source, artifact, UI, launcher, packaging, or journey change.

### Repository and independent evidence

- `0e2f895` changes only the approved launcher, private-file, ZIP-validation, test, and visible-evidence
  surfaces; `20e0c33` changes only `docs/sync/BUILD-STATUS.md`.
- The Windows worktree was clean at the handoff and the protected Companion files were unchanged.
- Product Assurance independently ran the decisive Windows launcher/project/source cases:
  **24/24 passed**.
- Product Assurance independently repeated the exact handle/path test in 100 fresh Windows pytest
  processes: **100/100 passed**, with no failure.
- Native identity now compares volume serial, 64-bit file index, link count, size, last-write FILETIME,
  and creation FILETIME for both handles. Reparse rejection, single-link enforcement, the pinned
  write/delete-denying handle, one attempt, and fail-closed dispatch remain intact.
- The committed 1456x939 visible frozen-window evidence is readable and contains no square glyphs.
  Its SHA-256 is
  `346cbdbd3510ab812fbb203eb66457ca2f4db4053bc1ae7576aa64cb166c12f8`.
- The four private Windows artifacts are tested against exactly two non-inherited Full Control ACEs:
  Owner Rights and Local System. Existing POSIX `0600` behavior remains present.
- Product Assurance independently verified the rebuilt unsigned development ZIP on Windows:
  SHA-256 `747d5b40dbc76f5fab3e777f40bbd3d586bcfb72eaeccadd6647df57996af239`.
- The persisted inert-journey report remains simulation-only, records 53 actions/50 inert writes,
  preserves decline-before-acceptance and separate boot verification, and records no physical command,
  wipe, relock, or retry.
- Product Assurance independently ran the focused project/source/launcher suite on Linux:
  **80 passed, 2 skipped, 1 failed**. The only failure is the host-specific assertion that
  `ZipInfo.filename` must equal `windows/boot.img`; Linux correctly returns the raw
  `windows\\boot.img`. The subsequent `ProjectError` rejection remains the intended contract.

### Required minimum correction

Modify only
`tests/test_source_installation.py::test_literal_backslash_archive_path_is_rejected_before_windows_normalization`:

- Keep the unconditional assertion that `member.orig_filename == r"windows\boot.img"`.
- Make the `member.filename` expectation accurately reflect host behavior: normalized forward slash
  on Windows and retained literal backslash on non-Windows hosts, or remove that secondary assertion
  where normalization is not part of the safety contract.
- Keep the cross-platform call to `SourceInstallationService.prepare` and its required `ProjectError`
  path rejection.
- Do not change production source, the fixture's raw unsafe name, accepted-path validation, the
  Windows launcher, ACL implementation, application, artifact, or documentation outside the handoff.

### Acceptance criteria

- The corrected single ZIP regression passes on Windows and Linux while still proving the raw literal
  backslash is rejected.
- The same focused Linux suite completes with **81 passed, 2 skipped** and no failure.
- The directly affected Windows source-installation test file passes.
- No frozen rebuild, ZIP rebuild, visible launch, inert Guided journey, broad regression, dependency
  change, or physical-device action is required because product code and accepted artifacts are
  unchanged.
- Commit the single test correction and updated `docs/sync/BUILD-STATUS.md`, push the branch, and stop
  for Product Assurance review.

### Approved next bounded task

Apply only the portable ZIP-test assertion correction above. After it passes on both hosts, Product
Assurance may close Windows development readiness without repeating already-valid build, visual,
launcher, ACL, archive, or journey evidence.

### Gate status

- v0.2 Golden Foundation: **CLOSED**
- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Windows unsigned frozen artifact and inert Guided journey: **VERIFIED**
- Windows completed development-readiness gate: **HELD ONLY FOR ONE TEST-PORTABILITY CORRECTION**
- Guardian/exact-device/UNKNOWN/no-blind-retry/no-relock invariants: preserved
- Physical Android/Recovery verification: outstanding; not authorized here
- Pre-v1.0 feature freeze: preserved
- Production signing, publication, and release: not authorized

## Reviewed checkpoint: 824d6e7

- Handoff commit: `824d6e7b3f59e16d9d2bffe3e6f1049ddc55470b`
- Runnable-build correction: `2b121c1540be0cd6b000075913cd753018936fdc`
- Portability audit: `a20402e110a181c1bf2c6bf138a2e1e69c9ba573`
- Approved baseline: `1d679d5b2f78bd153cd2d349047bd5a3217c116b`
- Branch: `windows-launcher-authorized-work`
- Review status: **CORRECTION REQUIRED — RUNNABLE ARTIFACT VERIFIED; WINDOWS READINESS HELD**

### Decision

The Windows checkpoint has achieved two genuine milestones. Product Assurance independently verified
that the unsigned frozen application and its ZIP are runnable on the real Windows host, and the
repository's inert Guided simulation completed the full
`Scan → Match → Prepare → Consent → Result → Reassessment → Verification` chain without a physical
phone or production Recovery execution.

The checkpoint is not yet approved as the completed Windows development-readiness gate. Independent
review reproduced the supposedly transient trusted-launcher handle/path failure, the submitted
offscreen visual evidence renders all user-facing text as square glyphs, and the remaining project
privacy tests have not yet been replaced with a real Windows ACL assertion. These are narrow
platform-correctness issues; none authorizes a feature expansion or weakening of fail-closed safety.

### Repository scope and implementation review

- The pushed branch is an exact descendant of the approved `1d679d5` launcher checkpoint.
- `2b121c1` changes only:
  - `scripts/build_desktop_executable.py`
  - `src/romverse/rom/source_installation.py`
  - `tests/test_desktop_bundle.py`
  - `tests/test_source_installation.py`
- `a20402e` adds only the complete Windows portability audit.
- `824d6e7` changes only `docs/sync/BUILD-STATUS.md`.
- The Windows checkout was clean after handoff. Protected Companion files were unchanged.
- The approved trusted-launcher implementation and contract were not changed by the runnable-build
  commit.

The two implementation corrections are appropriately narrow:

- Windows source verification retains device, file index, size, and modification-time identity
  while omitting only unreliable nanosecond creation-time rounding; POSIX remains strict.
- The PyInstaller build temporarily removes only non-System32 PATH entries containing `icuuc.dll`
  and restores the original PATH afterward. This prevents unrelated Poppler ICU DLLs from
  shadowing the Windows system ICU API shim without changing application behavior.

### Independently verified runnable artifact

- Executable: `build/windows-dev-frozen/ROMVERSE/ROMVERSE.exe`
- Archive: `dist/ROMVERSE-Desktop-0.1.0-windows-x86_64-dev.zip`
- Archive SHA-256:
  `e442685566f9f2012a19bfe848cf8234469b994b46d92e41ddddb93a1272fba2`
- Archive size: 73,445,618 bytes
- Archive verification: 305 files; 164,585,215 expanded bytes; exact tree verifier passed.
- No `icu*.dll` is present in the frozen application directory.
- Product Assurance independently ran the frozen release-smoke launcher: passed.
- Product Assurance independently ran the source release-smoke launcher: exit 0. Qt emitted a
  non-fatal DPI-awareness warning under the SSH-hosted smoke process; application startup passed.
- Classification: unsigned development build only; not production-signed, published, or released.

### Independently verified journey evidence

The persisted simulation report confirms:

- synthetic target only; `physical_phone_changed=false` and `production_certified=false`;
- exact simulated Xiaomi/`popsicle` target and the reviewed source procedure;
- 53 simulated actions including 50 inert image writes;
- consent decline sent no changing command and later acceptance remained explicit;
- no wipe, relock, blind retry, or physical command;
- durable installation receipt remained unchanged;
- stable boot observation was separate from installation success and did not promote the
  installation receipt to boot-verified;
- 60 simulated seconds, 11 samples, valid audit, and unchanged source;
- same Guided/Expert operation session and zero commands or additional changes when history opened.

Recorded receipt SHA-256:
`e5a8a09ee3119a40d32cc938983ddd3932561fbfbd2f01f9c58211034a814bff`.

### Verification reviewed

- Build's final relevant regression: **250 passed, 4 failed, 2 skipped** in 314.90 seconds.
- Product Assurance independently reran the desktop bundle tests, the new Windows fingerprint test,
  and the complete Windows trusted-launcher test file: **31/31 passed**.
- Product Assurance then repeated the exact handle/path sharing-lock test. It passed 15 consecutive
  fresh runs and failed on run 16. This independently reproduces the intermittent failure and means
  it cannot be certified as deterministic.
- The broad portability audit honestly records 2,901 collected tests, bounded file groups, complete
  failure/error/skip inventories, and the test-harness limitations rather than representing the
  Windows branch as fully green.

### Required minimum correction

1. **Stabilize exact Windows launcher identity without weakening it.** Capture the path and open-
   handle identity fields on failure and correct only the proven unstable comparison. Prefer a
   native Windows volume/file-ID identity or a documented normalization of the unreliable timestamp
   representation. Preserve reparse rejection, single-link requirement, device/file identity,
   size/mtime checks, the write/delete-denying open handle through process creation, one-attempt
   dispatch, and fail-closed behavior. Do not skip, loosen, or delete the adversarial test.

2. **Prove readable text in the real frozen application.** The committed offscreen screenshots show
   square glyphs for all user-facing text and therefore do not satisfy Guided-friction or visual-
   readability evidence. Capture a screenshot from the actual visible frozen Windows window. If its
   text is readable, classify the square-glyph result as an offscreen-backend limitation and retain
   both pieces of evidence. If the visible window is affected, correct only Windows font
   resolution/bundling and reverify the same journey; do not redesign the UI or branding.

3. **Replace POSIX-only privacy assertions with a real Windows privacy contract.** For the project
   manifest, working-copy record, snapshot record, and snapshot artifact, verify owner-only Windows
   ACL behavior or an equivalently strong Windows-native access rule. Do not merely skip the tests
   or accept inherited broad read access. Keep the existing `0600` requirements unchanged on POSIX.

4. **Repair only the invalid ZIP test fixture.** Construct an archive member containing a literal
   backslash without allowing the Windows ZIP writer to normalize the name, then prove the existing
   `_safe_member` boundary rejects it. Do not weaken accepted-path validation or change product
   behavior unless the corrected fixture demonstrates a defect.

### Acceptance criteria

- The exact launcher sharing-lock test passes at least 100 consecutive fresh-process repetitions on
  the real Windows host, followed by the full Windows launcher file passing once as a group.
- The diagnostic evidence explains which field was unstable and why the correction preserves exact
  same-file binding and fail-closed execution.
- A real visible frozen-window screenshot proves readable text, or the minimum font correction is
  implemented and then proves it.
- Windows ACL tests prove that the four named project artifacts are not broadly readable; POSIX
  permission behavior remains unchanged.
- The literal-backslash archive fixture is valid and its rejection test passes.
- Source and frozen startup smoke, exact ZIP verification, and the inert Guided journey still pass.
- No physical phone, real Recovery command, production adapter enrollment, APK installation,
  production signing, publication, release, relock, or protected Companion-file change occurs.

### Approved next bounded task

Apply only the four minimum Windows corrections above. This is a correction pass, not authorization
for a new feature, production Recovery integration, platform merge, installer, signing, or release.
Update `docs/sync/BUILD-STATUS.md`, commit and push the exact correction checkpoint on
`windows-launcher-authorized-work`, and stop for Product Assurance review.

### Gate status

- v0.2 Golden Foundation: **CLOSED**
- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Windows unsigned frozen artifact: **RUNNABLE AND ARCHIVE-VERIFIED**
- Windows inert Guided journey: **VERIFIED**
- Windows completed development-readiness gate: **HELD FOR MINIMUM CORRECTION**
- Windows trusted-launcher safety: fail-closed; deterministic reliability correction required
- Companion instrumentation APK artifact readiness: **VERIFIED on Linux track**
- Physical Android/Recovery verification: outstanding; not authorized here
- Pre-v1.0 feature freeze: preserved
- Production signing, publication, and release: not authorized

## Reviewed checkpoint: 36f99fe — corrected Fastboot round trip

- Handoff commit: `36f99fe1c5be6de1776f40bc4fbfb34dd0d449a3`
- Implementation commit: `03dc954fc0c5ec7f113c9696b6358c3500ab4349`
- Product Assurance correction/base: `1a33372cac002c6142b8ac0d86eb71b099ef8c57`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — CORRECTED FASTBOOT ROUND TRIP HARDWARE VERIFIED**

### Decision and independent evidence

The correction is the minimum bounded response to the observed Xiaomi transient. Fastboot source
inspection may reacquire only one successful-but-empty product read, never a failed, malformed or
conflicting read, and then requires two complete identical fresh observations before plan creation.
It does not widen the shared parser, reuse historical Device Engine evidence or grant authority
from the transport serial alone. Changed/missing identity or mode continues to reject before any
reboot.

Product Assurance independently inspected the exact source/test diff and reran the complete focused
transition suite: **43/43 passed**, with Ruff static/format and whitespace checks clean. It also
strictly verified the current Guardian active/archive chain at 181 entries and loaded the final
privacy-safe passport digest
`0d1dc13d75ba5053e39a61090a74102e347657c64d0608a0128bc191cd2ae3cd`, matching the handoff.
The two sealed transition journals show one verified Android-to-bootloader arrival and one verified
Fastboot-to-Android arrival. Final uncached Device Engine evidence re-established the same
`popsicle` Android identity and current HyperOS build.

The hardware run did not encounter the transient-empty branch, so that branch is correctly
classified as software-tested only. The complete normal-path round trip is hardware verified. No
reboot command was repeated and no flash, partition, slot, wipe, unlock/relock, APK or file-transfer
operation occurred.

### Gate status and next task

- Bounded Fastboot source reacquisition: **APPROVED / SOFTWARE VERIFIED**
- Corrected Android → bootloader Fastboot → Android round trip: **APPROVED / HARDWARE VERIFIED**
- Phone's final Android return and exact identity: **VERIFIED**
- Feature freeze and Guardian separation: **PRESERVED**
- Flashing, partition operations, Fresh Live Target and release: **NOT AUTHORIZED**
- Bootloader relocking: **PERMANENTLY PROHIBITED**

No further phone operation is approved by this verdict. Resume the previously queued read-only
external-package metadata and untrusted-procedure inventory only after the Windows convergence
handoff is issued separately; do not repeat this hardware journey.

## Reviewed checkpoint: 99f3534 — Fastboot return-plan transient observation defect

- Handoff commit: `99f353442f4aedf4a7f92739cac6b11f2fa21570`
- Evidence commit: `d02d459aae302326d5a5d2cfc29701a8d313887b`
- Product Assurance authorization/base: `46cda9e3780857d7aa33af02926dac0cf1aefa7f`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **CORRECTION REQUIRED — BOUNDED FASTBOOT SOURCE REOBSERVATION**

### Decision and cause

The checkpoint safely proved the same pseudonymous `popsicle` target arrived in bootloader Fastboot
and that the production Device Engine could read its product identity. The authorized return command
was never dispatched because the transition service performed a separate immediate source
revalidation and that one `getvar product` call returned exit zero without a parseable value. The
service correctly refused to substitute historical identity, but rejecting after one transient
missing read can strand a safely identified phone in Fastboot. That is a minimum product defect,
not evidence that the phone is incompatible.

Product Assurance inspected the sealed completed Android-to-bootloader journal and the redacted
Guardian records. The first reboot completed and exact bootloader arrival was verified. The fixed
Device Engine scan used only the five allowlisted variables. No return intent/command, flash, boot,
partition operation, slot change, wipe, unlock/relock or alternative command occurred. The safe
rejection and truthful partial classification are approved; completion of the user journey is not.

### Minimum exact correction and immediate recovery acceptance

Change only `LocalDeviceTransitionService` and its focused transition tests so source-mode
inspection can tolerate one transient, successful-but-empty Fastboot product response. A Fastboot
source review may make at most one bounded non-dispatching reacquisition when an otherwise
unambiguous exact transport is present but its product value is missing. Reacquisition must perform
fresh discovery and product/mode reads; it must not reuse the prior Device Engine value, widen the
parser, infer identity from the serial, or dispatch while any identity fact remains missing.

Require two complete, identical Fastboot source observations before creating the return plan. A
changed/multiple/absent serial, changed product or mode, tool hash change, malformed/conflicting
value, second missing product, timeout or command failure must still reject before reboot. Add
focused regressions proving one transient empty product can recover into two identical observations,
while repeated emptiness and every identity change remain command-free failures. Run only the
transition-focused tests plus lint/format/whitespace.

After those checks pass, commit the correction before touching the phone. Then perform one fresh
read-only Fastboot discovery/identity assessment through the corrected production service. If it
earns the two identical source observations for the same pseudonymous `popsicle`, create one new
one-use return plan under Steve's already recorded round-trip consent and dispatch exactly one
Fastboot reboot to Android. Observe bounded exact Android arrival and one reconnect-safe Device
Engine confirmation. This is completion of the previously authorized return, not a new experimental
operation.

If the corrected evidence cannot earn authority, issue no host-side reboot. Tell Steve to use the
Xiaomi-supported manual recovery: hold only the Power button for more than ten seconds to force a
restart. Do not instruct a data wipe or button combination that enters another mode. In either
outcome, record the exact result, commit/push the handoff and stop for Product Assurance.

No `getvar all`, arbitrary partition enumeration, fetch/upload, flash/boot/update, slot change,
erase/wipe/format, unlock/lock/relock, APK/root/debloat action, source authority, signing,
publication or release. Do not rehash the firmware or run broad tests.

### Gate status

- Android-to-Fastboot transition and fixed identity scan: **APPROVED / HARDWARE VERIFIED**
- Complete round trip: **CORRECTION REQUIRED**
- Corrected exact return-to-Android attempt: **AUTHORIZED ONCE AFTER FOCUSED TESTS PASS**
- Flashing, partition operations and Fresh Live Target authority: **NOT AUTHORIZED**
- Bootloader relocking: **PERMANENTLY PROHIBITED**

## Reviewed checkpoint: cb929ac — read-only popsicle Device DNA hardware acceptance

- Handoff commit: `cb929ac178fc1c099027eb46ca3263a8d9a3f10a`
- Evidence commit: `60e7e85b260b9ae368bd81733c02febdc014babe`
- Product Assurance authorization/base: `bccc0b1eb7fc3585a8c65006d07076f334f6b2d8`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — REAL ADB DEVICE DNA OBSERVATION VERIFIED**

### Decision and independent evidence

The checkpoint remained within the exact read-only authorization. Its complete repository diff
changes only `docs/sync/BUILD-STATUS.md`; no application, test, Device Pack, Companion, Windows or
Adaptive source changed. The production run recorded exactly fourteen Guardian-allowed operations:
two ADB discovery calls, two Fastboot discovery calls and ten fixed ADB detail probes. Product
Assurance independently inspected the corresponding redacted audit tail and verified the complete
active/archive chain as valid at 28,005 entries. All fourteen scoped records are read-only, the raw
transport identity is redacted, and the two expected absent-package results are ordinary known
non-zero observations rather than uncertain device failures.

Product Assurance also independently loaded the durable local stores through their strict production
loaders. The latest pseudonymous passport record digest is
`1217107ab1e2b287d3576fc3a672c93b6e14aea58de2325444fb8e98d32af092`, Device DNA digest is
`73016d262e6957bdc7383a861fa6933b7a15dbec9db05fcbfa2a0b399092601b`, and Compatibility Matrix
digest is `4cd90f4391d03c6f0ef9166cbec78f9072088229814f1045bc2a55d2df944e02`, exactly matching the
handoff. The observation truthfully proves one Xiaomi `popsicle` / `2509FPN0BC` Android target on
Fedora. It does not prove a Fastboot target, source compatibility, consent, execution or Recovery.
The Pack relationship remains advisory and `guardian_flash` remains `UNCONFIRMED`, which is correct.

### Vision, freeze and safety result

- Real production ADB Device Engine, Device Intelligence, Device DNA and Compatibility Matrix:
  **HARDWARE VERIFIED FOR THIS ONE READ-ONLY OBSERVATION**
- Exact-device privacy binding and audit integrity: **PASS**
- Feature freeze: **PASS — evidence-only acceptance; no product code changed**
- Guardian authority, UNKNOWN-on-uncertainty, no blind retry and permanent no-relock: **PRESERVED**
- Fresh Live Target, installation, flash, wipe, Recovery and release: **NOT VERIFIED OR AUTHORIZED**

### Approved next bounded task — one Fastboot identity round trip

Steve explicitly requested this physical Fastboot test on 8 September 2026. Perform one bounded
production-path Android-to-bootloader-Fastboot-to-Android round trip on the same currently connected
`popsicle` phone. This authorization covers two exact mode-change commands only: the existing
`LocalDeviceTransitionService` may send one reviewed ADB reboot to bootloader and, after the exact
Fastboot target is verified, one reviewed Fastboot reboot back to Android. Use its one-use plan,
tool-hash revalidation, pseudonymous exact-target binding, durable transition journal, bounded
arrival observation and Guardian audit. The creator's request supplies consent for this exact
round trip only; it grants no installation or flashing consent.

In bootloader Fastboot, exercise the production `DeviceEngine` identity path once. Allow only
Fastboot discovery and the existing fixed reads for `product`, `current-slot`, `unlocked`, `secure`
and `is-userspace`. Confirm one unambiguous target, no simultaneous ADB target, expected `popsicle`
product identity, bootloader rather than fastbootd mode, and agreement or explicit uncertainty for
slot/unlock/security evidence. Persist only the existing privacy-safe identity evidence. Do not use
`getvar all`, enumerate arbitrary partitions, fetch or upload any bytes, create a source-bound Fresh
Live Target receipt, or promote this observation into compatibility or execution authority.

After the single return-to-Android command, use the existing bounded ADB observation to confirm the
same product/codename and record whether normal Android transport returned. Do not repeat either
mode-change command if a command result or resulting mode is unknown. If Fastboot uses a changed
transport identity, arrival times out, any identity conflicts, or Android does not return within the
bounded observation, stop and report the measured state for recovery/reassessment; do not guess,
retry or issue an alternative command.

Absolutely no unlock/lock/relock, critical unlock change, slot change, erase, wipe, format, flash,
boot, update, partition read/write, APK action, root/debloat action, firmware execution, consent for
another operation, signing, publication or release. Run no broad test suite and do not rehash the
11.8 GB package. Record the exact redacted operation count and outcomes, update
`docs/sync/BUILD-STATUS.md`, commit/push, and stop for Product Assurance. If the phone is no longer
connected, report that one physical blocker and continue no device command.

### Gate status

- ADB Device DNA observation: **APPROVED / HARDWARE VERIFIED**
- Fastboot identity observation and reversible round trip: **AUTHORIZED NOW — EXACT BOUNDED SCOPE**
- Partition enumeration, Fresh Live Target, installation, execution and Recovery: **NOT AUTHORIZED**
- Bootloader relocking: **PERMANENTLY PROHIBITED**

## Current hardware authorization — one fresh read-only popsicle observation

- Authorization base: `ddfbdb7` on `linux/stage1-desktop-readiness`.
- Creator availability statement: Steve explicitly connected the phone on 8 September 2026.
- Read-only preflight: exactly one Linux ADB target is visible as product/device `popsicle`, model
  `2509FPN0BC`; no Fastboot target is visible.
- Status: **AUTHORIZED — READ-ONLY DEVICE DNA OBSERVATION ONLY**

### Exact bounded task

Temporarily queue the approved external-package metadata inventory; do not run both milestones at
once. Through the current production Device Engine/Device DNA/Fresh Live Target observation
services, perform one fresh read-only observation of the single currently connected ADB device.
Use only the existing allowlisted bounded identity/state probes and repeated discovery required by
the exact-target witness contract. Persist no raw serial; bind evidence to the existing pseudonymous
device identity and exact observed build/firmware properties.

Collect and present only read-only identity and safety evidence already supported by the product:
manufacturer/brand/model/product/device/codename, build fingerprint/ID/version/security patch,
current Android/transport mode, slot/dynamic-partition facts when exposed, verified-boot/flash-lock
state when exposed, and current Device Pack/Compatibility Matrix agreement or conflict. Compare
against existing firmware/project evidence only through current read-only contracts. Missing,
changed, ambiguous or conflicting facts remain `UNCONFIRMED`/`UNKNOWN` and stop the observation.

End at the truthful observed-device/review boundary before any plan consent. Do not reboot or change
mode, enter Fastboot/Recovery, install an APK, push/pull user files, copy backups, unlock/root/
debloat, write settings or partitions, create consent/admission, dispatch an adapter, flash/wipe,
sign/publish/release, or relock. If Android authorization is absent, report the visible user action
and wait; do not bypass it. Run one focused acceptance path, update BUILD-STATUS.md, commit/push and
stop for Product Assurance. No broad suite or package rebuild.

### Gate status

- Physical phone available on Linux ADB: **YES — ONE TARGET**
- Fresh read-only exact-device/firmware evidence: **AUTHORIZED NOW**
- Consent, execution, installation, Recovery and device mutation: **NOT AUTHORIZED**
- Bootloader relocking: **PERMANENTLY PROHIBITED**

## Reviewed checkpoint: 3d35b04 — same-handle external firmware evidence

- Handoff commit: `3d35b04`
- Correction commit: `aad0f2a934d069623b658a957632c4bee1002ec6`
- Product Assurance authorization/base: `56f0c4f117124f5718bfabdbcea7c174f0787359`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — HASH AND STRUCTURE EVIDENCE BOUND TO ONE HANDLE**

### Decision and evidence

The correction closes the identified evidence-mixing window. External intake now keeps the original
no-follow regular-file descriptor open through identity admission, SHA-256 hashing, rewind,
container detection, ZIP/TAR/raw structural inspection, final descriptor identity and final path
identity. `RomInspector` exposes one shared seekable-stream implementation while its existing path
API remains a compatibility wrapper. The directory-entry replacement regression proves inspection
continues on the original descriptor and final path binding fails before any receipt is written.

Product Assurance inspected the exact five-file implementation/handoff diff and the three required
regression groups. Build reports **38/38 focused tests passed**, with Ruff format/static and
whitespace checks clean. The 11.8 GB source was not needlessly rehashed and the package was not
rebuilt. No authority, UI decision or protected-source behavior changed.

### Approved next bounded task

Extend only the read-only external firmware inspection evidence so ROMVERSE can recognize useful,
bounded package metadata and the presence of untrusted executable procedure files without executing
or adopting them. For ZIP packages, from the same admitted open descriptor, identify a strict
allowlist of small metadata members such as `BUILD-INFO.txt`, `CUSTOMIZATION-MANIFEST.tsv`,
`SHA256SUMS`, and `android-info.txt` when present. Record each exact member path, size and SHA-256;
parse only an explicit bounded non-executable key/value identity allowlist needed for manufacturer,
codename, build/firmware version, Android version, region/channel and declared base provenance.

Separately inventory executable-looking members (`.sh`, `.bat`, `.cmd`, `.ps1` and updater-script)
as **untrusted procedure presence** by path/hash/size only. Never retain their body, parse them into
steps, invoke them, or treat their existence as a safe route. UI evidence must clearly distinguish
package-declared identity from ROMVERSE-verified facts and show that build/install/Guardian remain
locked. Conflicts, duplicates, malformed/oversized metadata, unexpected encoding, path ambiguity,
commands/relock text entering identity fields, or manifest/hash mismatch fail closed or remain
explicitly unconfirmed.

Add focused synthetic regressions first. Then perform one read-only reinspection of the existing
real external package only if needed to validate the new evidence; one full rehash is permitted for
that new schema, not as repetition. Do not copy/extract/mutate the package. Record the first concrete
defect only, update status, commit/push and stop for review. Do not use a phone/emulator/device tool
target, construct a flash route, unlock build/consent/Guardian/Recovery, touch Windows/Companion/
Adaptive work, sign, publish, release, force-push or relock.

### Gate status

- Same-handle external intake evidence: **VERIFIED**
- Next Linux milestone: **BOUNDED PACKAGE METADATA AND UNTRUSTED-PROCEDURE INVENTORY**
- Script adoption/execution, physical device and Guardian authority: **NOT AUTHORIZED**
- Public release: **NOT AUTHORIZED**

## Reviewed checkpoint: 024ed9f — external read-only firmware intake

- Handoff commit: `024ed9f`
- Implementation commit: `538992bb5cbd5f54edd828a6116aaf0de8041fe3`
- Product Assurance authorization/base: `d6930827a3dd679b1a460a7ab6e58975be6ac420`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **CORRECTION REQUIRED — BIND INSPECTION TO THE HASHED FILE HANDLE**

### Decision and independent evidence

The checkpoint delivers a valuable real capability: ROMVERSE can hash and structurally inspect an
external firmware package in place without copying, extracting or granting build/device authority.
The real packaged journey correctly preserved the 11.8 GB source, reported unknown compatibility,
kept seven consequential controls disabled and survived restart. Product Assurance independently
rehashed both the source and corrected archive; their SHA-256 values exactly match the handoff.
The native chooser automation limitation is accepted for this service/packaged checkpoint and
requires only a later human-driven UI acceptance, not a workaround or rebuild loop.

One evidence-integrity gap remains. `ExternalFirmwareIntakeService.inspect()` hashes an already-open
descriptor, closes it, and then calls `RomInspector().inspect(source, ...)`, which reopens the path.
The before/after path identity checks cannot prove that the independently opened inspection stream
was the same file handle that supplied the recorded hash; a transient path swap during inspection
could combine one file's hash with another file's container evidence. The receipt grants no
execution authority, but ROMVERSE must not persist internally mixed evidence.

### Minimum exact correction

Extend the existing `RomInspector` with the smallest bounded seekable-stream/file-handle inspection
entry point needed by external intake. Keep the original descriptor open from the first identity
check through hashing, rewind, container detection/ZIP-or-TAR metadata inspection, and the final
descriptor/path identity checks. The report's hash and structure must therefore come from the same
open regular file. Preserve the existing path-based inspector for current protected-source callers
unless a safe shared implementation avoids behavior change.

Add focused regressions proving:

1. external intake does not reopen the selected path for content inspection after descriptor open;
2. replacing the directory entry during inspection cannot mix replacement metadata with the
   original descriptor/hash and causes the final path binding to fail closed;
3. the existing ZIP/TAR/raw container results and no-copy/no-authority receipt remain unchanged.

Run only the external-intake and directly affected inspector regressions plus Ruff/whitespace. Do
not rehash the 11.8 GB source, rerun the packaged journey or rebuild the artifact for this source
correction. Update BUILD-STATUS.md, commit/push and stop for review.

Do not broaden Device DNA inference, copy/extract/mutate firmware, use a phone/emulator or device
tool target, unlock build/install/Guardian/Recovery, touch Windows/Companion/Adaptive work, sign,
publish, release, force-push or relock.

### Gate status

- Read-only external-source capability and locked UI: **PROVISIONALLY ACCEPTED**
- Hash/inspection same-handle evidence binding: **CORRECTION REQUIRED**
- Feature freeze and Guardian separation: **PRESERVED**
- Physical/consequential execution and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 5f61887 — packaged Fedora no-phone user journey

- Handoff commit: `5f61887`
- Product Assurance authorization/base: `df9351fd79bd811b9cccdfff2fb266f6e16bd1f1`
- Packaged source: `9ca297b4ad048fee89bb7686128f40d35b441456`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — PACKAGED FEDORA USER JOURNEY VERIFIED**

### Decision and evidence

The exact approved unsigned archive was extracted once and its real packaged executable completed
Guided entry, Command Deck, workspace-local Platform Tools remediation, an offline Knowledge lookup,
clean shutdown and a durable restart. The same executable/archive identities remained bound to the
previously approved hashes. Three durable workspace/evidence/tool receipts remained byte-identical
across restart, and five sampled consequential controls stayed disabled with no target present.
No corrective rebuild or duplicate automated suite was needed.

Opening `Resolve Platform Tools` is an explicit user request to repair that prerequisite. With the
documented `auto_download_verified_tools` preference enabled, automatically fetching the official
hash-verified package into the isolated workspace is accepted Guided zero-friction behavior. It is
not a system installation or device action. The UI reported the download and verified activation;
no operating-system authorization was hidden. Revisit the button wording only if a reproducible
user dead end appears—do not create a presentation-only rebuild loop from this checkpoint.

### Vision, freeze and safety result

- Real packaged first launch, useful offline lookup and durable restart: **PASS**
- Guided no-device truthfulness and workspace-local tool remediation: **PASS**
- Feature freeze: **PASS — evidence-only packaged integration**
- Guardian-only authority, exact evidence, consent separation, UNKNOWN/no-blind-retry and permanent
  no-relock: **PRESERVED**
- Phone, device command, execution, system installation, signing, publication and release: **NONE**

### Approved next bounded task

Run one real, no-phone, read-only packaged firmware-intake journey using the existing local
`adbb99b9d6e6c3e6-HyperOS4-Xiaomi17ProMax-Debloated-CustomRom.zip` as an external source selected
in place. Do not copy, extract, modify, build, sign or execute it. Through the packaged production
UI/service path, verify ROMVERSE identifies and hashes the source, presents its source/package
evidence and exact known-versus-unconfirmed boundaries, exposes a useful next read-only inspection
action, and preserves the protected-source/project identity across one clean restart. Stop before
Recipe mutation, local build, device selection, consent, Guardian admission or Recovery.

Use one disposable workspace and reuse existing receipt/fixture coverage. Record only the first
concrete packaged-runtime or Guided-friction defect. If one appears, implement its minimum
freeze-safe correction with one focused regression and at most one corrective rebuild; otherwise
commit evidence only. Do not run broad suites, repeat the prior startup/tool/Knowledge journey, use
a phone/emulator or ADB/Fastboot target, touch Windows/Companion/Adaptive work, install system-wide,
sign, publish, release, force-push or relock. Commit/push and stop for review.

### Gate status

- Fedora unsigned packaged first-run journey: **VERIFIED**
- Next Linux milestone: **REAL LOCAL FIRMWARE READ-ONLY INTAKE**
- Firmware mutation/build and physical target observation: **NOT AUTHORIZED**
- Consent, execution, Recovery and public release: **NOT AUTHORIZED**

## Reviewed checkpoint: 95c80bc — unsigned Fedora internal development build

- Handoff commit: `95c80bc70e9afed573ad21e27525ddf5cb48574b`
- Packaged source/authorization: `9ca297b4ad048fee89bb7686128f40d35b441456`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — RUNNABLE FEDORA DEVELOPMENT ARTIFACT VERIFIED**

### Decision and independent evidence

The checkpoint changes only the durable status handoff and records one local, portable, unsigned
Fedora development archive assembled from the previously approved source. Product Assurance
independently verified that the recorded archive is present, its SHA-256 is
`096d15bad7518fafe74074dd92b7e27ed9609e36ba5cf1b3c06044f8655505a4`, all compressed members pass
CRC validation, and the archive contains exactly 460 regular files totalling 360,259,562 expanded
bytes with no absolute or parent-traversal paths. The contained `ROMVERSE/ROMVERSE` executable
hashes to `2972216e8683cd73e3d9810da253d6571b595fb8d0fe7b46e17c9eea550a8fb5`, matching the handoff.

The artifact name and handoff classify it as unsigned and internal-only. It was not committed,
uploaded, signed, trusted, installed system-wide or released. Build's one bounded frozen-process
startup reached the truthful no-device Guided Command Deck and closed cleanly. That is sufficient
for this packaging checkpoint but is not a visual-layout, cross-machine, Windows or hardware claim.

### Vision, freeze and safety result

- Existing approved functionality packaged without application behavior changes: **PASS**
- Archive integrity, safe extraction paths and exact executable identity: **PASS**
- Feature freeze: **PASS — packaging/integration work only**
- Guardian authority, exact evidence, consent separation, UNKNOWN/no-blind-retry and permanent
  no-relock: **PRESERVED**
- Phone, ADB/Fastboot target, execution, production signing/trust, publication and release: **NONE**

### Approved next bounded task

With no phone available, do not idle and do not repeat the build or broad suites. Extract the exact
approved archive once into a disposable user-writable directory and run one bounded, no-phone
Fedora user journey through the packaged executable: first launch/Guided entry, Command Deck,
platform-tool status/remediation presentation, one offline Knowledge/Device DNA lookup, and clean
restart with durable state. Confirm every unavailable hardware action remains truthful and disabled.
Record the first concrete packaged-runtime or Guided-friction defect and apply only its minimum
freeze-safe correction with one focused regression and at most one corrective rebuild. If the
journey is clean, commit evidence only. Do not install system-wide, use a phone/emulator or device
tool target, create consent/admission, dispatch, sign, publish, release, touch Windows/Companion/
Adaptive work, run an open-ended visual/simulation loop, or relock. Commit/push and stop for review.

### Gate status

- Consolidated Fedora development artifact: **VERIFIED**
- Next Linux milestone: **ONE PACKAGED NO-PHONE USER JOURNEY**
- Fresh physical target observation: **QUEUED UNTIL PHONE AVAILABLE**
- Consent, execution, Recovery and public release: **NOT AUTHORIZED**
- v0.2 Golden Foundation: **CLOSED**

## Reviewed checkpoint: 44db4a6 — final signed installation-byte binding

- Handoff commit: `44db4a6`
- Implementation commit: `b174803`
- Product Assurance authorization/base: `7879f34c59d9a0e8501501a12a51462103bd36b4`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — FINAL SIGNED CANDIDATE BYTES VERIFIED**

### Decision and independent evidence

The version-two candidate composition now binds the exact offline-signing and signed-super-assembly
receipts and selects only the final signed `vbmeta_system.img` and assembled `super.img` as the two
replacement installation origins. Pre-sign outputs remain lineage evidence but cannot be staged as
installation bytes. Missing, moved, substituted, stale or byte-changed final evidence fails closed;
legacy version-one compositions remain audit-only and cannot be resealed into current authority.

Product Assurance inspected the nine-file source/test diff and durable handoff. Product Assurance
independently reran the core composition, reconstruction, missing-receipt, byte-drift, 53-step
private-staging and no-phone production-dialog checks: **9/9 passed**. Build's single affected set
reports **117/117 passed**. The working tree is clean and Windows, Adaptive Knowledge and protected
Companion work were untouched.

### Vision, freeze and safety result

- Final signed installation-byte and receipt lineage: **PASS**
- Durable reconstruction and Guardian historical provenance: **PASS**
- Feature freeze: **PASS — required correctness binding in the existing flow**
- Guardian-only authority, exact-device evidence, UNKNOWN/no-blind-retry and permanent no-relock:
  **PRESERVED**
- Phone, consent, execution, installation, Recovery and release: **NONE**

### Approved next bounded task

The next consequential boundary is a read-only fresh exact-device observation, but the creator has
not made a phone available for this unattended period. Queue that hardware checkpoint without
waiting for it. Instead produce exactly one consolidated unsigned Fedora internal-development build
from the current approved Linux source so the completed unfamiliar-intake → local-build → artifact
verification → offline-signing → final-signed preparation work is present in a runnable artifact.

Use the existing locked build environment and packaging scripts. Do not change product behavior
solely for packaging. Verify exact archive tree/hash, source identity, unsigned classification and
one bounded no-phone startup into a truthful Guided/Command Deck state. Reuse prior journey evidence;
do not rerun the full chain or broad suite. If packaging exposes one concrete defect, apply only its
minimum platform correction and one focused regression, then rebuild exactly once. Record all
included commits and limitations in BUILD-STATUS.md, commit/push and stop for Product Assurance.

Do not use a phone/emulator, ADB/Fastboot target, consent, execution, Recovery, real private key,
production trust, publication/release, force-push, protected Companion, Windows or Adaptive files,
or relock. This artifact is an unsigned internal development build only.

### Gate status

- Unfamiliar firmware through final signed candidate preparation: **VERIFIED IN SOURCE**
- Next Linux milestone: **ONE CONSOLIDATED RUNNABLE FEDORA DEVELOPMENT ARTIFACT**
- Fresh physical target observation: **QUEUED UNTIL PHONE AVAILABLE**
- Consent, execution, Recovery and public release: **NOT AUTHORIZED**
- v0.2 Golden Foundation: **CLOSED**

## Reviewed checkpoint: a52d6b7 — durable no-phone candidate preparation

- Handoff commit: `a52d6b7`
- Implementation commit: `4a4c61c027790954655e584a07d38ed54650dcf6`
- Product Assurance authorization/base: `bb799e1622197b36fcbf6f7cda9b8770f80db61f`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — DURABLE PREPARATION VERIFIED; FINAL-SIGNED-BYTE BINDING REQUIRED NEXT**

### Decision and independent evidence

The checkpoint fixes a genuine durability defect without weakening preparation. An unchanged exact
base/AVB pair is now loaded and freshly verified instead of being resealed under new timestamps and
digests after ordinary service reconstruction. Invalid or mismatched evidence still regenerates
only through the preparation path; verification never renews evidence behind an already reviewed
plan. Product Assurance inspected the exact two-file source/test diff and independently reran the
new reconstruction regression plus the two receipt-reuse/invalid-receipt checks: **3/3 passed**.

The no-phone endpoint is truthful and inert. It displays one USB connection action and creates no
target, review plan, consent, admission, dispatch or result. The three affected-set failures are
baseline-confirmed stale message expectations, not a product regression or weakened failure mode;
they should be corrected narrowly during the next touched candidate-preparation checkpoint.

This checkpoint does not yet prove the bytes that would ultimately be reviewed for installation.
The current candidate recipe binds pre-sign build/base/AVB evidence, while the repository separately
contains the exact offline-signing receipt and signed-final-assembly contracts. Those final signed
artifacts must be incorporated before live-target observation.

### Vision, freeze and safety result

- Durable exact preparation across reload: **PASS**
- No-phone Guided endpoint and authority separation: **PASS**
- Feature freeze: **PASS — minimum correctness repair in an existing flow**
- Guardian-only authority, exact evidence, UNKNOWN/no-blind-retry and permanent no-relock:
  **PRESERVED**
- Final signed installation-byte binding: **REQUIRED BEFORE LIVE TARGET**

### Approved next bounded task

Extend only the existing complete candidate preparation/verification contract so it consumes and
binds the current `OfflineSigningReceipt` and, where the Device Pack route requires a final super
container, the current `SignedSuperAssemblyReceipt`. The durable candidate recipe must name the
exact workspace-relative final installation artifacts and bind their hashes, sizes, signing receipt
digest and signed-assembly receipt digest. Every rebuilt role used by the 53-action route must come
from the verified final signed result; pre-sign build outputs may remain lineage evidence but must
not be selected as installation bytes.

Fresh verification and reload must fail closed if a final artifact, receipt, path, hash, size,
policy identity, build/source/Pack binding or assembly lineage is absent, stale, replaced or
ambiguous. Preserve one stable recipe digest across an unchanged reconstruction. Update only the
three baseline-stale `bytes differ` assertions to expect the current exact fail-closed message; do
not loosen their behavior.

Exercise one no-phone production preparation/reload journey using bounded synthetic signed
artifacts and inert tooling. End at the same disabled fresh-target wait. Do not observe a phone,
create consent/admission, dispatch, install, flash, enter Recovery, rebuild/sign again, add online
evidence, run a broad suite, package, publish, release, force-push, touch protected Companion,
Windows or Adaptive work, or relock. Implement the minimum correction with focused regressions,
update BUILD-STATUS.md, commit/push, then stop for Product Assurance.

### Gate status

- No-phone candidate preparation durability: **VERIFIED**
- Next core milestone: **BIND FINAL SIGNED INSTALLATION BYTES**
- Fresh live target, consent, execution, Recovery and release: **NOT AUTHORIZED**
- v0.2 Golden Foundation: **CLOSED**

## Reviewed checkpoint: 0a0e50a — signed-result import to durable Guardian handoff

- Handoff commit: `0a0e50a`
- Implementation commit: `5319ee61f0324b0bb4d1c45e178b308defbced90`
- Product Assurance authorization/base: `65da5c8f314d4b7a651f0d87582f20e021a36ba4`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — DURABLE SIGNING-READY HANDOFF VERIFIED**

### Decision and independent evidence

The bounded production widget/service/worker journey proves exact signed-result import, durable
receipt reconstruction and a truthful handoff into the existing Guardian-controlled preparation
boundary. The imported synthetic artifacts remain bound to the exported request, approved synthetic
policy, exact public-key identity, algorithm, rollback fields, descriptors, sizes and hashes. No
private key was stored and no phone, consent, installation, flash or Recovery result was invented.

The first concrete defect was presentation-only but user-significant: after reload, a genuinely
`signing_ready` project appeared to regress to generic local-build completion. `5319ee6` is the
minimum correction. It distinguishes `SIGNING READY / INSTALL NOT STARTED / FLASH NOT AUTHORIZED`
and preserves the existing preparation action without granting any consequential authority.
Product Assurance inspected the exact two-file source/test diff and independently reran the seven
named focused regressions against the reviewed source: **7/7 passed**. The working tree is clean and
the protected Companion, Windows and Adaptive Online Device DNA work remain untouched.

### Vision, freeze and safety result

- Exact signed-result import and durable reload: **PASS**
- Guided signing/install/flash truthfulness: **PASS**
- Feature freeze: **PASS — minimum correction inside the approved existing flow**
- Guardian-only authority, exact evidence, consent separation, UNKNOWN/no-blind-retry and permanent
  no-relock: **PRESERVED**
- Physical device, production trust/signing, installation, Recovery, publication and release:
  **NONE**

### Approved next bounded task

Run one fresh, no-phone **signed candidate to Guardian preparation and fresh-target waiting journey**
through the existing production UI/service boundaries. Begin from the durable signing-ready project
and activate `Prepare verified ROM installation…`. Verify ROMVERSE derives and displays the exact
project/source/Device Pack/route/action-sequence preparation, preserves its durable binding after one
normal service/UI reconstruction, and ends on one clear `connect the exact device` or equivalent
fresh-live-target action.

With no phone present, the journey must not create a live-target receipt, Guardian consent,
execution admission, adapter dispatch, installation/flash result or Recovery claim. `UNCONFIRMED`
device state must remain investigable/waiting rather than unsupported. Record the first concrete
defect and implement only its minimum freeze-safe correction with one focused regression; if clean,
commit evidence only. Reuse the existing signed receipt and preparation contracts—do not repeat ROM
build, AVB inspection or signing import, run a broad suite, use an emulator/phone, add online-evidence
work, package either app, enroll production trust, publish, release, force-push, touch protected
Companion/Windows/Adaptive work or relock. Commit and push, then stop for Product Assurance.

### Gate status

- Unfamiliar intake through durable signing-ready candidate: **VERIFIED**
- Next core milestone: **GUARDIAN PREPARATION TO FRESH-TARGET WAITING**
- Adaptive Online Device DNA foundation: **INDEPENDENT WORK IN PROGRESS**
- Physical target, consent, execution, installation, Recovery and release: **NOT AUTHORIZED**
- v0.2 Golden Foundation: **CLOSED**

## Reviewed checkpoint: 0ab911f — artifact verification to offline-signing readiness

- Handoff commit: `0ab911f8d052fb80b2d8f87b001b65f19cb27749`
- Implementation commit: `14de58e376bbd5cf14369f605bdfd6355f892cca`
- Product Assurance authorization/base: `a6d9bca06d35c4f0ca8b84ad6ebd990be7e5700a`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — ARTIFACT-VERIFICATION/OFFLINE-SIGNING BOUNDARY VERIFIED**

### Decision and independent evidence

The checkpoint completes the approved bounded transition from a durable unsigned local candidate to
exact AVB/artifact evidence and an offline-signing request. The first concrete defect was a real
Guided loop: completion of the four-image candidate inspection immediately dispatched the same AVB
inspection again and could then expose installation preparation while `signing_ready` remained
false. `14de58e` is the minimum correction. A freshly reloaded exact candidate AVB receipt now routes
to `Open offline signing ceremony`; unsigned completion terminates Autopilot, and neither the
repeated inspection nor the installation action is selected.

Product Assurance inspected the exact source/test diff and the durable handoff. The persisted AVB
receipt remains bound to the project, source, Device Pack contract and local-build receipt. The
existing ceremony retains content-addressed candidate artifacts, exports no private key and grants
no phone or execution authority. Product Assurance independently reran the seven named focused
regressions against the reviewed source: **7/7 passed**. The repository is clean and the protected
Companion files are untouched.

### Vision, freeze and safety result

- Artifact verification and offline-signing request handoff: **PASS**
- Guided no-repeat/no-premature-installation routing: **PASS**
- Exact evidence and durable reload behavior: **PASS**
- Feature freeze: **PASS — minimum correction inside the approved existing flow**
- Guardian-only authority, UNKNOWN/no-blind-retry, exact-device binding and permanent no-relock:
  **PRESERVED**
- Real signing, trust enrollment, phone, installation, Recovery, publication and release: **NONE**

### Approved next bounded task

Complete one fresh, no-phone **offline-signing return/import to durable signing-ready handoff** using
the existing production widget/service/worker path, a disposable project, bounded synthetic
artifacts and an inert AVBTool adapter. Begin from the exact exported request. Import only a bundle
that matches its content-addressed manifest and approved synthetic signing policy; verify the exact
public-key identity, algorithm, rollback fields, descriptors, artifact sizes and hashes; then close
and reconstruct the service/UI and prove the same signed-candidate receipt remains valid.

The final UI must distinguish `SIGNING READY` from installation or flash success and offer one clear
next action into the existing Guardian-controlled preparation/review boundary. Opening that boundary
must not grant consent, dispatch a device command or require a connected phone. Record the first
concrete defect and implement only its minimum freeze-safe correction with one focused regression;
if clean, commit evidence only. Reuse the current request and existing signing-contract coverage—do
not rebuild the ROM, rerun the preceding AVB journey, run a broad suite, use a real private key,
enroll production trust, package either app, use a phone/emulator, begin Recovery/installation,
publish, release, force-push, touch protected Companion/Windows work or relock. Commit and push, then
stop for Product Assurance.

The separate `adaptive-online-device-dna` worktree may continue independently. Linux Build must not
edit or duplicate that branch's online-evidence schema, adapters, tests or status document.

### Gate status

- Unfamiliar intake, durable local build and artifact-verification/offline-signing request:
  **VERIFIED**
- Next core milestone: **SIGNED RESULT IMPORT TO DURABLE GUARDIAN HANDOFF**
- Adaptive Online Device DNA foundation: **INDEPENDENT WORK IN PROGRESS**
- Physical device, production signing/trust, installation, Recovery and release: **NOT AUTHORIZED**
- v0.2 Golden Foundation: **CLOSED**

## Reviewed checkpoint: 0792fa8 — Recipe Forge to durable local build

- Handoff commit: `0792fa8`
- Implementation commit: `b77ee3c03aac1746a8e8f18acd370ddcb3094360`
- Product Assurance authorization/base: `4282da62947dd7e21de56eeb4550a827b468ae87`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — DURABLE LOCAL-BUILD JOURNEY VERIFIED**

### Decision and evidence

The bounded production-widget/service journey proves a useful complete local path: deterministic
Recipe creation and preview, explicit transactional application, durable Recipe evidence, seven-step
inert local build, exact output/receipt verification, and truthful reconstruction after normal
service/UI reload. It is correctly classified as simulated orchestration with no phone or real host
image-building claim.

The discovered restart defect is real and `b77ee3c` is the minimum correction. A durable unsigned
local candidate now remains `LOCAL BUILD COMPLETE / INSTALL NOT AUTHORIZED`; its primary action is
artifact verification, not installation preparation. The installation handoff is selected only
when the separately derived `signing_ready` state is true. Artifact trust, signing/AVB, Guardian,
installation and device execution semantics are unchanged.

Product Assurance inspected the exact two-file source/test diff and handoff. Build's one journey,
**7/7 focused regressions**, Ruff success and whitespace success are proportional evidence. No broad
suite or duplicate interruption/retry campaign is required. The later creator-approved Adaptive
Online Evidence plan at `b7e7a33` is a separate documentation-only commitment and does not alter
this verdict or grant implementation scope.

### Vision, freeze and safety result

- Recipe Forge through durable local-build completion/reload: **PASS**
- Guided completion truthfulness and next-action routing: **PASS**
- Feature freeze: **PASS — first concrete existing-flow correction only**
- Guardian-only authority, exact-device evidence, UNKNOWN/no-blind-retry and permanent no-relock:
  **PRESERVED**
- Phone, signing, installation, Recovery, publication and release activity: **NONE**

### Approved next bounded task

Run one fresh, no-phone **local candidate to artifact-verification/offline-signing readiness
journey** on Linux using a disposable project, bounded synthetic source and inert host adapters.
Begin from a durable unsigned local candidate and activate the production `Continue to artifact
verification` path. Verify that ROMVERSE rehashes and binds the exact candidate artifacts, inspects
the applicable AVB/signing requirements, and presents either a valid existing offline-signing
request/export route or one precise missing-evidence action. It must not present installation,
Guardian consent or flash readiness as complete, and a reload must preserve the same truthful state.

Record only the first concrete defect and apply only its minimum freeze-safe correction with one
focused regression; if clean, commit evidence only. Reuse current local-build receipts and existing
signing/AVB contract coverage rather than rebuilding the seven-step journey or running a broad
suite. Do not use a phone/emulator, import a real private signature, enroll production trust, build
packages/APKs, touch protected Companion/original-checkout Windows work, begin Guardian/Recovery/
installation, publish, release, force-push or relock. Commit and push, then stop for Product
Assurance.

Windows may separately synchronize only `b77ee3c`, run the one new completed-but-unsigned focused
test plus lint/whitespace, and stop without rebuilding its alpha artifact. Include both this fix and
the already approved neutral Command Deck subtitle naturally in the next normal Windows artifact
batch, not in another immediate packaging cycle.

### Gate status

- Unfamiliar intake and durable local build: **VERIFIED**
- Next core milestone: **ARTIFACT VERIFICATION / OFFLINE-SIGNING READINESS**
- Windows source synchronization of `b77ee3c`: **AUTHORIZED WITHOUT REBUILD**
- Physical device, production signing/trust, installation, Recovery and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 2d27723 — unfamiliar-firmware Guided intake

- Final handoff commit: `2d27723`
- Evidence checkpoint: `41580a949689087618a08fb0930422f45dfeba7d`
- Product Assurance authorization/base: `fc24870124004a250c1bd54b215280fe8c599e74`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — EVIDENCE-DERIVED UNFAMILIAR INTAKE VERIFIED**

### Decision and evidence

The bounded journey satisfies the requested Adaptive Discovery foundation milestone. One synthetic
archive with no exact Device Pack/recipe match passed through the production Guided ROM Studio
controls and existing service boundaries: protected import, automatic bounded inspection,
source-derived Device DNA, persisted Compatibility Matrix, isolated working copy, safe tree and an
inert Recipe Forge readiness handoff.

The classification stayed truthful. `guardian_flash` remained Device DNA `UNCONFIRMED` and Matrix
`Unknown`; it did not become `UNSUPPORTED`, known-incompatible or a terminal stop. The UI continued
safe local evidence gathering while displaying `EXECUTION AUTHORITY: NONE`. No known device name,
Pack, live target, consent, signature, execution or hardware result was invented.

No product-source change exists in this checkpoint, and none is required. Build's single
production-widget journey plus **5/5 focused regressions** is proportional evidence; the repository
diff contains only the Build handoff and passes whitespace validation. The evidence is correctly
classified as simulated UI/service behavior, not packaged-app, hardware, build-output or Recovery
verification.

### Vision, freeze and safety result

- Evidence-derived unfamiliar firmware intake: **PASS**
- `UNCONFIRMED` remains investigable rather than unsupported: **PASS**
- Guided next-action clarity through Recipe Forge readiness: **PASS**
- Feature freeze: **PASS — evidence-only checkpoint**
- Guardian-only authority, exact-device evidence, UNKNOWN/no-blind-retry and permanent no-relock:
  **PRESERVED**

### Approved next bounded task

Run one fresh, no-phone **Recipe Forge to durable local-build completion journey** using a new
disposable project and bounded synthetic unfamiliar firmware/input tree. Start from the existing
Recipe Forge-ready state, create one minimal deterministic recipe through the real production UI,
preview the exact change, apply it transactionally, run the existing local build path, and verify
the durable result/receipt and reopened project state after one normal application-level restart or
service reload. Stop before signing, Guardian, installation or any device action. The final UI must
distinguish local build completion from install/flash success and offer one clear next action.

Use existing tools only. Record the first concrete defect and implement only its minimum
freeze-safe correction with one focused regression; if clean, commit evidence only. Reuse prior
resume/UNKNOWN evidence rather than retesting interruption cases. Do not run a full suite, rebuild
desktop/Companion packages, use an emulator/phone, touch protected Companion or original-checkout
Windows drafts, download tools, sign, publish, release, force-push or relock. Commit and push, then
stop for Product Assurance.

### Gate status

- Unfamiliar firmware evidence intake: **VERIFIED**
- Next core user milestone: **RECIPE FORGE TO DURABLE LOCAL BUILD**
- Physical device, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 7785a25 — Companion offline acceptance blocker

- Final handoff commit: `7785a25`
- Evidence checkpoint: `ac22e2db430ab603d1b8ee0bc891c70b5ff33889`
- Product Assurance authorization/base: `292cd09131c3b788c88a2ef66041e358c8615494`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — EVIDENCE ACCEPTED; UI CORRECTION DEFERRED FOR PROTECTED OVERLAP**

### Decision and independent evidence

The non-rendered offline evidence is sufficient for this bounded pass. Product Assurance inspected
the retained Gradle XML results and confirmed **29/29 passed** with zero skips, failures or errors:
10 Link readiness, 4 navigation and 15 Device Atlas/Knowledge cases. The existing debug APK remains
byte-identical at `9,060,239` bytes and SHA-256
`62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`.

No emulator-rendered claim is accepted: the existing API 35 virtual device exited before ADB
registration and no APK was installed. The production-state checks support only the stated facts:
Home is the safe fallback, disconnected Link does not pretend to be paired, and evidence surfaces
carry zero execution authority.

The identified first-entry defect is valid. Internal-alpha identity is available in About and
authority boundaries exist in deeper surfaces, but neither is concise at the initial Home entry.
The minimum fix belongs in `MainActivity.kt`. Product Assurance independently confirmed that the
original authoritative checkout has protected uncommitted changes in exactly that file, plus the
related navigation source/test. Build correctly made no competing Companion edit. This is a scoped
overlap, not a creator decision and not a reason to stop unrelated product progress.

### Vision, freeze and safety result

- Companion offline state truthfulness: **PASS AT POLICY/JVM LEVEL**
- Rendered first-run journey: **NOT VERIFIED**
- First-entry internal-alpha/no-authority disclosure: **CORRECTION REQUIRED AFTER RECONCILIATION**
- Protected user work preservation: **PASS**
- Feature freeze and Guardian/no-relock invariants: **PRESERVED**
- Physical phone, APK install, Recovery, signing, publication and release activity: **NONE**

### Approved next bounded task

Keep the Companion correction parked until the protected `MainActivity.kt`/navigation work is
reconciled into authoritative history. Continue instead with one fresh, no-phone **unfamiliar
firmware intake journey** on Linux using a new disposable ROM workspace and a bounded synthetic
firmware archive that is not represented by a known device recipe. Drive the real Guided/ROM Studio
presentation from project creation through protected source import, automatic inspection,
evidence-derived Device DNA and Compatibility Matrix/next-action presentation. Verify that
`UNCONFIRMED` permits safe further investigation rather than becoming `UNSUPPORTED`, that no device
or execution authority is invented, and that the user reaches Recipe Forge/readiness or one clear
evidence-gathering action without a dead button or technical loop.

Record only the first concrete defect and apply only its minimum freeze-safe correction with one
focused regression; if the journey is clean, commit an evidence-only handoff. Do not run a full
suite, build/package either desktop app or Companion APK, use an emulator/phone, download tools,
begin Guardian/Recovery/install, sign, publish, release, force-push or relock. Commit and push, then
stop for Product Assurance.

### Gate status

- Companion offline policy baseline: **VERIFIED**
- Companion rendered first entry and disclosure: **WAITING FOR PROTECTED-SOURCE RECONCILIATION**
- Windows and Fedora internal alpha baselines: **VERIFIED; NO REBUILD LOOP**
- Next core product milestone: **EVIDENCE-DERIVED UNFAMILIAR FIRMWARE INTAKE**

## Reviewed checkpoint: 49821cc — refreshed Fedora Guided alpha

- Handoff commit: `49821cc`
- Packaged-run correction: `64ad510532a18b5e26a6feec46791069aee0e8ec`
- Artifact source/authorization base: `b59c3d86a24fdc08d8531ac2414ff6f97b4ee498`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — FEDORA GUIDED ALPHA REFRESH VERIFIED**

### Decision and independent evidence

The refreshed Fedora artifact contains the approved internal-alpha/Guided onboarding correction and
completed one real packaged first-run journey into a truthful no-phone Command Deck. Product
Assurance independently rehashed the canonical ZIP as
`cc9f1c7df7b9147e4a2e8bc1a3ac4b8acb5441ece9fd495854f725322fee9ac0`, confirmed its
`150,947,822`-byte size and mode `0644`, and reran complete ZIP integrity verification successfully.

The journey found one genuine presentation defect: a static subtitle claimed one live device and
one active project while the authoritative cards showed neither. `64ad510` is the minimum correct
repair. It changes only that neutral status text, exposes the label for focused verification and
adds one regression. Build's focused **1/1 passed**, Ruff success and whitespace success are
proportional. Product Assurance also instantiated the corrected production `DeviceCenter` directly
and independently confirmed the false claims are absent.

The exactly-once refreshed ZIP correctly was not rebuilt again. It contains the approved onboarding
correction but predates only the neutral subtitle fix; this limitation is explicit and must remain
visible. The source fix should be synchronized to Windows now and included naturally in the next
cross-platform artifact batch, not trigger another immediate rebuild cycle.

### Vision, freeze and safety result

- Real Fedora packaged first-run Guided/no-phone journey: **PASS**
- Command Deck truthfulness correction: **PASS**
- Feature freeze: **PASS — first concrete presentation defect only**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification and permanent no-relock: **PRESERVED**
- Phone, Recovery, signing, publication and release activity: **NONE**

### Approved next bounded task

Move to one fresh, no-phone **Companion first-run/offline user journey** using the existing approved
debug Companion baseline. Prefer an already available repository-managed emulator; do not download
or install an emulator/system image merely for this checkpoint. If no runnable emulator is already
available, exercise the production Android presentation/state path through the narrowest existing
local JVM/UI harness. Verify that a new user can identify the internal development build, understand
that Companion has no execution authority, reach Home, and see a truthful disconnected ROMVERSE
Link/device state without a dead action, false pairing/readiness claim or technical loop. Record the
first concrete defect and implement only its minimum freeze-safe correction with one focused
regression; if no defect appears, commit evidence only. Do not run the full Companion suite or
rebuild the APK unless a correction requires one later batched artifact refresh. Commit and push,
then stop for Product Assurance.

Windows is separately authorized to synchronize only `64ad510`, run its one focused subtitle test
plus lint/whitespace and stop without rebuilding. No physical phone, device-scoped ADB/Fastboot,
Recovery, Companion execution authority, signing, publication, release, force-push or relock.

### Gate status

- Fedora v0.2.0-alpha.1 onboarding-corrected development artifact: **VERIFIED**
- Windows v0.2.0-alpha.1 onboarding-corrected development artifact: **VERIFIED at `ab0f299`**
- Neutral Command Deck subtitle in current source: **VERIFIED; PACKAGE AT NEXT BATCH**
- Next user-facing milestone: **COMPANION FIRST-RUN/OFFLINE JOURNEY**
- Physical hardware, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 6c8411c — fresh-user Guided onboarding

- Handoff commit: `6c8411c`
- Implementation commit: `eaa3d615912a4eefddd44ee3b032562047ddadc3`
- Product Assurance authorization/base: `4528cea4cb4331afd78392f41edc91c56a8a57e2`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — GUIDED FIRST-RUN INTENT CORRECTED**

### Decision and evidence

The first-run defect was real and the correction is the minimum truthful fix. The wizard now names
the exact internal alpha, explicitly selects Guided Mode, explains that setup performs no phone
action, and hands that typed selection into the settings saved before Command Deck opens. It does
not grant Guardian, device, build, installation or Recovery authority.

Product Assurance inspected the exact source/test diff and confirmed that only application startup,
the setup wizard and one focused launch/settings regression changed. Build's focused result of
**5/5 passed**, Ruff success and Git whitespace success are accepted as proportional evidence. The
Product Assurance checkout does not contain the project's isolated test dependencies, so no
independent pytest result is claimed. Direct inspection confirms the settings handoff flows through
the existing `launch_settings` persistence boundary and the production-widget journey remains
no-engine/no-device with managed auto-start disabled.

The unchanged Fedora and Windows ZIPs remain valid evidence for the earlier alpha packaging and
no-device startup checkpoints, but they predate this correction and must not be represented as
containing the improved onboarding. Refresh each platform artifact exactly once after synchronizing
this approved source; do not repeat broad suites or unrelated journeys.

### Vision, freeze and safety result

- Guided friction and internal-alpha truthfulness: **PASS**
- Feature freeze: **PASS — minimum first-run intent correction only**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification and permanent no-relock: **PRESERVED**
- Phone, Recovery, signing, publication and release activity: **NONE**

### Approved next bounded task

Refresh the Fedora `0.2.0-alpha.1` unsigned development artifact exactly once from this approved
source. Verify its versioned filename, SHA-256/tree and one fresh first-run Guided/no-phone journey
that observes the corrected alpha identity and reaches the truthful Platform Tools or no-device
state. Do not run a full suite or another source correction unless that exact packaged journey finds
a concrete defect. Update the Build handoff, commit and push, then stop for Product Assurance.

In parallel, Windows may synchronize only `eaa3d61` onto the approved Windows branch, run the same
focused launch/settings tests plus lint/whitespace, and refresh its unsigned alpha executable/ZIP
exactly once. No phone/emulator target, device-scoped ADB/Fastboot, Recovery, Companion change,
system installation, signing, publication, release, merge/history rewrite, force-push or relock.

### Gate status

- Fresh-user Guided source journey: **VERIFIED**
- Refreshed Fedora and Windows alpha artifacts containing the correction: **NEXT PLATFORM MILESTONE**
- v0.2 Golden Foundation: **CLOSED**
- Physical hardware, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 677dc0b — cross-platform alpha source convergence

- Handoff commit: `677dc0b`
- Linux convergence implementation: `7ea47d24fab13a4df43745dc95954f425ca3a890`
- Approved Windows source: `a5527a04fe4b6183b903b209206b4eab40220f11`
- Product Assurance authorization/base: `87af66065ea679919d603e056d40dce7b6ee07b5`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — v0.2.0-alpha.1 SOURCE CONVERGED**

### Decision and evidence

The Linux product-source blob for `toolchain_versions.py` is byte-identical to the approved Windows
source blob (`2676599b64d8c104e35fc69d315988b27d69f94b`). Only the short unpublished staging-name
hunk was imported. Windows ACL assertions, branch history and handoff documents were not copied.

Build's focused Linux result of **22/22 passed**, Ruff success and Git whitespace success are
sufficient. The final digest-bound slot, source-byte verification, private staging, atomic
publication, retained receipt and cleanup behavior remain unchanged. Rebuilding the Fedora or
Windows alpha artifacts solely for this host-temporary path correction would add cost without
material user/runtime evidence and is not required.

### Safety and gate result

- Cross-platform internal-alpha source convergence: **PASS**
- Feature freeze: **PASS — exact approved portability correction only**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification and permanent no-relock: **PRESERVED**
- Phone, Recovery, signing, publication and release activity: **NONE**

### Approved next bounded task

Run one fresh ordinary-user **Fedora v0.2.0-alpha.1 first-run/onboarding journey** using the existing
unsigned frozen development artifact and a new disposable workspace. Do not skip onboarding. Verify
that the user can choose Guided mode, understand the internal-alpha/no-device state, reach the
Command Deck, open the existing Platform Tools resolution route if offered, and return to a truthful
ready/no-phone or actionable-host-prerequisite state without a dead button, misleading success or
technical loop.

This is one user-facing acceptance journey, not a broad test campaign. Record the first concrete
onboarding/navigation/readiness defect and implement only its minimum freeze-safe correction with
one focused regression; if no defect appears, commit a truthful evidence-only handoff. Reuse the
current artifact unless a correction makes one source-level rerun necessary; do not rebuild/package
either platform yet. No phone/emulator target, device-scoped ADB/Fastboot, Recovery, Companion
change, signing, publication, release, force-push or relock. Commit and push, then stop for Product
Assurance.

### Gate status

- Fedora and Windows v0.2.0-alpha.1 development artifacts: **VERIFIED**
- Cross-platform alpha source convergence: **VERIFIED**
- Fresh-user Fedora onboarding/readiness: **NEXT USER-FACING MILESTONE**
- Production/public v0.2, physical Recovery and production signing/trust: **NOT AUTHORIZED**

## Reviewed checkpoint: 679b0d8 — Fedora v0.2.0-alpha.1 development build

- Handoff commit: `679b0d8`
- Accepted implementation: `07b5b1721282b2af59abdc8eae0bd152b5361e81`,
  `9e6762aa8cf25b06b64c57486fbe4cd719155d91`
- Product Assurance authorization/base: `817e264cd37e74d0d49b8d627b12b3a523b89cf1`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — FEDORA v0.2.0-alpha.1 DEVELOPMENT ARTIFACT VERIFIED**

### Decision

ROMVERSE now has one coherent internal alpha identity: PEP 440 package/runtime version `0.2.0a1`
and user-facing version `0.2.0-alpha.1`. The visible desktop, Qt metadata and network/update user
agents derive from that authoritative identity. The valid alpha version also passes the corrected
release-order parser and no longer aborts startup.

The single Fedora ZIP is accepted as an unsigned internal development artifact. It is not a signed
release candidate, public release, hardware-verification result or authorization to update an
installed production system.

### Independent repository and artifact evidence

- `07b5b17` changes only authoritative version identity, directly visible desktop identity,
  version-derived user agents, current build guidance and focused bundle tests. `9e6762a` changes
  only the release-version parser and its focused ordering regression. Historical reports, Device
  Pack versions, fixture package/protocol identities, Companion and safety/execution code are
  untouched.
- Numeric PEP 440 `a`, `b` and `rc` stages order before the matching stable version and in their
  expected progression. Existing stable and hyphenated-label formats remain accepted.
- Build's focused result: **42/42 passed**; Ruff and whitespace checks passed. Product Assurance
  independently rehashed the artifact as
  `fb02858c5b8001ab03a8c3015210c74c66c26a00365844a7ab192a02b6116ea9`, confirmed its
  `150947125`-byte size and successfully retested every ZIP member.
- Product Assurance independently reran the frozen application with an empty executable-search path
  and offscreen Qt in a fresh disposable workspace: **startup/no-device smoke passed**.

### Vision, freeze and safety result

- Internal alpha version coherence and truthful development classification: **PASS**
- Fedora runnable artifact and bounded no-device startup: **PASS**
- Feature freeze: **PASS — milestone identity plus directly exposed startup correction only**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification and permanent no-relock: **PRESERVED**
- Phone, Recovery, production trust/signing, publication and release activity: **NONE**

### Approved next bounded task

On `windows-launcher-authorized-work`, synchronize only the approved platform-neutral source/test
commits `3475b45` then `dcd73cc` (durable local-build resume and its exact correction), followed by
`07b5b17` then `9e6762a` (alpha identity and parser correction). Do not copy Linux handoff/assurance
history or merge/rewrite either branch. Resolve only genuine Windows context differences and retain
the already approved Windows launcher and Platform Tools work.

Run the exact focused resume/version/parser regressions on Windows plus lint/whitespace. Then produce
exactly one consolidated unsigned Windows `0.2.0-alpha.1` development build and one matching ZIP,
verify their exact hashes/tree, and run one bounded no-phone startup/no-device smoke. Do not repeat
the full Guided journey or broad suite. Update the Windows Build handoff, commit and push, then stop
for Product Assurance. No phone/emulator target, device-scoped ADB/Fastboot, Recovery, Companion
change, driver/firewall/global PATH change, production signing, publication, release, force-push or
relock.

### Gate status

- Fedora v0.2.0-alpha.1 internal development build: **VERIFIED**
- Windows v0.2.0-alpha.1 consolidated build: **NEXT PLATFORM MILESTONE**
- Cross-platform public v0.2 release: **NOT CLAIMED**
- v0.2 Golden Foundation: **CLOSED**
- Physical hardware, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 96edc08 — corrected local-build durable resume

- Handoff commit: `96edc08`
- Correction implementation: `dcd73cca2fdeedc0992c5dd6793a6297eccd76e9`
- Required correction: `54bdefcdfdeafc34578c64c35ee0b7ab83d47e85`
- Original implementation: `3475b45d653ef2ed9ca49802804f385e6c00cdb5`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — EXACT LOCAL-BUILD INTERRUPTION/RESUME VERIFIED**

### Decision

Both held findings are corrected exactly. A stop already requested at a durable boundary dispatches
nothing and leaves resumable evidence; a request received during a bounded step still pauses only
after that step is observed and checkpointed. Completed logs now have their own exact path, size,
nanosecond mtime and SHA-256 evidence and must survive the same strict revalidation as outputs.

This closes the demonstrated restart loop without adding blind retry, weakening UNKNOWN or granting
any device authority. Conservative UNKNOWN after an already-recorded intent remains the correct
boundary even when the underlying host command may have reported failure, because ROMVERSE cannot
durably prove which side effects preceded that report.

### Independent repository and acceptance evidence

- `dcd73cc` changes only the local-build executor and its focused contract tests; `96edc08` changes
  only the Build handoff. The correction is an exact descendant of `54bdefc` and Git whitespace
  checks pass.
- The pre-intent callback is checked before checkpoint revalidation, intent recording and dispatch.
  The existing post-step check remains after output/log evidence is durably recorded.
- Attempt parsing and validation require one unique log-evidence entry for every completed-step log.
  Resumption verifies exact containment under the versioned log directory, regular non-symlink file
  type, size, mtime and SHA-256 before any next intent.
- Build's focused correction result: **19/19 passed**. Ruff and whitespace checks passed. The earlier
  accepted 66-case affected result and one production-UI simulated journey are not double-counted.
- Schema-three attempt evidence is corrected in place because it was neither approved nor released;
  final successful local-build receipts remain schema two and versions 1/2 remain read-compatible.

### Vision, freeze and safety result

- Existing Guided workflow and restart recovery: **PASS**
- Evidence integrity and exact-prefix continuation: **PASS**
- UNKNOWN-on-uncertainty and zero blind redispatch: **PASS**
- Feature freeze: **PASS — minimum correctness repair only**
- Guardian-only authority, exact-device evidence, consent separation, same-incident Recovery,
  independent verification and permanent no-relock: **PRESERVED**
- Physical phone, ADB/Fastboot target, Recovery, production trust/signing, publication and release:
  **NONE**

### Approved next bounded task

Begin the creator-approved **v0.2.0-alpha.1 development identity** checkpoint on Linux only. Update
the authoritative package/runtime and visible desktop version identity from `0.1.0`/`v0.1` to the
PEP 440 package version `0.2.0a1` and the user-facing label `0.2.0-alpha.1`. Update only directly
coupled build commands, filename expectations and focused version/readiness tests; do not rewrite
historical reports, Device Pack versions, fixture package versions or unrelated protocol versions.

Produce exactly one unsigned Fedora development artifact from the approved source, verify its exact
versioned filename/hash and one bounded startup/no-device smoke, and record it as an internal alpha
development build—not a signed, published or production release. Do not rerun the full suite or a
duplicate Guided/Recovery journey. Commit and push the platform-neutral identity/source changes and
Linux handoff, then stop for Product Assurance so Windows can synchronize the approved local-resume
and alpha identity changes once and perform one consolidated Windows rebuild.

### Gate status

- Fedora local-build interruption/resume: **VERIFIED**
- Windows synchronization of local-resume correction: **BATCH WITH ALPHA IDENTITY AFTER REVIEW**
- Next milestone: **v0.2.0-alpha.1 INTERNAL DEVELOPMENT BUILD**
- v0.2 Golden Foundation: **CLOSED**
- Physical hardware, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: d9f9f9f — local-build durable resume

- Handoff commit: `d9f9f9f`
- Implementation commit: `3475b45d653ef2ed9ca49802804f385e6c00cdb5`
- Product Assurance authorization/base: `9cb181ae3d6359a89569de5278fc816ea0397009`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **CORRECTION REQUIRED — RESUME DESIGN ACCEPTED; TWO EXACT BOUNDARY GAPS**

### Decision

The schema-three local-build attempt, exact completed-step prefix, output hashing, retained-toolchain
binding, UNKNOWN/no-retry handling and reopened Forge presentation are the correct minimum repair for
the demonstrated restart loop. The production-UI simulation is useful and honestly non-consequential.

Approval is held for two narrow mismatches between the claimed contract and the implementation. A
stop request that already exists before a new step may still record intent and dispatch that step,
and completed log bytes are not included in the hash-verified checkpoint even though the handoff
claims that they are. Neither issue warrants redesign, schema expansion beyond the proposed
unreleased version three, a broad suite or another full journey.

### Independent repository evidence

- `3475b45` changes only the local-build attempt/executor, durable inventory, background shutdown,
  Forge presentation and focused tests. `d9f9f9f` changes only the Build handoff. Companion, Device
  Engine, Guardian, Recovery, physical transport, signing and release source are untouched.
- Step intent is durably written before `_execute_step`; a caught post-intent result becomes UNKNOWN
  and no later call can redispatch it. Completed output artifacts are bound by relative path, size,
  nanosecond mtime and SHA-256 and are revalidated before continuation.
- The final successful local-build receipt remains schema two. Proposed attempt versions 1/2 remain
  read-compatible and schema three grants no phone or Guardian authority.
- Build's focused result of **66/66 passed**, Ruff success, one final simulated production-UI journey
  and Git whitespace success are accepted as proportional evidence. Product Assurance could not
  rerun the suite from this checkout because its isolated test environment is not present; the
  source, tests and committed evidence were reviewed directly.

### Required minimum correction

1. Before recording a new `step-intent`, check the cooperative stop callback at the current durable
   boundary. If stop is already requested, leave the existing `ready` or `step-complete` checkpoint
   intact, dispatch zero additional adapter calls and report the normal paused/resumable state. Keep
   the existing post-step check so a request received during a running bounded step pauses after that
   step is observed and checkpointed. Add one focused test proving a pre-requested stop performs zero
   runner calls and remains resumable from zero completed steps.
2. Bind every completed step log to the schema-three checkpoint with the same exact path/size/mtime/
   SHA-256 treatment already used for output artifacts, and revalidate it before resume. A changed,
   missing, linked or out-of-bound log must make the checkpoint invalid and dispatch nothing. Add one
   focused tampered-log regression. Because schema three is not approved or released, correct its
   proposed shape in place rather than opening another migration/version family.
3. Update only the affected Build handoff wording and counts, commit the correction, push the same
   branch and stop for Product Assurance. Do not add a discard/retry UI or reinterpret a known local
   command failure; conservative UNKNOWN after any already-recorded intent remains accepted.

### Acceptance criteria

- Pre-requested shutdown at a durable boundary records no new intent and dispatches no step.
- A request arriving during a step still permits only that bounded step to finish and checkpoint,
  then pauses before the next intent.
- Every completed output and log is hash-bound and revalidated; tamper or disappearance fails closed
  with zero resume dispatch.
- Existing exact-prefix resume, no redispatch, UNKNOWN/no-retry, legacy attempt-read compatibility,
  final schema-two receipt, reopened Forge presentation and durable inventory tests remain passing.
- Run only the directly affected focused tests, lint and whitespace checks. No phone, ADB/Fastboot
  target, Recovery, new feature, broad simulation, full suite, signing, publication or relock.

### Approved next bounded task

Apply only the two corrections above and return the exact checkpoint for review. Windows must not
sync `3475b45` until the corrected Linux checkpoint is approved.

### Gate status

- Local-build durable exact-prefix resume architecture: **ACCEPTED**
- Linux interruption/restart checkpoint: **HELD FOR TWO MINIMUM CORRECTIONS**
- Windows synchronization: **WAITING FOR CORRECTED APPROVED LINUX SOURCE**
- v0.2 Golden Foundation: **CLOSED**
- Physical hardware, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 17750ca — simulated AVB / Guardian boundary

- Handoff commit: `17750ca`
- Product implementation: unchanged at `37e2ee27d9373d90e6a3cd71cb31fcadb64f415b`
- Product Assurance authorization: `12b32d5`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — STRICT PRE-GUARDIAN BOUNDARY VERIFIED**

### Decision

The production UI correctly accepts exact test-only source AVB identity for simulation while keeping
Guardian handoff and flash readiness false. The missing Device Pack write/readback/transition/AVB/
recovery contracts, independent physical recovery evidence, and operation scope are real safety
requirements—not a Guided defect. No correction or broader synthetic Device Pack is warranted.

### Independent evidence and acceptance

- `17750ca` changes only the Build handoff; no product, test, policy, key, adapter, package, or asset
  source changed.
- The journey derived and reloaded the protected source, build, candidate and AVB evidence through
  production services and one inert adapter; it did not inject a Guardian manifest or completed
  authority state.
- Local candidate and simulation-only signer gates passed; Device Pack flash and physical-validation
  gates remained blocked; Guardian handoff, flash readiness and relock remained false.
- The result is clearly labelled `SIMULATED`, reports zero physical targets,
  `production_execution_authority: none` and `phone_changed: false`.
- Correct strict stop without a speculative fix or repeated suite: **PASS**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification, feature freeze, and permanent no-relock: **PRESERVED**
- Phone/device/Recovery/production-signing/release activity: **NONE**

### Approved next bounded task

Shift to one non-duplicative, offline Fedora **SIMULATED interruption-and-resume journey** for the
existing local-build workflow. In a disposable workspace, use valid sanitized source-derived inputs
and inert adapters to begin a local build, interrupt it at one durable boundary, close/reopen the
production UI, and verify that ROMVERSE reloads only committed evidence, never invents success, and
does not blindly retry an ambiguous or incomplete operation. Resume only when the existing contracts
explicitly permit it from the exact verified checkpoint.

Identify the first concrete user-facing recovery/resume defect and implement only its minimum freeze-
safe correction; rerun only the affected segment and focused test. Do not construct additional
Device Pack execution authority, Guardian consent, Recovery success, physical evidence, or production
signing to force progress. If current behavior is already correct, commit the truthful handoff with no
source change. No phone, ADB/Fastboot target, mode transition, signing, publication, release, or
relock. Commit and push, then stop for Product Assurance.

### Gate status

- Simulated local candidate and AVB verification: **VERIFIED**
- Guardian handoff absent required execution/recovery evidence: **CORRECTLY BLOCKED**
- Local-build interruption/restart truthfulness: **NEXT OFFLINE SLICE**
- Physical execution, production trust/signing, publication, and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 44199de — source-derived simulated Forge candidate

- Handoff commit: `44199de`
- Implementation commit: `37e2ee27d9373d90e6a3cd71cb31fcadb64f415b`
- Product Assurance authorization: `68b6902`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — SOURCE-DERIVED LOCAL CANDIDATE PATH VERIFIED**

### Decision

The Forge sequencing correction is sound. Exact input preparation legitimately changes the
source-derived working tree, so freezing that final tree in the same successful background operation
is the correct evidence boundary. It prevents ROMVERSE from rejecting its own newly prepared inputs
while retaining the separate Device Pack execution-plan revalidation before any local build.

The simulated journey produced a reloaded schema-two local-build receipt and byte-verified outputs
without promoting placeholder AVB material into signing, Guardian, Recovery, or execution authority.
That is the correct truthful boundary for this slice.

### Independent evidence and acceptance

- `37e2ee2` changes only `RebuildMetadataWorker` and one focused regression; `44199de` changes only
  the Build handoff. No Device Pack policy, executor contract, Guardian, Recovery, phone transport,
  signing, release, Companion, Windows, or asset source changed.
- The worker refreezes only after `prepare(...)` succeeds and before announcing completion. Existing
  planner hashing and the later exact execution-plan checks remain intact.
- The focused regression recreates the old ordering, adds one source-derived input, runs the worker,
  and proves the new final plan verifies and contains that exact file.
- `git diff --check 68b6902..44199de` passes. Build used one defect reproduction, one corrected
  affected rerun, and one focused test rather than a broad or duplicate suite.
- Simulated local candidate with three verified outputs: **PASS**
- Guardian handoff and flash readiness remain false without valid AVB/signing evidence: **PASS**
- Feature freeze, exact evidence, UNKNOWN, no blind retry, Guardian-only authority, and no-relock:
  **PRESERVED**
- Physical phone/device/Recovery/signing/release activity: **NONE**

### Approved next bounded task

Run one production-UI **SIMULATED** Fedora continuation from the verified local candidate using valid
test-only AVB material and the repository's existing strict, non-consequential adapters. Exercise
candidate AVB verification and the review-only Guardian manifest handoff as far as the current
product truthfully permits. Test keys and placeholder signatures must remain explicitly simulation-
only and must never satisfy production signer, runtime-trust, live-target, consent, Recovery, or
execution authority.

Identify the first concrete user-facing dead end or correctness defect in that existing flow and
implement only its minimum freeze-safe correction. Rerun only the affected segment and focused test.
If the strict product correctly stops before Guardian handoff, record the exact missing evidence
instead of forging a receipt or weakening validation. No real phone, ADB/Fastboot target, physical
mode transition, production key/trust, signing ceremony, Recovery action, publication, release, or
relock. Commit and push the handoff, then stop for Product Assurance.

### Gate status

- Fedora source-derived simulated local candidate: **VERIFIED**
- Simulated AVB and review-only Guardian handoff: **NEXT BOUNDED SLICE**
- v0.2 Golden Foundation: **CLOSED**
- Physical execution, production trust/signing, publication, and release: **NOT AUTHORIZED**

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
