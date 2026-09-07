# ROMVERSE Build Status

## Authoritative checkpoint

- Authoritative implementation commit: `9e6762aa8cf25b06b64c57486fbe4cd719155d91`.
- Identity implementation commit: `07b5b1721282b2af59abdc8eae0bd152b5361e81`.
- Product Assurance authorization/base: `817e264cd37e74d0d49b8d627b12b3a523b89cf1`.
- Handoff checkpoint: the commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, `v0.2.0-alpha.1` internal development identity.
- Working tree: clean apart from ignored local build output after the handoff commit is created.

## Exact implementation changes

- The authoritative PEP 440 package/runtime version is now `0.2.0a1`; the user-facing desktop
  identity is `0.2.0-alpha.1`.
- Qt application metadata, the main window title, navigation-sidebar version and About build tile
  now use the exact visible alpha identity.
- Desktop update and Galaxy HTTP user agents derive their version from the authoritative runtime
  package identity instead of retaining a hard-coded `0.1` identity.
- Current README and Fedora development commands use the exact alpha filename. The Fedora guide's
  previously stale executable-build, smoke and bundle CLI arguments now match the existing scripts.
- The bounded first frozen smoke exposed that the release/update version parser rejected the valid
  PEP 440 alpha version and aborted startup. The parser now accepts and correctly orders numeric
  `a`, `b` and `rc` prereleases while preserving the existing stable and hyphenated-label formats.
- Historical reports, Device Pack versions, fixture adapter/package/protocol versions, Companion
  identity and unrelated records were not rewritten.

## Fedora development artifact

- Classification: **unsigned internal development artifact only**; not a release candidate,
  signed artifact, published build or production release.
- File: `dist/ROMVERSE-Desktop-0.2.0-alpha.1-linux-x86_64.zip`.
- Source commit: `9e6762aa8cf25b06b64c57486fbe4cd719155d91`.
- SHA-256: `fb02858c5b8001ab03a8c3015210c74c66c26a00365844a7ab192a02b6116ea9`.
- Archive size: `150947125` bytes; mode `0644`.
- Verified contents: `460` regular files, `360254450` expanded bytes, expected
  `ROMVERSE/ROMVERSE` executable present, CRC validation passed.
- Exactly one `0.2.0-alpha.1` packaged artifact exists in `dist`. The ignored PyInstaller directory
  is intermediate local build output, not a distributed artifact.

## Result classification

- Implemented: yes — package, runtime, visible desktop, user-agent and directly coupled Fedora
  development identity plus the required alpha-version parser correction.
- Simulated/Tested: yes — focused deterministic tests and one final frozen no-device acceptance
  smoke on Fedora.
- Hardware Verified: no. The smoke deliberately made ADB and Fastboot undiscoverable and used no
  physical target.
- Released: no.

## Non-double-counted verification

- Final focused regression: **42/42 passed** across desktop bundle/version identity, desktop release
  ordering, launch settings, desktop update readiness and Galaxy network behavior.
- Ruff checks: **PASS** for every changed Python source and test file.
- Git whitespace checks: **PASS** before both implementation commits and the handoff.
- Final frozen startup/no-device smoke: **1/1 passed** using a disposable workspace, offscreen Qt and
  an empty executable-search path so neither ADB nor Fastboot could be discovered.
- Artifact integrity: **PASS** — exact versioned filename, independent SHA-256, safe archive member
  validation, expected executable, CRC, byte count and file count verified.
- One earlier development smoke failed before packaging because `0.2.0a1` was rejected by the
  release version parser. That failure identified the corrected defect and is not counted as a
  passing acceptance smoke or a second journey.
- No full regression and no duplicate Guided/Recovery journey were run.

## Blockers, failures and Guided friction

- No focused test, final smoke or artifact-integrity failure remains.
- Fixed: the alpha desktop no longer exits during startup when constructing its update service.
- No Guided workflow, dialog, navigation route, device flow or consequential operation was changed.
- This checkpoint creates no new user decision or dead end.

## Guardian, Recovery and safety implications

- Version identity and packaging grant no Guardian, device, flash, Recovery, installation, signing,
  update-installation, publication or release authority.
- UNKNOWN-on-uncertainty, no blind retry, exact-device evidence, consent separation, same-incident
  Recovery and independent verification remain unchanged.
- Production Recovery execution remains disabled and was not exercised.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora/Linux: the unsigned self-contained alpha development ZIP and final no-device startup smoke
  are genuinely software-verified on Fedora 44 x86-64; this is not hardware verification.
- Windows: unchanged. No simulated or genuine Windows claim is made by this checkpoint.
- Physical Android: not used and no hardware claim is made.
- 5 September 2026 feature freeze: compliant. Only approved version/readiness identity and the
  directly exposed alpha-startup defect were changed.
- v0.2 Golden Foundation remains **CLOSED**. This is an internal development identity, not a release
  gate approval.

## External actions

- Physical phone, USB target, ADB, Fastboot, Recovery, flash, install, APK transfer and device
  operation: none.
- Package/dependency/system installation, production signing, publication, release, merge and
  force-push: none.
- Network research and online product operation: none.
- Remote action: only the normal push of the scoped implementation and handoff commits to the
  existing Linux working branch is intended.
- The three protected Companion files, original-checkout Windows launcher drafts, website, assets
  and unrelated user work were untouched.

## Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice. After
approval, Windows may synchronize the approved local-resume and alpha-identity commits once and run
its consolidated rebuild as already directed by Product Assurance.

## Product Assurance Review Requested

- Confirm the exact package/runtime versus display-label split and the prerelease ordering repair.
- Confirm the single Fedora artifact and bounded no-device smoke satisfy the internal alpha identity
  checkpoint without implying hardware, signing, publication or release evidence.
- Confirm Windows may now synchronize through this handoff for its one consolidated rebuild.
