# Adaptive Online Device Evidence Foundation

This checkpoint implements a bounded, execution-inert evidence layer for unfamiliar Android
devices and firmware. Unfamiliarity produces `UNCONFIRMED` plus a focused investigation path; it
does not produce a broad `UNSUPPORTED` decision.

## Claim and storage contract

Each retained claim records one normalized claim key and exact device/firmware scope, plus exactly
one structured value or bounded supporting excerpt. Its source records the public HTTPS URL,
publisher, retrieval and optional publication time, freshness, source category, source-content
SHA-256, and parser identity/version. The claim also retains confidence, status reason,
corroborating claim IDs, and conflicting claim IDs.

The supported states are:

- `source-reported`;
- `officially-documented`;
- `independently-corroborated`;
- `firmware-derived`;
- `live-confirmed`;
- `conflicting`;
- `unconfirmed`;
- `outdated`;
- `retired`.

The private workspace archive is a strict, content-digested schema-one JSON record at
`knowledge/online-device-evidence/claims.romverse`. It is limited to 512 claims and 2 MiB, rejects
extra fields and symbolic-link targets, and uses the existing private atomic local-store boundary.
Every loaded relationship and archive digest is re-derived. Re-digesting a modified record cannot
enable a phone action: execution authority, Guardian approval, phone action, and bootloader relock
are literal false/none invariants in both claims and consumer projections.

## Deterministic merging and later comparison

Claims are grouped only when their normalized key and exact scope match. Ordering is derived from
content identities, not retrieval order. Equal values retain every source and may become
independently corroborated; firmware-derived and read-only live-confirmed observations strengthen a
matching value. Different values remain side by side, become `conflicting`, use the lower stated
confidence, and request focused investigation. No incoming source silently replaces retained
evidence.

Later local firmware inspection and read-only live device observations use the same comparison
contract. They must still supply exact scope and provenance. A match strengthens only the relevant
claim group. A mismatch remains visible and never becomes a command, Guardian approval, blind
retry, or permission to change the phone.

## Source registry and retrieval boundary

The source registry is configurable but closed by default. Each adapter declares a stable identity,
publisher, category, exact HTTPS host/path scope, parser identity/version, accepted content types,
byte and claim limits, freshness interval, minimum request spacing, redirect policy, authentication
policy, and an access/licensing note. The validator rejects unregistered or ambiguous URLs,
credentials/private query fields, redirects, compression, non-success status, unexpected content
types, and oversized bodies. It validates caller-supplied response bytes but performs no network
request itself and interprets no instructions or commands.

The default registry intentionally contains only sources already represented by reviewed repository
evidence:

- Google Play's fixed public supported-device catalog;
- public Android developer documentation;
- Google's exact Pixel factory-image index, with metadata-only access;
- public AOSP platform/device source through Android Gitiles;
- public Android kernel source through Android Gitiles.

Additional OEM firmware indexes/manifests, OEM documentation, maintained technical repositories,
maintainer documentation, and technical community reports have source categories and can be added
only as explicit reviewed adapters. They are deferred until Product Assurance accepts this common
boundary. Private services, authenticated pages, anti-bot bypass, scraping workarounds, and
unreviewed redirects are unsupported.

## Privacy and product integration

Free-text evidence and scope pass through bounded privacy filtering for labelled serial/IMEI/account
data, 15-digit IMEIs, email addresses, credential/token forms, and private home paths. Source URLs
with embedded credentials or privacy-sensitive query fields are rejected. This is a defensive
client boundary, not a claim that arbitrary personal prose can be perfectly classified; adapters
must form the smallest possible query from explicit non-personal device/firmware fields and retain
no raw response beyond the bounded supporting value and content digest.

Read-only projection contracts are available for Device DNA, Compatibility Matrix, Nexus,
Pathfinder, Foresight, Insight, Knowledge Archives, Device Atlas, and Simulation Lab. Every
projection follows the guided sequence:

`Connect device read-only → gather evidence → research gaps → show identity/confidence → one next action`

The next action is research or review. Consequential action remains a separate Guardian-owned
contract requiring exact current device, firmware/source, partitions and mode, artifacts/hashes,
ordered operation, consequences, recovery route, expected result, and fresh consent. Bootloader
relocking remains permanently prohibited.

## Fixed Google Play query-only acquisition

The first source-specific path uses only the already registered exact Google Play supported-device
catalog URL. A fixed HTTPS transport sends no credentials or cookies, accepts no redirects or
compression, and exposes separate connect, read and overall timeouts. The request and response are
bounded to 16 MiB, parsing is bounded to 100,000 rows, request spacing is at least two seconds, and
validated `ETag`/`Last-Modified` values are reused conditionally only when a prior content digest
exists.

The strict UTF-16 CSV parser requires the exact four-column schema and rejects malformed, empty,
overlong, control-character, spreadsheet-formula, and duplicate applicable rows. Because this is a
query-only parser, exact duplicate rows outside the requested identity are discarded and can never
be promoted; a duplicate row for the exact manufacturer/model/device-codename lookup fails closed.
Multiple applicable retail identities remain ambiguous.

Only an explicit privacy-checked manufacturer, model and device codename may be queried. One exact
match forms four official retail-identity claims. No match remains `UNCONFIRMED`; no catalog row is
promoted in bulk. The raw CSV exists only as bounded process memory during validation and is never
written. A strict private receipt records success, no exact match, HTTP failure, validation failure,
or cache-not-modified, along with bounded HTTP/cache metadata, content digest, parser identity,
retained claim references and literal zero authority.

