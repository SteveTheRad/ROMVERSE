# ROMVERSE Product Assurance

## Reviewed checkpoint: 5f17720

- Handoff commit: `5f17720d98f4c028908f7151051d093dc3923e48`
- Prior Product Assurance authorization:
  `14468a5ed96ef8e63eeab5d227317808999dad11`
- Title: `Record contained Link fixture environment blocker`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — PRE-ENDPOINT FAILURE STOP VERIFIED; EXISTING ENVIRONMENT RETRY AUTHORIZED**

### Decision

Build stopped at the exact required boundary. The sole emulator and approved APKs were admitted,
but the contained Desktop Link fixture failed during Python import before an endpoint, certificate,
pairing code, safety code, token, approval, application launch, or instrumentation run existed.
This is an invocation-environment mismatch, not a Companion, Link, TLS, or runtime failure.

Product Assurance independently verified that the repository declares `cryptography>=46,<47`, the
default `/usr/bin/python` 3.14.7 cannot discover that module, and the preserved traceback and hash
match the handoff. No product or dependency change is necessary.

An existing ROMVERSE virtual environment already contains Python 3.14.7 and `cryptography 46.0.7`,
which satisfies the committed dependency range. One repeat of the exact contained Link runtime is
authorized using only that existing interpreter and its installed dependency set. No package
installation, environment creation, upgrade, downgrade, or dependency mutation is authorized.

### Independent evidence

- Commit `5f17720` changes only `docs/sync/BUILD-STATUS.md`; the dedicated worktree is clean and
  matches `origin/linux/stage1-desktop-readiness`.
- Preserved fixture error log: 843 bytes / 10 lines; SHA-256
  `550e2d72b964a80a1c464e76f8fe0321e9111bd2993e78ac8478c7bf6b2864eb`.
- Preserved fixture stdout is empty; no fixture state or credential was emitted.
- The traceback ends at `from cryptography import x509` with
  `ModuleNotFoundError: No module named 'cryptography'`.
- `/usr/bin/python` is 3.14.7 and independently reports no discoverable `cryptography` module.
- Existing interpreter:
  `/run/media/stevetherad/Data/ROMVERSE-Recovered-2026-09-01/source/.venv/bin/python`.
- That interpreter independently imports `cryptography 46.0.7`, within the exact declared
  `>=46,<47` range.
- The existing virtual environment is used only as a dependency runtime. `PYTHONPATH` must point
  explicitly to the clean `ROMVERSE-Linux-Desktop-Readiness/src`, and the fixture script must be
  the exact committed file in that same clean worktree. Do not import ROMVERSE application source
  from the separate original checkout.

### Safety and classification

- Contained Link instrumentation remains **0 run / 0 pass / 0 fail / 0 skip** for this failed
  attempt; no integration claim is made.
- The prior approved standalone Companion runtime remains valid and is not affected.
- The emulator was shut down and ADB is empty after the failure.
- SELinux remains Enforcing; no host-policy or package change occurred.
- No Companion source, tests, fixture, protocol, dependency declaration, resource, or brand asset
  changed.
- Guardian remains the sole execution gate; the fixture grants no execution or device-changing
  authority.
- Exact-target evidence, UNKNOWN-on-uncertainty, no blind retry, and consent separation remain
  unchanged.
- Bootloader locking and relocking remain permanently prohibited with no override.
- The pre-v1.0 feature freeze is preserved.

### Approved next bounded task

Repeat exactly the previously approved contained Desktop-to-Companion Link runtime once, changing
only the Python executable used to start the committed fixture.

Invoke the exact clean-worktree fixture with the existing verified virtual-environment interpreter,
explicit clean-worktree `PYTHONPATH`, and user-site packages disabled. Before starting the emulator
or fixture, prove with that exact invocation context that:

- `romverse.__file__` and the relevant `romverse.companion` modules resolve under
  `/run/media/stevetherad/Data/ROMVERSE-Linux-Desktop-Readiness/src`;
- `cryptography.__version__` is exactly `46.0.7` and its module resolves from the existing virtual
  environment's site-packages; and
- no ROMVERSE application module resolves from the separate original checkout.

Then use the same isolated API-35 toolchain, exact approved APK hashes, clean visible host-GPU AVD,
SELinux enforcing, and sole exact `emulator-5556` admission. Start one fixture instance, pass only
its ephemeral endpoint/code/fingerprint values to the existing runner, and execute the complete
12-test suite once. Require 12 passes, zero failures, and zero skips, two fresh health snapshots,
encrypted-session reconnection after Activity recreation, and `execution_authority: none`.

Preserve full fixture and runner logs and hashes and capture bounded readable Link, Live Console,
Device DNA, and Ascension Guardian-boundary evidence where practical. Shut down the fixture and
emulator and confirm ADB is empty.

Any dependency mismatch, source-resolution mismatch, target ambiguity, artifact mismatch,
TLS/pinning/safety-code failure, test failure or skip, fixture timeout, runtime error, or emulator
failure ends the task without another retry or any code/environment change.

Do not install or modify packages; create or mutate an environment; import ROMVERSE source from the
original checkout; change the app/tests/fixture/protocol; use a phone; expose the endpoint beyond
the contained emulator route; grant execution authority; enable Recovery; use production signing;
change protected files; merge platforms; publish; or release.

Update `docs/sync/BUILD-STATUS.md`, commit and push the exact checkpoint on
`linux/stage1-desktop-readiness`, then stop for independent Product Assurance review.

### Gate status

- v0.2 Golden Foundation: **CLOSED pending remaining release gates**
- Fedora runnable build and inert Guided journey: **VERIFIED**
- Companion standalone API-35 emulator runtime: **VERIFIED**
- Contained Desktop/Companion Link integration: **ENVIRONMENT-ONLY RETRY AUTHORIZED**
- Companion physical-device verification: outstanding; not authorized
- Windows runnable development build: separate correction track in progress
- Production Recovery, signing, publication, and release: outstanding and not authorized
