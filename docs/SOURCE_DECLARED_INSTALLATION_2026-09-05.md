# Source-declared installation and read-only follow-up

ROMVERSE now has a separate Guided route for a **supported package installation procedure**.
It is not a universal Android installer and does not infer a flashing order from filenames.
The manually mapped image route remains available separately.

## What is supported

The first adapter recognizes the complete `flash_all.sh` declaration from the protected custom
HyperOS package previously used for the Xiaomi 17 Pro Max (`popsicle`). Its exact declaration
SHA-256 is `589afffba7bc1e3528f936caeb9fe3bfd43da8d4017d0b5d4562c6f9e2be41ac`.
The script is read as data, never executed. A recognized declaration establishes which
instructions ROMVERSE understands; it does not authenticate the publisher or prove that an
arbitrary repack, its images or its data-preserving mode have been physically tested.

The declaration becomes a typed, fully reviewable sequence: select slot A, write the 47 declared
physical slot-A images in order, write the full sparse super container with the declared 700M
transfer chunk limit, write `vbmeta_system_a` and `vbmeta_a`, optionally erase metadata and user
data, select slot A again, and optionally restart Android. There are 50 image writes and 53
default actions, 55 with data erasure, or 52 with neither erasure nor restart. Whole-super writes
do not imply that slot B is an untouched recovery route.

Both bootloader unlock states must be positively reported. A known wrong product, codename or
manufacturer is rejected; matching super capacity alone is not accepted as device identity.
ROMVERSE does not issue unlocking, relocking or verification-disabling commands in this route.
The declaration does not establish anti-rollback compatibility. That uncertainty remains a
warning, not a fabricated green safety result.

## User journey

1. Open **Prepare local image installation…** from Forge Control or Genesis. Choose
   **Follow the package's supported installation procedure**. This uses the protected package,
   not the rebuilt candidate; the other two choices retain their separate provenance.
2. Choose whether to erase user data and whether to restart Android. Erasure is off by default.
   Keeping data is not a compatibility guarantee. Keep an independent backup and recovery route.
3. Verification freshly hashes the protected archive and every manifest-listed member, checks
   sparse geometry and rejects unsupported or ambiguous declarations. No phone command is sent.
4. Select the exact USB phone. A necessary mode change is separately reviewed and confirmed.
   Review the complete procedure, hashes, target, slot, capacities and warnings.
5. Explicitly confirm the exact plan. Cancel is the default. ROMVERSE privately stages and
   verifies every image before the first slot change, then runs the declared actions while
   holding one device-operation lock. It records intent before each command and checks exact
   device state, tool identity and staged image bytes at their use boundaries.
6. Stop requests take effect between actions. A failed or interrupted sequence is not
   automatically retried. Diagnosis receives the exact attempted phone and current project/source
   attribution, never an unrelated connected device.
7. A confirmed final restart starts a separate read-only boot observation, with up to fifteen
   minutes to arrive and a measured stability interval. Installation command completion is not
   proof of boot, image readback or subsystem health.
8. Reopening Genesis shows bounded, source-associated installation history. **Review installation
   and boot results…** opens a read-only follow-up, not another installation. It can observe the
   same phone again without rebooting or writing it. Invalid or interrupted newer evidence does
   not reveal an older success in its place. Camera, calls, Android Auto and other subsystem tests
   remain separate; a stable boot record does not certify the full first-boot stage.

Local receipt digests detect changes to recorded evidence; they are not externally signed
production certificates or fresh proof of what remains on a phone. No production Guardian grant
or Device Pack attestation is invented by this route.

## Verification boundaries

The existing protected custom archive was checked read-only using the production verifier:
SHA-256 `adbb99b9d6e6c3e62520c144d8b841ff6f34543feddf2969cfc38f4acf90f89a`,
11,797,532,065 archive bytes. All manifest files and 50 images verified. The sparse super image
expands to 13,421,772,800 bytes. This check performed no extraction, image copying or phone action.

The automated user journeys use tiny synthetic images, real Qt dialogs, production services and
strictly inert transports. The simulated phone starts on slot B. Tests exercise the ordered
53/55/52-action variants, consent decline, target/source/tool changes, cancellation, failures at
different actions, private snapshots, receipt linkage, measured boot and exact-target recovery.
The reusable `scripts/simulate_source_installation.py` produces clearly labelled simulation
screenshots and a measured layout/results report in a new isolated directory. Its declaration
fixture is bounded data and is never executed.

Unsupported OEM scripts, payload OTAs, generic Fastboot update packages and other devices still
need explicit adapters and validation. Modified rebuilt candidates are not silently substituted
into this protected-source procedure. No physical flash or broad device compatibility has been
proven by these simulations. Approved ROMVERSE and RadForge Labs logos remain unchanged.

## Local desktop checkpoint — 2026-09-05

The full Fedora desktop regression completed successfully: **2,398 tests passed in 770.14
seconds**, with no failures or skips. A native Qt crash in the preceding attempt was reproduced
with the new Stop tests followed by Time Machine. An inert test callback retained a closed-dialog
reference cycle; restoring that callback at teardown removed the reproducer. No production
garbage-collection policy was weakened and no crashing test was excluded.

After full-suite collection, a second test callback received the same cleanup, the simulation
helper's history-path assertion was made platform-neutral, and the real-symlink test was guarded
only for Windows error 1314 (missing symlink privilege). MainWindow received formatting-only
cleanup, checked for identical parsed program structure. The final changed-area run passed
**233 tests in 94.72 seconds**, including installation, history, Guided entry and Time Machine.
These counts overlap; they are not additive. The six new installation suites are now selected by
Windows CI; all 162 selected cases passed locally, but no Windows job was run for this checkpoint.

Repository-wide `ruff check .` and `git diff --check` pass. The 19 scoped Python files pass their
format check. Repository-wide formatting is **not** green: 26 files remain flagged, including
inherited MainWindow formatting outside this increment. This remains a release-quality task.

The final installed wheel initializes a new disposable workspace, loads 22 Device Packs, 170 known
fixes, 281 offline evidence records and 19 desktop routes, and reopens populated project evidence
byte-for-byte. Its installed user simulation executes 53 inert actions / 50 image writes, reopens
saved history, and completes two separate accelerated 60-second / 11-sample boot windows. Opening
history sends no phone command; the second boot check adds zero changing actions and preserves the
original installation receipt. Five compact-window screenshots were reviewed.

The self-contained Fedora application launches successfully in its isolated smoke workspace.
All 238 bundled ROMVERSE code objects match current source; the 290-member wheel preserves all
runtime modules/assets and 22 indexed Device Packs byte-for-byte. The Linux ZIP passes member,
boundary and CRC checks: 460 files, 359,892,970 expanded bytes.

Local artifacts and XML/simulation evidence are retained under
`dist/source-installation-2026-09-05/` (not published or installed over the user's running app):

| Artifact | SHA-256 |
| --- | --- |
| `romverse-0.1.0-py3-none-any.whl` | `b3a753d3bf7c4bc780be58fea9d2f393cbee9da5540f858ab07f8f6978aa91b6` |
| `ROMVERSE-Linux-Source-Installation-checkpoint.zip` | `e1617bc8ad966cd34503c500bd5a8a5bedda07c498a8d5684ecaa68898c00090` |

This is a local software checkpoint, not a production release. No physical phone was flashed,
erased or rebooted, the user's running desktop was not restarted, and nothing was pushed or
published. Full rebuilt-candidate installation, local First Light subsystem follow-up, current
Windows execution and supported-hardware validation remain incomplete. All twenty master-goal
stages retain their full scope.
