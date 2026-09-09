# Fedora Source Lab durable-history refresh — 2026-09-10

## Scope and implementation

- Branch: `linux/stage1-desktop-readiness`.
- Product Assurance authorization:
  `777981cdc30a7d9f0987945148cdca7ac5f4dbd0`.
- Implementation: `da50987f85a21fdae1b7f02268c642a3acbe9cfe`
  (**Refresh Source Lab after durable history**).
- Production ownership stayed within the authorized two files:
  `src/romverse/ui/backup_center.py` and `src/romverse/ui/main_window.py`.
- Backup Center now publishes `local_history_completed(project_id)` only after a successful
  `VaultEntry` result matches the exact Project Vault worker project and the local history surface
  has refreshed. An incomplete worker, failure, non-history result or mismatched project emits no
  completion notification.
- Main Window listens for that exact notification and refreshes ROM Studio only when the notified
  project is still the currently displayed project. Another project's completion cannot replace or
  refresh the visible project.
- Automatic Time Machine snapshot/Project Vault protection remains mandatory and unchanged.
  Genesis, ROM Studio implementation, Guardian/Recovery, Companion, Windows, Device Intelligence,
  package assets and every other production area were untouched.

## Focused verification

- `tests/test_time_machine_ui.py` plus the exact Main Window integration test
  `test_completed_local_history_refreshes_only_the_current_rom_project`: **22/22 passed**.
- The retained automatic-history test now proves each durable capture emits the exact project ID.
  A new failure/incomplete-worker test proves no false completion notification is emitted.
- The Main Window integration proves another project's completion causes no refresh or project
  replacement, while the current project's completion refetches that exact project.
- Ruff 0.16.6 focused lint passed. Ruff 0.16.6 focused format check passed for all four changed
  production/test files. Git diff/whitespace check passed.
- No broad or overlapping test suite, hosted CI or unchanged-package run was performed. The count
  above is 22 unique selected nodes, not a cumulative/double-counted number.

## One offline Fedora rebuild

Exactly one corrected unsigned one-folder package was built using the established local cached
PyInstaller 6.22.2 environment. No dependency or network acquisition occurred.

- Package directory: `build/fedora-history-refresh-777981c/ROMVERSE`.
- Executable: mode `0755`, 6,337,400 bytes, SHA-256
  `25f8b1c6e5eec861d0a29f21b3717b555058f5c86757abe9ed8e072505a4457d`.
- Contained package inventory: 423 regular files / 243,102,803 regular-file bytes / 38 internal
  links.
- The package is a local development build. It is unsigned, unpackaged for release and unpublished.

## Fresh corrected-package acceptance

- Fresh private root: `/tmp/romverse-linux-history-refresh-l0Djtb`, mode `0700`.
- Settings: mode `0600`, 670 bytes, SHA-256
  `ea33acc45036fb023520189080ae1ea129aa3c3517fd387fc6cedf970699ebcb`; Guided mode and all
  online/community/download/contribution controls false.
- Process-local Android-tool `PATH`: an empty directory under the private root.
- Bubblewrap `--unshare-net`: application namespace distinct from Build's, with only zero-byte
  loopback throughout the journey.
- Source: byte-identical copy of the approved deterministic harmless ZIP, mode `0400`, 551 bytes,
  SHA-256 `c3f5c1711d648a0f6c8f2ba2e3c910048c4e81e6f3ee39bb82e9e85888ac89c8`.
- Project: **History Refresh Acceptance**, ID `history-refresh-acceptance-7b4eca34`.

Build used the normal Command Deck/Genesis route to create the project, accepted protected intake
of only the harmless fixture, completed bounded Provenance, reached task 4 with 3 of 15 tasks
verified, and used Genesis **Save & exit**. Pre-action inspection proved `working_roms`,
`time_machine` and `tools` empty for the fresh workspace; source and protected original were
mode/size/hash identical.

From ROM Studio Source Lab, Build invoked exactly one accessible **Create working copy** action.
It did not use **Resume Mission** or **Prepare working lab**. After the successful background
history capture:

- the contained writable baseline was 551 bytes and SHA-256 `c3f5c171…89c8`;
- the strict working-copy record bound exact project/path/size and matching source/current digest;
- automatic snapshot `20260909T221648-eede3e` was 551 bytes and SHA-256 `c3f5c171…89c8`;
- Project Vault entry `20260909T221648-94757d12` was labelled **Protected working baseline**, had
  zero tree files/bytes, and bound the exact source/project/inspection/Device DNA evidence;
- Source Lab automatically refreshed to **Snapshots • 1 (newest first)**, displayed that exact
  snapshot ID/size/current-evidence state, and no longer contained **No snapshots yet**;
- the next visible workflow instruction remained **Extract and verify working tree**;
- the Guided mission stayed at task 4 `workspace`, with no error, build plan or install request;
- the working tree contained zero files, the tree index was absent and tools remained empty.

Activity truthfully recorded protected import, working-copy success and automatic Project Vault
success. Live Console truthfully retained 12 import/Provenance/Genesis/working-copy/Vault events.
No device evidence, Guardian ledger, Recovery incident/result, consent or execution record exists.
The packaged offline archive was created locally at its retained 880,760-byte SHA-256
`2384ebb6ce9616af2270991da2c7b594d08b7534e71bf819549c92c091e27764`; it was not refreshed
from the network.

## Separate retained wording defect

The completed-history defect is fixed and its acceptance passed. The same Source Lab card also
contains a separate pre-existing readiness sentence claiming **Contained working tree extracted;
Guardian-assessed build plan saved** even though the page correctly says the next step is extraction
and the filesystem contains no tree, tree index or build plan. This false readiness wording is not
caused by the asynchronous history refresh and lies outside the two-file authorized correction.
Build made no unauthorized `rom_studio.py` change and refers this distinct truthfulness defect to
Product Assurance for minimum disposition.

## Exit, classification and external actions

Fedora accessibility again exposed no compositor-owned main-window close action. After the exact
acceptance evidence was captured, Build verified and sent `SIGTERM` only to the corrected package
process; Bubblewrap returned exact status 143. The runtime guard contains one start marker and no
clean-close marker. No clean-shutdown or restart-persistence claim is made. GNOME toolkit
accessibility was restored to false.

- **Implemented:** exact successful-history notification and current-project-only Source Lab
  refresh.
- **Simulated/Tested:** 22/22 focused tests, one offline package build and one genuine Fedora
  corrected-package no-network/no-phone runtime acceptance.
- **Hardware Verified:** no.
- **Released:** no.

External actions were limited to focused local tests/lint/format/diff checks; exactly one offline
cached build; one fresh private profile/project and byte-identical harmless fixture copy; one
Bubblewrap-isolated package launch; normal import/Provenance/Genesis **Save & exit**; exactly one
Source Lab **Create working copy**; automatic local rollback/evidence writes; exact process
termination; read-only evidence/Git inspection; and scoped commits. No network request,
real firmware, extraction, retry, tool/download/install, phone/emulator, ADB/Fastboot, APK/firmware
mutation, build plan/ROM build, Guardian/Recovery execution, flash, wipe, unlock/root, bootloader
lock/relock, signing, publication, release, hosted CI or Forgejo Action occurred.

## Product Assurance review requested

1. Approve the durable-history notification/current-project refresh and the successful corrected
   package acceptance.
2. Authorize a separate minimum correction for the false Source Lab readiness sentence, without
   reopening or broadening this completed history-refresh slice.
3. Keep extraction and every later build/device/release boundary closed.
