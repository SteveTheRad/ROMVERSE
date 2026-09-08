# ROMVERSE Build Status

## Authoritative checkpoint

- Product Assurance authorization/base: `bb799e1622197b36fcbf6f7cda9b8770f80db61f`
  (`Approve signed-result import journey`).
- Implementation checkpoint:
  `4a4c61c027790954655e584a07d38ed54650dcf6`
  (`Preserve exact candidate preparation across reload`).
- Final handoff checkpoint: the follow-up commit containing this status document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, signed-candidate preparation to no-phone
  fresh-target waiting.
- Working tree at the implementation checkpoint: clean.

## Exact journey and first defect

- Continued from the approved durable signing-ready handoff without rebuilding the ROM, repeating
  artifact inspection, or importing another signing result.
- Exercised the complete rebuilt-ROM preparation through the production
  `CandidateInstallationService`, production source/base/AVB evidence services, a normal service
  reconstruction, and the production Guided `SourceInstallationDialog`, with no phone present.
- The exact preparation identified one project, protected source, source-bound Device Pack, base
  package, two rebuilt plus 48 exact-base image origins, and 53 ordered package actions.
- First concrete defect: reconstructing `CandidateInstallationService` and preparing the unchanged
  exact route generated new base-image and candidate-AVB receipts. Their new timestamps changed both
  receipt digests and therefore changed the candidate recipe digest despite unchanged bytes and
  choices. The route was safe but its durable identity did not survive a normal reconstruction.
- Minimum correction: preparation now loads and freshly verifies existing exact base/AVB receipts.
  It creates new evidence only when no current valid matching receipt exists. The same unchanged
  preparation now reconstructs byte-for-byte with the same recipe, base and AVB digests, and the
  durable receipt files and mtimes remain unchanged.
- The no-phone endpoint remained `Connect the intended phone by USB`. Its primary action was
  disabled, and no selected target, read-only review plan, result, device command or phone change
  existed.

## Result classification

- Implemented: stable durable identity for an unchanged complete candidate preparation across
  ordinary service/UI reconstruction.
- Simulated/Tested: yes — production preparation/evidence/UI boundaries with bounded synthetic
  firmware, real hashes and cryptographic AVB fixture bytes, inert build tooling, and no device
  transport.
- Hardware Verified: no. Creator authorization for later read-only Android verification is noted,
  but this specifically approved no-phone slice did not use it.
- Released: no.

## Non-double-counted verification

- No-phone production service/UI journey: **1/1 passed**. It proved stable exact preparation after
  reconstruction, 53 retained actions, a clear USB wait, and no target/plan/result/phone action.
- Candidate preparation/integration/UI/desktop affected set: **52 unique nodes collected**:
  - **49 passed** in the applicable bounded run;
  - **3 pre-existing failures** in
    `test_changed_built_bytes_never_fall_back_even_with_original_mtime` for `super.img`,
    `vbmeta_system.img`, and `product.img`. All three expect the older phrase `bytes differ`, while
    the current fail-closed implementation reports that no verified local build remains. The same
    three failures were independently reproduced at the unchanged authorization/base commit
    `bb799e1`; this checkpoint introduced no new regression.
- New focused durable-reconstruction regression: included once in the 52-node set and passed.
- Ruff on the two changed Python files: passed.
- Git whitespace check: passed.
- No full suite, broad interruption campaign, ROM rebuild, signing import, package/APK build,
  emulator, phone, production key/trust, installation, flash or Recovery execution ran.

## Guided friction and remaining boundaries

- The reconstruction-only loop is fixed: reopening the unchanged exact preparation no longer
  silently reseals it under new evidence identities.
- Guided reaches one calm no-phone wait and does not expose or enable a consequential action.
- The user still must provide/select the exact understood base installation package for a complete
  rebuilt route when no matching imported package exists; manual subsets remain explicitly
  separate.
- This checkpoint did not demonstrate that externally signed artifact paths and the signed final
  super-assembly receipt are consumed by the complete candidate recipe. That boundary must be
  independently reviewed before treating the no-phone preparation as proof of the final signed
  bytes that would later be eligible for target review.

## Guardian, Recovery and safety implications

- A preparation remains evidence only. It creates no live-target receipt, consent, execution
  admission, adapter dispatch, installation/flash result or Recovery claim.
- Existing exact-device, same-incident Recovery, UNKNOWN-on-uncertainty, no-blind-retry and
  independent post-operation verification invariants are unchanged.
- Guardian remains the sole execution gate.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora/Linux: genuinely exercised production Python/Qt service and dialog boundaries under
  offscreen Qt with deterministic inert tooling.
- Firmware/AVB bytes: bounded synthetic fixtures; not a bootable ROM and not hardware evidence.
- Packaged Fedora artifact: unchanged and not exercised in this slice.
- Windows: unchanged; no Windows claim is made.
- Physical Android: not used. Read-only verification is authorized for a later explicitly scoped
  Linux checkpoint, but no hardware claim is made here.
- Adaptive Online Device DNA: separate worktree remained untouched; its currently uncommitted work
  was not edited, staged or committed.
- 5 September 2026 feature freeze: compliant. This is a minimum correctness repair to the approved
  existing candidate-preparation boundary, not new capability.
- v0.2 Golden Foundation remains **CLOSED**. Live target, consent, execution, installation,
  Recovery reassessment, verification and release gates remain closed.

## External actions

- Physical phone operation, ADB/Fastboot device command, APK transfer/install, emulator, Recovery,
  flash, real signing/private key, production trust enrollment, publication and release: none.
- Dependency/tool installation, package build, merge, history rewrite and force-push: none.
- Remote action: normal push of these scoped Linux checkpoints to the existing Linux working branch
  only.
- The protected Companion files, original-checkout Windows drafts, Adaptive Online Device DNA
  source, website, logos/assets and unrelated user work were untouched.

## Next proposed Build task

Stop for Product Assurance. If approved, perform only the next bounded Stage 1 evidence step chosen
by Product Assurance: either prove/bind the exact offline-signed artifacts plus signed final
assembly into the durable complete candidate preparation, or—if that binding is already proven by
an authoritative contract—advance to one read-only exact-device fresh-target observation. Do not
cross into consent or execution.

## Product Assurance Review Requested

- Confirm the durable receipt-reuse behavior and its regenerate-only-when-no-current-match policy.
- Decide whether the complete candidate recipe must explicitly include the offline-signing receipt
  and signed-final-assembly digests/paths before any live-target checkpoint. Current preparation
  binds pre-sign build/base/AVB evidence; Build does not claim this checkpoint proves consumption of
  the final externally signed installation bytes.
- Accept the three baseline-confirmed error-message assertion failures as pre-existing test debt or
  authorize a separate minimal expectation correction; they do not weaken fail-closed behavior.
