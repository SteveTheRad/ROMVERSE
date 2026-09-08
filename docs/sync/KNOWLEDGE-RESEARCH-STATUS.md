# ROMVERSE Knowledge Research Status

## Checkpoint identity

- Authorized base: `a6d9bca06d35c4f0ca8b84ad6ebd990be7e5700a`
  (`linux/stage1-desktop-readiness` at isolated-worktree creation).
- Isolated branch: `adaptive-online-device-dna`.
- Implementation commit: `d4c7d57ea7bc4e5f289973d6558b85b0633d6af3`
  (`Add bounded online device evidence foundation`).
- Status/handoff commit: the follow-up commit containing this document.
- Milestone: first bounded Adaptive Online Device DNA evidence foundation.
- Product Assurance: requested after this checkpoint; no source expansion or consequential workflow
  is authorized by this status.

## Implemented

- Strict immutable claim schema covering exact scope, source URL/publisher/category, retrieval and
  publication time, freshness, exact structured value or bounded excerpt, confidence/status,
  corroboration/conflict links, source-content SHA-256, and parser identity/version.
- All approved states: source-reported, officially documented, independently corroborated,
  firmware-derived, live-confirmed, conflicting, unconfirmed, outdated, and retired.
- Private atomic `romverse.online-device-evidence` schema-one archive with strict fields, 512-claim
  and 2 MiB limits, relationship re-derivation, content digest, regular-file containment, and
  symlink rejection.
- Deterministic merging by exact claim key and scope. Matching sources remain individually
  retained; independent publishers corroborate. Different values remain individually retained,
  become conflicting, use conservative confidence, and request focused investigation.
- Later firmware-derived and read-only live-confirmed claims use the same comparison contract:
  matches strengthen the relevant group; conflicts remain explicit.
- Configurable, deterministic, closed-by-default adapter registry with exact HTTPS host/path,
  content type, bytes, claim count, freshness, minimum spacing, redirect, authentication, parser,
  licensing/access, and publisher metadata.
- Bounded registered-response validation rejects unregistered/ambiguous URLs, credentials/private
  query fields, redirects, compression, non-success status, unexpected types, oversized content,
  and excerpts absent from the exact retrieved bytes.
- Privacy filtering removes common serial/IMEI/account, credential/token, email, and private-path
  forms before claim creation and rejects privacy-unsafe stored text on reload.
- Read-only integration projections for Device DNA, Compatibility Matrix, Nexus, Pathfinder,
  Foresight, Insight, Knowledge Archives, Device Atlas, and Simulation Lab.
- Unknown or incomplete evidence yields `UNCONFIRMED` and one focused investigation action, never
  automatic broad `UNSUPPORTED`.

## Initial source coverage

Only four repository-supported official/public adapters are active by default:

1. Google Play public supported-device catalog at its fixed official URL.
2. Public Android developer documentation.
3. Public AOSP platform/device source through Android Gitiles.
4. Public Android kernel source through Android Gitiles.

The schema/registry has categories for official OEM documentation, official firmware
indexes/manifests, maintained technical repositories, reputable maintainer documentation, and
technical community reports. Concrete adapters for those categories are deferred pending
source-specific terms, parser, rate/freshness, redirect, licensing, and Product Assurance review.
No authentication, private service, anti-bot bypass, or scraping workaround exists.

## Focused verification

- `79 passed`:
  `tests/test_online_device_evidence.py`, `tests/test_local_store.py`, and
  `tests/test_online_remediation.py`.
- New cases cover strict/private round trip; extra fields; same-user tampering of authority fields;
  archive/body limits; symlink target; duplicate/ambiguous/unregistered adapters; redirect, 429,
  compression, unexpected type, absent excerpt; exact provenance; deterministic independent
  corroboration; contradictory online/live evidence; matching firmware/live strengthening; unknown
  device investigation; privacy-unsafe text/URL; explicit current/aged/stale/future freshness; and
  every approved claim state.
- Ruff check and format check passed on the new module, package export, and focused tests.
- `git diff --check` passed.
- The full suite was intentionally not run.

## Privacy result

The synthetic privacy test confirms that labelled serial, IMEI and account data, 15-digit IMEIs,
credential/token forms, email addresses, and private home paths are absent from the formed claim.
Credential-bearing URLs and sensitive query keys are rejected. No response body is persisted;
storage retains only the bounded structured value/excerpt and the source content digest.

This is a defensive bounded filter, not a proof that arbitrary prose contains no personal
information. Each future adapter must form minimal queries from explicit non-personal
device/firmware fields and needs source-specific adversarial review before activation.

## Guardian and execution boundary

- Online evidence is guidance and research input only.
- Archive, claims, and all consumer projections permanently state execution authority `none`, phone
  action `false`, Guardian approval `false`, and bootloader relock `false`.
- No source text is parsed as a command. No adapter can invoke a network request or local/device
  command in this checkpoint.
- Exact-device/exact-firmware validation, UNKNOWN on uncertainty, no blind retry, one meaningful
  consent boundary, and Guardian-only consequential authority remain unchanged.
- Bootloader relocking remains permanently prohibited.

## Simulated, deferred, and unsupported behavior

- Simulated/tested: synthetic response validation, claim creation/storage, deterministic merge,
  conflict handling, privacy filtering, and read-only consumer projections.
- Hardware verified: no. No phone or emulator was targeted.
- Deferred: network scheduling/client, robots/terms automation, conditional HTTP cache, real OEM or
  community parsers, UI wiring, live Device Engine ingestion, firmware inspection ingestion,
  persistent cross-process rate limiting, contribution/publication, and production services.
- Unsupported: private/authenticated source access, anti-bot bypass, arbitrary crawling, remote
  instruction execution, flashing, rooting, debloating, unlocking, wiping, relocking, recovery,
  APK installation, production trust enrollment, publication, and production execution.

## Files changed at implementation checkpoint

- `src/romverse/knowledge/online_evidence.py`
- `src/romverse/knowledge/__init__.py`
- `tests/test_online_device_evidence.py`
- `docs/ADAPTIVE-ONLINE-DEVICE-EVIDENCE.md`

This handoff additionally changes:

- `docs/sync/KNOWLEDGE-RESEARCH-STATUS.md`
- `docs/sync/BUILD-STATUS.md`

Protected Companion work, active Linux/Windows build branches, original-checkout launcher drafts,
physical devices, firmware artifacts, release assets, and unrelated files were not touched.

## Proposed next bounded milestone

Stop for independent Product Assurance. If accepted, add one source-specific official OEM firmware
index/manifest adapter with its exact parser, licensing/terms note, conditional-fetch/rate policy,
fixture-based adversarial tests, and read-only Device DNA projection. Do not expand community
sources or any consequential workflow in the same slice.
