# Fedora non-flashable Forge Bundle acceptance blocker

Date: 2026-09-10 (Australia/Brisbane)
Branch: `linux/stage1-desktop-readiness`
Product Assurance authorization: `624cd62296b5d8a37032b2bc819f42c04160fe94`
Application/evidence base: `5cf5eaeb7ef323c689a60f5935a16d579aea337d`

## Result

**BLOCKED — deterministic Forge artifact passed, but Project Vault history changed contrary to the
exact acceptance contract.** Build stopped immediately after observing the mismatch. It did not
retry, repair, re-plan, clean the disposable result, or start another application run.

## Exact preconditions

One fresh disposable profile was mode `0700`. It retained Guided mode with online intelligence,
community research, Synapse contributions and automatic tool download disabled. Before launch:

- the mode-`0755`, 6,338,544-byte packaged executable was SHA-256
  `e42d66cf95bcd66170f8500faf7c51bcbbc10c99c8895f26fb1b411b06e703e5`;
- the protected 551-byte synthetic source was SHA-256
  `c3f5c1711d648a0f6c8f2ba2e3c910048c4e81e6f3ee39bb82e9e85888ac89c8`;
- the 1,106-byte schema-2 plan was SHA-256
  `1bd66952a0fae926160d095694e3a1f813e10ee145b0b9839e7093d10034ecf4`;
- the tree index was SHA-256
  `2822bd269479def4b22ee3655a0971ec5d8310641b7141bebbc10fffe8bf4a66`;
- the 257-byte metadata and 40-byte inert payload were respectively
  `7b21d60b939893071ad4895c3270860ef87cd710eda6c2c203f51d256453d9de` and
  `5db7a969a06334c08958a02c13722f11a343126f781fdcbdbdf9cf05754b4237`;
- Guided state was `workspace`, `build_plan_verified: true`, `install_requested: false`, with no
  error;
- Source Lab showed 8/8, last background verification passed and enabled Forge Bundle; and
- there was no prior Forge receipt, archive, partial output, build file or Forge history. Project
  Vault contained two existing entries. Activity contained eight events and Live Console 22.

## One exact application operation

The unchanged package launched exactly once in a Bubblewrap network namespace with loopback only,
zero network traffic, private runtime directories, an empty Android-tool path and no phone,
emulator or device simulation. Build opened **Build & Proof** and invoked **Forge Bundle exactly
once**. It did not click Verify Forge, Plan, Forge Control or any other operation. The producer's
required internal check and one automatic `verify-forge` continuation ran as designed.

## Deterministic artifact and verifier result

Every authorized Forge artifact expectation passed:

- exact output path:
  `builds/history-refresh-acceptance-7b4eca34/forge-8b49a05b100b6a23eddc.romverse.zip`;
- exact 1,594-byte archive SHA-256
  `8b49a05b100b6a23eddc4fec8c43bec4f435b4122e2428fe18e8f5186210f302`;
- exact stored, fixed-2020-timestamp inventory in order:
  `ROMVERSE-FORGE-MANIFEST.json`, `tree/META-INF/com/android/metadata`, `tree/payload.bin`;
- exact 891-byte schema-3 manifest SHA-256
  `49237325086cd182cdb5202c456ab9c2a07e6d9bed8dc2a3035fff721f1a2e6f`;
- manifest safety fields `protected_original_included`, `signed`, `bootable`, `flashable` and
  `phone_changed` were all false;
- schema-2 receipt bound the exact project, plan tree, archive and manifest, two entries / 297
  content bytes, no Ascension/rooted artifact, and signed/bootable/flashable all false;
- independent receipt reload matched the saved plan; archive/member rehash and exact inventory
  inspection passed; the existing read-only receipt verifier returned valid with identical expected
  and actual archive hashes; and
- UI terminal state was **Verified intermediate** with explicit unrooted, unsigned, non-bootable,
  non-flashable and no build/signing/Guardian/device/flash/execution authority wording. Build Control
  was observed only and not opened.

The protected source, plan, tree index, both inert inputs and Guided state stayed byte-identical.
The archive contains no protected original. No partial file or project `forge-history` directory
exists.

## Exact mismatch and stop reason

The acceptance required Project Vault history to remain unchanged. Instead, the automatic operation
chain increased Vault entries from two to four:

1. `20260910T012425-0f2b5bd5` — **Verified local build candidate**, parented to the previous retained
   entry and created after `forge bundle` completion; record SHA-256
   `3d809b6ff7a2c2d230c0adddf6351b082b85b949fc32451ee20abeba72bdff55`.
2. `20260910T012426-337fa66c` — **Reverified local build candidate**, parented to the first new entry
   and created after automatic `verify forge` completion; record SHA-256
   `dee82a554ce299cc31faa50118cf6d260973a4448a400973560c5a28f55804ba`.

Both are local `verified-build` Project Vault records over the same two-file/297-byte tree. Their
context capture added content-addressed copies of the existing plan and ROM-DNA to the Vault object
store. Activity increased from eight to 12 with Forge created, Vault captured, Forge verified and
Vault recaptured successes. Live Console increased from 22 to 30 with the corresponding four
running/succeeded pairs. The ordinary runtime fault log also gained one startup marker.

This does not alter the Forge ZIP or grant authority, and the separate project `forge-history`
directory correctly remains absent. It nevertheless violates the exact invariant that **Vault
history remain unchanged**, so the acceptance cannot pass.

## Classification and safety

- **Implemented:** no product change.
- **Simulated/Tested:** one genuine Fedora no-network/no-phone package acceptance; deterministic
  artifact/verifier passed, exact Vault-history invariant failed.
- **Hardware Verified:** no.
- **Released:** no.

No pytest, Ruff, rebuild or second UI run occurred. No network/tool acquisition, phone/emulator,
ADB/Fastboot, real firmware, ROM build, signing, Guardian/Recovery execution, installation,
publication, release or bootloader lock/relock occurred. The disposable result is preserved for
Product Assurance. Every later gate remains closed.
