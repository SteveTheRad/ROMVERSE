# ROMVERSE Build Status

## Authoritative checkpoint

- Product Assurance authorization/base: `7879f34c59d9a0e8501501a12a51462103bd36b4`
  (`Approve durable candidate preparation`).
- Implementation checkpoint: `b174803` (`Bind candidate preparation to final signed bytes`).
- Final handoff checkpoint: the follow-up commit containing this status document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, final-signed installation-byte binding before any
  fresh live-target observation.
- Working tree at the implementation checkpoint: clean.

## Exact implementation changes

- `CandidateInstallationService` now requires the current exact `OfflineSigningReceipt` and
  `SignedAssemblyReceipt` in addition to the existing source, Device Pack, build, base and AVB
  evidence chain.
- The durable candidate composition is version 2 and binds both receipt digests. Its two replaced
  installation roles now point to exact workspace-relative final evidence:
  - `vbmeta_system.img` from the request-bound signing-evidence directory;
  - `super.img` from the signing-receipt-bound signed-assembly directory.
- Pre-sign `product.img`, `vbmeta_system.img` and `super.img` build outputs remain required lineage
  evidence for build/AVB consistency, but none is selected as an installation origin.
- The final signed product must be the one exact signed input represented by the sealed super
  assembly, including path, hash and size, and the final super must retain the Device Pack's exact
  geometry.
- Preparation and reload fail closed for missing, malformed, ambiguous, stale, moved, substituted
  or byte-changed final evidence. Each selected final file is freshly opened without following a
  symlink and hashed before the recipe is returned.
- Guardian historical provenance accepts only the new signed-final origin contract and rejects
  legacy or resealed candidate compositions that do not carry the two new exact receipt bindings.
- Runtime private staging reads the sealed signed-final origins; unchanged source roles continue
  to come only from the exact protected base package.
- The Guided review labels the two selected replacements as `FINAL SIGNED IMAGE`.
- Corrected only the three Product Assurance-authorized stale assertions for changed pre-sign build
  bytes; the existing fail-closed behavior was not weakened.

## Result classification

- Implemented: exact final signing/assembly receipt and byte binding in durable complete candidate
  preparation, verification, historical provenance and private runtime staging.
- Simulated/Tested: yes — bounded synthetic signed artifacts, production signing/release loaders,
  production preparation/Guardian/UI boundaries, deterministic inert host tools and offscreen Qt.
- Hardware Verified: no. No phone was observed or operated in this checkpoint.
- Released: no.

## Non-double-counted verification

- One final combined affected regression set: **117/117 unique tests passed in 19.39 seconds**.
- The single 117-node set covers:
  - candidate preparation and stable reconstruction;
  - production offline-signing and signed-super receipt loading;
  - exact final-origin, hash, size and lineage binding;
  - missing receipt and final-byte drift rejection with restored mtimes;
  - Guardian provenance, staging and historical evidence validation;
  - Guided/desktop presentation and the required no-phone preparation/reload journey.
- Required no-phone production journey: passed within the 117-node set. It ended at the disabled
  `Connect the intended phone by USB` wait with no selected target, review plan, consent,
  admission, result, device call, write or phone change.
- Ruff on all nine changed Python files: passed.
- Git whitespace validation: passed.
- No broad/full suite was run, in accordance with the approved bounded verification scope.
- Current blockers/failures: none inside this checkpoint. An intermediate lightweight fixture
  still used a generic signing directory after strict path sealing was added; it was corrected to
  the production request-digest layout before the final 117/117 run.

## Guided friction and remaining boundaries

- The former durability loop remains fixed: unchanged preparation reconstructs with one stable
  recipe identity and does not reseal existing exact base/AVB evidence.
- Guided now shows the actual final signed installation origins without exposing signing machinery
  or enabling a consequential action.
- With no phone present, the journey has one clear next action and no dead end: connect the exact
  intended phone by USB. The action remains disabled until a separately authorized fresh target is
  observed and validated.
- The exact understood base package remains required. A missing or mismatched signing receipt,
  signed assembly or final byte produces a precise fail-closed preparation error rather than a
  fallback to pre-sign or protected-source bytes.
- Fresh target, consent, execution, durable result, Recovery reassessment and verification remain
  separate, unopened boundaries.

## Guardian, Recovery and safety implications

- A complete candidate preparation is still evidence only. It grants no target, consent,
  admission, execution, installation, flash, Recovery or release authority.
- Guardian remains the sole execution gate. Exact-device identity, exact-incident attribution,
  UNKNOWN-on-uncertainty, no blind retry and independent post-operation verification are unchanged.
- Historical records cannot be relabeled or resealed to adopt arbitrary final paths; legacy
  candidate composition version 1 is audit-only and cannot satisfy the current executable
  provenance contract.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora/Linux: genuinely exercised the production Python/Qt service, persistence, signing-result,
  signed-assembly, Guardian and dialog boundaries under offscreen Qt.
- Firmware/AVB/signing bytes: bounded synthetic fixtures; not a bootable ROM and not hardware
  evidence.
- Fedora package/launcher: unchanged and not exercised in this slice.
- Windows: unchanged; no Windows verification claim is made.
- Physical Android: not used. Existing creator authorization for a later read-only Linux hardware
  checkpoint was not exercised because this approved slice explicitly required no phone.
- Companion, Windows launcher, Knowledge/Adaptive work, website, logos and unrelated user work:
  untouched.
- 5 September 2026 feature freeze: compliant. This is the minimum required correctness binding in
  the approved existing Stage 1 journey, not a new feature or execution capability.
- v0.2 Golden Foundation remains **CLOSED**.

## External actions

- Physical phone observation/operation, ADB/Fastboot device command, APK transfer/install,
  emulator, Recovery, flash, private-key use, production trust enrollment, publication and release:
  none.
- Dependency/tool installation, package build, merge, history rewrite and force-push: none.
- Remote action: normal push of the two scoped Linux checkpoint commits to the existing
  `linux/stage1-desktop-readiness` branch only.
- No protected Companion, Windows launcher, Knowledge/Adaptive or unrelated files were edited,
  staged, discarded or committed.

## Next proposed Build task

Stop for Product Assurance. If this final-signed-byte binding is approved, Product Assurance may
authorize one bounded read-only fresh exact-device target observation. Do not cross into consent,
execution, installation, Recovery or another consequential slice without that review.

## Product Assurance Review Requested

- Confirm the candidate composition now proves the exact final signed `vbmeta_system.img` and
  signed-assembly `super.img` that would later be presented to Guardian.
- Confirm version-1 candidate compositions correctly remain non-executable audit evidence rather
  than being migrated into current authority.
- Confirm the next boundary, if approved, is one read-only fresh exact-device observation ending
  before consent.
