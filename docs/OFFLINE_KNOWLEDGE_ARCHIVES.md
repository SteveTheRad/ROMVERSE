# ROMVERSE Offline Knowledge Archives

ROMVERSE Archives is the app's offline repair brain. Device DNA, diagnostic findings, and typed
boot/flash failures are evidence queries into this local corpus. Network access may update the
corpus later, but it is never required to explain a locally known problem or recovery boundary.

## Current vertical slice

The initial archive promotes the existing curated ROMVERSE known-fix catalog into the structured
store and adds modular, exact-scope evidence packs reviewed on 2026-09-04. The resulting seed
currently contains 245 records and 150 distinct provenance entries. It includes platform guidance
and OEM coverage for
Samsung, Google/Pixel, Huawei/Honor, Xiaomi/Redmi/POCO, OnePlus, Sony, Motorola/Lenovo, Nothing,
OPPO, realme, vivo/iQOO, ASUS, HMD/Nokia, Fairphone, TECNO, Infinix, itel, ZTE, and nubia/REDMAGIC.

The archive also preserves XDA and Reddit outcomes. One explicit owner report that a guide fixed an
identified device is usable community evidence and can be returned by the matcher. The record keeps
the source tier, report/corroboration count, exact known scope, confidence, and known gaps. A single
success is not silently promoted to a universal claim.

## Record contract

Each record has a stable identifier and revision plus:

- kind: diagnosis, fix, guide, compatibility, or recovery;
- symptoms, exact error codes, and typed diagnostic finding IDs;
- diagnostic checks and compatible fix guidance;
- prerequisites and expected outcomes;
- compatibility and known-incompatibility statements;
- recovery routes and search tags;
- device scope: manufacturer, brand, model, codename, build, Android version, bootloader state,
  and partitions;
- provenance source IDs, source tier, review date, confidence, and corroboration count;
- optional typed operation declarations.

The source tiers are `official_vendor`, `official_platform`, `reputable_technical`, `community`,
and `romverse_verified`. Official vendor and AOSP/Android platform evidence receive equal highest
source weight. Source weight is only one small part of ranking: an exact error/build/codename match
outranks a broad official family article.

## Deterministic lookup

`OfflineKnowledgeService` builds a query from confirmed Device DNA facts and partition inventory.
A failure producer can add an exact phase, message, error code, diagnostic finding, partition,
operation, verified input evidence, and rollback route. Ranking is deterministic and favors:

1. exact error or typed finding;
2. exact firmware/build relationship;
3. exact codename and model;
4. exact partition;
5. Android/bootloader/brand/manufacturer scope;
6. bounded symptom and evidence-term overlap;
7. provenance tier and stated record confidence.

Contradictory known build, codename, model, Android version, or manufacturer scope excludes a
record. Unknown evidence remains visible as missing; it is not treated as a match. Results explain
the match, confidence, missing evidence, scope, corroboration, diagnostic steps, compatible
guidance, prerequisites, outcomes, incompatibilities, and source URLs.

Every successful Device DNA refresh automatically scans the archive and exposes the result through
`DeviceDnaService.last_knowledge_lookup`. Typed boot/flash failure producers use
`DeviceDnaService.scan_knowledge_after_failure` or `OfflineKnowledgeService.scan_after_failure`.
Archive corruption never invalidates a valid Device DNA profile; it is reported separately through
`knowledge_lookup_error`.

Boot Observatory receipts use a strict, bounded schema-two contract and classify observed device
mode, identity drift, uptime-reset boot loops, boot-completion timeouts, and incomplete property
probes. An attention receipt is translated into typed failure evidence automatically. Genesis and
Forge Control immediately rank the offline corpus, show the number and best compatible matches,
and keep the full evidence explanation available for review. Stable boot samples do not trigger a
failure lookup. The desktop Archives also searches the structured records directly and exposes
scope, confidence, corroboration count, diagnostic steps, compatible guidance, known
incompatibilities, and provenance alongside the original curated guides.

