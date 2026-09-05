# Preferred verified ROM installation route

This Stage 1 correction removes outdated **local image installation** language from the Guided
entry journey. The route chooser now describes the user's intent and makes a complete, understood
installation procedure the default whenever that route is available.

## Guided behavior

- Forge Control and Genesis use one consistent **Prepare verified ROM installation…** action.
- A complete rebuilt-ROM composition is preferred when its candidate service is available.
- When no rebuilt-candidate service is available but the protected package has a source
  installation service, the complete protected-firmware procedure is preferred.
- Manual rebuilt and protected-source image subsets remain available. They are explicitly labelled
  as manual subsets, require the user to supply partition, slot and ordering details, and are never
  presented as a complete ROM installation.
- Reopening an in-progress preparation restores the exact retained route and choices instead of
  replacing them with the current default.
- The route chooser only verifies and prepares evidence. It does not reboot, write, retry, unlock,
  relock or otherwise change a phone.

## Evidence and safety boundary

A complete route means ROMVERSE understands and verifies the declared package procedure. It does
not mean OEM trust, physical boot success, subsystem health, broad device compatibility or release
certification. Manual mapping remains possible for deliberate specialist use, but missing procedure
knowledge is not inferred from image filenames. Every later phone-changing operation keeps its own
exact-device review, consequences, Guardian checks and explicit final consent.

## Verification

One non-overlapping affected regression run covered Guided Mission, Forge Control, project/manual
installation, complete rebuilt candidate composition, complete protected-source installation,
history, Guardian and desktop integration: **426 tests, 0 failures, 0 errors and 0 skips in 82.957
seconds**. The run includes user-style Qt selection and dispatch behavior and inert transports; it
is simulation/software evidence on Fedora/Linux, not physical phone verification.

Changed-file Ruff, Python compilation and diff checks pass. Windows was not exercised. No physical
phone operation, app restart, package installation, Companion or website change, publication or
remote push occurred. The approved ROMVERSE and RadForge Labs logo assets were not edited.
