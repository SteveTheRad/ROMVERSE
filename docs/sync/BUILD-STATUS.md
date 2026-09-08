# ROMVERSE Product Assurance Sync

## Linux product checkpoint — requested Simulation completes its inert dry run

### Authoritative checkpoint and scope

- Tested implementation: `85aba5f2ff098b478d5f33dc8c887c281a774d06` — `Complete requested
  Simulation dry run`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Product Assurance approval/base: `280a9a4` — approved fresh Guided continuity and authorized one
  automatic use of the existing bounded dry-run after the user's Simulation request.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Pre-Build Simulation continuation only.
- Exact changed files: `src/romverse/rom/builds.py`, `src/romverse/ui/rom_studio.py`,
  `tests/test_navigation_vocabulary.py` and `tests/test_rom_studio_ui.py`. No other implementation,
  platform or product file changed.

### Exact implemented behavior

- One intentional Command Deck Pre-Build Simulation request now remains active through the already
  approved exact-project working-copy/extraction preparation and then starts the existing `plan`
  worker once. It does not require a second technical Plan button click.
- The existing `RomBuildPlanner` remains the only dry-run engine. At its producer boundary it now
  verifies the protected original, requires current sealed inspection evidence and detects
  project/source/inspection metadata drift before atomically persisting its result.
- ROM Studio accepts the result only through its existing typed producer mapping and independent
  persisted-record equality check. The exact project-bound `BuildPlan` is presented with input,
  partition, tree-digest and Guardian preflight summary, remains execution-locked, and focuses the
  existing Verify plan continuation.
- Reopening Simulation with a structurally exact saved result presents that result without running
  the dry run again. A saved identity mismatch or malformed final record is preserved and stops
  visibly instead of being overwritten.
- A `build-plan.tmp` transaction marks completion unknown. ROMVERSE preserves it, starts no worker
  and offers the existing Build & Proof review path; it never infers success or blindly retries.
- A known planning failure—including fresh protected-source hash drift—records a bounded failure,
  preserves preparation evidence, starts no second worker and keeps the direct Build & Proof
  continuation visible.

### Verification without double-counting

- One focused affected run: **6/6 unique tests passed** across the Simulation UI, representative
  fresh Guided journey, existing ROM Studio handoff and existing locked planner contract.
- Success journey proves exact worker order `working-copy → extract → plan`, visible Simulation
  progress, a durable schema-two typed result, execution lock, valid current tree verification and
  zero additional worker after completion.
- The representative fresh-workspace production-service journey now durably reloads the exact
  project, protected original, inspection, working baseline, contained tree and BuildPlan after one
  initial Simulation request.
- At-most-once evidence proves reopening the same exact saved result starts zero workers. An
  additional interrupted temporary transaction reports unknown, remains on disk and also starts
  zero workers.
- Adversarial source-drift journey modifies only the disposable protected-source fixture after safe
  preparation; the planner rehash fails, no final BuildPlan is written, the contained tree remains,
  and no retry is queued.
- Existing insufficient-resource admission still starts no dry-run because preparation never
  becomes admissible.
- Ruff static check and format check passed for all four changed files. `git diff --check`: passed.
- No broad suite was run. The six-test total is not combined with or double-counted against prior
  checkpoints.

### Classification, safety, platforms and gates

- **Implemented:** request-bound automatic inert planning, producer-bound source/inspection drift
  validation, exact typed-result presentation, saved-result reuse and interrupted/no-retry stops.
- **Simulated/Tested:** 6 sanitized Linux-hosted Qt/store/planner journeys.
- **Hardware Verified:** no. **Released:** no.
- Guided friction removed: one Simulation choice now resolves safe local prerequisites and completes
  the intended bounded dry run without a duplicate technical click. Later tree verification remains
  a distinct visible evidence boundary.
- Guardian/Recovery/safety: the result is an inert execution-locked plan and Guardian preflight
  only. No real build, signing, approval, flash or execution authority exists. Exact-device,
  consent, UNKNOWN-on-uncertainty, no blind retry, independent verification, same-incident Recovery
  and permanent no-relock rules remain unchanged.
- Fedora/Linux: genuinely tested in the existing Fedora Qt development runtime. Windows: not run or
  claimed. Physical Android: not used.
- Feature freeze: compliant existing-journey continuity and correctness work; no parallel engine,
  new screen, format, feature, adapter or device capability was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and existing release gates.
- Current blockers/limitations: Product Assurance has not independently reviewed this checkpoint;
  the dry-run result still requires its separate existing current-tree verification before later
  build boundaries; malformed, drifted or interrupted saved evidence intentionally stops.
- Protected Companion, Windows launcher, Knowledge/UI Design Lab, website and unrelated files were
  not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware/device operation, real build,
  flash/boot, partition/slot/wipe/unlock/lock/relock, package installation, publication and release:
  **none**. External action after final verification: one normal push of this scoped Linux branch
  only; no force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that the existing persisted-record equality boundary plus producer-bound source,
  inspection and project stability checks satisfy typed exact-result validation for this inert
  planning step.
- Confirm that a saved exact plan should be presented without rerunning, while any interrupted temp,
  malformed record or identity drift stops for review with no automatic retry.
- Confirm that focusing the existing Verify plan control is the appropriate next independent
  boundary and that automatic tree verification is outside this checkpoint.

## Linux product checkpoint — fresh Guided project continuity

### Authoritative checkpoint and scope

- Tested implementation: `c15f0d3434591bd667ac26b33fb16554457597c8` — `Advance Genesis
  after project creation`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Product Assurance approval/base: `e0a91f6` — approved the shared local-preparation coordinator and
  authorized one representative production-service fresh-workspace journey.
- Stage: Stage 1 — v0.2 Golden Foundation, first genuine continuity defect in the existing
  Start-ROM-Project → Simulation-readiness journey only.
- Exact changed files: `src/romverse/ui/guided_mission.py` and
  `tests/test_navigation_vocabulary.py`. No other implementation, platform or product file changed.

### Reproduced defect and minimum correction

- The real Command Deck `Start ROM Project` dispatch opened Genesis and project creation persisted
  the exact new workspace correctly, but Genesis refreshed while retaining the now-complete Project
  card. Firmware selection was available only after an unnecessary manual `Next` click. This was
  the first user-visible break in the requested fresh journey.
- The project-creation completion path now reselects the first stage lacking verified evidence,
  matching existing Genesis worker-completion behavior. A successful project creation therefore
  advances directly to Firmware; cancellation and failure behavior remain unchanged.
- The correction is one production-line behavior change. It does not automate firmware selection,
  change source responsibility, modify preparation services or alter Simulation/build semantics.

### Verification without double-counting

- One focused affected run: **3/3 unique tests passed**.
- The new representative MainWindow journey uses the real Command Deck primary button, real Genesis
  action controls, real project/import workers, real project/inspection stores and the approved real
  Simulation coordinator. Only the deterministic human project-name, local-file-selection and
  existing import-acknowledgement inputs are supplied by the harness; no navigation result,
  producer result or durable evidence is mocked.
- Demonstrated chain: fresh workspace → Start ROM Project → exact project manifest → automatic
  selection of Firmware → protected copy and SHA-256 ownership → saved bounded inspection →
  Simulation request → admitted working baseline → contained tree → Build & Proof readiness.
- A newly constructed project store/inspection service reloads the exact protected original,
  inspection, working-copy record and contained tree from disk after the journey. The external
  sanitized fixture remains byte-identical.
- The test proves the only production workers were exact-project `import`, `working-copy` and
  `extract`; no BuildPlan exists before or after the journey, no phone is present, and no modal is
  left open.
- Adjacent focused checks for the Genesis evidence-driven UI and transient new-project cancellation
  also passed.
- Ruff static check passed for both changed files. The changed test file passes Ruff format check.
  `guided_mission.py` retains unrelated pre-existing formatter drift outside this one-line hunk and
  was intentionally not mechanically reformatted. `git diff --check`: passed.
- No previously proven Recipes/Simulation unit journey and no broad suite was rerun. The 3-test
  total is not combined with or double-counted against earlier checkpoints.

### Classification, safety, platforms and gates

- **Implemented:** automatic Genesis continuation from verified project creation to the next
  unverified Firmware stage.
- **Simulated/Tested:** 3 sanitized Linux-hosted Qt/store journeys, including one production-service
  fresh-workspace journey.
- **Hardware Verified:** no. **Released:** no.
- Guided friction removed: a successful project no longer strands the user on a completed creation
  card. Firmware choice remains the intentional next human decision; after source inspection, the
  approved local coordinator resolves preparation and resumes Simulation readiness.
- Guardian/Recovery/safety: no build, plan, device, consent, Guardian, Recovery, durable-result or
  verification boundary changed. Exact-device evidence, UNKNOWN-on-uncertainty, no blind retry,
  independent verification and permanent no-relock remain authoritative.
- Fedora/Linux: genuinely tested in the existing Fedora Qt development runtime. Windows: not run or
  claimed. Physical Android: not used.
- Feature freeze: compliant one-line continuity correction to the existing Stage 1 Guided journey;
  no screen, format, feature, adapter or architecture was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all existing release gates.
- Current blockers/limitations: Product Assurance has not yet independently reviewed this
  checkpoint; firmware selection remains intentionally human-owned; Simulation still stops at
  readiness and does not create/run its dry-run plan automatically.
- Protected Companion, Windows launcher, Knowledge/UI Design Lab, website and unrelated files were
  not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware/device operation,
  build/flash/boot, partition/slot/wipe/unlock/lock/relock, package installation, publication and
  release: **none**. External action after final verification: one normal push of this scoped Linux
  branch only; no force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that selecting the first unverified stage immediately after successful project creation
  is the minimum zero-friction correction and preserves intentional firmware consent.
- Confirm the production-service durable-evidence journey sufficiently demonstrates the approved
  fresh-workspace continuity without rerunning previously proven unit slices.

## Linux product checkpoint — automatic exact-project Simulation preparation

### Authoritative checkpoint and scope

- Tested implementation: `a7c6857098d11a595fe5f627423c57d20894fc94` — `Automatically
  prepare exact Simulation inputs`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Product Assurance approval/base: `e2f6b46` — approved the Recipes coordinator and authorized its
  minimum reuse for existing Pre-Build Simulation continuity.
- Stage: Stage 1 — v0.2 Golden Foundation, one existing Command Deck Pre-Build Simulation
  local-prerequisite gap only.
- Exact implementation files: `src/romverse/ui/rom_studio.py` and
  `tests/test_navigation_vocabulary.py`. No other implementation, platform or product file changed.

### Exact implemented behavior

- The already-approved Recipes-only preparation coordinator is minimally generalized into one
  destination-bound local coordinator shared by exactly `Recipes` and `Pre-Build Simulation`; no
  second preparation engine or persistent authority state was created.
- An exact Simulation request with a protected original and current valid inspection now admits the
  same existing bounded working-copy/extraction producers, whole-sequence storage budget, critical
  finding denial, exact project binding, independently reloaded completion evidence and visible
  progress already approved for Recipes.
- After the contained-tree result passes current readiness, ROMVERSE resumes the original
  Simulation request at existing Build & Proof dry-run readiness and focuses its existing plan
  control. It does not run the plan, generate a BuildPlan or start a build.
- Insufficient resource admission starts no worker or write and retains the exact project in Source
  Lab with a direct Simulation continuation. Known worker failures use the same destination-aware
  bounded-stop path proven by Recipes, preserve verified partial progress and schedule no retry.
- Recipe creation and execution, device compatibility, Guardian authority and all phone operations
  remain outside this coordinator.

### Verification without double-counting

- One bounded affected run: **7/7 unique tests passed** across
  `tests/test_navigation_vocabulary.py` and `tests/test_rom_studio_ui.py`.
- New real offscreen MainWindow success journey: exact project → Pre-Build Simulation → verified
  isolated baseline → verified contained tree → automatic Build & Proof readiness resume. The test
  proves no BuildPlan exists before, during or after this preparation.
- New admission adversary: deterministic insufficient storage starts zero workers, creates no
  baseline/tree/BuildPlan and leaves the exact Source Lab continuation visible.