Device DNA, Compatibility Matrix and Knowledge Archives consume the result through the existing
read-only projection contract. Catalog identity cannot define firmware compatibility, a Device
Pack, a build/flash contract, Guardian approval, a command, or device support.

## Typed knowledge and fixed Android connection guide

Schema one now carries a typed knowledge kind—identity, diagnostic, guide, fix-claim, or outcome—
plus bounded symptoms, error identifiers, prerequisites, affected builds, diagnostic/remedy
descriptions, expected result, rollback/recovery route, and outcome provenance. Descriptions reject
command-shaped/code/script text and remain evidence metadata with literal zero execution authority.
An old schema-one identity archive is verified against its original bytes and digest, loaded with
empty identity-safe defaults, and receives new claim/archive identities only at an explicit save or
merge boundary. Its values and evidence states are never promoted during migration.

The first fixed guide path accepts only
`https://developer.android.com/studio/run/device`. It requires the canonical English HTML page,
exact reviewed headings, a two-MiB response limit, separate connect/read/overall timeouts, no
redirects or compression, and the same conditional-cache/private receipt boundary. Scripts, code,
preformatted content, navigation, footer, templates, event attributes, unrelated blocks, and raw
HTML are never retained.

Exactly three heading-bound phrases may become official guidance: Connection Assistant setup,
faulty USB-cable diagnosis, and enabling USB debugging. Their combined retained source excerpt is
eight words; the surrounding diagnostic, prerequisite, expected-result, and rollback context is
ROMVERSE-authored non-executable metadata. Missing/changed headings, duplicate or conflicting
candidate text, privacy-unsafe content, localization, excessive sections, and stale evidence fail
or remain explicitly investigable. Official publication never means a confirmed fix.

The retained guidance projects read-only to Knowledge Archives, Device DNA diagnostics, Nexus, and
Insight. It executes no diagnostic, follows no page link, targets no device, and grants no Guardian
or compatibility authority.

## Fixed Pixel 6 factory-index metadata boundary

The next reviewed adapter accepts only `https://developers.google.com/android/images` and only the
already retained public identity `Google / Pixel 6 / oriole`. It performs one no-redirect,
identity-encoded HTML request with 8/12/30-second connect/read/overall timeouts and a four-MiB
limit. It sends no authentication or cookies and never follows an image link, posts a form, accepts
terms, or downloads an archive.

The canonical English parser recognizes only one exact Pixel 6/oriole table and requires its
reviewed Version, Download, and SHA-256 columns. Each complete row becomes one bounded structured
metadata claim containing the explicit release label, build identifier, date, Android version,
carrier/region scope when stated, official `dl.google.com` image URL identity, and published
SHA-256. Duplicate/conflicting builds, duplicate image identities, missing dates or hashes,
unexpected URLs, changed layout, excessive rows, private text, and executable/relock content in a
candidate field fail closed. Scripts, code, forms, buttons, terms, instructions, navigation, and
raw HTML are excluded from claims.

Receipts permanently record `terms_accepted: false`, `binary_downloaded: false`, zero execution,
phone, Guardian, and relock authority, and `UNCONFIRMED` compatibility. Device DNA, Compatibility
Matrix, Pathfinder, Nexus, Foresight, and Knowledge Archives may inspect this metadata, but it
cannot establish artifact compatibility, a safe flash route, a confirmed outcome, or permission to
act on a device.

## Knowledge Coverage & Value Gate

Every future source must close a named evidence gap for a named ROMVERSE consumer. A proposal must
state the exact fields expected, feature benefit, source authority/scope, revision and freshness,
parser/validation/corroboration method, conflict behavior, privacy/licensing/retention limits, stop
condition, capability unlocked, and why it is higher value than alternatives. A source is not
acquired merely because it exists.

Useful coverage is limited to device/variant identity; firmware/build/package manifests, dates,
hashes and dependencies; partition/dynamic-super layout, sizes, filesystems, slots and mount roles;
SoC/architecture, kernel/device-tree and boot artifact formats; AVB/unlock/rollback and verified-boot
state; read-only ADB/Fastboot/Fastbootd/Recovery observations and transitions; host tools/drivers;
recovery/backup/failure modes; diagnostics/errors/expected findings; ROM/root/debloat prerequisites,
risks, outcomes and rollback; and privacy-safe exact outcome evidence.

Generic marketing/news/reviews, SEO summaries, duplicated mirrors, uncited or scope-free tips, bulk
copyrighted text, raw response archives, personal identifiers, credentials, unrelated telemetry,
and votes/popularity as proof are excluded. Technically specific community evidence can remain only
low-confidence `source-reported` evidence until genuinely independent corroboration. Exact observed
device/firmware outcomes—not source repetition—are required for live-confirmed/ROMVERSE-verified
status.

## Implemented, simulated, deferred, unsupported

- **Implemented:** strict claim model and archive, deterministic merging/linking, privacy filtering,
  registered-content validation, freshness states, later firmware/live comparison, and read-only
  consumer projections.
- **Simulated/tested:** bounded response ingestion and local storage using synthetic public text,
  exact matching/corroborating/conflicting firmware and live observations, malformed/tampered data,
  oversize bodies/archive, stale/future times, redirects, compression, symlinks, and privacy-unsafe
  evidence.
- **Deferred:** network client and scheduler, robots/terms-specific adapter review, HTTP caching,
  actual OEM/firmware/community parsers, UI wiring, runtime Device Engine/firmware ingestion, and
  cross-process rate coordination.
- **Unsupported in this checkpoint:** authentication or anti-bot bypass, private source access,
  arbitrary web crawling, instruction execution, Guardian approval, physical-device mutation,
  publication/contribution, production trust enrollment, and bootloader relocking.
