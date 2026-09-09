# Fedora Source Lab inert plan verification blocker — 2026-09-10

## Scope and preflight

- Branch: `linux/stage1-desktop-readiness`.
- Product Assurance authorization:
  `bfbf359b3b493f119543bccbd1a37ae9beab6a43`.
- Application, tests and package bits were unchanged. Build reused the approved unsigned package
  at `build/fedora-readiness-wording-f069610/ROMVERSE`; its mode-`0755`, 6,337,408-byte executable
  remained SHA-256 `d110771c730b45695413c0606de072f9c560550c88ae223913ca1fd1e5e670e4`.
- Fresh private disposable root: `/tmp/romverse-linux-inert-plan-5gwpeq`, mode `0700`, copied from
  the approved contained-extraction state. Only the copied settings workspace path changed;
  Guided/offline/community/download/contribution controls remained in their approved state.
- Preflight reverified the 551-byte protected original, working baseline and automatic snapshot as
  byte-identical at SHA-256
  `c3f5c1711d648a0f6c8f2ba2e3c910048c4e81e6f3ee39bb82e9e85888ac89c8`.
- The contained tree had no symlinks and exactly the approved 257-byte metadata and 40-byte inert
  payload marker. Strict pre-plan tree-index SHA-256 was
  `8aab1ce6c83ba64774086b289e03c55ada45d138f12e8e1883cb0f7d1480b557`. No build plan existed;
  Guided remained at `workspace` with no install request/error/verified plan, and tools were empty.

## Exact Plan and Verify actions

- The unchanged package launched once under Bubblewrap `--unshare-net`, a private minimal `/dev`,
  read-only host root, writable disposable profile, private temporary directory and empty
  process-local Android-tool `PATH`.
- Host network namespace was `net:[4026531833]`; package namespace was distinct at
  `net:[4026533562]`. Its only interface was loopback with zero receive/transmit bytes and packets.
- Build used only **Open ROM Studio**, selected the visible **Build & Proof** tab, and invoked the
  visible enabled **Plan build (dry-run)** action exactly once.
- Only after the durable plan appeared and **Verify plan** became enabled, Build inspected its
  safety fields and invoked that action exactly once. Activity and Live Console independently
  record one plan success and one verify-plan success; no retry or inferred completion occurred.

## Safely produced and independently verified plan

- Saved `build-plan.romverse` is 1,106 bytes at SHA-256
  `1bd66952a0fae926160d095694e3a1f813e10ee145b0b9839e7093d10034ecf4`.
- Independent product-service reload accepted it as schema 2 for exact project
  `history-refresh-acceptance-7b4eca34` and exact contained tree
  `working_roms/history-refresh-acceptance-7b4eca34/tree`.
- It binds exact protected-source SHA-256 `c3f5c171…89c8`; ordered inputs
  `META-INF/com/android/metadata` and `payload.bin`; no symlinks; no partitions; no Device Pack;
  no recipe/debloat/choice/toolchain authority; and no required/unverified tools.
- It is `local_only: true`, `execution_locked: true`, `flashable: false`, and
  `execution_authority: none`. Guardian risk is `none`; `guardian_status: ready` is explicitly the
  recorded preflight result for a read-only plan, with reason **All available preconditions pass
  for a read-only plan**. It is not a Guardian approval or execution grant.
- No Guardian ledger/approval, device evidence, phone action, flash/installation record or valid
  relock path exists. Device DNA/Compatibility Matrix continue to report Guardian flash
  `UNCONFIRMED`/Unknown and bootloader relocking permanently `UNSUPPORTED`/Known Incompatible.
- Independent re-enumeration found only the 257-byte metadata at SHA-256 `7b21d60b…53d9de` and
  40-byte marker at `5db7a969…4b4237`. Independently recomputed tree SHA-256
  `84c7699a74b49f5d940c7d307adad07fab6207edd7cd61ee1d8361bbfb259de8` exactly matches the
  plan. Product `verify_tree` independently returned valid with identical expected/actual digest.
- Planning refreshed only the tree-index timestamp and its integrity digest; all material bindings
  stayed exact at two files, 297 bytes, the same contained relative path and source digest. The new
  518-byte index is SHA-256 `2822bd269479def4b22ee3655a0971ec5d8310641b7141bebbc10fffe8bf4a66`
  with record digest `3d4abb4a130b3929b5062bd7164e6698d743695f2049e123e760503c98a87976`.