- Shared-coordinator regressions: all three existing Recipes success, known-failure/no-retry and
  resource-denial journeys passed unchanged.
- Adjacent no-project Command Deck routing and already-ready ROM Studio Simulation/Recipes handoff
  journeys passed in the same seven-test run.
- Ruff static check: both changed files passed. Ruff format check: both changed files passed.
  `git diff --check`: passed.
- No broad suite was run, per the approved focused-test boundary. The seven-test total is not added
  to or double-counted against the prior five-test checkpoint.

### Classification, safety, platforms and gates

- **Implemented:** shared exact-project local-preparation coordination and Pre-Build Simulation
  automatic prerequisite/resume continuity.
- **Simulated/Tested:** 7 sanitized Linux-hosted Qt/store journeys.
- **Hardware Verified:** no. **Released:** no.
- Guided friction removed: an inspected exact project no longer requires two technical preparation
  choices before reaching Simulation dry-run readiness. Remaining intentional stops are missing or
  invalid evidence, critical findings, insufficient resources, producer failure, drift, ambiguity,
  or an already-busy project.
- Guardian/Recovery/safety: no build or device boundary changed. Guardian-only authority,
  exact-device evidence, consent separation, durable result/verification boundaries,
  UNKNOWN-on-uncertainty, no blind retry, same-incident handling and permanent no-relock remain
  authoritative.
- Fedora/Linux: genuinely tested in the existing Fedora Qt development runtime. Windows: not run or
  claimed; Windows launcher work was untouched. Physical Android: not used.
- Feature freeze: compliant correction to one existing Stage 1 continuity path; no new screen,
  format, product capability, adapter or architecture was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and existing release gates.
- Current blockers/limitations: the checkpoint awaits independent Product Assurance review;
  Simulation still requires the user to intentionally choose the existing dry-run action after
  preparation, and unsafe/ambiguous evidence remains an intentional stop.
- Protected Companion work, Windows launcher work, Knowledge/UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, package installation, publication and release: **none**.
  External action after final verification: one normal push of this scoped Linux branch only; no
  force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that the destination-bound generalization preserves the previously approved Recipes
  behavior without introducing a second preparation engine.
- Confirm that automatic resume to current dry-run readiness—without generating or running the
  BuildPlan—is the correct boundary for this Simulation continuity checkpoint.
- Confirm the existing shared known-failure/no-retry coverage plus the new Simulation
  resource-admission stop are proportionate acceptance evidence for this bounded slice.

## Linux product checkpoint — automatic exact-project Recipes preparation

### Authoritative checkpoint and scope

- Tested implementation: `18a0537992b04a8e5e5373fe069da12f70af24a6` — `Automatically
  prepare exact Recipes inputs`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Approved base: `b13481a62fe4d7abd0d2986550318d860cf88b38` — creator Guided Experience
  contract lock.
- Stage: Stage 1 — v0.2 Golden Foundation, one existing Command Deck Recipes automatic-resolution
  gap only.
- Exact implementation files: `src/romverse/ui/rom_studio.py` and
  `tests/test_navigation_vocabulary.py`. No other implementation, platform or product file changed.

### Exact implemented behavior

- An exact selected project with a protected original and current valid structure inspection may
  now satisfy the already-required Recipe Forge contained-tree prerequisite automatically.
- Before starting, ROMVERSE rejects critical inspection findings and proves an extraction budget.
  If an isolated baseline is also missing, admission reserves space for that baseline in addition
  to the extracted tree and retained Guardian reserve. Missing/invalid evidence or insufficient
  storage starts no worker and leaves a direct Source Lab continuation visible.
- After admission, ROMVERSE runs only the existing bounded local `working-copy` producer when
  needed, independently reloads its durable evidence at the existing completion boundary, then
  re-admits and runs only the existing bounded `extract` producer. Each worker remains bound to the
  exact project ID; progress states explicitly state that the protected source and phone are
  unchanged.
- Only the independently accepted contained-tree result resumes the original Recipes request and
  opens the existing Recipe Forge. Navigation creates no recipe and grants no build, approval,
  Guardian, device or execution authority.
- A known producer exception records `FAILED`, preserves any already-verified baseline, returns to
  the focused Source Lab continuation and schedules no retry. Project/evidence drift stops the
  coordinator rather than adopting another project or guessing. Existing UNKNOWN-on-uncertainty
  and interrupted-workspace recovery semantics were not changed.

### Verification without double-counting

- One bounded affected run: **5/5 unique tests passed** across
  `tests/test_navigation_vocabulary.py` and `tests/test_rom_studio_ui.py`.
- Real offscreen MainWindow success journey: exact project → Recipes → measured isolated baseline
  producer → measured contained-tree producer → independently reloaded evidence → automatic return
  to Recipe Forge. The RecipeStore stays empty and no modal appears.
- Real offscreen MainWindow bounded-failure journey: baseline succeeds, extraction producer raises a
  deterministic known failure, baseline remains valid, tree/recipe remain absent, failure is
  visible, and zero retry workers are queued.
- Admission adversary: a deterministic insufficient-resource result starts zero workers and creates
  neither a working baseline nor a tree.
- Adjacent existing no-project Command Deck routing and already-ready ROM Studio handoff journeys
  also passed in the same five-test run.
- Ruff static check: both changed implementation/test files passed. Ruff format check: both changed
  files passed. `git diff --check`: passed.
- No broad regression was run, as Product Assurance explicitly constrained this checkpoint to
  focused affected tests. The five-test total is not combined with or double-counted against any
  earlier suite.

### Classification, safety, platforms and gates

- **Implemented:** exact Recipes local-prerequisite admission, sequencing, producer-result
  revalidation, bounded-stop behavior and automatic destination resume.
- **Simulated/Tested:** 5 sanitized Linux-hosted Qt/store journeys; no device or hardware simulation
  was presented as physical verification.
- **Hardware Verified:** no. **Released:** no.
- Guided friction removed: a safely resolvable inspected project no longer strands the user at two
  technical Source Lab controls. Remaining intentional stops are missing/invalid source or
  inspection evidence, critical structure findings, insufficient storage, producer failure, drift,
  or a busy exact project.
- Guardian/Recovery: no device boundary, Recovery adapter, consent, execution, durable-result or
  verification contract changed. Guardian-only authority, exact-device evidence,
  UNKNOWN-on-uncertainty, no blind retry, same-incident handling, independent verification and
  permanent no-relock remain authoritative.
- Fedora/Linux: genuinely tested in the existing Fedora Qt development runtime. Windows: not run or
  claimed; Windows launcher work was not inspected or modified. Physical Android: not used.
- Feature freeze: compliant foundation/correctness repair to one existing Stage 1 journey; no new
  screen, format, product capability or architecture was introduced.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all existing release gates.
- Current blockers/limitations: Product Assurance has not yet independently reviewed this
  checkpoint; missing evidence and unsafe/insufficient-resource states intentionally remain manual
  evidence-resolution stops; no hardware or Windows claim exists.
- Protected Companion work, Windows launcher work, Knowledge/UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, package installation, publication and release: **none**.
  External action after final verification: one normal push of this scoped Linux branch only; no
  force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that the whole-sequence storage admission, exact-project coordinator and existing
  producer completion checks are sufficient for this reversible local preparation boundary.
- Confirm that a proven producer exception should remain `FAILED` while process/transport ambiguity
  retains the existing `UNKNOWN`/recovery treatment, with no automatic retry.
- Confirm the Guided success resume and bounded Source Lab failure continuation close exactly the
  approved Recipes gap without expanding Stage 1.

## Linux product checkpoint — connected exact-project Recipes handoff

### Authoritative checkpoint

- Product Assurance approval/base: `1f05268` — approved connected Simulation continuity and
  authorized the bounded existing Recipes handoff inspection.
- Creator connected-journey contract remained acceptance criteria only: retain exact context and
  open an existing resolvable prerequisite without weakening consequential safety boundaries.
- Tested implementation: `68c7cf5d6c7d5c44e65dccc905fb55ae80a1fd8b` — `Connect Recipes to
  exact project prerequisite`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck Recipes handoff.

### Reproduced defect and exact correction

- Command Deck's Recipes action always opened Recipe Forge, even when the exact current project
  lacked its contained working tree. ROM Studio truthfully described the prerequisite, but the
  responsible preparation action remained in Source Lab, leaving the user at a non-resolving tab.
- Recipes now retains the exact current project and opens Source Lab when project creation, source
  import, working-copy creation or safe-tree preparation is the current existing prerequisite. The
  appropriate existing control receives focus.
- Once the exact project's protected source and contained tree exist, the same action opens Recipe
  Forge and focuses its existing guided entry. If those inputs are complete but a bounded Studio
  worker is active, Recipe Forge remains visible with the existing truthful wait prerequisite.
- Navigation does not open the recipe designer modal, create a recipe, preview/apply an operation,
  mutate firmware or start any worker.

### Verification without double-counting

- One final bounded run: **4/4 unique focused tests passed** — the new exact-project two-state
  Recipes journey, the existing Command Deck route journey, the adjacent connected Simulation
  journey and the existing ready ROM Studio Simulation/Recipes handoff journey.
- New sanitized real MainWindow coverage proves an unprepared project opens Source Lab on that same
  project with working-copy preparation available; after test-created contained-tree evidence, the
  same project opens Recipe Forge with a truthful `READY` explanation.
- Before and after both navigation actions, `RecipeStore` remains empty, the genuine event ledger
  is unchanged, no ROM Studio worker exists and no modal decision opens.
- Ruff static check: **2/2 changed implementation/test files passed**. Ruff format check: **2/2
  passed**. `git diff --check`: passed.
- No broad regression, package build, screenshot loop or physical-device test was run.

### Classification, safety, platforms and gates

- **Implemented:** exact-project routing to Recipe Forge or its current existing Source Lab
  prerequisite.
- **Simulated/Tested:** four sanitized synthetic Qt widget/store journeys.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction/dead end: a prerequisite no longer leaves the user inside an unusable Recipe
  Forge tab or requires rediscovery of Source Lab/project context.
- This is navigation only. It creates no recipe/result, changes no project/firmware, starts no build,
  infers no compatibility and issues no device command.
- Exact-device/source/project evidence, Guardian-only authority, applicable consent,
  UNKNOWN-on-uncertainty, durable intent/result, no blind retry, same-incident Recovery,
  independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt widget/store journeys verified. Windows: not run or claimed;
  Windows managed-tool recovery work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 journey. v0.2 Golden Foundation
  remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. Continue only from its next bounded existing-journey direction;
do not broaden Stage 1.

### Product Assurance Review Requested

- Confirm direct Source Lab prerequisite focus and exact-project Recipe Forge routing are the
  minimum correction for the existing Recipes dead end.
- Confirm navigation remains strictly inert because the RecipeStore, ledger, worker and modal state
  remain unchanged.

## Linux product checkpoint — connected exact-input Simulation handoff

### Authoritative checkpoint

- Product Assurance approval/base: `0f2d221` — approved Mission Pulse continuity and authorized
  inspection of Pre-Build Simulation first, with Recipes only if Simulation already worked.
- Creator experience contract received during the slice was applied as acceptance criteria only:
  unavailable states must retain exact context and open their existing responsible action without
  weakening any consequential safety boundary.
- Tested implementation: `c7ea82f00f0e9b74344d16e3cddaeb653cf1cfec` — `Connect Simulation
  readiness to exact inputs`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck Pre-Build Simulation handoff.

### Reproduced defect and exact correction

- Command Deck previously labelled Pre-Build Simulation `READY` whenever protected firmware
  existed, while ROM Studio correctly required a saved structure inspection and contained working
  tree. Clicking the apparently ready card then produced `PREREQUISITE` and opened Build & Proof,
  leaving the actual preparation action back in Source Lab.
- Command Deck now receives Simulation readiness from the same current-project ROM Studio contract
  used by the destination. Firmware without complete inputs reports `PREPARE INPUTS`; only the exact
  current project's inspection and contained tree report `READY`.
- A missing-input click retains the exact project and opens Source Lab with focus on the existing
  next responsible control: project creation, source import, structure inspection, working-copy
  creation or safe-tree preparation as applicable. A ready click opens Build & Proof and focuses
  the existing dry-run plan control.