Recovery Bay automatically builds a privacy-safe query from the selected device identity, Android
build, bootloader state, exact typed symptom, ADB errors, and current diagnostic finding IDs. It
shows the top compatible structured records inside the safety plan and includes their record IDs,
confidence, corroboration and source IDs in the exportable local report. ROM Studio worker failures
use the same path. Exact observed failure symptoms outrank unrelated broad Device DNA terms, so a
specific transport or tool error cannot be buried by generic profile context. These automatic scans
start no online request, repair worker, command, or phone action.

Device discovery failures also enter this path before a phone snapshot exists. Recovery Bay ranks
the bounded ADB/host error against the local corpus, displays the compatible evidence beside any
separate host-daemon recovery option, and can hand the exact error to Archives for review. This
pre-device lookup neither assumes an identity nor starts the host recovery option automatically.

## Persistence and import

The packaged core, OEM recovery, boot-error/device-alias, and Fastboot/transport evidence packs are
merged and copied on first use to `knowledge/archive.romverse` inside the selected workspace. More reviewed packs can be added
without turning the archive loader into one unmaintainable data file. The local file is private,
atomically replaced, byte-bounded, strict-schema, and sealed
with a canonical SHA-256 digest. Loading rejects links, extra/missing fields, invalid types,
duplicate IDs, unknown provenance, invalid URLs, digest changes, oversized collections, and unsafe
operation declarations.

On application upgrade, newly packaged records are reconciled into the existing local archive.
Higher-revision packaged records replace older local copies, while newer locally reviewed/imported
revisions are retained. Equal-revision content or provenance conflicts fail closed instead of
silently choosing one meaning.

Imports are local JSON bundles using the same schema and digest. Merge behavior is deterministic:

- a new record ID is added;
- a higher revision replaces that record;
- identical content at the same revision is unchanged;
- conflicting equal revisions and revision downgrades are rejected;
- a reused source ID with changed provenance is rejected.

This makes the brain continuously expandable without letting an update rewrite the meaning of an
existing source or silently downgrade a record.

The boot-error pack includes the canonical AOSP `update_engine` meanings for payload hash/size,
signature, timestamp downgrade, install-device access, operation hash, insufficient-space, and
device-corruption failures. It also records A/B fallback and Virtual A/B snapshot boundaries plus
maintainer-published Device DNA aliases such as `capri`, `caprip`, `clark`, `klte`, `Z00T`, and
OnePlus 8T `kebab` regional model families. A generic Recovery `status 1` is deliberately not
treated as a diagnosis when the underlying error line is absent.

The Fastboot and transport pack distinguishes bootloader Fastboot from userspace fastbootd; locked
policy refusals from missing logical partitions; super-allocation errors from unreadable metadata;
and Virtual A/B snapshot guards from ordinary slot errors. It also gives offline answers for ADB
`unauthorized`, `offline`, Linux `no permissions`, Windows OEM-driver, direct-USB transfer, and
version-scoped Platform-Tools failures. Google-published Pixel May 2025 and May 2026 bootloader
anti-rollback boundaries are model-scoped. Community outcomes for Pixel, Lenovo, OnePlus, Samsung,
and Xiaomi retain their exact known circumstances and explicitly record what the report did not
prove.

## Device-change boundary

The archive has no execution authority. Read-only identification and diagnosis may use broad
evidence. A record cannot even declare a device-changing operation unless it contains an exact
model/codename scope, exact build IDs, exact target partitions, named verified-input requirements,
and an explicit rollback route. At lookup time all of those must match current evidence before the
operation can be labelled eligible for a separate Guardian review. It is still never executed by
the archive.

Community success reports can therefore give ROMVERSE a useful answer immediately while remaining
honest about device/build scope. They can recommend a guide and describe a reported outcome; they
cannot turn a family-level anecdote into an automatic flash, wipe, unlock, relock, or partition
write.
