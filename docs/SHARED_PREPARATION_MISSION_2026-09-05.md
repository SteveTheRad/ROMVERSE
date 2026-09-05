# Shared preparation mission checkpoint

Status: implemented and software-verified Desktop checkpoint, 2026-09-05. This is not
physical-device validation, release certification, or completion of the twenty-stage master goal.

## Dead end removed

ROM Studio previously handed source or rebuilt-ROM preparation to a dialog-owned worker. Hiding or
replacing that dialog could separate the user from the real work, while reopening the project could
start preparation again. A failure also risked sending the user back through the same choices
without retaining the exact request that failed.

The application-owned `SourceOperationSession` now begins before preparation. It retains the exact
project and source identity, chosen route, base package, wipe/restart consequences, preparation
worker, verified recipe, installation review, write, device transition, boot observation, result,
and recovery handoff as one mission. Screens render that mission; they no longer own it.

## Implemented behavior

- Complete supported source and rebuilt-ROM routes may be hidden while read-only hashing and
  verification continue. Reopening the same project attaches to the same worker and request.
- Successful hidden preparation is retained and reported inline. ROMVERSE waits for the user to
  choose **Continue installation** before opening review; it does not interrupt another screen or
  silently advance into a phone-changing action.
- The continued installation uses the same session and exact verified recipe. Preparation is not
  repeated, and no second executor or worker is created.
- A failed preparation preserves the selected route, base package and erase/restart choices. The
  same project reopens with the real error and an enabled retry instead of restarting the setup.
- The session rejects output whose project, protected source, route, base package, wipe choice, or
  restart choice differs from the retained request. Rejected output cannot become an installable
  recipe, and no phone-changing command is sent.
- Guided/Expert presentation changes do not replace active preparation. Competing device work still
  yields to the existing mission.
- Manual individual-image mapping keeps its established explicit dialog lifecycle. It is not
  presented as the complete automatic route and does not inherit consent from preparation.

## Verification evidence

- Real Qt integration tests hide preparation, replace its view, switch the application experience
  mode, finish the original worker, and reopen the same mission at installation review. They verify
  object identity for the session, worker and recipe, plus zero phone changes during preparation.
- Adversarial coverage returns a recipe with different data-erasure consequences. ROMVERSE rejects
  it, preserves the original choice, and accepts only a correct explicit retry.
- Failure coverage injects a protected-source verification error while the preparation screen is
  hidden. ROM Studio reports an actionable status, reopens the exact route, enables retry, and
  records zero phone changes.
- The reusable source-installation simulation now verifies that preparation and installation share
  one application-owned session while remaining visibly labelled as simulation-only.
- All 628 affected source/candidate/project/local-installation, Guardian, ROM Studio and First Light
  regressions pass. The complete Desktop/Python suite passes all 2,674 tests with zero failures,
  errors or skips in 817.502 seconds. Its JUnit record is
  `/tmp/romverse-preparation-mission.Zts9qa/desktop-full.xml`.
- Whole-source Ruff and final diff checks pass. Approved production logo files were not edited.

## Deliberate remaining boundaries

- The shared mission is in memory. Reconstructing an interrupted worker safely after a process crash
  or host reboot belongs to Continuity Core and is not claimed here.
- Manual individual-image mapping remains a separate dialog-owned Expert lifecycle.
- This checkpoint does not prove a particular ROM boots, establish partition readback, certify a
  Device Pack, or complete automatic diagnosis and repair.
- No physical phone command, running-app restart, package build, Companion change, website update,
  publication, or remote push was performed for this checkpoint.
