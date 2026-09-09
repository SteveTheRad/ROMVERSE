# ROMVERSE Device Intelligence Foundation

## Checkpoint 1 boundary

This checkpoint adds deterministic, local and acquisition-inert schema contracts. It extends the
existing Device DNA, firmware source identity and online evidence architecture; it does not create
a parallel device database, compatibility system, source harvester or execution path.

External, firmware-derived and historical information remains evidence only. Every new record fixes
execution authority to `none`, phone action and Guardian approval to `false`, and bootloader
relocking to `false`. Compatibility remains `UNCONFIRMED` until the existing evidence and Guardian
contracts establish otherwise.

## Canonical device identity

`CanonicalDeviceIdentity` provides one immutable SHA-256 identity derived from exact normalized
manufacturer, brand, model, codename, region, OEM identifiers and platform facts. Creation requires
exact evidence claim digests and the manufacturer, model and codename; missing consequential
identity fails closed as `UNCONFIRMED`.

Marketing names, aliases and family relationships are retained as discovery metadata but excluded
from exact identity. They cannot establish equivalence. A different model, regional variant or OEM
identifier produces a different canonical identifier. Strict schema-one parsing rejects unknown
fields, malformed types, non-canonical ordering, identifier tampering, private data and any attempt
to promote compatibility or execution authority. Existing schema-one device-name receipts remain
unchanged and continue through `DeviceIdentityResolver`.

## Canonical firmware identity

`CanonicalFirmwareIdentity` is bound beneath one canonical device ID and one exact artifact
SHA-256. Its deterministic ID also covers exact model/variant, region, build, firmware version,
Android version, security patch and the optional bounded partition/layout digest. Exact evidence
claim digests are required.

Changing the device, model, region, build or artifact produces a different firmware identity. No
compatibility is inherited between versions or variants. Existing filename-derived
`FirmwareSourceIdentity` remains descriptive and unchanged; it cannot construct a canonical
identity without an exact artifact digest and evidence.

## Claim-specific source authority

`ClaimSourceAuthority` replaces no existing source category. It adds a separate, explicit mapping
from one source to reviewed claim domains and exact claim keys. The domains cover identity,
firmware, Android platform, partitions, boot architecture, OEM technical facts, observed behaviour
and compatibility outcomes.

Applicability is true only when both the requested domain and exact claim key are listed. There is
no universal source trust score or inheritance into an unlisted claim. The contract itself remains
evidence-backed and has no execution authority.

## Evidence lifecycle

`EvidenceLifecycle` binds one claim to:

- observation, retrieval and optional revalidation timestamps;
- the exact source artifact digest;
- device, model, firmware, build and region scope through the existing `EvidenceScope`;
- supporting and contradicting claim relationships;
- explicit active, superseded, quarantined or expired status; and
- immutable ordered status history.

The lifecycle is content-addressed and strictly parsed. Contradictory and superseded records remain
visible rather than being overwritten. Duplicate existing online claims remain deterministically
deduplicated by claim ID, and stale or conflicting evidence continues to require investigation.
Observation cannot follow retrieval, revalidation cannot precede retrieval, history cannot predate
observation, and the final history status must equal the record's current lifecycle status.
Checkpoint 1 does not change the Synapse state machine; its separately authorized lifecycle work is
still gated behind independent Product Assurance.

## Privacy

Canonical identity, firmware and evidence boundaries reject or sanitize serials, IMEI, account and
user identifiers, email addresses, credentials, tokens, cookies, sessions, private-key material and
personal home-directory paths. Only bounded claim fields and exact digests belong in these records;
unrelated logs and personal files are not evidence payloads.

## Persistence interface

`romverse.knowledge.evidence_persistence` defines structural protocols for future append-only
records and content-addressed artifact references. It contains no filesystem, database, PostgreSQL,
network or object-store implementation and performs no upload. The protected existing local store
is not modified.

## Backward compatibility and migration

- Existing Device Identity receipts retain schema one and their prior resolver semantics.
- Existing Online Evidence schema-one archives load with their original confidence, evidence state
  and zero-authority values; saving through the existing store retains the existing conservative
  migration behaviour.
- Existing Device DNA schema one/two, Compatibility Matrix and Nexus records are unchanged and are
  verified by their baseline suites.
- New canonical and lifecycle records accept only their exact schema-one fields. Unknown versions,
  extra fields, corrupt digests, malformed types or authority promotion fail closed.
- Migration never upgrades confidence, compatibility, physical verification or Guardian authority.

## Permanent exclusions

This checkpoint performs no live acquisition, crawling, phone or emulator access, ADB/Fastboot,
firmware operation, ROM build, flashing, rooting, debloating, device transition, runtime consumer
wiring, database deployment, object upload, UI/platform/Companion change, hosted CI, signing,
publication or release. ROMVERSE never locks or relocks a bootloader.
