# Shared source-operation session checkpoint

Status: implemented and software-verified desktop checkpoint, 2026-09-05. This is not physical-device
validation, release certification or completion of the twenty-stage master goal.

## User problem removed

The source-declared and rebuilt-ROM installation screens previously owned their worker and evidence.
Closing a screen ended the presentation lifetime, and returning through ROM Studio could prepare a
second route instead of showing the operation already under way. Guided also exposed the same dense
technical controls as Expert, encouraging repeated reviews and circular navigation.

`SourceOperationSession` is now owned by the application for this workflow. It retains the exact
project/source identity, selected phone, immutable reviewed plan and revision, worker, progress,
Stop state, result, phone-mode transition, Android boot observation and recovery handoff. A dialog is
only a presentation attached to that session.

## Implemented behavior

- Guided and Expert display the same live operation. Switching presentation does not recreate a
  plan, worker, result or command and does not grant consent.
- An app-owned operation can be hidden while a write continues. Reopening the same project/source
  attaches a fresh screen to the same worker and evidence.
- A second acceptance while work is already active is rejected without scheduling a second worker
  or replacing the real progress message.
- Changing project/source cannot discard a busy operation. The periodic phone scan and application
  shutdown cannot overlap or implicitly destroy its changing work.
- Opening installation history or the separate Expert image writer while a source mission exists
  reopens that mission instead of starting competing phone work. Closing an idle mission retires it,
  so a reviewed-but-abandoned choice cannot trap ROM Studio in a reopen loop.
- Guided presents one human-readable next action, one compact exact-phone/outcome card and one
  optional **View technical details** control. Raw hashes, the full action table, logs and phone-mode
  controls remain available in Expert.
- A successful measured boot no longer appears as a recovery fault. A failed read-only preparation
  check offers one bounded **Check readiness again** route; an uncertain phone-changing result goes
  to diagnosis and recovery instead of blindly retrying.
- Write completion, Android boot observation, readback, subsystem health and release readiness stay
  separate claims. The UI continues to state that a no-erase request is not a data-preservation
  guarantee.

The existing source inspection, exact-target executor, local transition, local boot, history and
Recovery Bay services remain the authorities. This checkpoint adds no second executor and no
Expert bypass.

## Verification evidence

- An inert production-service integration journey proves one exact 53-action installation while the
  Guided view is hidden, the presentation changes to Expert and a new view attaches. It verifies the
  same plan object, revision, worker, result and command count throughout.
- A real `MainWindow` integration journey proves preparation-to-install dispatch, detachment during
  the active write, application-wide experience switching, exact completion while detached,
  reattachment to the terminal result and intentional retirement on Close.
- Failure coverage proves a read-only inspection error changes to a retry action without entering
  recovery or sending a phone-changing command.
- `scripts/simulate_source_installation.py` drives only visible Guided controls, declines once with
  zero changes, confirms once, observes a stable Android boot, switches the same result to Expert and
  checks the 760-by-720 layout. All artifacts are visibly labelled simulation-only.
- All 624 affected source/candidate/project/local-installation, Guardian, ROM Studio and First Light
  regressions pass after the final lifecycle corrections. The complete application suite passes
  all 2,670 tests with zero failures, errors or skips in 808.157 seconds.
- Ruff passes for every changed runtime, simulation and test file. Approved logo files were not
  edited by this work.

## Deliberate remaining boundaries

- Project source/rebuilt-image preparation still has a dialog-owned worker. Extending the shared
  session across preparation is the next continuity slice.
- The manual individual-image Expert route still uses its established dialog-owned lifecycle.
- The in-memory session survives screen closure, not a process crash or host reboot. Durable
  interruption reconstruction and safe resumability belong to Continuity Core.
- Recovery receives the exact attempted phone and evidence, but autonomous diagnosis/repair and
  safe continuation are not complete.
- No physical phone, installed desktop build, Companion APK, published artifact, website or remote
  repository was changed or exercised for this checkpoint.
