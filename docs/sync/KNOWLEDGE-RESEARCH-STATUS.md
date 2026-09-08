# ROMVERSE Knowledge Research Status

## Pixel 6 official factory-image metadata checkpoint — 8 September 2026

### Value-gate decision

- Named consumers and gap: Device DNA, Compatibility Matrix, Pathfinder, Nexus, Foresight, and
  Knowledge Archives need exact official Pixel 6 firmware-index identities. The retained retail
  identity currently proves `Google / Pixel 6 / oriole`, but no official release/build/date/image
  identity or published package hash is retained.
- Exact retained fields: Pixel 6/oriole release label, build identifier, publication/release date,
  explicit Android version and carrier/region scope when present, official image URL identity, and
  the page-published SHA-256. Missing scope remains empty and is never inferred.
- Authority and scope: one canonical public Google OEM index only,
  `https://developers.google.com/android/images`, canonical English content, restricted to the
  Pixel 6/oriole section. Facts are `officially-documented` firmware-index metadata only.
- Freshness and validation: retain page revision/HTTP validators, retrieval time, response digest,
  parser identity, and exact section/row provenance. Revalidate after 30 days. Require one exact
  Pixel 6/oriole section, complete build/date/image/SHA-256 rows, unique build-to-image/hash
  relationships, HTTPS Google-hosted image identities, and explicit layout markers. Stale facts
  remain visible and request investigation; duplicate, ambiguous, changed, or conflicting rows fail
  closed rather than selecting by order.
- Parser and limits: `romverse.google-pixel-factory-index` version 1; exact URL; no redirect,
  localization, query, authentication, cookies, compression, or followed links; 4 MiB response,
  1,000 parsed headings/table rows, 256 matching rows, 240 characters per field, and 8/12/30-second
  connect/read/overall timeouts. Conditional validators are sent only after a prior validated
  content digest.
- Privacy, licensing, and minimum retention: public product/build/package metadata only. Retain
  normalized matching claims, source/revision/digests, and one strict receipt. Retain no raw HTML,
  binary archive, page bulk, account/device identifier, credential, cookie, personal information,
  source instruction, command, script, navigation, terms text, or relock text. This minimal factual
  metadata use remains subject to Google's published site and image terms; ROMVERSE neither accepts
  terms nor obtains gated binaries.
- Capability benefit: name official Pixel 6 firmware candidates and verify a later user-supplied
  artifact against a published identity/hash. This does not prove compatibility, safe flashing,
  installation route, outcome, package authenticity beyond the retained page claim, or Guardian
  authority.
- Stop conditions: stop on a terms/consent gate, missing exact section, missing date or SHA-256,
  unexpected host/path, layout drift, excessive size/count, privacy-unsafe content, executable or
  relock text entering a candidate field, conflicting metadata, or any need to download/click/follow
  a link. Stop after one bounded live retrieval and sanitized receipt/archive, then return to
  Product Assurance.

### Explicit exclusions

No archive download, terms acceptance, instruction/procedure retention, command construction,
bootloader unlock/relock guidance, device action, compatibility promotion, background scheduling,
UI integration, phone/emulator access, build/flash/root/debloat work, Guardian approval, production
trust/signing, publication, crawling, or second source is authorized.

### Implementation checkpoint

- Product Assurance authorization/base: `0e51b025d300b1a2c3f9635501c41942325816ae`
  (`Approve official Android guide evidence`).
- Branch: `adaptive-online-device-dna`.
- Implementation commit: `977da29c741ef9ca1e0ebd43284e1bf81858d3bd`
  (`Add bounded Pixel factory metadata adapter`).
- Live evidence/status commit: the follow-up commit containing this update.
- The adapter and receipt enforce the proposed exact URL, identity, metadata, transport, parser,
  storage, terms/download, privacy, and authority boundaries. Read-only projections remain
  `UNCONFIRMED` for Device DNA, Compatibility Matrix, Pathfinder, Nexus, Foresight, and Knowledge
  Archives.

