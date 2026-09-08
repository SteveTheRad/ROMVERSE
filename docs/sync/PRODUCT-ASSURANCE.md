# ROMVERSE Product Assurance

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
