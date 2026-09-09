# Fedora installed-package cancellation and context journey

## Scope

- Authoritative source base: `50c56ed4c3c7057b941d2c7ea626977e08e0e006`.
- Retained unsigned package: `build/fedora-f1da4b9/ROMVERSE`.
- Executable SHA-256:
  `4fbfed3244d93ba535413151c26f5fe53ef526d402f638a5e81e662f8b562500`.
- Test profile: installed one-folder package, Fedora, disposable workspace, no simulated device,
  no imported firmware and no production execution.

## Exact manual-acquisition journey

ROMVERSE was launched with an isolated settings profile, a disposable workspace and no host tools
on `PATH`. In the application settings, **Acquire hash-verified build tools when required** was
disabled before the journey so Forge Arsenal remained an explicit user decision.

1. ROM Studio created one project named **Installed Manual Cancellation Journey**.
2. **Inspect firmware in place…** opened the packaged firmware chooser. Cancelling it left the
   project manifest byte-identical at SHA-256
   `48e9eb3c9868695bf4f4a4abf0708282b0ba6770ebcb0422f24dd5090fe47210`.
3. The project remained selected, continued to report **Awaiting original**, and kept
   **Inspect firmware in place…** and **Import original…** as its visible next actions. Its durable
   `original` value remained `null`; no source file or working tree appeared.
4. Command Deck's **Resolve Platform Tools** handoff opened
   **ROMVERSE • Start Device Engine**. Forge Arsenal showed an enabled
   **Install and verify requirements** action and an enabled **Close** action. No installation had
   begun.
5. Closing Forge Arsenal created no install plan and no managed download. The workspace's `tools`
   directory remained empty.
6. Returning to ROM Studio preserved the exact project, project ID and source-less next action.
7. The package process was closed and reopened once against the same profile and workspace. The
   reopened application restored exactly one project with the same ID, name, `original: null`,
   empty Device Pack ID and next action. No device, firmware result, Guardian execution result or
   Recovery result was invented.

The automation host used a normal process termination signal for the close/reopen boundary because
the packaged window does not expose a window-close action through its Fedora accessibility tree.
This demonstrates durable context preservation across a process restart; it is not represented as
a separate clean-shutdown verification. Desktop accessibility was enabled only for this interaction
and restored to its original disabled state afterward.

## Preliminary preference-enabled observation

An initial disposable run inherited the creator profile's enabled automatic-tool-acquisition
preference. Pressing **Resolve Platform Tools** therefore performed the behavior that preference
authorizes: ROMVERSE downloaded and verified the pinned Platform Tools package into that disposable
workspace, activated the read-only runtime and began its periodic discovery loop. This was a test
setup mismatch rather than a reproduced source defect, and no system-wide package was installed.

The immutable Guardian ledger for that preliminary workspace verifies as valid with **14 records**:
seven `adb.devices` and seven `fastboot.devices` host-discovery probes. Every entry is allowed,
read-only, risk `none`, return code `0` and target `host`; there are **zero device-targeted probes**.
The ledger tail is
`73bd284d2eb89ea21cc16c373358f6faec4491c871af0088608f4637063badfa`.
No phone identity or device-specific command was observed. The downloaded tools and receipt remain
confined to the disposable `/tmp` workspace as evidence of the observation.

## Classification and limits

- **Implemented:** no production or test source changed.
- **Simulated/Tested:** genuine packaged Fedora UI interaction and durable-state inspection; no
  synthetic device or success state.
- **Hardware Verified:** no. Host-only discovery returned no target and issued no device-targeted
  probe.
- **Released:** no. The package remains unsigned, local and unpublished.
- No firmware/APK operation, device write, reboot, Recovery/Fastboot transition, flash, wipe,
  unlock/root, lock/relock, signing, publication or release occurred.
- Guardian-only authority, exact-device/source/incident binding, durable `UNKNOWN`, no blind retry,
  independent verification and permanent no-relock remain unchanged.

