# ROMVERSE Build Status

## Authoritative checkpoint

- Implementation commit: `f61cbc54c203283e457a346bd327a99bec29d880`
- Title: `Invalidate stale Companion Link attempts`
- Product Assurance authorization: `44a3332d975583747e576bfa2967c1bb0bfb0014`
- Branch: `linux/stage1-desktop-readiness`
- Stage: Stage 1 — v0.2 Golden Foundation Companion Link correctness
- Milestone: minimum Companion stale-result invalidation correction
- Product result: an older pairing request can no longer overwrite current presentation or
  authorization state after reset, a newer attempt, or Activity teardown.
- Working-tree target state: clean after the implementation commit except for this handoff update.
  The separate original checkout's protected Companion modifications and Windows launcher drafts
  remain unchanged and uncommitted there.

## Exact changes

- Added a bounded, synchronized generation gate to the existing Companion Link pairing lifecycle.
- Every valid new pairing submission receives a fresh attempt identity and invalidates any older
  request generation.
- Visible pairing reset invalidates the current generation before clearing the session, UI, and
  remembered trust state.
- Activity teardown permanently closes its generation gate, so its pending worker cannot update the
  destroyed presentation or restore authorization.
- Initial request results, polling, late success, secure-storage failure, and final timeout are
  accepted only for the current generation.
- Session-token vault persistence and pairing-preference writes now occur within the guarded main
  thread completion boundary. Reset/new-attempt events and late authorization writes therefore have
  deterministic ordering; the final current user action wins.
- Added one deterministic local unit regression that proves an older timeout and approval cannot
  replace reset state, restore a token, or restore pairing preferences; it also proves a newer attempt
  accepts only its own result and teardown rejects its pending result.
- Corrected the retained direct-product evidence wording: the Desktop log contains **13 total
  snapshot observations, of which 12 are authenticated**. The first is the expected unauthenticated
  waiting observation. The milestone required two authenticated observations.
- No Desktop source, protocol, certificate-pinning rule, safety-code behavior, consent surface,
  telemetry schema, Recovery path, Guardian policy, approved asset, Windows source, or build/release
  configuration changed.

## Result classification

- Implemented: Companion request-generation invalidation, guarded UI/authorization result
  application, and deterministic regression coverage.
- Simulated/Tested: pure deterministic lifecycle regression plus existing Link security invariants;
  Android compilation and static analysis passed.
- Hardware Verified: no. No emulator or physical Android target was started for this correction.
- Released: no.

## Non-double-counted verification

- Focused current Android unit result: **8/8 passed**.
  - `LinkPairAttemptGateTest`: 1/1.
  - Existing `DesktopLinkSecurityTest`: 7/7.
- The first isolated 1/1 run of the new regression is a subset of the final 8/8 run and is not added.
- `:app:compileDebugKotlin` and test compilation: passed as part of the focused test gate.
- `:app:lintDebug`: passed; zero blocking Android lint result.
- Git whitespace validation: passed.
- No APK rebuild, instrumentation run, emulator journey, broad Android inventory, Fedora journey, or
  Python regression was repeated.
- Prior evidence remains unchanged and is not added to this checkpoint:
  - Companion instrumentation inventory: **12/12 passed** at `b86aca2`.
  - Full Fedora/Linux Python regression: **2,881/2,881 passed** at `1300dde`.
  - The prior 79-test and 240-test groups remain subsets of that 2,881 result.

## Corrected direct-product evidence

- Direct real Fedora Desktop-to-Companion Link remains verified at handoff `c4bcdfa` and Product
  Assurance review `44a3332`.
- Both products displayed the same certificate-derived safety code and retained their explicit
  approval boundaries.
- The retained 17-event Desktop log contains ready, approved, 13 snapshot observations,
  reconnected, and reset in order.
- Snapshot observation 1 is unauthenticated waiting state; observations 2 through 13 are the
  **12 authenticated observations**.
- Every retained event reports `execution_authority: none`.
- Remembered-session reconnect, visible revocation, and old-credential rejection remain verified.

## Guided friction and dead ends

- The observed stale `APPROVAL TIMEOUT • TRY AGAIN` overwrite after a visible reset is corrected at
  its source boundary. Late approval, rejection, network failure, and timeout from an invalidated
  request are ignored rather than presented as retry, success, or current state.
