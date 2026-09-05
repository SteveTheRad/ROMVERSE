# Source failure and Recovery Autopilot handoff checkpoint

Status: implemented and software-verified Desktop checkpoint, 2026-09-05. This is not
physical-device validation, proof of a successful repair, or completion of the twenty-stage master
goal.

## Dead end removed

A failed source installation already left a sealed command journal, but its automatic handoff to
Recovery Bay carried only a short error sentence. A process interruption could reopen as a generic
unfinished 0/0 result even when the journal knew which ordered actions completed and which command
had been dispatched without a terminal result. Recovery Autopilot also did not automatically query
the offline Knowledge Archives with that typed installation failure.

ROMVERSE now reconstructs one exact, source-bound action ledger from the sealed journal. It keeps
four states separate: **completed**, **known failed**, **uncertain in-flight**, and **not started**.
An uncertain write is never renamed as failure or success and is never automatically retried.

## Implemented behavior

- Terminal and safely sealed interrupted records expose every declared action in original order,
  including its zero-based internal index, human-readable one-based step, operation, target and
  measured status.
- A command that returned a non-zero result or timed out is **known failed**. A command whose runner
  vanished before a result was recorded is **uncertain in-flight**. Later commands are **not
  started**, not assumed failed.
- Application restart can recover a sealed command-in-flight journal with its genuine completed
  count and expected count instead of reporting 0/0. The interrupted record still cannot authorize
  a boot check or claim a fresh phone identity.
- The historical installation screen displays the same sealed action summary and local receipt
  digest. The Recovery Autopilot diagnosis receives a bounded, workspace-relative receipt pointer,
  source/recipe/record digests and the exact failed or uncertain action.
- Recovery Bay combines that typed failure with privacy-bounded current Device DNA and immediately
  scans the local Knowledge Archives. Matched records can influence ranked advisory routes and are
  preserved by record identifier and Archive digest. They grant no execution authority.
- The exact project is retained only while its protected source digest still matches. A changed
  project/source, invalid journal, unrelated phone or malformed chronology cannot inherit the
  evidence.
- The Guided USB watcher now checks at 1.5 seconds during ordinary authorization/reconnection and
  still backs off to five seconds after repeated discovery failures. This removes a timing edge
  without creating a busy retry loop.

## Verification evidence

- New coverage proves known Fastboot failure, runner disappearance during `flash super`, restart
  reconstruction of a sealed in-flight journal, privacy-safe device/failure Archive lookup,
  automatic Recovery Autopilot knowledge attachment and the real Guided MainWindow handoff.
- All 187 focused source-installation history/UI, Recovery Bay, offline knowledge, local lifecycle
  and complete user-journey tests pass. A timing-sensitive authorization watcher case also passes
  inside the complete focused group after the watcher responsiveness adjustment.
- The complete Desktop/Python regression gate passes all 2,684 tests with zero failures, errors or
  skips in 825.011 seconds. Its JUnit record is
  `/tmp/romverse-source-recovery.KmComV/desktop-full.xml`.
- Whole-change Ruff checks pass. Approved production logo files remain byte-identical:
  ROMVERSE PNG `ab9286ce69e77abd82fe88105df70680186a4eb992289580c23f5d362c132a18`,
  ROMVERSE ICO `bcfe1c5b960de2327c5e706cc22b872923c8ce2c254aa0b125c4f9b1dd4036b2`,
  RadForge Labs `d82ff146aab1f18474005d1a2d9ce0c3944467ae30ff7cb4fb3284387daa95cb`.

## Deliberate remaining boundaries

- ROMVERSE reconstructs the durable evidence after a process interruption; it does not resume an
  unknown command or assume what the phone did while transport was unavailable.
- Archive results diagnose and rank routes only. A future recovery write still needs a typed owner,
  fresh exact-device/input checks and its own meaningful confirmation.
- The supported complete source/rebuilt-ROM recipe remains device-specific. This checkpoint does
  not prove general Android flashing, image readback, stable boot, subsystem health or a particular
  physical repair.
- No physical phone command, app restart, package build, Companion change, website update,
  publication or remote push was performed.
