# ROMVERSE Product Assurance

## Reviewed Windows launcher checkpoint

- Implementation: `ea292e75db8de3d2ed44feb0e8fb070c70ebf849`
- Deterministic coverage: `7124a89aefac8cf6e957a0805d4576f2a960ea0c`
- Reviewed remote tip: `cf162675213049f454103a42b1c975ec6b55353c`
- Approved base: `fdb1692b0a5056cce0992b9045cd6f3a55cabf97`
- Review status: **APPROVED — WINDOWS TRUSTED-LAUNCHER CONTRACT VERIFIED**

### Decision

The checkpoint implements the approved Windows anti-TOCTOU boundary behind the existing sealed
process-runner protocol. It revalidates the signed package and exact Windows artifact, rejects
reparse components and hard-linked artifacts, pins the executable through a non-write/non-delete-
sharing handle, rehashes the handle contents, and confirms path-to-handle identity immediately
before a fixed `Popen` dispatch surface. The verified handle remains open through process creation.

Callers cannot provide a path, command, arguments, environment, retry policy, or bootloader action.
Production packages require the exact platform launcher class; deterministic fake runners remain
test-only. Request, output, error, and timeout bounds are explicit. Malformed, truncated,
contradictory, timed-out, or otherwise ambiguous post-dispatch evidence cannot become success and
does not permit retry.

This is genuine Windows-hosted software verification of inert file-handle and replacement-lock
semantics. It is not a production adapter, phone operation, physical Recovery result, publication,
or release claim.

### Evidence reviewed

- `src/romverse/guardian/recovery_runtime_adapter.py`
- `docs/WINDOWS-RECOVERY-LAUNCH-CONTRACT.md`
- `tests/test_guardian_recovery_windows_launcher.py`
- Branch ancestry is linear from approved base `fdb1692`; later commits change only the Build
  handoff.
- Genuine Windows affected suite: **61 passed, 2 expected Linux-only skips** from 63 collected;
  focused launcher coverage **21/21 passed** as a subset.
- Exact remote-tip Linux regression: **2899 passed, 2 expected Windows-only skips** from 2901
  collected. Product Assurance independently reproduced the focused launcher/package/runtime
  suite on Linux with only host-specific Windows cases skipped.
- The optional broader Windows baseline was incomplete after unrelated portability failures and a
  stall; it is not accepted or counted as passing evidence.

### Acceptance criteria

- Exact signed package, artifact bytes, file identity, and fixed launch surface remain bound.
- Reparse, hard-link, replacement, hash/size, platform, launcher, and timing drift fail closed.
- Post-dispatch uncertainty remains UNKNOWN; no blind or automatic retry exists.
- Guardian-only authority and permanent bootloader-relock prohibition remain intact.
- No production enrollment, UI, physical execution, phone command, publication, or release was
  introduced.

All scoped criteria are met.

### Next authorized Build task

Perform only a bounded, read-only Windows portability triage of the incomplete broader regression.
Capture the full failing/stalling test inventory with per-test time bounds, separate pre-existing
platform-fixture failures from Stage 1 correctness failures, and produce a repository audit/handoff.
Do not fix unrelated tests in the same checkpoint, add features, enroll a production adapter, wire
execution, operate a phone, retry uncertain actions, or claim a passing Windows baseline.

Product Assurance must review that inventory before any correction slice. Production adapter
enrollment and controlled physical Android verification remain separate creator-authorized gates.

### Gate status

- Windows trusted-launcher anti-TOCTOU software contract: **IMPLEMENTED AND WINDOWS VERIFIED**
- Full Windows repository baseline: **INCOMPLETE; NOT CLAIMED PASSING**
- v0.2 Golden Foundation: **CLOSED**
- Pre-v1.0 feature freeze: preserved
- Production adapter enrollment: not implemented/released
- Controlled physical Android verification: outstanding release blocker
- Physical execution, publication, release, and relocking: not authorized