- The busy-operation case retains Build & Proof and its truthful wait prerequisite because its
  inputs are already complete; no operation is cancelled or inferred.
- Recipes was not inspected or changed because a genuine defect was found in the first authorized
  path.

### Verification without double-counting

- One bounded affected run: **29/29 unique tests passed** — the complete Command Deck rendering
  widget suite, the real exact-project Simulation journey, the existing Command Deck route journey
  and the existing ready ROM Studio handoff journey.
- New sanitized real MainWindow coverage proves the same exact project first reports/previews its
  missing contained tree in Source Lab, then reports `READY` and opens Build & Proof after the test
  creates the existing working copy/tree evidence. Both destinations name the same project.
- The test proves navigation preserves the ledger byte-for-byte, starts no ROM Studio worker, opens
  no modal decision and claims only `Execution remains locked` on the ready dry-run path.
- Ruff static check: **5/5 changed implementation/test files passed**. Ruff format check passed for
  the four changed files without inherited drift; `device_center.py` retains unrelated pre-existing
  formatter drift and was not mechanically reformatted.
- `git diff --check`: passed. No broad regression, package build, screenshot loop or physical-device
  test was run.

### Classification, safety, platforms and gates

- **Implemented:** one shared current-project Simulation readiness result plus direct existing
  prerequisite/ready destination selection.
- **Simulated/Tested:** 29 sanitized synthetic Qt widget/store journeys.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction/dead end: the card no longer contradicts its destination, and missing evidence
  opens the owner/action that can provide it without making the user rediscover project context.
- This is navigation/readiness presentation only. It does not automatically prepare inputs, run a
  plan/build, create a mission result, claim compatibility, alter firmware or issue a device command.
- Exact-device/source/project evidence, Guardian-only authority, applicable consent,
  UNKNOWN-on-uncertainty, durable intent/result, no blind retry, same-incident Recovery,
  independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt widget/store journeys verified. Windows: not run or claimed;
  Windows Device Engine work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 journey. v0.2 Golden Foundation
  remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, follow its next bounded existing-journey direction;
do not assume Recipes is next or broaden Stage 1.

### Product Assurance Review Requested

- Confirm sharing ROM Studio's exact current-project readiness result with Command Deck is the
  minimum correct defense against the false-ready handoff.
- Confirm direct Source Lab prerequisite focus and Build & Proof ready focus satisfy the connected
  Guided journey contract without starting work or adding another confirmation.

## Linux product checkpoint — durable Mission Pulse warning visibility

### Authoritative checkpoint

- Product Assurance approval/base: `fbf1f4d` — approved exact Command Deck mission resume and
  authorized the adjacent Mission Pulse/direct Live Operations continuity inspection.
- Tested implementation: `a19d2db60863239b6bb2d8e7d8d8ae77e717a2f5` — `Keep Mission Pulse
  warnings visible`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck Mission Pulse continuity.

### Reproduced defect and exact correction

- Mission Pulse previously displayed an urgent warning only when the newest ledger record itself
  was `FAILED`, `BLOCKED` or `ATTENTION`. A newer ordinary informational note therefore replaced
  the warnings panel with `No unresolved warning` even though the genuine warning remained in the
  verified ledger.
- Mission Pulse now selects the newest genuine warning record from its existing bounded ledger
  view independently of newer information/success records. It continues to show only one warning,
  preserving the existing compact presentation and event ordering.
- The adjacent direct `Open Live Operations` route was inspected and is correct: after leaving an
  exact project/mission Resume view, deliberate Mission Pulse navigation restores the complete
  global ledger, including unrelated genuine records. It was not rewritten or project-scoped.

### Verification without double-counting

- One bounded affected run: **30/30 unique tests passed** — the complete Command Deck rendering
  widget suite plus four focused Command Deck navigation/mission journeys.
- New synthetic ledger/widget coverage proves an older verified Recovery attention remains visible
  after a newer Device Engine information record and the false `No unresolved warning` copy is not
  displayed.
- New real MainWindow coverage proves a scoped current-project Resume view contains only its exact
  mission, then Mission Pulse direct navigation restores both current and unrelated genuine global
  records. The ledger is unchanged and no ROM Studio, Recovery host or online worker starts.
- Ruff static check: **3/3 changed implementation/test files passed**. Ruff format check passed for
  both changed test files; `device_center.py` retains unrelated pre-existing formatter drift and was
  not mechanically reformatted.
- `git diff --check`: passed. No broad regression, package build, screenshot loop or physical-device
  test was run.

### Classification, safety, platforms and gates

- **Implemented:** latest genuine warning selection for the existing Mission Pulse warning lane.
- **Simulated/Tested:** 30 sanitized synthetic Qt widget/store journeys.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: newer routine information can no longer make an existing genuine warning appear
  resolved or absent. The compact pulse still gives one clear next action.
- Mission Pulse and Live Console remain read-only views of producer-recorded evidence. Navigation
  creates no event, progress or result, changes no ownership, starts no worker and grants no build,
  consent, Guardian or execution authority.
- Exact-device evidence, Guardian-only authority, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt widget/store journeys verified. Windows: not run or claimed;
  Windows Device Engine/Build Control work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 status surface. v0.2 Golden
  Foundation remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, inspect only the next adjacent shipped Command Deck
action with a reproducible continuity/dead-end defect; do not broaden Stage 1.

### Product Assurance Review Requested

- Confirm retaining the newest genuine warning independently of later informational events is the
  minimum correct Mission Pulse behavior.
- Confirm the direct Live Operations path remains the intentionally complete global ledger after
  leaving an exact Resume context.

## Linux product checkpoint — exact current Command Deck mission ledger

### Authoritative checkpoint

- Product Assurance approval/base: `50e3eec` — approved exact Command Deck Recovery context and
  authorized the bounded Resume Mission → Live Operations continuity check.
- Tested implementation: `46533cafaa75962c71f7551eb6c0689b7572f292` — `Bind Command Deck
  resume to current mission`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck mission-ledger continuity.

### Reproduced defect and exact correction

- Command Deck previously selected the newest running mission from the entire local ledger. A
  newer event from unrelated Project B could therefore replace Project A's real active mission in
  A's `Resume Mission` card; opening Live Operations then selected the unrelated newest event.
- Command Deck now retains the exact current project ID, derives its active mission only from that
  project's genuine ledger events, and labels Resume Mission from that project-owned state.
- The Resume action independently reloads and revalidates the exact mission/project pair at click
  time. Live Console opens a temporary mission-scoped view containing only records for that exact
  pair; direct Live Console navigation continues to expose the ordinary complete ledger.
- If the current mission becomes terminal or disappears between rendering and the click, ROMVERSE
  does not adopt another project's running mission. It follows the existing truthful current-
  project Genesis fallback without fabricating progress or starting work.
- Global Mission Pulse warnings and accomplishments remain global and unchanged; only active
  Resume ownership and its destination are project-scoped.

### Verification without double-counting

- One affected regression run: **40/40 unique tests passed** — the complete Command Deck rendering
  and Live Console widget suites plus four focused Command Deck continuity journeys.
- New sanitized synthetic widget/store coverage proves that a newer running event for Project B is
  excluded while Project A's exact mission opens alone, the selected project/device remain
  unchanged, both genuine events remain running and byte-for-byte ledger state is unchanged.
- A second adversarial journey proves that if Project A's event finishes after Command Deck renders
  but before the click, Project B is not substituted and the existing Genesis fallback opens for
  Project A with no new ledger event, modal decision or worker.
- Ruff static check: **5/5 changed implementation/test files passed**. Ruff format check passed for
  the four files without inherited drift; `device_center.py` retains unrelated pre-existing
  formatter drift and was not mechanically reformatted.
- `git diff --check`: passed. No broad regression, package build, screenshot loop or physical-device
  test was run.

### Classification, safety, platforms and gates

- **Implemented:** exact current-project mission selection, click-time revalidation and temporary
  exact-mission Live Console view.
- **Simulated/Tested:** 40 sanitized synthetic Qt widget/store tests.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: Resume Mission now opens the one relevant live record directly. A stale rendered
  action returns calmly to the existing Genesis journey instead of showing an unrelated stream.
- Ledger context is read-only navigation evidence. It creates no event or progress, changes no
  ownership, starts no worker and grants no build, consent, Guardian or execution authority.
- Exact-device evidence, Guardian-only authority, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt widget/store journeys verified. Windows: not run or claimed;
  Windows Build Control work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 route. v0.2 Golden Foundation remains
  **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, inspect only the next adjacent existing Command
Deck continuity route with one reproducible defect; do not broaden Stage 1.

### Product Assurance Review Requested

- Confirm project-owned active selection plus click-time exact mission/project revalidation is the
  minimum correct boundary for Resume Mission.
- Confirm the temporary exact-mission view and stale-action Genesis fallback preserve the intended
  zero-friction Guided behavior without hiding the global ledger from direct navigation.

## Linux product checkpoint — exact-device Command Deck Recovery handoff

### Authoritative checkpoint

- Product Assurance approval/base: `0168582` — approved shared exact Command Deck ROM Mission
  entry and authorized inspection of the existing Diagnose/Recover routes.
- Tested implementation: `74092ee41e0ad50d818cd3767cf5382c02bb5a7d` — `Bind Command Deck
  recovery finding to exact device`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck Diagnose/Recover context
  continuity.

### Reproduced defect and exact correction

- `Diagnose Problem` was inspected first and already opens the current selected device's
  read-only Diagnostics owner; its passing path was not rewritten.
- `Recover Device` previously forwarded the actionable finding from Diagnostics by finding ID
  alone. If Diagnostics retained Phone A while Recovery was bound to Phone B, an identical finding
  ID on both phones (for example `storage.capacity`) allowed A's diagnostic context to be displayed
  as B's Recovery context.
- Command Deck now obtains its one explicitly selected device and requires it to match the current
  diagnostic report device before forwarding a finding. Recovery independently verifies the
  expected serial before accepting that context.
- A mismatch opens the existing calm general Recovery intake with `EXACT DIAGNOSTIC NEEDS FRESH
  EVIDENCE`; it keeps the selected Recovery target, current project and incident history unchanged,
  starts no worker and implies no recovery result.

### Verification without double-counting

- Affected regression: **36/36 unique tests passed** — five focused Command Deck/Recovery widget
  journeys plus all 31 Repair UI tests. The focused set includes the reproduced same-finding-ID
  cross-device collision, exact current handoff, general intake, mismatched Recovery evidence and
  existing primary routing.
- The new real-widget test uses a temporary isolated workspace and sanitized synthetic phones. It
  proves Phone A's diagnosis is rejected for selected Phone B, the project stays unchanged, no
  incident is created or duplicated, and no session, host worker or online worker starts.
- Post-audit rerun of the new regression: **1/1 passed** using the current branch source.
- Ruff static check: **4/4 changed implementation/test files passed**. The repository has unrelated
  pre-existing formatter drift in `device_center.py`; it was not reformatted or included.
- `git diff --check`: passed. No broad regression, package build, screenshot loop or physical-device
  test was run.

### Classification, safety, platforms and gates

- **Implemented:** exact-device validation at both Command Deck sender and Recovery owner boundary.
- **Simulated/Tested:** 36 sanitized synthetic Qt widget regressions.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: an unsafe cross-device context now degrades to one actionable, non-modal fresh-
  evidence message rather than a dead end or false plan. The correct-device path remains unchanged.
- Diagnostic context remains evidence only. It grants no Recovery incident, consent, Guardian or
  execution authority and cannot imply durable result, reassessment or verification.
- Exact-device evidence, Guardian-only authority, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt journeys verified. Windows: not run or claimed; Windows Build
  Control work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 route. v0.2 Golden Foundation remains
  **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice until this exact-device
Recovery boundary is independently reviewed.

### Product Assurance Review Requested

- Confirm that validating exact identity at both the Command Deck handoff and Recovery owner is the
  minimum correct defense against stale cross-device diagnostic attribution.
- Confirm the calm fresh-evidence intake is the correct Guided fallback without introducing another
  confirmation or duplicate incident.

## Linux product checkpoint — shared exact Command Deck ROM Mission entry

### Authoritative checkpoint

