# Fedora Source Lab plan-verification continuity evidence

Date: 2026-09-10 (Australia/Brisbane)
Branch: `linux/stage1-desktop-readiness`
Product Assurance authorization: `cd7ca570e5c909168c06af0664062c9e82699b69`
Scoped implementation: `8ac135f74ca1f3c691e18d0eee5da3d6574ef6b6`

## Correction implemented

Source Lab now records an accepted exact-plan verification into the shared Guided mission state
before it emits completion or refreshes successful UI. A new plan attempt and every failed or
mismatched verification clear that state before Source Lab can advertise success. A persistence
failure fails closed, reports no successful completion, and leaves Forge disabled.

The 8/8 Guided counter, Plan inputs wording, and Forge availability now consume the same persisted
state. The implementation changes only `src/romverse/ui/rom_studio.py`; focused coverage changes
only `tests/test_rom_studio_ui.py`.

## Focused verification

- Ruff 0.16.5 lint passed for both changed files.
- Ruff format verification passed for both changed files.
- Git whitespace/diff validation passed.
- Final affected acceptance: **7/7 unique test nodes passed**:
  - persisted exact verification converges the 8/8, Plan inputs, and Forge views and survives reopen;
  - a new plan and a failed verification invalidate prior success;
  - verification-state persistence failure reports no success and disables Forge;
  - same-project Command Deck handoff remains correct;
  - forged success evidence bound to a different tree is rejected and invalidates shared success;
  - Genesis simulated-device continuity remains non-authoritative; and
  - the existing verified non-flashable Forge workflow remains available only after verification.
- An earlier development run reported 6 pass / 1 fail because the new invalidation test fixture
  omitted its working-copy evidence. The fixture was corrected; this was not a product failure and
  is not added to the final 7-test total.

No broad or full regression suite was run or counted; Product Assurance authorized the focused
correction and proportional affected checks only.

## Fedora package

Exactly one cached/offline Fedora build completed successfully with PyInstaller 6.22.2 and Python
3.14.7. No dependency or network acquisition occurred.

- Package: `build/fedora-plan-continuity-cd7ca57/ROMVERSE`
- Executable: `build/fedora-plan-continuity-cd7ca57/ROMVERSE/ROMVERSE`
- Executable mode/size: `0755`, 6,338,544 bytes
- Executable SHA-256: `e42d66cf95bcd66170f8500faf7c51bcbbc10c99c8895f26fb1b411b06e703e5`
- Inventory: 423 regular files, 243,103,947 regular-file bytes, 38 symbolic links
- Host: genuine Fedora Linux, kernel `7.1.13-200.fc44.x86_64`, x86-64

PyInstaller reported its existing non-fatal Linux limitations: the platform ignored the Windows/
macOS icon input and the optional hidden import `xxsubtype` was absent. The build still completed.
The package is an unsigned, local development artifact; it was not installed, published or
released.

## Isolated retained-plan acceptance

One launch of the newly built package used a fresh private copy of the retained accepted-plan
workspace at `/tmp/romverse-linux-plan-continuity-WHB5SN`. Bubblewrap supplied a distinct network
namespace with loopback only (zero packets/bytes), a private home/config/data/cache/temp set, and an
empty Android-tool path. No phone, emulator, ADB, Fastboot or network service was available.

Precondition:

- accepted 1,106-byte plan SHA-256
  `1bd66952a0fae926160d095694e3a1f813e10ee145b0b9839e7093d10034ecf4`;
- planned tree SHA-256
  `84c7699a74b49f5d940c7d307adad07fab6207edd7cd61ee1d8361bbfb259de8`;
- `build_plan_verified: false`;
- Source Lab showed 7/8, **Plan inputs • verification required**, and disabled Forge.

The acceptance selected **Build & Proof** and invoked **Verify plan exactly once**. It did not invoke
Plan, Forge Bundle, Forge Control, any build, or any device/consequential action.

Observed result:

- `guided-mission.json` durably changed to `build_plan_verified: true`;
- Source Lab converged to **8/8 steps complete • Next: Workflow complete**;
- Plan inputs changed to **last background verification passed**;
- Forge Bundle became enabled but was observed only and was not invoked;
- Activity gained one exact `Build plan inputs verified` success;
- Live Console gained the exact Verify Plan running/succeeded pair;
- plan SHA-256 and `created_at` remained unchanged, proving no re-plan;
- working-tree index SHA-256 remained
  `2822bd269479def4b22ee3655a0971ec5d8310641b7141bebbc10fffe8bf4a66`;
- extracted metadata and inert payload remained respectively
  `7b21d60b939893071ad4895c3270860ef87cd710eda6c2c203f51d256453d9de` and
  `5db7a969a06334c08958a02c13722f11a343126f781fdcbdbdf9cf05754b4237`;
- Vault entry count remained two; and
- no Forge or receipt file was created.

The exact app process was terminated after observation because the compositor exposed no close
action; exit 143 is therefore expected and no runtime reopen/shutdown claim is made. The focused
automated test separately verifies reopen continuity. Desktop accessibility was restored to false,
and no ROMVERSE process remained.

## Classification and safety

- **Implemented:** minimum Source Lab/Guided shared-state correctness correction.
- **Simulated/Tested:** seven focused software tests plus one genuine Fedora no-network/no-phone
  retained-plan UI acceptance.
- **Hardware Verified:** no Android hardware claim. No phone was connected or operated.
- **Released:** no.

Guardian-only authority, exact-device evidence, independent verification, durable UNKNOWN, no blind
retry and permanent bootloader no-relock are unchanged. This correction grants no build, flash,
device, signing, publication or release authority and remains within the feature freeze.