- This adds no confirmation, modal, new route, or user decision. The one existing phone identity
  confirmation and separate Desktop approval remain unchanged.
- Emulator multicast discovery previously required the existing manual endpoint/fingerprint/code
  route. That emulator-only usability limitation is unchanged and was not in this correction.
- Product Assurance identified emulator-versus-physical-USB classification as a separate Desktop
  defect. It remains queued for one owner after the active Windows listener lifecycle checkpoint;
  Linux did not duplicate or begin it.

## Guardian, Recovery, and safety implications

- A stale Link worker can no longer restore a bearer token, pairing preferences, trusted state, or
  success presentation after the current lifecycle invalidates it.
- Certificate pinning, exact safety-code comparison, explicit confirmation, remembered-session
  behavior, reset/revocation, and read-only telemetry are preserved.
- Companion Link retains zero flash, root, wipe, unlock, relock, command, Recovery, or Guardian
  authority.
- Guardian remains the only execution gate.
- Exact-device evidence, same-incident Recovery, durable UNKNOWN, no blind retry, and independent
  reassessment/verification were not changed.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora runnable development build and inert Guided journey: **VERIFIED** and unchanged.
- Companion standalone API-35 runtime: **VERIFIED** at the prior checkpoint.
- Direct Fedora Desktop-to-Companion product Link: **VERIFIED**.
- Companion reset-versus-late-result presentation: correction implemented and focused-tested; now
  awaiting independent Product Assurance review.
- Windows optional-listener lifecycle: separate active Windows correction; untouched here.
- Physical Android hardware and production Recovery/trust/signing: not run or authorized.
- 5 September 2026 pre-v1.0 feature freeze: preserved. This is the minimum correctness repair to an
  existing asynchronous presentation/authorization boundary, not a new feature.
- v0.2 Golden Foundation remains **CLOSED** pending the existing Windows, physical, production-trust,
  signing, and release gates.

## Environment note

The first focused Gradle invocation discovered that the dedicated removable-data Android SDK did not
contain SDK Platform 35 revision 2 or Build-Tools 34.0.0. Android's build tooling automatically
downloaded those two components into
`/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain`. No Fedora system package, user-wide
SDK, application dependency declaration, repository source, firewall, SELinux policy, or host
security setting changed. The automatic dedicated-toolchain provisioning was not required again and
is disclosed for Product Assurance because this slice was intended to be dependency-neutral.

## Blockers and remaining limitations

- The corrected behavior has deterministic JVM coverage and Android compile/lint evidence, but was
  not rerun through an emulator because Product Assurance explicitly prohibited repeating the full
  journey and did not require a bounded emulator run when the defect could be proven deterministically.
- The separate Desktop emulator/USB source-classification correction remains queued.
- Windows release readiness, physical-device verification, production-signed Recovery adapter trust,
  release signing, packaging, publication, and release remain open gates.

## Next proposed Build task

Stop for independent Product Assurance review of this exact implementation and handoff. Do not begin
the Desktop source-classification correction, another Companion slice, a full journey, broad suites,
hardware operation, Recovery, signing, packaging, publication, or release without the next repository
verdict.

## External actions

- Physical phone connection/operation: none.
- Emulator start or APK installation: none.
- Firmware, partition, bootloader, flash, wipe, root, unlock, relock, or Recovery operation: none.
- Production execution/trust/signing: none.
- System-wide installation or dependency change: none.
- Dedicated Android SDK auto-provisioning: Platform 35 revision 2 and Build-Tools 34.0.0, as disclosed
  above.
- Desktop source or Windows branch change: none.
- Protected original-checkout Companion/Windows draft change: none.
- Website, logo, publication, release, merge, or force-push: none.
- Remote action: normal push of the scoped implementation and this handoff is intended after final
  repository verification.

## Product Assurance Review Requested

- Confirm the generation gate and guarded main-thread persistence satisfy reset/new-attempt/teardown
  stale-result invalidation without adding Guided friction.
- Confirm the 8/8 focused tests, Android compile, and lint gates are proportional and sufficient.
- Confirm the evidence count is now exact: 13 total observations / 12 authenticated.
- Review the disclosed automatic provisioning of two components into the dedicated removable-data
  Android SDK and determine whether any follow-up environment action is required.
- Keep the emulator/physical-USB classification defect assigned to one owner after the Windows
  checkpoint; Linux requests no authorization to begin it here.