- Product Assurance approval/base: `e67f289` — approved zero-match ROM Mission handoff and
  completed Device Intelligence ownership sequence.
- Tested implementation: `312b3458b6f8f445f48d05cd83ce2010b9225067` — `Share exact ROM
  mission entry from Command Deck`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck primary ROM project/mission
  continuity.

### Reproduced defect and exact correction

- With one live synthetic device, one exact Pack-matching saved project and an unrelated retained
  ROM Studio project, Command Deck's primary `Start ROM Project` action bypassed the completed
  Device Intelligence ownership boundary and opened Genesis on the unrelated project.
- Command Deck `Build ROM` and `Continue Genesis` now reuse the already-approved Device
  Intelligence `Start ROM Mission` boundary whenever a current selected device and current Pack
  report exist. They therefore receive the same single/multiple/zero saved-project ownership rules
  and the same independent exact device, Device DNA, Compatibility Matrix and Pack/report
  validation.
- If no current Device Intelligence report/selected device exists, the established Command Deck
  behavior remains unchanged: ROM Studio opens its ordinary first-use or retained-project Genesis
  path. No duplicate Guided session, project mutation or worker is introduced.

### Verification without double-counting

- Focused/affected real-widget coverage: **6/6 unique tests passed** — the reproduced Command Deck
  primary-action journey, existing Command Deck routing, exact Device Intelligence handoff,
  single-match ownership, multiple-match selection/cancellation and zero-match transient project
  creation/cancellation.
- The new test uses a temporary isolated workspace and sanitized synthetic device evidence. It
  proves the primary button selects the one exact saved owner, opens exactly one Guided context,
  retains the current device and Pack, carries the current DNA digest and advisory
  `guardian_flash: Unknown` Matrix verdict, excludes the unrelated project and starts no worker.
- Ruff static check: **2/2 changed implementation/test files passed**.
- `git diff --check`: passed.
- No broad regression, package build, screenshot loop or physical-device test was run.

### Classification, safety, platforms and gates

- **Implemented:** shared exact mission entry for Command Deck's existing ROM primary actions.
- **Simulated/Tested:** six focused synthetic Qt widget journeys.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: Command Deck no longer creates a competing ownership path or silently enters an
  unrelated project when current Device Intelligence is available. It opens one shared mission.
- Device/Pack/DNA/Matrix context remains evidence and navigation only. `UNCONFIRMED` remains
  advisory `Unknown`; no compatibility, build, consent, Guardian or execution authority flows.
- Exact-device validation, Guardian separation, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt journeys verified. Windows: not run or claimed; Windows Build
  Control work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 action. v0.2 Golden Foundation
  remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, inspect the next existing Command Deck primary
action with a concrete continuity/runtime defect; do not broaden Stage 1 or cross a consequential
boundary.

### Product Assurance Review Requested

- Confirm that reusing Device Intelligence's completed ownership/evidence boundary is the minimum
  correct way to prevent Command Deck from creating a second inconsistent ROM Mission path.

## Linux product checkpoint — zero-match Genesis new-project entry

### Authoritative checkpoint

- Product Assurance approval/base: `0458aa3` — approved explicit ROM Mission project choice.
- Tested implementation: `2e366b45725ede030e6d9999e866c5b5efaea580` — `Route unmatched
  device into new ROM project mission`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, adjacent existing Device Intelligence Hub zero-match
  `Start ROM Mission` journey.

### Exact behavior

- When the retained ROM Studio project is Pack-mismatched and no saved project matches Device
  Intelligence's current exact Pack, `Start ROM Mission` now routes to ROM Studio and opens the
  existing Genesis `New project` stage instead of stopping or entering the unrelated project.
- This entry is transient until the user completes the existing local project-name action. Genesis
  presents no firmware or Compatibility verdict from the unrelated project and persists no Guided
  state into it. The current live device and exact Pack ID are carried only as a suggestion for a
  potential new project.
- Cancelling the existing project-creation dialog leaves Genesis at `New project`. Closing Genesis
  and returning to Device Intelligence preserves the unrelated selected project, all saved
  projects and all project evidence unchanged.
- A completed existing project-creation action remains the only point at which a new project is
  created; it uses ROM Studio's existing suggested-Pack behavior and then reloads ordinary
  project-bound Genesis state. No project is created, associated, merged or modified merely by
  entering or cancelling this route.

### Verification without double-counting

- Focused and affected Qt widget run: **57/57 unique tests passed** — one new real zero-match
  journey, the three adjacent Device Intelligence ownership/evidence journeys and all 53 ROM Studio
  UI tests. The focused test was rerun once after formatting cleanup only as confirmation and is not
  double-counted.
- The new path uses a temporary isolated workspace and sanitized synthetic device evidence. It
  proves the transient context reports no project, retains the current live target and Pack
  suggestion, shows `AWAITING COMPARISON`, cancels project creation without a new manifest or
  Guided state, and returns to Device Intelligence with the unrelated project intact.
- Ruff static check: **4/4 changed implementation/test files passed**.
- `git diff --check`: passed.
- No broad regression, package build, screenshot loop or physical-device test was run.

### Classification, safety, platforms and gates

- **Implemented:** zero-match routing into the existing transient Genesis new-project stage.
- **Simulated/Tested:** sanitized synthetic Qt widget journey and 57 affected tests.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: zero-match users now receive the existing actionable first project step; cancel
  and return are calm and non-mutating. No new confirmation or product capability was introduced.
- The Pack suggestion, current Device DNA, historical evidence and navigation convenience grant no
  compatibility, build, consent, Guardian or execution authority. `UNCONFIRMED` remains advisory
  `Unknown`.
- Exact-device/DNA/Matrix validation, Guardian separation, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt journey verified. Windows: not run or claimed; Windows work was
  untouched.
- Feature freeze: compliant minimum completion of an existing Stage 1 journey. v0.2 Golden
  Foundation remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. Continue only with the next approved adjacent existing Device
Intelligence journey; do not broaden Stage 1 or cross a consequential boundary.

### Product Assurance Review Requested

- Confirm the transient no-project Genesis context correctly preserves the unrelated current
  project while retaining only suggestion-level live device/Pack context.
- Confirm project-dialog cancellation, mission close and owner return are sufficiently inert.

## Linux product checkpoint — explicit ambiguous ROM Mission ownership

### Authoritative checkpoint

- Product Assurance approval/base: `4e9c772` — approved exact ROM Mission project selection.
- Tested implementation: `f869f59e97aab0854ed8456b8c0dbbabe08305a7` — `Require explicit
  ambiguous ROM project choice`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, adjacent existing Device Intelligence Hub ambiguous
  saved-project ownership journey.

### Exact behavior

- When the current ROM Studio project does not match Device Intelligence's current exact Pack and
  multiple saved projects do, `Start ROM Mission` now presents one local, non-editable project
  choice. Each choice includes its saved name, exact project ID and protected-source filename or
  truthful `firmware not imported` status.
- ROMVERSE continues only with the user's explicitly selected saved owner, refreshes that
  project's current DNA/Compatibility evidence, then passes through the already-approved
  independent Device Intelligence → ROM Studio validation.
- Cancellation remains on Device Intelligence, reports that the choice was cancelled and starts no
  worker. No project or evidence is changed by presenting or cancelling the choice.
- The existing zero-friction automatic path remains limited to exactly one matching saved project.
  Zero matches now stop truthfully on Device Intelligence instead of opening an unrelated current
  project. Zero and multiple matches are never guessed.

### Verification without double-counting

- Focused real-widget coverage: **3/3 passed** — the multiple-match selection/cancellation journey,
  the sole-match automatic journey and the existing exact Device Intelligence mission handoff.
- The new journey uses a temporary isolated workspace and sanitized synthetic device evidence. It
  proves both matching projects are offered, explicit selection enters Guided with the selected
  exact owner, and cancellation retains the unrelated current project while remaining on Device
  Intelligence. No worker starts in either choice operation.
- Ruff static and format checks: **2/2 changed implementation/test files passed**.
- `git diff --check`: passed.
- No broad regression, package build, screenshot loop or physical-device test was run.

### Classification, safety, platforms and gates

- **Implemented:** explicit local owner choice for multiple exact Pack-matching saved projects;
  truthful zero-match refusal.
- **Simulated/Tested:** three focused synthetic Qt widget journeys.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: one choice appears only when ownership is genuinely ambiguous. This is a local
  context selection, not a consequential confirmation; the single-match path remains automatic.
- Project selection grants no compatibility, build, consent, Guardian or execution authority.
  `UNCONFIRMED` remains advisory `Unknown`.
- Exact-device/DNA/Matrix validation, Guardian separation, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt journeys verified. Windows: not run or claimed; Windows work
  was untouched.
- Feature freeze: compliant minimum completion of the existing saved-project ownership journey.
  v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. Continue only with the next approved adjacent existing Device
Intelligence journey; do not broaden Stage 1 or cross a consequential boundary.

### Product Assurance Review Requested

- Confirm the chooser is a proportionate local context decision, the cancellation path is calm and
  inert, and the explicit zero-match refusal closes the remaining ownership guess.

## Linux product checkpoint — exact saved-project ownership for ROM Mission

### Authoritative checkpoint

- Product Assurance approval/base: `47d5055` — approved exact Device Intelligence mission
  handoff.
- Tested implementation: `3ec7026f9168b3ad7a5d123129ff98723406d242` — `Select exact saved ROM
  mission project`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, adjacent existing Device Intelligence Hub
  `Start ROM Mission` saved-project ownership journey.

### Reproduced gap and exact correction

- First-use/no-project behavior was inspected and remains functional: Genesis begins at its
  existing `New project` stage and a newly created project receives the selected device's
  suggested Pack.
- The next adjacent real gap occurred when ROM Studio retained an unrelated current project while
  exactly one saved project matched Device Atlas's current Pack. `Start ROM Mission` opened
  Genesis on the unrelated project even though the correct saved owner was unambiguous.
- Immediately before the already-approved device/DNA/Matrix handoff revalidation, ROMVERSE now
  checks authoritative saved projects. Only when the current project is Pack-mismatched and
  exactly one saved project has the current exact Pack ID does it select that project and refresh
  its current Device DNA/Compatibility evidence. Zero or multiple matches are not guessed.
- Genesis then receives the existing independently validated selected device, current DNA/Matrix,
  Pack report and exact saved project. No project is created, modified, associated or executed by
  the selection itself.

### Verification without double-counting

- Focused real-widget journey: **1/1 passed** with a temporary isolated workspace, sanitized
  synthetic phone evidence, one deliberately unrelated selected project and one exact matching
  saved project. The real button selected the matching owner, refreshed advisory evidence and
  entered Guided with `guardian_flash: Unknown`; no worker started.
- Affected navigation regression: **65/65 unique tests passed** in one combined run. The focused
  journey is included in this total and is not counted again. It also retains first-use,
  stale-report, exact-device substitution, owner-return and existing Device Atlas/Nexus handoffs.
- Ruff static and format checks: **2/2 changed implementation/test files passed**.
- `git diff --check`: passed.
- No broad suite, package build, screenshot loop or physical-device test was run.

### Classification, safety, platforms and gates

- **Implemented:** unambiguous saved-project selection for the existing ROM Mission entry.
- **Simulated/Tested:** sanitized synthetic Qt widget journey and 65 affected tests.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: the user no longer lands in a clearly unrelated project when one exact saved
  Pack owner exists. Ambiguous ownership is not guessed. No new prompt or confirmation was added.
- `UNCONFIRMED` remains advisory `Unknown`; project convenience grants no compatibility, consent,
  Guardian or execution authority.
- Exact-device/DNA/Matrix validation, Guardian separation, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt journey verified. Windows: not run or claimed; Windows work was
  untouched.
- Feature freeze: compliant minimum correction to an existing Stage 1 journey. v0.2 Golden
  Foundation remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, inspect the next repository-defined adjacent
Device Intelligence journey without broadening Stage 1 or crossing a consequential boundary.

### Product Assurance Review Requested

- Confirm that auto-selecting only one exact Pack-matching saved project is the correct
  zero-friction ownership rule, while leaving zero/multiple matches unguessed.

## Linux product checkpoint — Device Intelligence starts an exact ROM Mission

