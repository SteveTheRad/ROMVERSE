# ROMVERSE Build Status

## Authoritative checkpoint

- Linux implementation commit: `eaa3d615912a4eefddd44ee3b032562047ddadc3`.
- Product Assurance authorization/base: `4528cea4cb4331afd78392f41edc91c56a8a57e2`.
- Handoff checkpoint: the commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, fresh-user Fedora onboarding/readiness.
- Working tree: clean apart from ignored previously accepted build output after the handoff commit
  is created.

## First concrete onboarding defect

- The existing frozen alpha opened its real first-run dialog without `--skip-onboarding`, but that
  dialog exposed only `Initialize ROMVERSE`.
- It did not identify `0.2.0-alpha.1` as an internal development build and did not make the initial
  Guided choice explicit. A new user therefore could not verify the approved alpha/mode state before
  entering Command Deck, even though the underlying fresh settings defaulted to Guided.
- This was a truthful-intent defect, not an execution or device-safety bypass.

## Exact implementation changes

- First-run now displays `0.2.0-alpha.1 • INTERNAL DEVELOPMENT` with an accessibility identity.
- The onboarding explanation states that Guided is the selected evidence-bound workflow, no phone
  is required during setup, the setup screen cannot perform phone or install actions, and Command
  Deck will truthfully report missing Platform Tools or device state.
- The only completing action is now `Continue in Guided Mode`, with an explicit accessibility name.
- The wizard's selected mode is typed as `ExperienceMode.GUIDED`, and application startup carries
  that exact selection into the settings used by Command Deck. Expert entry remains separate behind
  its existing risk warning.
- One focused Qt regression drives the corrected production widgets from onboarding through Guided
  Command Deck, opens the existing ADB/Platform Tools prerequisite path with managed auto-start
  disabled, and returns to the truthful no-engine/no-device Command Deck state.

## Acceptance evidence

- Existing unsigned frozen artifact entry: launched with a fresh disposable config and workspace,
  without `--skip-onboarding`, with an empty executable-search path. It remained alive at the real
  onboarding boundary until the bounded three-second harness termination; ADB and Fastboot were
  undiscoverable and no workspace/device operation began.
- Pre-correction production-widget inspection confirmed the exact visible gap: no alpha/internal
  identity, no Guided wording and only `Initialize ROMVERSE`.
- Corrected source-level production journey: **1/1 passed** — internal-alpha identity visible,
  Guided selected and carried forward, Command Deck reachable, no phone/engine/scan present,
  `Resolve Platform Tools` offered, its exact ADB prerequisite dialog invoked without installation,
  and Command Deck remained reachable with a clear host prerequisite.
- The previously accepted frozen artifact was not rebuilt or modified. It proves the packaged
  first-run entry point; the minimum source correction was rerun through the production Qt widgets
  as explicitly permitted by Product Assurance.

## Result classification

- Implemented: yes — minimum first-run alpha/Guided intent correction.
- Simulated/Tested: yes — one bounded frozen-entry check and one corrected production-widget Qt
  journey.
- Hardware Verified: no.
- Released: no.

## Non-double-counted verification

- Focused `tests/test_app_launch_settings.py`: **5/5 passed**, comprising one new onboarding journey
  regression and four neighboring launch/settings contracts.
- Ruff: **PASS** for both changed source files and the focused test module.
- Git whitespace checks: **PASS** before the implementation commit and handoff.
- No full/broad suite, Guided ROM/Recovery journey, artifact rebuild, packaging run or second
  corrected onboarding journey was performed.

## Guided friction and remaining boundaries

- Fixed: a fresh user now knowingly enters the exact internal alpha in Guided Mode instead of
  pressing an ambiguous initialization action.
- Fixed: the onboarding message establishes that no phone is needed and that Command Deck—not a
  success claim—will own any Platform Tools/device prerequisite.
- No dead button, misleading readiness claim or navigation loop remained in the bounded corrected
  journey.
- The accepted frozen ZIP predates this small source correction and intentionally remains unchanged
  pending Product Assurance direction on when to batch the next artifact rebuild.

## Guardian, Recovery and safety implications

- Onboarding grants no Guardian, build, device, flash, Recovery, installation, signing,
  publication or release authority.
- UNKNOWN-on-uncertainty, no blind retry, exact-device evidence, consent separation, same-incident
  Recovery and independent verification remain unchanged.
- Expert mode was not entered; its existing warning/acceptance boundary is unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora/Linux: frozen first-run entry and corrected source-level onboarding/readiness journey are
  genuinely software-tested on Fedora 44 x86-64; this is not hardware verification.
- Windows: unchanged; no new Windows execution claim is made.
- Physical Android: not used; no hardware claim is made.
- 5 September 2026 feature freeze: compliant. This is the minimum correction for the first concrete
  misleading onboarding intent found by the approved journey.
- v0.2 Golden Foundation remains **CLOSED**. No release gate changed.

## External actions

- Physical phone, emulator, USB target, device-scoped ADB/Fastboot, Recovery, flash, install, APK
  transfer and device operation: none.
- Managed tool auto-install, package/dependency/system installation, artifact rebuild, signing,
  publication, release, merge and force-push: none.
- Remote action: only the normal push of the scoped Linux implementation and handoff commits to the
  existing Linux working branch is intended.
- The three protected Companion files, original-checkout Windows launcher drafts, website, assets
  and unrelated user work were untouched.

## Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice or rebuild
either platform artifact until directed.

## Product Assurance Review Requested

- Confirm the explicit Guided/internal-alpha onboarding correction is the minimum appropriate fix
  for the first observed intent gap.
- Confirm the split evidence—unchanged frozen first-run entry plus corrected source-level production
  widget journey—is sufficient under the instruction not to rebuild this artifact yet.
- Advise whether this source correction should be batched into a later cross-platform artifact
  rebuild or requires a dedicated development-artifact refresh.
