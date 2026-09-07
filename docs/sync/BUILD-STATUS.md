# ROMVERSE Build Status

## Authoritative checkpoint

- Implementation commit: `3475b45d653ef2ed9ca49802804f385e6c00cdb5`.
- Product Assurance authorization/base: `9cb181ae3d6359a89569de5278fc816ea0397009`,
  approving handoff `17750ca`.
- Handoff checkpoint: the commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, offline Fedora local-build interruption/resume.
- Milestone: production Forge Control now resumes a non-consequential local build only from a
  durable, exact, hash-verified completed-step boundary and refuses every ambiguous in-flight
  result without redispatch.

## First concrete defect

- A process interruption could leave the versioned candidate directory partially populated before
  the old end-of-build attempt receipt existed.
- After reopening, Forge displayed the ordinary Build action. Pressing it then rejected the existing
  output directory and told the user to create a fresh plan, but the deterministic current plan
  retained the same identity. The user was stranded in a build/retry loop.
- The old flow also lacked a durable intent boundary, so it could not distinguish a fully committed
  local step from a command whose completion became ambiguous.

## Exact implementation changes

- `LocalDeviceBuildExecutor` writes schema-3 `romverse.local-build-attempt` evidence atomically:
  initial readiness, exact next-step intent before dispatch, and the observed completed-step
  checkpoint only after its log and output hashes are durable.
- Each checkpoint binds the current project, plan and digest, Device Pack build contract, exact
  toolchain manifest, ordered completed-step prefix, output paths, sizes, mtimes and SHA-256 values.
- Resume revalidates the current source/plan contract, retained toolchain, every checkpoint artifact
  and every completed log. It continues at the first uncompleted exact planned step.
- A saved `step-intent`, malformed/tampered checkpoint, plan drift, artifact drift, missing log or
  unavailable exact toolchain cannot resume. In-flight uncertainty is durably classified UNKNOWN;
  no runner call or blind retry occurs.
- The final schema-2 local-build receipt remains unchanged. Legacy schema-1/2 attempt receipts remain
  readable; the durable compatibility inventory now declares attempt versions 1, 2 and 3.
- During normal application shutdown, the background supervisor asks the local-build worker to stop
  cooperatively. The current bounded step finishes, is verified and checkpointed, then the worker
  pauses before another intent is recorded.
- Reopened Forge Control clearly shows `Resume verified local build` with the exact completed/total
  step count. UNKNOWN or invalid partial evidence disables the build button and states that no
  automatic retry is available.

## Production-UI simulated journey

- Used a fresh disposable offline workspace, sanitized source-derived OTA inputs, a source-bound
  test Device Pack, test-only executable identities and the existing strict inert build adapter.
- Production Forge Control prepared the exact source blueprint, inputs and deterministic plan, then
  began the seven-step local build.
- A cooperative shutdown request paused after `rebuild-erofs`: the attempt recorded one of seven
  completed steps and one hash-verified artifact. Only one build adapter command (`fakeroot`) had
  run.
- Forge Control closed and reopened against the same workspace. It displayed
  `Resume verified local build` and `1 of 7 steps verified`.
- Resume dispatched only `fsck.erofs`, two `avbtool` actions, `lpmake`, `simg2img`, `lpunpack` and
  `lpdumps`; it did not redispatch the completed `fakeroot` step.
- The resumed journey produced and reloaded the verified `product.img`, `vbmeta_system.img` and
  `super.img` candidate receipt. Guardian handoff and flash readiness remained false.

## Result classification

- Implemented: durable local-build intent/completion checkpoints, exact safe resume, UNKNOWN/no-
  retry handling, cooperative shutdown pause, and reopened Forge resume/blocked presentation.
- Simulated/Tested: yes — offline production Fedora UI plus focused service, UI, durable-schema and
  background-worker regression.
- Hardware Verified: **no new claim**. No physical target was requested, connected or used.
- Released: no.

## Non-double-counted verification

- Final affected regression: **66/66 passed** across:
  - `tests/test_build_contracts.py`: 14;
  - `tests/test_build_control_ui.py`: 41;
  - `tests/test_durable_schema_inventory.py`: 6;
  - `tests/test_background_workers.py`: 4;
  - `tests/test_background_policy.py`: 1.