### Authoritative checkpoint

- Approved base: `43c133ea0260a04e4994dc50ad91c153c363d718` — runnable Linux Stage 1
  milestone approved by Product Assurance.
- Tested implementation: `78009cb89080f3e21421667bb31b4518dc9888cf` — `Preserve Device
  Intelligence mission context`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Device Intelligence Hub `Start ROM Mission`
  handoff into shared ROM Studio/Guided state.

### Exact product correction

- A real widget journey exposed that Device Atlas already transferred the current Pack report and
  selected live device into ROM Studio/Guided, but omitted the current Device DNA digest and
  Compatibility Matrix verdict from the visible/shared mission evidence.
- `Start ROM Mission` now revalidates the current report against the selected device's
  manufacturer, model, product and codename, the current persisted Device DNA profile, and any
  current DNA-bound Compatibility Matrix before navigation.
- ROM Studio independently revalidates the one selected transport identity, report/device match,
  current persisted DNA digest, live-device evidence and advisory Compatibility Matrix binding.
  A same-model/different-device substitution is rejected and returned to Device Atlas before
  Genesis opens.
- The successful handoff visibly retains the privacy-masked selected target, current Device DNA
  digest, matched Pack/report and `guardian_flash` Compatibility verdict. Shared Guided evidence
  now includes the current DNA and advisory Matrix digests; `UNCONFIRMED` remains `Unknown`, never
  inferred compatible or terminally unsupported.
- Returning from ROM Studio to Device Atlas preserves the selected device, matched Pack, exact
  report and current Device DNA owner context. No new feature, action, confirmation or authority
  surface was added.

### Verification without double-counting

- One focused end-to-end Qt widget journey: **1/1 passed** after formatting. It uses a temporary
  isolated workspace and sanitized synthetic Xiaomi evidence, creates current source-bound Device
  DNA and a Compatibility Matrix, clicks the real `Start ROM Mission` button, inspects the actual
  shared Guided context, returns through the real owner/navigation signal, and adversarially tries
  a same-model/different-device substitution.
- One combined affected regression run: **139/139 unique tests passed** — 64 navigation vocabulary,
  53 ROM Studio UI and 22 Guided mission tests. The focused journey is included in this total and
  is not counted again.
- Ruff static check and format check: **3/3 changed implementation/test files passed**.
- `git diff --check`: passed.
- No broad suite, package rebuild, screenshot loop or physical-device test was run.

### Classification, safety and Guided behavior

- **Implemented:** exact Device Intelligence mission-context validation and visible/shared
  evidence continuity.
- **Simulated/Tested:** the synthetic widget journey and 139 affected tests above.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction/dead ends: successful context now remains visible and available to Genesis; stale
  or substituted context calmly returns to Device Atlas with a specific stopped-handoff message.
  No extra user confirmation was introduced.
- Compatibility Matrix evidence is explicitly advisory and grants zero execution authority.
  `guardian_flash` remains `Unknown` for missing execution evidence. Guardian remains the only
  execution gate.
- Exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no blind retry, independent
  verification, same-incident Recovery and permanent no-relock are preserved.

### Platform, freeze, version gate and external actions

- Fedora/Linux: implementation and actual offscreen Qt widget journey verified.
- Windows: not run or claimed; Windows/launcher work was untouched.
- Feature freeze: compliant correction to an incomplete existing Stage 1 user journey; no new
  capability, Pack, adapter, route or autonomous behavior.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and remaining release gates.
- Remaining limitations: this is sanitized synthetic evidence only; it proves no physical-device,
  firmware, build, consent, Guardian execution, installation or Recovery result.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware copy/import from user data,
  build execution, flash/boot/update, partition access, slot change, wipe/erase/format,
  unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped implementation and this
  repository handoff to the existing Linux branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, continue the same Device Intelligence milestone to
the next repository-evidenced incomplete existing action; do not broaden Stage 1 or cross a new
consequential boundary.

### Product Assurance Review Requested

- Confirm that independently validating the selected device plus current DNA/Matrix at the ROM
  Studio boundary is the minimum correct closure for this existing handoff.
- Confirm that visibly retaining an `Unknown` advisory compatibility verdict preserves the intended
  investigable `UNCONFIRMED` behavior without implying Guardian or execution authority.

## Linux correction checkpoint — fatal native file chooser fallback

### Authoritative checkpoint

- Base: `9b054b6997404e18993efa3f8b92adac23d3e935` — runnable Linux Stage 1 journey.
- Tested implementation:
  `30d157d1e050b6b6d15847ca995e9640b6dfff10` — `Fall back from unsafe Linux file dialogs`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, minimum Fedora runtime crash correction.

### Reproduced incident and cause

- Steve used the visible source application launched by Build and selected the Guided project flow
  that opens `Import original firmware`.
- The fatal record at
  `build/visible-stage1-fc34291/logs/crash/runtime-fault.log` binds the abort to
  `RomStudio._import_original()` → `QFileDialog.getOpenFileName()` at 18:29:11 local time.
- Build had deliberately removed the ordinary host `PATH` from that visible process to make ADB and
  Fastboot undiscoverable. GTK's native chooser then tried to start its `bwrap` image-loader sandbox
  helper by name, could not find it and asserted/aborted the entire process. `/usr/bin/bwrap` exists
  on the host; this was an invalid constrained launch environment, not firmware corruption or a
  Python exception in ROMVERSE's project logic.
- The interrupted workspace strictly reloads one project, `Hyperos 4`, with no protected original.
  No source selection, copy, import, extraction or project mutation had begun when the chooser
  aborted, so the saved project is intact.

### Exact correction

- Before creating `QApplication`, Linux startup now checks whether `bwrap` is discoverable. If it is
  unavailable, ROMVERSE sets Qt's application-wide `AA_DontUseNativeDialogs` safety attribute so all
  38 current file/folder chooser call sites use Qt's built-in chooser rather than entering the fatal
  GTK native path.
- When `bwrap` is available, normal Linux native chooser behavior is unchanged. Non-Linux platforms
  are explicitly unchanged. No device, project, firmware, Guardian, Recovery or authority logic was
  altered.

### Verification without double-counting

- Focused launch/settings and Guided candidate Desktop tests: **11/11 unique tests passed**.
- New tests prove missing `bwrap` selects the Qt fallback and that non-Linux startup remains
  unchanged.
- Exact constrained GUI reproduction: with `bwrap`, ADB and Fastboot all absent from `PATH`, a real
  `QFileDialog.getOpenFileName()` opened under the configured Qt fallback, was cancelled by timer,
  returned `("", "")` and exited normally instead of aborting.
- Ruff static check: **2/2 changed files passed**.
- Ruff format check: **2/2 changed files passed**.
- `git diff --check`: passed. No broad suite or package rebuild was run.
- The corrected source app is visibly running from a new isolated workspace
  `build/visible-crash-fix-9b054b6` with no device tools in its process path; its runtime fault log
  contains only the normal startup marker.

### Classification and safety

- **Implemented:** conditional Linux non-native chooser fallback.
- **Simulated/Tested:** 11 focused tests plus one exact constrained real-GUI chooser reproduction
  and a fresh visible corrected-source launch on Fedora.
- **Hardware Verified:** none. No Android transport was used.
- **Released:** no. The prior unsigned development package was not rebuilt or published here.
- Guided impact: the Import-original action now falls back safely instead of terminating the app
  when the native chooser's helper is missing. Cancellation returns to the same Guided project.
- Guardian-only authority, consent separation, exact-device/evidence rules, UNKNOWN/no-blind-retry,
  independent verification, same-incident Recovery and permanent no-relock are unchanged.

### Platform, freeze, preservation and external actions

- Fedora/Linux: exact crash cause reproduced and corrected fallback verified.
- Windows: behavior explicitly unchanged by the platform condition; no Windows runtime claim.
- Feature freeze: compliant minimum correctness fix; no feature or execution surface was added.
- v0.2 Golden Foundation remains **CLOSED** pending independent review and remaining release gates.
- Protected Companion files, Windows work, UI Design Lab, website and unrelated user files were not
  modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, firmware copy/import/extraction, APK action,
  flash/boot/update, partition access, slot change, wipe/erase/format, unlock/lock/relock,
  installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped correction and handoff to the
  existing Linux branch only; no force-push.

### Next proposed Build task

Allow Steve to repeat the same visible Guided import action in the corrected app. Continue only if a
new reproducible application defect appears; do not re-enter device or packaging work for this fix.

### Product Assurance Review Requested

- Confirm the conditional application-wide Qt chooser fallback is the minimum correct defense for
  the observed fatal GTK dependency failure and does not alter normal Linux or Windows behavior.

## Linux checkpoint — runnable Stage 1 desktop and Guided journeys

### Authoritative checkpoint

- Source checkpoint: `fc342914868a938f7ba9dfc5108a01f130a1b43a`, including the newly completed
  external-package evidence boundary.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, runnable Fedora Desktop and inert Guided acceptance.

### Product result

- The actual current source application launched through the documented `python -m romverse`
  entry point, initialized a new isolated workspace and remained stable. Its visible acceptance
  instance is running from `build/visible-stage1-fc34291`; ADB and Fastboot were deliberately absent
  from that process environment, so it cannot scan or operate a physical phone.
- The documented installed-style smoke initialized a fresh workspace, loaded 22 verified Device
  Packs, 170 known fixes and 281 offline evidence records, exposed all 19 desktop routes, exercised
  the actionable Time Machine empty state, created a project/working copy/snapshot and reopened all
  tracked bytes exactly.
- The representative inert Guided Recovery journey completed the existing production boundaries:
  Scan → Match → Prepare → Consent → Result → Reassessment → Verification. Three test-only adapter
  actions completed; result and reassessment remained distinct from final verification. No external
  process, production adapter, persistent test trust, automatic retry or physical target existed.
- Every current top-level navigation destination, Guided-visible nested feature, Command Deck launch
  card, exact owner/return handoff, Guided/Architect shared state boundary and representative no-tool,
  no-phone or stale-evidence action was exercised through the targeted real-widget acceptance set.
  All visible tested actions either performed their inert/read-only function or presented their
  existing truthful actionable boundary. No new inert button, crash, silent failure, navigation loss
  or Guided dead end was found.

### Verification without double-counting

- Actual source entry release-smoke startup/shutdown: **passed**.
- Installed-style production smoke: **passed once**. This is acceptance-harness evidence, not added
  to the pytest count.
- Manual inert Guided Recovery script: **passed once**. Its matching pytest coverage was included in
  the targeted test run and is therefore not counted again.
- Targeted desktop/navigation/action regression: **108/108 unique tests passed** in one combined
  run. It covered navigation vocabulary, command palette, workspace shell, app launch/settings,
  dashboard rendering, Guided Recovery simulation and candidate-installation Desktop behavior.
- Frozen executable launch smoke: **passed once**.
- No full Python suite, repeated packaging loop, screenshot loop or physical-device suite was run.

### Runnable Fedora development artifact

- Built once on Fedora 44 x86-64 with Python 3.14.7 and PyInstaller 6.22.2.
- Runnable executable:
  `build/frozen-stage1-fc34291/ROMVERSE/ROMVERSE`, SHA-256
  `9f3e225384244b121cebac56fc79d76407187201d25d99ee4a2cb22208b70a9f`.
- Portable unsigned archive:
  `dist/ROMVERSE-Desktop-0.2.0-alpha.1-linux-x86_64-stage1-fc34291.zip`,
  **150,981,736 bytes**, SHA-256
  `8b817aad6548519f02130e697935e65feb2a56371a6b23fe7301a88987280b6b`.
- Packaging verification passed for **460 files** and **360,288,306 expanded bytes**. The archive is
  a local internal-development artifact only; it was not installed, signed, uploaded or released.

### Classification and safety

- **Implemented:** current Stage 1 source plus the approved external-package evidence slice at the
  source checkpoint above. This evidence-only milestone adds no further application source change.
- **Simulated/Tested:** 108 unique targeted UI tests, two distinct desktop launch smokes, one
  installed-style smoke, one inert Guided journey and one frozen-bundle verification on Fedora.
