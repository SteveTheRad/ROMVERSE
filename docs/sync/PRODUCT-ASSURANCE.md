# ROMVERSE Product Assurance

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