- Focused adversarial coverage proves exact-prefix resume, no redispatch of the completed step,
  durable intent before dispatch, UNKNOWN after an unobserved interruption, zero adapter calls on
  reopen/retry, strict legacy receipt loading, locked-tool drift rejection, hostile record
  rejection, reopened UI state and shutdown stop signaling.
- Production UI acceptance: **1/1 final journey passed**. One earlier development journey preceded
  final artifact revalidation; one final-check run caught and removed an overly broad UI shortcut.
  Neither is counted as an additional product milestone.
- Ruff checks: **PASS** for every changed Python file.
- Final simulation report SHA-256:
  `e7681ed225961da3ed48e04f0d2104557dbfc4e8c873cba505c38223658c9075`.
- Sanitized OTA SHA-256:
  `e2740827105b1d83e5f58bf15eecb58aac9b1b82c0baa4153884ee644554552e`.
- Final Forge screenshot SHA-256:
  `20b2e206fc2369cf66c8753b14c4dcd6529f8d38dfe5071f810f480cd9b139f0`.
- No full Linux suite was rerun. Retained accepted evidence of **2,881/2,881 passed** at `1300dde`
  is not added to this checkpoint's count.

## Guided friction and remaining boundaries

- Fixed: reopening no longer presents a normal Build button that loops into an existing-output
  rejection. A valid checkpoint becomes one visible Resume action with no additional decision.
- Fixed during final validation: Forge's broad unchanged-source readiness must not hide a more exact
  partial-build Resume state; the persisted local attempt remains authoritative for that button.
- An in-flight/ambiguous step deliberately stops at `Local build needs review`. This is a truthful
  safety boundary, not an automatic retry dead end; a later bounded product slice may define an
  explicit evidence-preserving discard/archive route if Product Assurance authorizes it.
- The current work does not create Device Pack execution authority, Guardian consent, Recovery
  success, physical evidence or production signing.

## Guardian, Recovery and safety implications

- The local executor still has no device transport and every attempt records `phone_changed: false`.
- Convenience/context/evidence do not become authority. A local checkpoint can only resume its exact
  host-side build plan; it grants no Guardian, phone, flash, install, Recovery or release authority.
- UNKNOWN-on-uncertainty and no blind retry are now enforced for the local build itself. Completed
  evidence is preserved precisely; an intent without a proven result is never assumed failed or
  successful.
- Guardian-only authority, exact-device evidence, consent separation, same-incident Recovery and
  independent verification remain unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora/Linux: production-UI interruption, close/reopen, exact resume and candidate completion are
  simulated and focused-regression verified.
- Windows: unchanged; no Windows claim is made by this checkpoint.
- Physical Android: unavailable and not targeted; no new hardware claim is made.
- 5 September 2026 feature freeze: preserved. This is the minimum correctness repair for a proven
  dead end in the existing Stage 1 local-build workflow.
- v0.2 Golden Foundation remains **CLOSED**. Guardian execution/recovery evidence, physical
  verification, Windows secure launch, production signing/trust, publication and release remain
  separate open gates.

## External actions

- Physical phone, ADB/Fastboot target, mode transition, Recovery and device operation: none.
- APK/dependency/system installation, reboot, flash, wipe, unlock, root, trust enrollment,
  production signing and locking/relocking: none.
- Online intelligence/research: none; the journey was offline.
- Publication, release, merge or force-push: none.
- Remote action: only the normal push of the scoped implementation and handoff commits to the
  existing Linux working branch is intended.
- Protected Companion files, original-checkout Windows launcher drafts, website, assets and
  unrelated user work: untouched.

## Next proposed Build task

Stop for independent Product Assurance review. Do not add a partial-build discard/retry flow or
advance to another consequential slice without an approved bounded direction.

## Product Assurance Review Requested

- Confirm schema-3 local-build attempts correctly preserve versions 1/2 as audit-compatible reads
  while final successful local-build receipts remain schema 2.
- Confirm that conservatively classifying every caught post-intent step exception as UNKNOWN is the
  correct no-blind-retry boundary even when an adapter reports an explicit local command failure.
- Confirm the cooperative shutdown contract—finish and verify the current bounded host-only step,
  pause before the next intent—is appropriate for Guided's zero-friction behavior.