- **Hardware Verified:** none in this checkpoint. The earlier Fastboot acceptance was not repeated.
- **Released:** no. The new package is unsigned, local and explicitly not a release.
- Guardian-only authority, consent separation, exact-device/evidence rules, UNKNOWN-on-uncertainty,
  no blind retry, independent verification and same-incident Recovery remain unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override or route.

### Guided, platform, freeze and version gate

- Guided friction/dead ends: none reproduced in the exercised no-phone, missing-tool, inert-device,
  candidate-preparation, Recovery or exact-context navigation paths. Consequential controls remain
  disabled until their own evidence/authority boundaries are earned.
- Fedora/Linux: source launch, isolated workspace initialization, persistence, all 19 routes, focused
  user actions, inert end-to-end Recovery and current frozen package verified.
- Windows: not run or claimed. Separate Windows work remains on its own branch and was not merged.
- Feature freeze: compliant. No post-v1 feature, speculative architecture or unapproved UI Design
  Lab work was introduced.
- v0.2 Golden Foundation remains **CLOSED**. This is runnable-development and simulated/inert
  acceptance, not physical execution, signing or release evidence.

### Preservation, blockers and external actions

- Protected Companion files, Windows launcher/convergence work, local UI Design Lab, website and
  unrelated user files were not modified, staged, discarded or committed.
- No Linux runtime blocker or tested Stage 1 Guided dead end remains from this acceptance pass.
  Physical-device-changing and signed-release gates remain intentionally outside this milestone.
- Physical phone access, ADB/Fastboot invocation, APK action, file transfer, flash/boot/update,
  partition access, slot change, erase/wipe/format, unlock/lock/relock, root/debloat, production
  signing, installation, publication and release: **none**.
- External network action after verification: one normal push of this handoff to the existing Linux
  branch only; no force-push and no publication.

### Next proposed Build task

Continue with the next concrete Linux usability defect only when repository evidence identifies one.
Do not manufacture a rebuild/test loop, merge the isolated UI Design Lab, operate a phone or cross a
new consequential boundary without its own authorization.

### Product Assurance Review Requested

- Confirm the source, installed-style, navigation/action, inert Guided and frozen-bundle evidence is
  sufficient for the current runnable Linux Stage 1 development milestone without re-running a full
  suite.
- Confirm the intentionally tool-less visible launch preserves the no-phone boundary while giving
  Steve a real current application to inspect.

## Linux checkpoint — bounded external-package metadata and untrusted-procedure inventory

### Authoritative checkpoint

- Product Assurance authorization/base: `c0de9b2` — approved corrected Fastboot round trip, with
  this package-evidence task queued after the separate Windows convergence handoff.
- Windows convergence prerequisite: `3936d934224294544981c505aba98275c910cd60` exists on
  `origin/assurance/windows-core-convergence`; it was inspected as a prerequisite only and was not
  merged or modified by this Linux checkpoint.
- Tested implementation commit:
  `bc6e0ef66399df2fbfed0e9418c8d8931c254122` — `Inventory external package evidence safely`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, bounded read-only external package evidence.

### Exact implementation

- `ExternalFirmwareIntakeService` now inventories only four root-level, case-insensitive metadata
  names from the already admitted and hashed ZIP descriptor: `BUILD-INFO.txt`,
  `CUSTOMIZATION-MANIFEST.tsv`, `SHA256SUMS` and `android-info.txt`. Each admitted member records
  exact path, bounded size and SHA-256. Only an explicit identity-field allowlist can be parsed;
  every parsed value remains package-declared and unverified.
- `.sh`, `.bat`, `.cmd`, `.ps1` and the Android updater-script path are recorded separately as
  untrusted procedure presence by exact path, bounded size and SHA-256 only. Procedure bodies are
  never persisted, parsed into actions, adopted as routes or executed.
- ZIP directories are safely ignored. Relevant ambiguous/case-folded duplicate paths, unsafe paths,
  symlink/special-file entries, encryption, malformed or non-UTF-8 metadata, duplicate identity
  declarations, bounded-size/count overflow, command-like or relock identity text, and a declared
  SHA-256 mismatch reject before either durable receipt is written.
- The strict inventory loader rejects extra/hidden fields, boolean schema confusion, unbound
  manifest paths, malformed members, source-receipt drift and altered record digests. It grants no
  build, device or execution authority and permanently records bootloader relock as `never`.
- ROM Studio renders metadata claims as `UNVERIFIED`, procedures as `NEVER EXECUTED`, and the full
  build/install/Guardian/flash boundary as `LOCKED`. The untrusted evidence label is forced to plain
  text so package values and paths cannot become UI markup.
- The durable-schema compatibility inventory now declares both the existing external intake receipt
  and the new external package metadata record as version-1, strict, fail-closed evidence formats.

### Deterministic verification

- `tests/test_external_firmware_intake.py`: **19/19 unique tests passed**.
- `tests/test_rom_inspection.py`: **32/32 unique adjacent regression tests passed**.
- `tests/test_durable_schema_inventory.py`: **6/6 unique schema checks passed**.
- Total: **57/57 non-overlapping tests passed**. No broad suite was run or double-counted.
- Ruff static check: **5/5 changed source/test files passed**.
- Ruff format check: **5/5 changed source/test files passed**.
- `git diff --check`: passed.

### Real source evidence

- One permitted read-only reinspection used the existing in-place file
  `adbb99b9d6e6c3e6-HyperOS4-Xiaomi17ProMax-Debloated-CustomRom.zip`; it was not copied, extracted,
  modified or reopened through a replacement path.
- Exact source: **11,797,532,065 bytes**, SHA-256
  `adbb99b9d6e6c3e62520c144d8b841ff6f34543feddf2969cfc38f4acf90f89a`, complete ZIP inspection,
  68 entries, zero critical findings and zero warnings.
- The package contains no member from the four-name metadata allowlist. Therefore it produced no
  package identity facts and no manufacturer, device, build, Android, region, channel or base claim.
  That absence remains explicitly `UNCONFIRMED`; ROMVERSE does not infer identity from procedure
  names or contents.
- Eleven untrusted procedure members were inventoried: four `.sh`, five `.bat` and two `.ps1`
  files. The exact durable list retains only path, size and SHA-256; it contains no procedure body.

