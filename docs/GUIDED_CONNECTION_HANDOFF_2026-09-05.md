# Guided connection and bootloader handoff checkpoint

Status: implemented and software-verified Desktop checkpoint, 2026-09-05. This is not
physical-device validation, release certification, or completion of the twenty-stage master goal.

## Circular route removed

The complete supported source/rebuilt-ROM route requires bootloader Fastboot for its read-only final
review and later installation. Guided previously hid the phone-mode controls. When the correct phone
was connected in Android, **Prepare installation** therefore ran a bootloader-only check, failed,
and offered **Check readiness again**, which repeated the same failure.

Guided now derives the next action from the retained phone and recipe. Normal Android and fastbootd
show **Restart phone to bootloader…**. The existing exact-target transition service performs its
read-only review, asks once for the reboot decision, observes arrival of the same phone, and then
continues the safe installation review automatically. Installation remains a separate consequential
decision with its own exact-plan confirmation.

## Implemented behavior

- Missing, unauthorized, offline and unstable USB states show the physical action the user can take.
  An application-owned timer watches in the background, so approving the on-phone ADB dialog or
  reconnecting the phone does not require repeatedly pressing Refresh.
- Successful detection automatically performs only deterministic device selection and read-only
  installation review. It cannot approve a reboot, accept data erasure, start installation, or
  reuse an old final confirmation.
- Android/fastbootd to bootloader uses one reviewed mode-change confirmation. Verified bootloader
  arrival continues directly into read-only package/phone review and stops at **Install ROM…**.
- Repeated USB discovery errors stay outside Recovery Bay because no phone-changing action occurred.
  The watcher changes to an actionable cable/Platform Tools explanation and backs off from 1.5 to
  five seconds instead of spinning aggressively.
- With several connected phones, ROMVERSE automatically selects only one unambiguous recipe match.
  Ambiguous devices receive an explicit **Choose the intended phone…** entry; the app does not pick
  the first USB device.
- A known product/codename or manufacturer contradiction keeps the selector visible, refuses mode
  change and installation review, and continues watching for the one exact matching phone. Region
  alone is not used as an incompatibility signal.
- A read-only failure is described as attention rather than falsely claiming that recovery was
  prepared. Unknown write outcomes and real changing failures retain their existing recovery route.

## Verification evidence

- Six new user-style integration cases cover Android-to-bootloader confirmation and automatic
  review, real timer-driven ADB authorization continuation, bounded discovery-error backoff,
  ambiguous multi-phone selection, product mismatch, and manufacturer mismatch. Every case records
  zero installation commands before final install confirmation.
- `scripts/simulate_source_installation.py` now begins its inert phone in Android, renders the Guided
  bootloader action, confirms the production transition service, verifies exact bootloader arrival,
  continues read-only review automatically, declines installation once with zero image writes, and
  then runs the separately confirmed inert full procedure and measured boot. Its new
  `simulation-source-android-handoff.png` artifact is visibly labelled **SIMULATION ONLY · NO
  PHYSICAL PHONE**.
- All 634 affected source/candidate/project/local-installation, Guardian, ROM Studio and First Light
  regressions pass. The complete Desktop/Python suite passes all 2,680 tests with zero failures,
  errors or skips in 821.354 seconds. Its JUnit record is
  `/tmp/romverse-guided-handoff.5ULdQO/desktop-full.xml`.
- Whole-source Ruff and final diff checks pass. Approved production logo files remain byte-exact and
  were not edited.

## Deliberate remaining boundaries

- The automatic watcher and live operation remain in memory. Crash/reboot reconstruction belongs to
  Continuity Core and is not claimed here.
- Automatic connection handling currently covers this supported complete source/rebuilt-ROM mission;
  it is not evidence that every future firmware format or Android transport is implemented.
- A confirmed reboot is not installation consent, and bootloader arrival is not proof that a ROM is
  compatible, flashed, readable, booted, stable, or subsystem-tested.
- No physical phone command, running-app restart, package build, Companion change, website update,
  publication, or remote push was performed for this checkpoint.
