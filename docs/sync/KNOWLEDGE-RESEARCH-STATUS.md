# ROMVERSE Knowledge Research Status

## Google Play query-only acquisition checkpoint — 8 September 2026

### Checkpoint identity

- Product Assurance authorization/base: `f2975629d9decddcd3e0103ca7bb88ab14c41020`
  (`Approve online evidence foundation`).
- Branch: `adaptive-online-device-dna`.
- Implementation commit: `68a2bf7573b99146ef36b8e127943820d99dd520`
  (`Add fixed Google Play evidence acquisition`).
- Live evidence/status commit: the follow-up commit containing this update.

### Implemented source path

- One fixed HTTPS source only:
  `https://storage.googleapis.com/play_public/supported_devices.csv`.
- Exact request contract: no alternate host/path, credentials, authentication, cookies, redirects,
  private query fields, or response compression; stable `ROMVERSE/0.2
  query-only-device-evidence` user agent.
- Explicit connect/read/overall timeouts of 8/12/30 seconds, a 16 MiB body limit, 100,000-row
  limit, 160-character field limit, two-second minimum spacing, and conditional validators only
  after a prior content digest has been validated.
- Exact UTF-16 four-column parser with strict row shape, formula/control-character and empty-row
  rejection. Duplicate rows applicable to the exact lookup fail closed; irrelevant duplicates are
  discarded and can never become claims. Multiple applicable retail identities remain ambiguous.
- Explicit privacy-checked manufacturer/model/device-codename lookup only. Exactly one match forms
  four bounded identity claims; the catalog is never bulk-promoted or written to disk.
- Durable strict receipts cover success, no exact match, HTTP failure, validation failure, and
  cache-not-modified. Device DNA, Compatibility Matrix, and Knowledge Archives reuse the existing
  read-only projections.

### Exact retained live evidence

- Lookup: public non-personal identity `Google / Pixel 6 / oriole`.
- Retrieval time: `2026-09-08T02:14:51.576529+00:00`.
- HTTP result: `200`; validated response bytes: `4,753,074`; validated unique rows: `53,689`.
- Cache metadata: ETag `"8ddd0f19c3de99f3c413484a1b578878"`; Last-Modified
  `Mon, 07 Sep 2026 12:08:02 GMT`.
- Source-content SHA-256:
  `f3812a8275cd7357473cc920f74867f957842d319e07068e09e7a0fd897abe56`.
- Parser: `romverse.google-play-supported-devices` version `1`.
- Result: `success`; four officially documented retail-identity claims retained; compatibility
  remains `UNCONFIRMED`.
- Evidence archive digest:
  `9f5d9e29ed16cd4362ee7e382b469462711afd90f8ea0eafff4fd4913ce54c61`.
- Acquisition receipt digest:
  `c9033d258c0629bc6835669be10d4ff74989961265f6083c36474e7d1fb45c49`.
- Retained files:
  `docs/sync/evidence/google-play-live/knowledge/online-device-evidence/claims.romverse` and one
  lookup-digest-named receipt below its `acquisitions` directory.
- Raw catalog response retained: **NO**. No `.csv` file exists in the retained evidence tree.

The live exercise exposed and corrected three bounded validation-path issues before the successful
receipt: blank optional official cells were initially treated as unsafe; a failed validation could
incorrectly send conditional cache headers without a validated content digest; and the live catalog
contains exact duplicate rows outside this lookup. The final parser permits blank non-matching
descriptive cells, conditions only from validated content, rejects duplicate applicable rows, and
discards irrelevant duplicates without promotion. Each correction has a focused deterministic
regression. No safety, scope, or source restriction was weakened.

### Focused verification

- `100 passed` across `tests/test_google_play_evidence_acquisition.py`,
  `tests/test_online_device_evidence.py`, `tests/test_local_store.py`, and
  `tests/test_online_remediation.py`.
- Acquisition cases cover exact claim-only success, zero raw retention, fixed request headers and
  timeouts, alternate URL/auth/cookie rejection, three consumer projections, no match, ambiguity,
  HTTP failure, timeout, redirects, compression, truncation, unexpected content, formula/control
  characters, malformed/empty/duplicate/oversized rows and bodies, privacy-unsafe lookup input,
  conditional matched/no-match `304`, request spacing, tampering, and symlink containment.
- Focused Ruff check and format check passed; Git whitespace check passed.
- The full suite was intentionally not run. Fixture tests do not depend on the network.

### Privacy, Guardian, and limitations

- Only normalized public manufacturer/model/codename and the matching identity values are retained.
  The raw response and non-matching catalog entries are absent. No device/account identifiers,
  private paths, secrets, credentials, cookies, or personal information were queried or stored.
- Claims and receipt state execution authority `none`, phone action `false`, Guardian approval
  `false`, relock `false`, and raw-response retention `false`.
- Retail identity does not prove firmware, partitions, slots, AVB, compatibility, Device Pack,
  build/flash contract, recovery route, or device support. It cannot become a command.
- This is an explicit synchronous query path, not UI/background scheduling or a production service.
  DNS/TLS policy hardening, cross-process rate coordination, general conditional-cache retention,
  OEM/community sources, UI wiring, and live-device/firmware comparison remain deferred.
- No phone, emulator, firmware mutation, APK, production trust/signing, publication, Guardian
  workflow, execution, or relock was used.

### Ordered post-approval Knowledge pipeline

After Product Assurance accepts this checkpoint, advance only one reviewed source family at a time:

1. Official OEM support, firmware-index/manifest, and service documentation.
2. Official Android/AOSP technical documentation, compatibility requirements, and public issue
   evidence.
3. Maintained public device/kernel/recovery/tool repositories and maintainer documentation.
4. Reputable technical guides and diagnostic/error-code references.
5. Technical community reports only as low-confidence `source-reported` evidence pending genuine
   independent corroboration.

Before those families need richer records, extend the claim model deliberately for symptoms,
diagnostic observations, prerequisites, affected builds, fix-procedure descriptions, expected
results, rollback/recovery route, and outcome evidence. Source prose must never be parsed directly
into commands. Preserve exact provenance, revision/date, device/firmware applicability, conflicts,
and freshness. A guide may be officially documented or source-reported. A fix becomes independently
corroborated only across genuinely independent publishers, and becomes live-confirmed/ROMVERSE-
verified only from exact device/firmware outcome evidence—not repetition, votes, or a source's own
claim.

Private/authenticated sources, anti-bot bypass, arbitrary crawling, personal data, copyrighted bulk
copying, consequential execution, and bootloader relocking remain prohibited throughout.

### Next action

Stop for independent Product Assurance. Do not begin the first OEM source until this exact code,
fixture suite, and retained sanitized live evidence are accepted.

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
