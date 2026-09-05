# Recovery in-place scan continuation

This bounded Stage 1 checkpoint removes a navigation dead end from Recovery Autopilot. Connection,
authorization and bootloader-identity routes no longer send a Guided user to Command Deck or Device
Atlas and leave the recovery incident behind.

## Implemented behavior

- **Restore USB evidence**, **Authorize ADB** and **Refresh bootloader identity** routes now expose
  direct, outcome-specific controls: **Check connection now**, **Check authorization now** and
  **Refresh identity now**.
- Activating one of those controls records the reviewed route, keeps Recovery Bay and the same
  incident active, and requests one fresh read-only Device Engine scan.
- Fresh scan results already flow back through the shared Recovery service. The exact-device
  boundary therefore either updates the same incident or continues waiting for the original phone;
  it cannot attribute another connected phone.
- Recovery-owned informational guidance is shown inline rather than in a modal dialog. It remains
  available beside the incident and does not imply that a repair ran.
- Routes owned by Archives, Guardian, Time Machine, ROM Studio or another typed subsystem retain
  their explicit owner handoff. This change does not turn advisory ranking into execution.

## Safety boundary

The three in-place controls request discovery only. They do not run a device-targeting command,
observe boot, switch slots, erase data, write an image, approve a plan or retry an uncertain action.
Recovery continues to require immutable sealed incident identity, fresh matching device evidence,
typed action ownership and any separate meaningful confirmation. Bootloader relocking remains
forbidden.

## Verification

The final affected regression run passes **87 tests with zero failures, errors or skips in 70.599
seconds** across Recovery UI, Recovery Autopilot, Recovery evidence, desktop
interrupted-installation routing and Activity Center integration. It verifies that in-place
authorization and Fastboot identity controls emit one read-only scan request and no owner
navigation, local guidance opens no modal, typed external owner routes still dispatch, incident
history is retained and `phone_changed` remains false.

Changed-file Ruff, Python compilation and diff checks pass on Fedora/Linux. Windows and physical
hardware were not exercised.

## Honest status

This behavior is implemented and simulated/tested, not hardware verified or released. It is a
Stage 1 Guided-friction correction under the active feature freeze and does not open the v0.2
Golden Foundation gate. No physical phone operation, running-app restart, package installation,
Companion or website change, publication or remote push occurred. Approved ROMVERSE and RadForge
Labs production logo assets were not edited.