- Normal Source Lab rendering derived a 502-byte ROM DNA record at SHA-256
  `945cdf2b14cd49a6487cf8a91ea691e5e00ebbc87c7e729593e4cfbdb9fe85d0`, binding the same exact
  project/source/tree and no Device Pack/recipe. It grants no authority.
- Source, baseline, snapshot, project, working-copy and inspection evidence remained byte-identical.
  Existing Project Vault entry count remained two; Plan/Verify created no additional snapshot or
  Vault checkpoint. Activity grew from five to seven records and Live Console from 16 to 20—the
  exact running/succeeded Plan and Verify Plan events.
- Guided persisted state remains `workspace`, `install_requested: false`,
  `build_plan_verified: false`, and `last_error` empty. No ROM build/bundle, Forge, Recipe, Guardian,
  Recovery or device action occurred.

## Reproduced UI truthfulness blocker

The exact plan and tree verification succeeded, but the post-verification Source Lab UI retained
contradictory state:

- operation evidence recorded **Build plan inputs verified** and **Verify Plan ... succeeded**;
- the local checklist showed **8/8 steps complete  •  Next: Workflow complete**;
- **Forge Bundle** became visible and enabled;
- the plan evidence line still said **Plan inputs  •  verification required** because the persisted
  Guided `build_plan_verified` flag remained false.

Build did not invoke Forge Bundle or any other action. This checkpoint does not claim the Source
Lab plan-verification acceptance passed, even though the plan itself is execution-locked,
non-flashable and independently verified. The stale verification statement and simultaneous
workflow-complete/enabled-Forge state are referred to Product Assurance as one bounded Stage 1
truthfulness/continuity defect. No source change or retry was attempted.

Fedora accessibility exposed no compositor-owned application close action. Build verified and sent
`SIGTERM` only to the exact disposable ROMVERSE process; Bubblewrap returned exact status 143.
No clean-shutdown or restart-persistence claim is made. GNOME toolkit accessibility was restored
to false and no ROMVERSE process remained.

## Classification, gates and external actions

- **Implemented:** no new product behavior; runtime evidence/handoff only.
- **Simulated/Tested:** the dry-run plan and exact tree verification succeeded in one genuine
  Fedora no-network/no-phone package run. The Source Lab post-verification UX acceptance is
  **BLOCKED** by the retained contradiction above. Per authorization, no unchanged automated test
  rerun and no package rebuild occurred.
- **Hardware Verified:** no phone, emulator or Android simulation was used.
- **Released:** no. The package remains local, unsigned, uninstalled and unpublished.
- Guardian/Recovery/safety: plan authority remains none, execution remains locked and no
  consequential boundary was entered. Guardian-only authority, durable `UNKNOWN`, no blind retry,
  independent verification and permanent bootloader no-relock remain unchanged.
- Feature freeze: no product change. Any correction requires a new minimum Product Assurance
  authorization.
- Version gate: the plan artifact and verification evidence are valid, but the user-visible Source
  Lab verification boundary is **BLOCKED**. ROM build/bundle and every device/consequence/signing/
  publication/v0.2/release gate remain **CLOSED**.
- External actions were limited to read-only preflight; a fresh private state copy; one no-network
  package launch; ROM Studio/Build & Proof navigation; exactly one Plan and one Verify Plan action;
  deterministic local plan/index/ROM-DNA/activity evidence writes; read-only independent reload and
  rehash; exact process termination; scoped documentation commits; and planned Forgejo-first/GitHub
  synchronization. No test/rebuild, import/working-copy/extraction repeat, ROM build/bundle/Forge,
  network/tool acquisition, phone/emulator, real firmware, ADB/Fastboot, firmware/APK mutation,
  Guardian/Recovery execution, flash, wipe, unlock/root, lock/relock, signing, installation,
  publication, release or hosted CI occurred.

## Product Assurance review requested

1. Approve the exact execution-locked/non-flashable plan artifact and independent tree verification.
2. Classify and authorize the minimum correction for stale `Plan inputs • verification required`
   after successful Source Lab Verify Plan, including the contradictory 8/8 complete and enabled
   Forge state.
3. Keep Forge/ROM build and every later Stage 1/release boundary closed.
