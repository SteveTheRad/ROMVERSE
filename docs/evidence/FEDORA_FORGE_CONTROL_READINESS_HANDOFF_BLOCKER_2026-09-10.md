# Fedora Forge Control readiness handoff blocker

Date: 2026-09-10 (Australia/Brisbane)
Branch: `linux/stage1-desktop-readiness`
Product Assurance authorization: `902d299f022ec0ac689375457525de85b347a479`
Approved base: `81c1dd092128ed67ed4381a9496a73d85a2d69ad`

## Result

**BLOCKED — the passive readiness report is structurally correct and safely gated, but the visible
top-level state differs from the exact authorized acceptance.** Product Assurance required
**EVIDENCE INCOMPLETE**. The unchanged package instead displayed **WORKSPACE READY / BUILD LOCKED**.
Build stopped without retry, refresh, correction, another launch or any action inside Forge Control.

## Exact preconditions

One fresh disposable profile was mode `0700`. Guided mode remained selected, with online
intelligence, community research, Synapse contributions and automatic tool download disabled.
Before launch:

- the mode-`0755`, 6,338,544-byte packaged executable was SHA-256
  `e42d66cf95bcd66170f8500faf7c51bcbbc10c99c8895f26fb1b411b06e703e5`;
- exact project was `history-refresh-acceptance-7b4eca34`;
- protected source SHA-256 was
  `c3f5c1711d648a0f6c8f2ba2e3c910048c4e81e6f3ee39bb82e9e85888ac89c8`;
- plan SHA-256 was
  `1bd66952a0fae926160d095694e3a1f813e10ee145b0b9839e7093d10034ecf4`;
- planned tree SHA-256 was
  `84c7699a74b49f5d940c7d307adad07fab6207edd7cd61ee1d8361bbfb259de8`;
- accepted Forge archive/manifest SHA-256 values were
  `8b49a05b100b6a23eddc4fec8c43bec4f435b4122e2428fe18e8f5186210f302` and
  `49237325086cd182cdb5202c456ab9c2a07e6d9bed8dc2a3035fff721f1a2e6f`;
- Guided state remained verified with no install request or error; and
- there was no readiness report, source blueprint, Device Pack execution plan, local-build receipt,
  signing receipt, simulation or release artifact.

## One passive handoff

The unchanged package launched exactly once in a Bubblewrap network namespace with loopback only,
zero traffic, private runtime directories, an empty Android-tool path and no phone, emulator or
device simulation. Build opened **Build & Proof**, observed the already-approved verified Forge
state without replaying Forge or Verify, and opened **Forge Control exactly once**.

`BuildControlCenter` remained passive with `auto_start=false`. Build did not click Auto-resolve,
Refresh evidence, any resolution action, specialist tool, build, AVB, simulation, signing,
installation, release, Guardian, Recovery or device control.

## Persisted readiness evidence

The single derived `build-readiness.romverse` is 6,915 bytes, strict schema 1, SHA-256
`ce83ea443114338ccb16ca49ef11c2fd2b7e88d904caff2fd6ea53d6516acdbd`, and binds the exact project.
Recomputing its canonical payload digest produced the recorded report digest
`e86233316f7e5cc65a97fe909e426dcabeda1f3cf054feb53bd0825519d72e04`.

The report contains the exact ordered set of 18 unique gates with strict fields and these counts:

- 5 pass;
- 4 attention; and
- 9 blocked.

The report correctly records:

- `workspace_ready: true`;
- `build_ready: false`;
- `local_candidate_ready: false`;
- `signing_ready: false`;
- derived Guardian handoff readiness false; and
- `flash_ready: false`.

The nine blockers are Device Pack build contract, deterministic source/build plan, verified local
candidate, artifact trust and AVB policy, Device Pack flash/recovery contract, exact authorized
target, battery safety margin, boot-state evidence, and operation/release scope. The Forge Bundle
does not satisfy any of them.

The surface visibly reported 5 verified, 4 needing attention and 9 blocked, rendered the unresolved
Build/Signing/Recovery/Flash/Guardian evidence, and claimed no build, signing, installation, flash
or phone action. However, its overall badge was **WORKSPACE READY / BUILD LOCKED**, while the exact
acceptance required **EVIDENCE INCOMPLETE**. Although the actual badge is bounded and does not grant
authority, it is a different and nominally stronger readiness presentation, so this checkpoint
cannot be accepted under the stated contract.

## Post-close integrity

Forge Control closed through its normal Close control. The compositor exposed no normal close for
the remaining main window, so Build reverified the exact packaged-process command line and private
profile immediately before terminating only that process. Exit 143 is honest and no clean
application-shutdown claim is made. No ROMVERSE process remained and desktop accessibility was
restored to false.

Independent post-close inspection found only the permitted schema-1 readiness report and one normal
runtime-start marker relative to the accepted profile. Activity remained 12 events, Live Console
remained 30, and Project Vault remained four entries. No partial file or new Vault, source,
blueprint, Device Pack plan, local candidate, signing, simulation, release, Guardian/Recovery,
device or Forge-history artifact appeared.

The approved Forge receipt still matches the saved plan. Its 1,594-byte archive retained the exact
authorized hash and the existing receipt verifier returned valid with the explicit unrooted,
unsigned, non-bootable and non-flashable result. Protected source, plan, tree index, both inert tree
members, Guided state, Forge receipt/archive and all Vault evidence remained unchanged.

## Classification and safety

- **Implemented:** no product change.
- **Simulated/Tested:** one genuine Fedora offline/no-phone package handoff; report integrity and
  downstream gating passed, exact required top-level badge failed.
- **Hardware Verified:** no.
- **Released:** no.

No pytest, Ruff, rebuild, Forge replay, Autopilot, tool resolution/acquisition, source preparation,
ROM build, AVB operation, simulation, phone/emulator/ADB/Fastboot, Guardian/Recovery execution,
signing, installation, publication, release or bootloader lock/relock occurred. The disposable
result is preserved for Product Assurance. Every later gate remains closed.