### Single bounded live outcome

- Sole request: `https://developers.google.com/android/images`, exact canonical page only.
- Lookup: public identity `Google / Pixel 6 / oriole`.
- Retrieval time: `2026-09-08T04:34:23.843003+00:00`.
- HTTP result: `200`; bounded response bytes: `75,167`; ETag and Last-Modified absent.
- Parser: `romverse.google-pixel-factory-index` version `1`.
- Outcome: `validation-failure` — the returned static canonical English response did not expose one
  unambiguous reviewed Pixel 6/oriole metadata table section.
- Parsed releases and retained claims: `0`; evidence archive: none.
- Receipt digest: `c36e36561d215ecad094e63b164bc989f9eb04ec921afa8049f661e5ddfe8378`.
- Content digest: intentionally absent because the response did not pass the reviewed parser.
- Raw HTML, binary archives, page scripts, terms acceptance, clicked/followed links, commands,
  instructions, relock text, credentials, cookies, and personal information retained: **NONE**.

The approved missing/ambiguous-section stop condition fired. ROMVERSE did not retry, execute page
scripts, follow an image or consent link, accept terms, use an alternate/localized/query URL, or
seek a second source. The validation-failure receipt is the complete sanitized live result.

### Focused verification and authority

- `154 passed` across the Pixel factory index, official Android guide, Google Play acquisition,
  typed/legacy online evidence, local store, and online remediation focused suites.
- Pixel-specific cases cover exact identity/build metadata, read-only consumer projections,
  duplicate/conflicting builds, duplicate/ambiguous image identities, missing dates/hashes,
  changed layout, redirect/localization/query rejection, wrong content type, compression,
  truncation, executable/relock/private/oversized candidate data, ignored scripts/forms/terms,
  response and row limits, stale metadata, HTTP/timeout/cache behavior, request spacing, receipt
  tampering, and symlink containment.
- Focused Ruff check and format check passed; Git whitespace check passed. The full suite was not
  run, and deterministic fixture tests do not depend on the network.
- Receipt invariants state `officially-documented`, compatibility `UNCONFIRMED`, terms accepted
  `false`, binary downloaded `false`, raw response retained `false`, execution authority `none`,
  and phone, Guardian, and bootloader-relock authority `false`.
- No physical device, emulator, package, firmware operation, APK, unlock, root, debloat, flash,
  wipe, relock, production signing/trust, publication, UI/background scheduling, or other product
  track was touched.

### Next action

Stop for independent Product Assurance. The live stop condition must be reviewed before any parser
revision, second request, alternate endpoint, terms interaction, source expansion, or consequential
workflow.

## Official Android connection-guide checkpoint — 8 September 2026

### Checkpoint identity

- Product Assurance authorization/base: `7b58c8be04754b9adecbe75d50686ffa8aebdcbb`
  (`Approve live Google Play acquisition`).
- Branch: `adaptive-online-device-dna`.
- Implementation commit: `655e4578342f6cc55bccc6b6de9ef3c6786de5ec`
  (`Add typed official Android guide evidence`).
- Live evidence/status commit: the follow-up commit containing this update.

### Typed schema and migration

- Schema one adds `identity`, `diagnostic`, `guide`, `fix-claim`, and `outcome` knowledge kinds plus
  bounded symptoms, error identifiers, prerequisites, affected builds, diagnostic/remedy
  descriptions, expected result, rollback/recovery route, and outcome provenance.
- Descriptions reject command-shaped, code, and script text. Every claim remains execution-inert.
- Existing schema-one identity claims validate against their original exact field set, claim IDs,
  and archive digest. They load with empty identity-safe defaults and receive new IDs/digest only at
  an explicit save/merge boundary; their values and evidence state are unchanged and never promoted.

### Exact source and retained live evidence

