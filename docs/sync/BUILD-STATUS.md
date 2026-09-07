# ROMVERSE Build Status

## Authoritative Windows launcher checkpoint

- Commit: `ea292e75db8de3d2ed44feb0e8fb070c70ebf849`
- Title: `Add Windows trusted Recovery launcher contract`
- Deterministic coverage commit: `7124a89aefac8cf6e957a0805d4576f2a960ea0c`
- Base: `fdb1692b0a5056cce0992b9045cd6f3a55cabf97` (`Approve Stage 1 closure audit`)
- Branch: `windows-launcher-authorized-work`
- Stage: Stage 1 — Windows trusted-launcher anti-TOCTOU correctness contract
- Build status: implemented, committed, independently reproduced on Windows and fully regression-
  tested on Linux; Product Assurance review pending

### Exact changes

- Added `WindowsSubprocessRecoveryAdapterProcessRunner` behind the existing package/request/timeout
  process-runner protocol.
- Revalidates the signed package, platform, exact artifact name, byte length and SHA-256 before
  opening the Windows launch boundary.
- Rejects reparse path components, non-regular files and hard-linked artifacts.
- Opens the exact artifact with `CreateFileW`, without following the final reparse point, while
  denying write/delete sharing; the handle remains open through process creation.
- Binds the path and open handle to the same device/inode, link count, size, modification time and
  creation time immediately before dispatch.
- Preserves fixed protocol arguments/environment, no shell, bounded request/output, bounded timeout,
  no automatic retry and UNKNOWN-on-ambiguous-result behavior.
- Requires the exact platform launcher class for production-trust packages; test-only fake runners
  remain explicitly separate.
- Added the normative Windows launch contract and deterministic adversarial tests.
- Added no production adapter enrollment, UI, consent, physical execution or phone integration.

Files in the implementation commit:

- `src/romverse/guardian/recovery_runtime_adapter.py`
- `docs/WINDOWS-RECOVERY-LAUNCH-CONTRACT.md`
- `tests/test_guardian_recovery_windows_launcher.py`

### Verification evidence

Host: Windows 11 x64, Python 3.12.10, pytest 9.1.1.

- Focused Windows launcher contract tests: **21/21 passed**.
- Combined affected Recovery launcher/package/runner regression: **61 passed, 2 skipped** from 63
  collected tests. This total includes the 21 focused tests and is not added to it.
- Existing affected regression excluding the focused file: **40 passed, 2 skipped**.
- The two skips are existing Linux-only sealed-memfd path-substitution and timeout tests; they are
  not claimed as Windows evidence.
- Linux Build independently reproduced the exact pushed checkpoint at
  `f94bd7389526d373f6233ceb41406e7ae3b4fc9a` on Fedora 44, kernel 7.1.13, Python 3.14.7:
  - Combined affected Recovery regression: **61 passed, 2 skipped** from 63 collected tests. The
    skips are the two Windows-host-specific handle-identity and sharing-lock cases.
  - Full Linux Python regression: **2,899 passed, 2 skipped** from 2,901 collected tests. The
    affected 61-pass result is a subset of this total and is not added again.
- Linux Build also reran the combined affected suite over authenticated SSH on the real Legion and
  independently reproduced **61 passed, 2 skipped**. This is the same suite already reported above,
  so it is corroborating evidence and is not counted again.
- Ruff lint and formatting checks for the launcher source and new tests: passed.
- Git whitespace/diff check: passed.
- An optional full-repository Windows baseline was stopped after 67% when an unrelated integration
  test stalled. It had already exposed numerous pre-existing Windows/platform-fixture failures
  outside this slice, so it is not reported as a passing or completed regression.

### Classification and limitations

- Implemented: Windows trusted-launcher anti-TOCTOU software boundary and contract.
- Windows-hosted deterministic verification: yes. Tests exercised real Windows file-handle,
  hard-link and replacement-lock behavior with inert local bytes; process dispatch used fakes.
- Linux regression: full suite passed at the exact pushed checkpoint; the two Windows-only cases
  were skipped honestly and are covered by genuine Windows-hosted evidence.
- Production adapter verified: no.
- Physical Android hardware verified: no.
- Released or published: no.

Passing these tests does not claim that a production Recovery executable or phone command ran. It
does not open production enrollment, physical execution, hardware verification, release or
publication gates.

### Guardian and safety invariants

- Guardian remains the only higher-level execution gate.
- Callers cannot supply executable paths, commands, arguments, environment overrides or retries.
- Start failure is attempted once only.
- Timeout, truncation, malformed/ambiguous results and contradictory identity become failure or
  `UNKNOWN`, never inferred success.
- Bootloader locking/relocking remains permanently prohibited with no override.
- Protected Companion files were not edited, staged, discarded, tested or committed.

### External actions

- Physical phone operation: none.
- Recovery command execution: none.
- Package/APK installation: none.
- Physical execution enablement: none.
- Production adapter enrollment: none.
- Publication/release: none.
- Working branch publication: `origin/windows-launcher-authorized-work` only; no force-push,
  release or publication of an application artifact.
- Companion source change: none.

### Product Assurance review requested

Review implementation commit `ea292e75db8de3d2ed44feb0e8fb070c70ebf849` and deterministic coverage
commit `7124a89aefac8cf6e957a0805d4576f2a960ea0c` against
`docs/WINDOWS-RECOVERY-LAUNCH-CONTRACT.md`, particularly Windows handle-sharing semantics,
reparse/hard-link rejection, final path-to-handle identity, fixed process surface, timeout/output
uncertainty and production/test launcher separation. Do not begin another feature or consequential
slice until this review is complete.