| Package-relative path | Bytes | SHA-256 |
| --- | ---: | --- |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/flash_all.sh` | 5,330 | `589afffba7bc1e3528f936caeb9fe3bfd43da8d4017d0b5d4562c6f9e2be41ac` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/flash_all_except_data_windows.bat` | 211 | `f4b58a3dc91d5a0d66a41c6439c332c6b5bf71c78ee664bed2c4bbdbe7cfd4bb` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/flash_all_windows.bat` | 134 | `974945bf7168b7d1e53016a749cbfe08f24a4c8a9ae9f90056e52b0e075385e4` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/post_boot_check.ps1` | 1,461 | `b451a9ac15f9c3af8a0d16ebd878d5c52279014b7b03383b9c94bec1869739f0` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/post_boot_check.sh` | 1,239 | `a78ca4a8c8dadcc2879d8c0e964ae3f61899e345cba97837903d1b4dffd7341f` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/post_boot_check_windows.bat` | 145 | `b8c077cdcaf685f610f84b21a24eda0f3f73a9fac63f57d92ede493066bd305e` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/repair_signed_root_vbmeta.sh` | 1,353 | `760e2c855253c33e0b7adc8b59dcc65041801fdf2f25efbba7c86babcb932817` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/verify.bat` | 223 | `650ffb3c955a745d6b4e8f42197fe37d34ff67fdd0b1f6c0b058a638bda59d82` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/verify.ps1` | 1,139 | `9886ee971c960dea27e4559f0908f2d8505cd1f2b7f86c16f883651fc53b875d` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/verify.sh` | 294 | `19fb9dc3af66d882c38e1cd634a8ab35500df1d0be19cbc49f22ec64903d53c3` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/windows_flash_common.bat` | 4,061 | `d7736caeafe87d466908463a8b15efeca67da09e879fed7a648f26892859e9cb` |

- Inventory digest: `6613af442b27157a4116fc150e5a1f72e7cf7602c3d7453a520055215d7e0b54`.
- Durable external intake receipt digest:
  `782b1e5e2ca167e71d72939b611e35c242bbe30d607fec48578e998e91a755f2`.
- Evidence was written only inside the ignored disposable workspace
  `build/external-metadata-inventory-c0de9b2`; the external package stayed at its original path.

### Classification and safety

- **Implemented:** strict metadata/member inventory, procedure-presence evidence, durable loader,
  locked/plain-text ROM Studio presentation and schema declarations.
- **Simulated/Tested:** 57 deterministic tests on Fedora Linux plus one production-service read of
  the real external package.
- **Hardware Verified:** none in this checkpoint. No phone, emulator, ADB or Fastboot target was
  accessed. The earlier approved Fastboot round trip was not repeated.
- **Released:** no. Nothing was packaged, installed, signed, published or released.
- Guardian-only authority, exact evidence, UNKNOWN-on-uncertainty, no blind retry, independent
  verification and same-incident Recovery rules are unchanged. The inventory is evidence-only and
  cannot create a build, consent, live-target, Guardian, Recovery or execution route.
- Bootloader locking/relocking remains permanently prohibited and has no valid path.

### Guided, platform, freeze and version gate

- Guided now exposes the useful evidence without adopting package procedures or creating another
  decision. No new Guided loop or dead end was found; absence of recognized metadata remains calm
  and truthful rather than being labelled incompatible.
- Fedora/Linux: implementation, UI boundary, durable reload and real-source service path verified.
- Windows: not run or claimed here. The separate Windows convergence checkpoint was only confirmed
  present on its remote branch.
- Feature freeze: compliant. This is the previously approved minimum evidence/correctness slice;
  it adds no format/vendor support, dynamic route, adapter, device command or execution capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance review and later explicitly
  approved boundaries.

### Preservation, blockers and external actions

- Protected Companion files, Windows launcher/convergence source, website, Adaptive work and all
  unrelated user files were not edited, staged, discarded or committed.
- Remaining limitation: the real package supplies no allowlisted metadata identity. Its relationship
  to any phone/source contract remains unconfirmed, and all consequential controls remain locked.
- Physical phone operation, ADB/Fastboot command, APK action, file transfer, firmware execution,
  flash/boot/update, partition read/write, slot change, erase/wipe/format, unlock/lock/relock,
  root/debloat, package installation, signing, publication and release: **none**.
- External network action after verification: one normal push of the scoped implementation and
  handoff commits to the existing Linux branch only; no force-push and no unrelated push.

### Next proposed Build task

Stop for independent Product Assurance review. Do not adopt any inventoried procedure, infer package
identity, operate a phone or begin another consequential Stage 1 slice.

### Product Assurance Review Requested

- Confirm the four-name metadata allowlist, strict identity fields and failure behavior preserve the
  evidence-only boundary without turning absence into incompatibility.
- Confirm that retaining procedure path/size/hash only, combined with plain-text UI and zero
  authority, closes the approved untrusted-procedure inventory milestone.

## Linux correction checkpoint — bounded Fastboot source reacquisition

### Authoritative checkpoint

- Product Assurance correction/base:
  `1a33372cac002c6142b8ac0d86eb71b099ef8c57` — `Require bounded Fastboot return reobservation`.
- Tested implementation commit:
  `03dc954fc0c5ec7f113c9696b6358c3500ab4349` — `Bound Fastboot source reacquisition`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, minimum Fastboot return-plan correctness correction.

### Exact correction

- `LocalDeviceTransitionService` now treats a successful but completely empty Fastboot product
  response as one narrowly typed transient observation. It permits at most one fresh,
  non-dispatching reacquisition; that reacquisition performs a new exact-target discovery plus new
  product and mode reads and reuses no historical Device Engine fact.
- A Fastboot-source transition plan can now be created only after **two complete, identical** live
  observations agree on exact serial, product identity and known bootloader/Fastbootd mode.
- A second empty product, absent/duplicate/changed target, changed product or mode, missing mode,
  failed discovery, failed product command, timeout, malformed/conflicting value or tool drift still
  rejects before plan creation and before any reboot command.
- The general Fastboot parser was not widened. Arrival observation and executor revalidation remain
  strict. No historical/pseudonymous identity was converted into live execution authority.

### Verification

- Focused `tests/test_guardian_local_transition.py`: **43/43 unique tests passed**.
- New adversarial coverage proves:
  1. one successful-empty product read may be followed by two complete identical observations;
  2. repeated empty product reads stop after one reacquisition with no reboot;
  3. discovery failure, product-command failure and missing mode do not reacquire or reboot;
  4. changed product or bootloader/userspace mode rejects with no reboot.
- Ruff static check: **2/2 changed source/test files passed**.
- Ruff format check: **2/2 changed source/test files passed**.
- `git diff --check`: passed.
- No broad or overlapping regression suite was run or double-counted. The firmware was not hashed
  or inspected.

### Hardware disposition

- The correction was implemented, tested and committed before any possible hardware use, as
  required.
- Steve manually returned the phone from the earlier stopped attempt, then explicitly authorized a
  fresh Fastboot acceptance when needed. Build ran one complete corrected production-path round
  trip with no retry.
- Reconnect-safe Device Engine observation first re-established the same pseudonymous Android
  `popsicle`. One reviewed Android-to-bootloader plan then completed and sealed journal
  `0e57c25452224b978fa29fe90cd45912.json`, digest
  `ca436f6393e045a82136f67b7bd3451ee68398391cec9421d432b26eac169325`.
- The fixed Device Engine Fastboot scan found exactly one bootloader target and no ADB target. It
  reported `popsicle`, slot `a`, and unlocked bootloader; all five authorized fixed variables were
  queried once. The pseudonymous Fastboot passport digest is
  `a436de0dae35b4fdd522f50c7d33d06778f128f5351a964d2a6c515824c477cd`.
- The corrected return review then earned **two complete identical fresh Fastboot source
  observations** before plan creation. No transient empty response occurred in this hardware run,
  so the one-reacquisition branch remains adversarially software-tested rather than hardware-hit.
- Exactly one reviewed Fastboot reboot returned the same pseudonymous phone to Android. Journal
  `b546399e5ab648cda8f0f6257045d914.json` completed with
  `command_completed=true`, `arrival_verified=true`, `phone_state_uncertain=false`, and digest
  `6865b376662edb1f96fd4cac6c79d5f9b64dd4fb9467112c4711f69484f9149c`.
- A new, uncached reconnect-safe Device Engine completed two Android discovery cycles and confirmed
  USB Android state, product/codename `popsicle`, and HyperOS `OS4.0.0.32.XPBCNXM`. The final
  privacy-safe passport digest is
  `0d1dc13d75ba5053e39a61090a74102e347657c64d0608a0128bc191cd2ae3cd`.
- The acceptance recorded exactly **104 redacted Guardian operations**: **102 read-only** bounded
  discovery/identity/arrival observations and **2 state-changing reboot commands**. All had
  measurable non-timeout results; the complete active/archive audit chain passed at sequence 181.

### Classification

- **Implemented:** bounded one-time successful-empty product reacquisition and two-identical-source
  observation requirement.
- **Simulated/Tested:** 43 deterministic transition tests on Fedora Linux, including the required
  new adversarial cases.
- **Hardware Verified:** one complete corrected Android → bootloader Fastboot → Android production
  round trip on the same pseudonymous `popsicle`, including two-identical Fastboot source review and
  final uncached reconnect-safe Android identity. The transient-empty reacquisition branch itself
  was not encountered on hardware.
- **Released:** no. Nothing was packaged, signed, installed, published or released.

### Guardian, Recovery and Guided impact

- The correction removes the identified one-read transient dead end without permitting a reboot on
  incomplete identity. Guided may reacquire once silently, then remains truthful and actionable.
- Plan creation, one-use consent, executor revalidation and command dispatch remain separate. The
  reacquisition grants only source-observation evidence.
- UNKNOWN-on-uncertainty, no blind retry, exact-device binding, same-incident attribution,
  independent verification and Guardian-only authority remain unchanged.
- Bootloader locking/relocking remains permanently prohibited and has no valid path.
- No Fresh Live Target, compatibility, source, installation, executor, Recovery or partition
  authority was created.

### Platform, freeze and version gate

- Fedora/Linux: correction implemented and deterministically verified.
- Physical Android: complete corrected round trip and exact final Android return verified on the
  connected Xiaomi 17 Pro Max.
- Windows: not tested or claimed.
- Feature freeze: compliant. This is the minimum Product Assurance-required correctness correction,
  with no new product capability or expanded parser/command surface.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance review and any separately
  approved hardware acceptance.

### Preservation and external actions

- Protected Companion files, Windows launcher work, website, Adaptive work, external firmware and
  unrelated user files were not edited, staged, discarded or committed.
- Physical phone actions after the correction commit: exactly one ADB reboot to bootloader, one
  Fastboot reboot to Android, and bounded allowlisted ADB/Fastboot observations. No dispatch was
  repeated.
- APK action, file transfer, firmware/source action, flash/boot-image/update, partition enumeration
  or read/write, fetch/upload, slot change, erase/wipe/format, unlock/lock/relock, root/debloat,
  signing, publication and release: **none**.
- External action after verification: one normal push of the scoped correction and handoff commits
  to the existing Linux branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance. Do not run another phone command or begin the queued external-package
metadata task until the latest verdict is reviewed.

### Product Assurance Review Requested

- Confirm the one-reacquisition maximum and two-complete-identical observation rule close the
  transient product-read dead end without weakening exact live identity authority.
- Confirm the complete corrected hardware round trip and final uncached Android observation satisfy
  this recovery acceptance while the transient-empty branch remains correctly classified as
  software-tested only.

## Linux hardware checkpoint — Fastboot round trip stopped fail-closed

### Authoritative checkpoint

- Product Assurance authorization/base:
  `46cda9e3780857d7aa33af02926dac0cf1aefa7f` — `Approve popsicle Fastboot identity round trip`.
- Evidence checkpoint:
  `d02d459aae302326d5a5d2cfc29701a8d313887b` — `Record fail-closed Fastboot transition evidence`.
- Final handoff: the follow-up commit containing this exact identifier on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, bounded physical device-mode transition and Fastboot
  identity acceptance.
- Working tree before the attempt: clean and synchronized with the remote branch. The live
  ROMVERSE UI session was confirmed closed before the transition service started.

### Exact measured result

- The production reconnect-safe Device Engine first re-established exactly one authorized USB ADB
  `popsicle` target and matched its sealed pseudonymous identity.
- `LocalDeviceTransitionService` created a one-use, tool-hash-bound Android-to-bootloader plan and,
  under the creator's exact consent recorded by Product Assurance, sent one ADB
  `reboot bootloader` command. The command returned success and the bounded arrival observer
  durably verified the same pseudonymous `popsicle` target in bootloader Fastboot.
- Transition journal `7f76f05f75eb4776b67c7d8b75518823.json` is `completed`, with
  `command_completed=true`, `arrival_verified=true`, `phone_state_uncertain=false`, and sealed
  digest `03d2b5201e8d9fbd92536ae7dd7139eb3d6e755da22557dde8a718dc4fe7d5b0`.
- One production `DeviceEngine.scan()` Fastboot observation then found no simultaneous ADB target,
  exactly one Fastboot target, product/codename `popsicle`, and bootloader rather than Fastbootd.
  It invoked only the fixed `product`, `current-slot`, `unlocked`, `secure`, and `is-userspace`
  variables. Product and bootloader mode were established; slot, unlock and secure values remained
  explicitly unconfirmed because the transport did not return parseable values for those fields.
- The Fastboot observation was persisted through the existing privacy-safe Device Intelligence
  store under the same pseudonymous key `ad74e54831f21bf55d75`, record digest
  `b75b42f09e7ba5a46633a00f684ac08e2817a4d35c9c583799f85fd33cd419d7`, and exact literal-product
  Pack match `xiaomi.popsicle.hyperos4.os4.0.0.23`.
- Before the authorized return command, `LocalDeviceTransitionService.inspect()` correctly
  re-observed the source transport. Fastboot discovery still returned success, but its immediately
  following exact `getvar product` result contained no value parseable by the transition contract.
  The service therefore rejected the return plan with: `The selected phone is no longer in its
  reviewed mode. Refresh devices and try again.`
- No return plan, return consent or Fastboot reboot command was created. In accordance with the
  no-blind-retry rule, Build issued no retry, alternative reboot or further device command. The last
  verified phone state is bootloader Fastboot; its state after the rejected revalidation was not
  guessed.

### Focused acceptance evidence

- **1/1 bounded physical round-trip acceptance attempted; 0/1 completed.** The Android-to-Fastboot
  half and fixed identity scan passed; the Fastboot-to-Android half was rejected before command
  dispatch. This is a truthful partial hardware result, not a completed round trip.
- The attempt produced exactly **75 redacted Guardian records**: **74 read-only observations** and
  **1 state-changing reboot**. Every recorded command was within the authorized transition or fixed
  identity surface and returned a measurable result; no timeout or runner exception occurred.
- The fixed production Fastboot identity scan itself used exactly **7/7 read-only operations**:
  one ADB discovery, one Fastboot discovery and the five approved `getvar` values.
- The complete active/archive Guardian chain passed strict verification at active sequence 77.
- No broad, overlapping or package test suite was run. The 11.8 GB firmware was not rehashed.

### Classification

- **Implemented:** no application code changed. Existing Device Engine, Local Device Transition,
  Device Intelligence and Guardian audit paths were exercised unchanged.
- **Simulated/Tested:** none claimed; this was a real physical target.
- **Hardware Verified:** Android-to-bootloader arrival and one fixed Fastboot identity observation
  are verified for this phone. Fastboot-to-Android return and a complete round trip are **not**
  hardware verified.
- **Released:** no. Nothing was signed, published, installed or released.

### Blocker and Product Assurance impact

- **New blocker:** the return transition cannot currently earn a fresh source-mode plan because a
  Fastboot product probe that immediately followed a successful fixed Device Engine scan returned
  no parseable product value. Product Assurance should determine whether this is expected transient
  transport behavior requiring a bounded non-dispatching observation strategy, a parser/protocol
  mismatch, or an external phone/tool condition. Build must not fix or retry it under this stopped
  hardware authorization.
- Guided impact: the phone can remain at the bootloader screen after the safe rejection. Guided
  needs a truthful recovery instruction and must never loop or silently retry a reboot command.
- Guardian correctly prevented the second mode change when fresh identity authority could not be
  re-earned. Historical/pseudonymous identity did not substitute for the missing live product fact.
- The result is not an execution `UNKNOWN`: the only dispatched reboot command completed and its
  requested bootloader arrival was verified. The proposed return command never reached INTENT or
  dispatch. The phone's later current mode is operationally unconfirmed until reassessed.
- No Fresh Live Target receipt, source compatibility, plan consent, executor admission, Recovery
  incident, adapter action, partition evidence or flash authority was created.
- Permanent no-relock, exact-device binding, consent separation, UNKNOWN-on-uncertainty, no blind
  retry and independent verification remain preserved.

### Platform, freeze and version gate

- Fedora/Linux: partial real hardware verification as stated above.
- Windows: not tested or claimed.
- Feature freeze: compliant. This is an evidence-only acceptance attempt with no new feature,
  product code, route, Device Pack, adapter or execution capability.
- v0.2 Golden Foundation remains **CLOSED**. The incomplete return and identified transition
  revalidation blocker require Product Assurance review before further device work.

### Preservation and external actions

- Protected Companion files, Windows launcher work, website, Adaptive work, external firmware and
  unrelated user files were not edited, staged, discarded or committed.
- Physical phone action: one ADB reboot to bootloader plus bounded read-only ADB/Fastboot identity
  and arrival observations.
- Fastboot reboot to Android: **not dispatched**. Retry or alternative reboot: **none**.
- Flash, boot image, partition enumeration/read/write, fetch/upload, slot change, erase/wipe/format,
  unlock/lock/relock, APK action, root/debloat, source authority, signing, publication and release:
  **none**.
- External action after documentation: one normal push of this evidence handoff to the existing
  Linux branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance. Do not issue another device command or begin the queued external-package
metadata task until the latest verdict is reviewed. If the user needs the phone immediately, use a
manual hardware-button reboot rather than an unreviewed host-side retry.

### Product Assurance Review Requested

- Review why the transition service's fresh Fastboot product observation became unparseable after
  the immediately preceding production Device Engine identity scan succeeded.
- Define the minimum safe reassessment/recovery path for returning this exact phone to Android
  without converting a missing live fact into guessed authority or a blind retry.

## Linux hardware checkpoint — one fresh read-only popsicle observation

### Authoritative checkpoint

- Product Assurance authorization/base:
  `bccc0b1eb7fc3585a8c65006d07076f334f6b2d8` — `Authorize read-only popsicle observation`.
- Evidence checkpoint:
  `60e7e85b260b9ae368bd81733c02febdc014babe` — `Record read-only popsicle hardware evidence`.
- Final handoff: the follow-up commit containing this exact identifier on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, production Device Engine / Device DNA read-only
  hardware acceptance.
- Working tree before the checkpoint: clean and synchronized with the remote branch.

### Exact observed result

- The production `DeviceEngine.scan_reconnect_safe()` path observed exactly one stable USB ADB
  target over two required unchanged discovery cycles. The second cycle completed the existing
  fixed, allowlisted detail probes; both cycles also confirmed that no Fastboot target was present.
- The target resolved as Xiaomi 17 Pro Max: manufacturer/brand `Xiaomi`, model `2509FPN0BC`,
  product/codename `popsicle`, SoC `SM8850`, Android `17`, HyperOS
  `OS4.0.0.32.XPBCNXM`, build ID `CP2A.260605.016`, security patch `2026-08-01`,
  China firmware region, active slot `a`, Virtual A/B and dynamic-partition evidence.
- Read-only safety state reported bootloader `unlocked` and Verified Boot `orange`. Battery was
  100%; the bounded live telemetry contained no warning.
- The live build fingerprint was observed by the allowlisted aggregate-property probe and used by
  the existing firmware relationship assessment. The privacy-safe passport deliberately excludes
  the raw fingerprint and serial. Device DNA records the result as
  `SAME INSTALLED OTA BUILD • 17OS4.0.260902.070444909.QCPECN.S`.
- `DevicePackRegistry` matched `xiaomi.popsicle.hyperos4.os4.0.0.23` version `0.1.1` to the live
  device identity. The current project does not have that exact source-bound Pack/execution
  contract, so Device DNA correctly reports `guardian_flash: UNCONFIRMED` and the Compatibility
  Matrix reports `Unknown`; execution remains locked.
- The local Device Intelligence passport is bound to pseudonymous device key
  `ad74e54831f21bf55d75` and sealed record digest
  `1217107ab1e2b287d3576fc3a672c93b6e14aea58de2325444fb8e98d32af092`.
  Strict reload succeeded and a byte scan of the affected evidence, identity and Guardian audit
  stores confirmed that the raw serial was not persisted.
- Device DNA digest:
  `73016d262e6957bdc7383a861fa6933b7a15dbec9db05fcbfa2a0b399092601b`.
  Compatibility Matrix digest:
  `4cd90f4391d03c6f0ef9166cbec78f9072088229814f1045bc2a55d2df944e02`.

### Focused acceptance evidence

- **1/1 production hardware acceptance path passed.** This is the only acceptance total for this
  checkpoint; no broad, overlapping or package suite was run.
- Guardian recorded exactly **14/14 allowed read-only operations** for this acceptance: two ADB
  discovery calls, two Fastboot discovery calls, and ten fixed ADB detail probes. Every operation
  was redacted in the audit; expected absent-package probes returned a normal non-zero result and
  did not alter the phone.
- The complete active and archived Guardian audit chain passed verification; the current active
  ledger contains 28,005 entries.
- Passport, Device DNA and Compatibility Matrix passed their strict production loaders after the
  observation.
- The acceptance reporting wrapper referenced the Pack-resolution boolean by its wrong attribute
  name after all phone probes and evidence validations had completed. No probe was repeated; the
  final sanitized report was reconstructed exclusively from the sealed local receipts. This was a
  harness-only reporting mistake, not an application defect or uncertain phone result.

### Classification

- **Implemented:** unchanged production Device Engine, privacy-safe Device Intelligence, Device
  DNA and Compatibility Matrix paths were exercised; this checkpoint adds no product code.
- **Simulated/Tested:** none claimed. The result came from a real physical Android target.
- **Hardware Verified:** yes, limited strictly to one fresh read-only ADB identity/state and
  project-compatibility observation of the connected `popsicle` phone on Fedora Linux.
- **Released:** no. Nothing was signed, published, installed or released.

### Guided, Guardian and Recovery impact

- The production Fresh Live Target receipt service is intentionally Fastboot-only. Because mode
  change was prohibited and the phone remained safely in Android/ADB, no Fresh Live Target receipt
  was created. This checkpoint therefore ended at reviewed Device DNA evidence.
- No recommendation, preparation, plan consent, executor admission, adapter dispatch, durable
  execution result, Recovery incident, reassessment or post-repair verification was created.
- The observed exact device identity does not become flash authority. Missing exact source-bound
  execution evidence remains `UNCONFIRMED` / `Unknown`, never guessed or misreported as proven
  incompatibility.
- Bootloader locking/relocking remains `UNSUPPORTED` / `Known Incompatible`, permanently
  prohibited, and has no authorization path.
- Exact-device evidence, Guardian-only authority, UNKNOWN-on-uncertainty, no blind retry,
  same-incident attribution and independent verification remain unchanged.

### Blockers, platform status and freeze

- Blockers/failures in the authorized observation: none.
- Fedora/Linux: genuine production-path hardware verification passed on the current host.
- Windows: not tested or claimed by this checkpoint.
- Guided friction/dead ends: none introduced; Fresh Live Target and all later consequential stages
  remain truthfully unavailable in Android/ADB mode.
- Feature freeze: compliant. This is evidence-only acceptance of existing Stage 1 behavior, with
  no new feature, architecture, route, Device Pack, adapter or execution capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance review of this hardware
  evidence and later explicitly authorized work.

### Preservation and external actions

- The protected Companion files, Windows launcher work, website, Adaptive work, external firmware
  package and unrelated user files were not edited, staged, discarded or committed.
- Physical action: read-only ADB/Fastboot discovery and allowlisted ADB identity/state probes only.
- Phone reboot/mode change, APK installation, file push/pull, backup, settings write, root/unlock,
  debloat, partition access, consent, Guardian admission, adapter execution, flash/wipe, signing,
  publication, release and relock: **none**.
- External action after verification: one normal push of the scoped evidence handoff to the existing
  Linux branch only; no force-push.

### Next proposed Build task

Stop for independent Product Assurance review. The previously approved bounded external-package
metadata and untrusted-procedure inventory remains queued and was not run concurrently. Do not
begin it or another consequential slice until the latest repository verdict is reviewed.

### Product Assurance Review Requested

- Confirm that the real observation remained within the exact read-only authorization and that the
  pseudonymous passport plus sealed Device DNA/Compatibility evidence are sufficient for this
  checkpoint.
- Confirm the truthful boundary: Device DNA was hardware-verified, but Fresh Live Target, consent,
  execution and Recovery remain unverified and unavailable.

## Authoritative checkpoint

- Product Assurance correction/base:
  `56f0c4f117124f5718bfabdbcea7c174f0787359` — `Require same-handle firmware inspection`.
- Tested implementation commit:
  `aad0f2a934d069623b658a957632c4bee1002ec6` — `Bind external inspection to hashed descriptor`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, external firmware evidence-integrity correction.
- Working tree at handoff: clean. Ignored local artifacts from the previously reviewed packaged
  checkpoint remain local and unchanged.

## Exact correction

Product Assurance found that external intake hashed one open descriptor, closed it, then reopened
the pathname for container inspection. A transient directory-entry replacement could therefore have
combined one file's SHA-256 with another file's structure evidence.

The minimum correction changes four files:

- `src/romverse/rom/inspection.py` adds a bounded seekable-stream inspection entry point. Container
  detection plus ZIP/TAR/raw inspection now operate on the supplied stream. The existing path API is
  retained as a compatibility wrapper that opens once and delegates to the shared implementation.
- `src/romverse/rom/external_intake.py` keeps the original no-follow regular-file descriptor open
  continuously through identity validation, SHA-256 hashing, rewind, container detection, bounded
  metadata inspection, final descriptor identity validation, and final pathname identity validation.
- `tests/test_external_firmware_intake.py` proves the selected path is not reopened for inspection
  and that replacing its directory entry cannot mix replacement metadata with the original hash.
- `tests/test_rom_inspection.py` proves the stream entry point preserves ZIP, TAR, and raw results.

The replacement adversary test observes the original descriptor's SHA-256 and `super` signal even
after the pathname is replaced by a different ZIP containing `vbmeta`; the final pathname binding
then rejects the intake and writes no receipt. This preserves internally consistent evidence and
fails closed.

## Verification

- Focused external-intake and directly affected inspector regression: **38/38 unique tests passed**.
- Required adversarial groups:
  1. selected content path cannot be reopened after descriptor admission: passed;
  2. directory-entry replacement cannot mix evidence and fails before receipt persistence: passed;
  3. ZIP/TAR/raw results plus no-copy/no-authority receipt behavior remain unchanged: passed.
- Ruff static check: **4/4 changed source/test files passed**.
- Ruff format check: **4/4 changed source/test files passed**.
- `git diff --check`: passed.
- The real 11.8 GB firmware was **not rehashed**.
- The prior packaged journey was **not replayed**.
- The Fedora package was **not rebuilt**.
- No broad or overlapping regression suite was run or double-counted.

## Classification

- **Implemented:** same-open-handle hash/container/structure evidence binding and final fail-closed
  path identity check.
- **Simulated/Tested:** deterministic fixture-based ZIP/TAR/raw and adversarial directory-entry
  replacement tests on Fedora Linux.
- **Hardware Verified:** no. No phone, emulator, ADB target, Fastboot target, or other device was
  used.
- **Released:** no. No artifact was signed, published, installed, or released.

## Guided, Guardian, and Recovery impact

- Guided presentation and decisions are unchanged; no new prompt, interruption, route, or dead end
  was introduced.
- External evidence remains `UNCONFIRMED`; Compatibility Matrix remains `Unknown` until exact
  evidence exists.
- The receipt remains evidence-only and creates no protected source, build input, Device Pack match,
  device selection, consent, Guardian authority, Recovery incident, execution, or durable result.
- Exact-device evidence, Guardian-only authority, UNKNOWN-on-uncertainty, no blind retry,
  same-incident attribution, independent verification, and permanent no-relock remain unchanged.
- Bootloader locking/relocking has no authorization or execution path.

## Blockers and platform status

- Blockers/failures: none in the authorized correction.
- Fedora/Linux: correction implemented and deterministically tested on Fedora 44 x86-64.
- Windows: not tested or claimed by this checkpoint.
- Physical Android: not connected, observed, or operated.
- The previously reviewed unsigned Fedora artifact remains superseded for this source correction;
  Product Assurance explicitly prohibited rebuilding it at this checkpoint.

## Freeze and version gate

- Feature freeze: compliant. This is the exact evidence-integrity correction required by Product
  Assurance and adds no device, build, Recovery, Adaptive, Companion, Windows, or product capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance approval and later authorized
  Stage 1 work.

## Preservation and external actions

- Protected Companion files, Windows launcher work, Adaptive work, website, logos, and unrelated
  user changes were not edited, staged, discarded, or committed.
- Firmware copy/extraction/mutation/hash/build/sign/execute, physical phone operation, APK
  installation, system package installation, publication, release, and force-push: **none**.
- Remote action after verification: one normal push of the scoped implementation and handoff commits
  to the existing `linux/stage1-desktop-readiness` branch only.

## Next proposed Build task

Stop at this committed checkpoint for Product Assurance. Do not begin another consequential slice.
Continue only from the next top verdict in `docs/sync/PRODUCT-ASSURANCE.md`.

## Product Assurance Review Requested

- Confirm that the original open descriptor now binds SHA-256, container detection, structural
  evidence, and final identity validation without a pathname reopen.
- Confirm that the three focused regression groups close the identified TOCTOU gap while preserving
  the external receipt's zero-authority boundary.