- Sole source: `https://developer.android.com/studio/run/device`.
- Retrieval time: `2026-09-08T03:16:43.397973+00:00`.
- Page revision/Last-Modified: `2026-08-14T21:43:56+00:00` /
  `Fri, 14 Aug 2026 21:43:56 GMT`; ETag absent.
- HTTP status: `200`; bounded response bytes: `311,029`.
- Content SHA-256: `9a1e3f4e18646ce53efc5f76920163a94eaa5400d4122208a94bdf6286ce7bce`.
- Parser: `romverse.android-device-connection-guide` version `1`.
- Retained: three typed `guide` claims, each `officially-documented`, for Connection Assistant,
  faulty USB-cable, and USB-debugging evidence. The exact source excerpts total eight words.
- Evidence archive digest:
  `c2460577445e75494b761e6ad9a1eec1b055214c3f28b6352d517d42a4434996`.
- Acquisition receipt digest:
  `cce1ecb99bfc4038c3c7d275b51e8aa0c1fbd643c6d89931c8a0f54411b8e223`.
- Raw HTML, code, scripts, navigation, footer, templates and followed links retained: **NONE**.

The bounded live alignment found and corrected three parser assumptions before the final retained
success: an oversized unrelated visible block was initially treated as a page-wide failure;
anonymous ordinary metadata exposed a missing-value assumption; and the current reviewed headings
differed from the repository-era fixture. Each was corrected without broadening the source or
extracting generic page text, and deterministic regression coverage was added. Earlier validation
receipts were superseded; only the final successful sanitized receipt and claims are retained.

### Verification and projections

- `125 passed` across the official guide, typed/legacy evidence, Google Play acquisition, local
  store, and online remediation focused suites.
- Adversarial cases cover legacy migration, executable descriptions, missing/changed headings,
  scripts/code/navigation/events, oversized sections, conflicting guidance, privacy-unsafe text,
  localized/query redirects, wrong type, compression, truncation, timeout/HTTP failure,
  cache-not-modified, stale revisions, receipt tampering, and symlink containment.
- Focused Ruff check and format check passed; Git whitespace check passed. The full suite was not
  run, and deterministic fixture tests do not depend on the network.
- The final retained guide archive and the earlier Google Play archive both revalidated with zero
  command, phone, Guardian, execution, and relock authority.
- Read-only projections are limited to Knowledge Archives, Device DNA, Nexus, and Insight. The
  guide does not assert device compatibility or create Pathfinder, Recovery, or execution authority.

### Privacy, status, and limitations

- Retention is limited to three short reviewed phrases and ROMVERSE-authored typed descriptions.
  No raw page, HTML, executable prose, command, code, script, navigation, footer, cookie,
  credential, account identifier, device identifier, or personal information is retained.
- Each claim is `officially-documented`, not independently corroborated, live-confirmed, or
  ROMVERSE-verified. The page documents general Android Studio device-connection guidance; it does
  not prove that any remedy worked on an exact device, firmware, host, cable, or incident.
- The path is explicit and synchronous. It is not background scheduling, UI wiring, a production
  service, arbitrary crawling, or permission to take action on a phone.
- No physical device, emulator, firmware, APK, unlock, root, debloat, flash, wipe, relock,
  production signing/trust, publication, or consequential workflow was used.

### Knowledge Coverage & Value Gate

`docs/KNOWLEDGE-COVERAGE-VALUE-GATE.md` now maps prioritized evidence categories and their fields to
named ROMVERSE consumers, source authority, validation, freshness, privacy/licensing/retention,
conflict behavior, capability unlocked, and stop conditions. It also permanently excludes generic
or duplicative material, arbitrary crawling, private/authenticated sources, raw/bulk content, and
anything without a direct named feature or evidence-gap benefit.

### Next action

Stop for independent Product Assurance. Do not acquire another source family or broaden this source
until the typed schema, bounded adapter, focused tests, final sanitized live evidence, and coverage
gate are accepted.

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