## Historical Stage 1 closure checkpoint

- Commit: `3b61639e16ee21e033ed8eb17cb6b35065142992`
- Title: `Audit Stage 1 closure evidence`
- Stage: Stage 1 — v0.2 Golden Foundation closure audit
- Milestone: read-only closure assessment after Future-proofing 3/3
- Build status: audit committed; Product Assurance review required before another consequential slice
- Working tree: only the three pre-existing unrelated Companion modifications remain. The audit did
  not edit, stage, discard, test, or commit them.

## Exact changes

- Added `docs/STAGE-1-CLOSURE-AUDIT_2026-09-06.md`.
- Audited the authoritative Stage 1 and Guided Experience requirements against the committed
  Recovery chain, current source boundaries, tests, retained-schema inventory, three future-proofing
  checkpoints, and Product Assurance history.
- Confirmed the complete software separation of Recommendation, Preparation, Fresh Live Target,
  Consent, Executor, Durable Result, Recovery Reassessment, and Verification.
- Confirmed that the production app can continue an existing durable Recovery result but does not
  construct or enroll the governed Recovery adapter runner for physical execution.
- Confirmed that the current concrete trusted launcher is Linux-only: it rejects non-Linux hosts and
  depends on `memfd`, `/proc/self/fd`, `fcntl`, `pass_fds`, and process-group signals.
- Identified the previously approved Windows trusted-launcher anti-TOCTOU correctness contract and
  deterministic tests as the smallest remaining software gap.
- Made no application, test, schema, UI, Companion, asset, package, or execution change.

## Classification

- Implemented: the audit document only. The previously committed Linux software chain and
  Future-proofing 3/3 remain implemented.
- Simulated/Tested: no new execution or test run was performed for this documentation-only audit.
  The audit relies on the immediately preceding verified checkpoint's full **2,880/2,880** Python
  result and preserved Product Assurance evidence without recounting historical suites.
- Hardware Verified: no.
- Released: no.

## Verification evidence

- Immediate preceding implementation checkpoint `b9afd9f`: full Python regression
  **2,880/2,880 passed**.
- Its affected firmware/source regression **223/223** and new adversarial cases **11/11** are subsets
  of that full total and are not added again.
- Git history contains committed and approved boundaries for preparation, live target, consent,
  execution admission, per-step durable journal, trusted adapter protocol, aggregate result,
  same-incident reassessment, fresh boot verification, app-owned continuation, durable schemas,
  neutral contracts, and the bounded source-evidence registry.
- Audit Markdown and Git whitespace check: passed.
- Approved production assets were not edited and remain byte-exact at the prior verified hashes.

## Blockers and remaining limitations

- Windows trusted Recovery launch and anti-TOCTOU correctness are not implemented or verified.
- Controlled physical Android Recovery execution and post-repair verification have not been run.
- No production-signed Recovery adapter artifact, client trust enrollment, or app execution wiring
  exists; only test adapters and inert transports exercise the architecture.
- Android instrumented and physical Companion behavior remain outside this audit and unverified.
- v0.2 Golden Foundation remains closed.

## Guided friction and dead ends

- No new Guided dead end was found in the implemented software continuation. The same incident
  survives the complete evidence chain; wrong/missing phones wait, while FAILED and UNKNOWN stop
  without retry.
- The absence of a production physical Recovery runner is a truthful release boundary, not a
  circular Guided checklist. It must remain visible as unavailable until independently proven.
- No Guided screen, dialog, confirmation, route, or wording changed in this audit.

## Guardian, Recovery, and safety implications

- Guardian remains the only execution gate.
- Evidence, consent, and command completion remain insufficient to claim Recovery.
- FAILED and UNKNOWN remain distinct, durable, and non-retry states.
- Exact-device and same-incident attribution remain mandatory.
- Bootloader locking/relocking remains permanently prohibited with no override.
- The audit grants no authority and does not enable physical or Windows execution.

## Platform status

- Linux/Fedora: software chain and full Python regression verified at the preceding checkpoint.
- Windows: trusted-launcher contract and genuine Windows verification remain outstanding.
- Android physical hardware: not run for this Recovery chain.

## Feature-freeze and version-gate impact

- 5 September 2026 pre-v1.0 feature freeze: compliant. This is documentation-only analysis and adds
  no feature, UI, route, format, vendor, adapter, device operation, or release capability.
- Future-proofing checkpoints: **3/3 complete and Product Assurance approved**.
- v0.2 Golden Foundation: remains **CLOSED**.

## Next proposed Build task

After a new Product Assurance approval, implement only the previously approved Windows
trusted-launcher anti-TOCTOU correctness contract and deterministic Linux-hosted software tests.
The slice must preserve the existing process-runner interface, exact verified package binding,
fixed protocol/environment, bounded I/O, UNKNOWN-on-uncertainty, no retry, and no relock. It must not
launch a phone command, wire production execution, add UI, claim Windows verification, publish, or
release.

## External actions

- Physical phone operation: none.
- Package/APK installation: none.
- Publication/release: none.
- Remote push: none.
- Website change: none.
- Source-data migration: none.
- Companion source change: none.
- Application source change: none.
- Local action: read-only repository inspection followed by one documentation-only audit commit.

## Product Assurance Review Requested

- Confirm or correct the audit's Stage 1 evidence matrix and closed-gate conclusion.
- Confirm the production-runner absence is correctly classified as a deliberate unimplemented
  release boundary rather than a Guided navigation defect.
- Approve, narrow, or reject the Windows trusted-launcher anti-TOCTOU correctness contract as the
  next smallest Stage 1 software slice.
