# Fedora Source Lab incomplete-readiness wording — 2026-09-10

## Scope and implementation

- Branch: `linux/stage1-desktop-readiness`.
- Product Assurance authorization:
  `f0696102f002e9caec5b36b4963b192a992464bb`.
- Implementation: `a40fa52c92dac2630caa526132217fa384512b87`
  (**Clarify missing Source Lab prerequisites**).
- Production ownership is exactly `src/romverse/ui/rom_studio.py`. The existing Source Lab
  readiness booleans and `LOCAL INPUTS READY` condition are unchanged. Only incomplete-state
  presentation changed so an absent original, inspection, contained tree or build plan is prefixed
  with **Missing:**; tree and plan rows also name their required next action.
- Test ownership is exactly `tests/test_rom_studio_ui.py`. One focused deterministic test advances
  the same synthetic project through three local states: working copy with tree/plan absent; tree
  present with plan absent; and all local prerequisites present. It asserts that incomplete text
  names only missing evidence and that the ready text remains unchanged.
- No button, navigation, sequencing, Genesis, Backup Center, Main Window, Guardian, Recovery,
  schema, Companion, Windows, Device Intelligence or package asset changed.

## Focused verification

- Exact selected test node
  `test_source_lab_readiness_names_only_missing_local_prerequisites`: **1/1 passed**. That one node
  contains assertions for all three Product Assurance-required evidence states; it is counted once.
- Ruff 0.16.6 focused lint passed for the two changed files. Focused Ruff format verification
  passed. Git diff/whitespace validation passed.
- No broad or overlapping test suite and no hosted CI ran.

## One offline Fedora rebuild

Exactly one corrected unsigned one-folder package was built using the established cached local
PyInstaller 6.22.2 environment. No dependency or network acquisition occurred.

- Package directory: `build/fedora-readiness-wording-f069610/ROMVERSE`.
- Executable: mode `0755`, 6,337,408 bytes, SHA-256
  `d110771c730b45695413c0606de072f9c560550c88ae223913ca1fd1e5e670e4`.
- Inventory: 423 regular files / 243,102,811 regular-file bytes / 38 internal links.
- This is a local unsigned development package. It was not installed, signed, published or
  released.

## Read-only no-network/no-phone observation

- Disposable private root: `/tmp/romverse-linux-readiness-wording-NOWMuD`, mode `0700`.
- Build copied the retained approved synthetic project/profile and changed only the copied
  settings workspace path. The copied settings remained mode `0600`, Guided, reduced-motion and
  offline/community/download/contribution disabled.
- Process-local Android-tool `PATH` was the copied empty directory. Bubblewrap used
  `--unshare-net`, a private minimal `/dev`, a read-only host root and a writable bind only for the
  disposable profile. No phone, emulator, Android simulation, ADB or Fastboot tool was available
  or used.
- The first sandbox command supplied no writable temporary directory, so the packaged process
  stopped before application initialization with `FileNotFoundError`. It opened no ROMVERSE
  window and touched no project state. Build corrected only the disposable harness by supplying a
  private `TMPDIR`; no rebuild, source change or project action was repeated.
- The one actual UI observation opened the corrected package, started on its retained project and
  invoked only the accessible **Open ROM Studio** navigation action. It did not invoke import,
  working copy, extraction, planning, Genesis or any later action.
- Source Lab accessibility exposed the exact current state:
  `Project readiness  •  INCOMPLETE  •  Missing: contained working tree (extract and verify it);
  Missing: Guardian-assessed build plan (create and verify it)`.
- It also retained `Working copy ready`, the exact existing snapshot
  `20260909T221648-eede3e`, and `6/8 steps complete  •  Next: Extract and verify working tree`.
  Neither former completed-action phrase appeared in the incomplete readiness line.
- After observation, the disposable workspace differed from the retained source only by the normal
  runtime-fault start marker. The project, working-copy, inspection, snapshot receipt and Vault
  entry hashes remained identical. The working tree still had zero files, its index and build plan
  remained absent, and tools still contained zero files.
- Selected retained hashes: project
  `56026d52de3e00163a26d938b95987358dcbe25031df7542b0c6a0484d4adf6c`; working-copy record
  `96c478c6d8e239b791e37fbdb008256bee76aee0acf3b02de146cbfc2cb4cb4a`; inspection
  `2158422a5283c3fc150b8e148ca1106627a599e61c6fe375739a02eea02dddf2`; snapshot payload
  `c3f5c1711d648a0f6c8f2ba2e3c910048c4e81e6f3ee39bb82e9e85888ac89c8`; snapshot receipt
  `b5566b5b52f662e459864772aa8214cca6e2926a02181fbe4896a1ffc1d36edd`; Vault entry
  `c10b11321785d55f1e40ee25374097db90bb08749299e3a398cc497951fd4e7c`.

Fedora accessibility exposed no compositor-owned application close action. Build verified and sent
`SIGTERM` only to the exact disposable ROMVERSE process; Bubblewrap returned exact status 143.
No clean-shutdown or restart-persistence claim is made. GNOME toolkit accessibility was restored
to false and no ROMVERSE process remained.

## Classification, gates and external actions

- **Implemented:** minimum presentation-only Source Lab missing-prerequisite wording correction.
- **Simulated/Tested:** 1/1 focused test, focused lint/format/diff checks, exactly one offline build
  and one actual read-only Fedora Source Lab observation after the disclosed pre-initialization
  sandbox-harness failure.
- **Hardware Verified:** no.
- **Released:** no.
- Guardian/Recovery/safety: this correction changes no readiness decision or authority. Exact
  evidence, Guardian-only authority, durable `UNKNOWN`, no blind retry, independent verification
  and permanent bootloader no-relock remain unchanged.
- Feature freeze: compliant minimum Stage 1 truthfulness correction; no new capability.
- Version gate: incomplete Source Lab text is ready for Product Assurance review. Extraction and
  every later build/device/consequence/v0.2/release gate remain **CLOSED**.
- External actions were limited to focused local test/lint/format/diff checks; exactly one offline
  cached build; a private copy of retained synthetic state; one failed pre-initialization sandbox
  attempt; one successful no-network package launch and read-only Source Lab observation; exact
  process termination; scoped commits; and planned Forgejo-first/GitHub branch synchronization.
  No import/copy/extraction/planning action, phone/emulator, real firmware, ADB/Fastboot, APK/package
  installation, Guardian/Recovery operation, flash, wipe, unlock/root, lock/relock, signing,
  publication, release or hosted CI occurred.

## Product Assurance review requested

Approve the presentation-only correction and keep extraction and every later Stage 1/release gate
closed. No next consequential slice is proposed by this checkpoint.
