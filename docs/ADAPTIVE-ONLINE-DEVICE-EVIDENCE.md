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

The first default registry intentionally contains only sources already represented by repository
evidence:

- Google Play's fixed public supported-device catalog;
- public Android developer documentation;
- public AOSP platform/device source through Android Gitiles;
- public Android kernel source through Android Gitiles.

OEM firmware indexes/manifests, OEM documentation, additional maintained technical repositories,
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
