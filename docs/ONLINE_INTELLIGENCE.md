# ROMVERSE online intelligence boundary

ROMVERSE uses connected evidence to improve diagnosis and planning, but connectivity never grants
permission to change a phone. All remote text remains guidance until a built-in typed action proves
its prerequisites and produces a source-bound verification receipt.

## Resolution order

The provider-independent AI Gateway resolves a bounded, privacy-scrubbed request in this order:

1. deterministic local rules;
2. exact or bounded ROMVERSE Synapse evidence;
3. verified local cache;
4. Compatibility Matrix rules;
5. a configured server-side AI provider only when existing evidence is insufficient.

AI suggestions remain unvalidated, guidance-only evidence. They require normal evidence checks and
Guardian review. The gateway has no execution authority and permanently sets bootloader relock to
false.

## Connected remediation evidence

Each new remediation lookup writes a content-digested V2 receipt bound to the normalized error,
device/build facts that were actually available, the exact verified tool name/version when the
failing operation has one authoritative runtime tool, and the returned candidates. Multi-tool or
unverified operations remain tool-unconfirmed rather than guessing. ROMVERSE displays:

- source authority and URL;
- retrieval time and source publication/update time where supplied;
- freshness as current, aged, stale, or explicitly unconfirmed;
- exact-device/build/tool scope or a clear category-only limitation;
- independent-source corroboration count and authority families;
- numeric confidence and a plain-language explanation of that confidence.

Recovery Bay derives a deterministic Smart Solution Brief from the persisted, revalidated receipt.
It chooses one of eight honest states: no match, locally verified, typed action available, official
guidance, reported risk, corroborated hypothesis, community hypothesis, or discovery review. The brief
names why the lead ranks first and one next safe move; the UI shows up to five ranked evidence links
with authority, confidence, freshness, scope, and evidence signal. A maintainer/community report that
describes a boot loop, bricking, data loss, or a failed post-action result is labelled reported risk
and the next move explicitly says not to reproduce it. This text classification may add caution but
can never add authority.

Before presenting the brief, the service reopens the exact persisted research receipt. Any stale,
changed, missing, or malformed record discards the proposed solution. A locally verified label is
derived again from the exact source URL/action tuple and a currently valid typed outcome receipt; an
in-memory or provider-supplied claim is insufficient. The exported Recovery Bay report contains only
the bounded derived decision and source identifiers, plus `execution_authority: guidance-only` and
`phone_action_allowed: false`.

For a lead official/maintainer candidate with a registered typed local action, Recovery Bay may show
one matching workflow control. Before emitting a handoff it must reload the same fingerprint receipt,
recheck its digest, lead source, authority, action ID, and current synthesized state. MainWindow must
repeat that validation before accepting the route. ADB evidence stays on the current Recovery Bay
surface; Platform Tools opens an immutable host-only Forge Arsenal context; OTA payload,
source-classification, and AVB actions bind the current ROM project and protected-source SHA-256
before opening Forge Control in review-only mode. The user must make a separate click on the local
inspection. Merely opening any of these views starts no scan, install, worker, build, flash, or phone
command. Provider-injected IDs and stale fingerprint, receipt, lead, project, or source evidence fail
closed with a visible in-page explanation.

The connected provider set always begins with ROMVERSE's curated official Android/AOSP/OEM index.
When community research is enabled it also searches Reddit reports and accepted-answer Android
Enthusiasts threads. A configured Google Programmable Search connection may add official OEM pages,
actual tool-maintainer repositories, XDA discussions, and wider discovery results. Host classification,
exact identity tokens, freshness, and independent corroboration remain visible; a platform name or
accepted answer never self-promotes a result to verified working.

Stale community/discovery evidence is downgraded. Missing or future-dated timestamps do not become
current by assumption. V1 cached receipts remain readable but their new evidence fields stay
unconfirmed. Editing any V2 evidence assessment invalidates its digest. None of these fields grants
execution authority: only a matching built-in typed action with a verified local receipt can be
promoted as working for the same fingerprint.

Local persistence is a bounded evidence cache, not remote authority. V1/V2 research receipts and
verified-outcome records are read only as regular files beneath the resolved workspace, have strict
shape and byte/count limits, and are replaced atomically through unique private staging files.
Symlinked/reparse-point directories, symlinked targets, oversized or extra-field records, invalid
source identifiers, provider-injected action identifiers, and malformed candidate collections are
rejected. Providers cannot self-assert `confirmed working`; that label is reconstructed only while
the corresponding validated local typed-outcome record is still present. These protections detect
and contain damaged or casually altered workspace evidence; they do not turn a same-user local
digest into a cryptographic remote trust anchor.

## Official Android device identity catalog

Device Atlas has a separate, non-remediation online path for Google's public supported-device CSV.
It contacts only `https://storage.googleapis.com/play_public/supported_devices.csv`, rejects a
redirect or compressed response, and bounds the declared and received bytes before decoding the
required UTF-16 catalog. Exact columns, row shape, entry count, local regular-file containment,
SHA-256, and a private strict receipt are revalidated whenever identity data is used. A failed
refresh never activates the received bytes; a prior cache is reused only while it independently
continues to pass those checks.
The background worker stages a validated update in memory rather than writing it immediately.
Disabling online sources cancels the worker, discards any late candidate, and gates activation on
the current setting. Cancellation never removes the previously activated local mirror.

The phone supplies `Build.BRAND`, `Build.DEVICE`, and model through ROMVERSE's read-only Device
Engine. Matching requires the exact normalized brand/device pair. An exact model may narrow known
variants, but multiple remaining retail names are reported as ambiguous and never resolved by row
order, popularity, manufacturer guess, or marketing-name similarity. A valid stale cache stays
explicitly update-due and may provide read-only naming while offline.

Catalog authority ends at retail identity. The downloaded data cannot define a firmware digest,
partition layout, compiler toolchain, Device Pack, build contract, write contract, physical recovery
attestation, approval, command, or execution authority. Device Atlas uses the result only to improve
labeling and select the ordinary integrity-indexed Pack roadmap; every independent build and flash
gate remains in force.

Verified-fix outcomes use schema two. Creation requires all three bindings to pass together: the
candidate still exists in the persisted receipt for that exact error fingerprint; its action ID is
on ROMVERSE's typed local allowlist; and a workspace-relative action receipt passes its
format-specific verifier. Current verifiers cover successful ADB host recovery, exact required-tool
verification, OTA source blueprints, and AVB topology receipts. The same verifier runs again when
an outcome is loaded, so a missing, changed, symlinked, wrong-project, wrong-format, failed, or
artifact-stale source receipt removes `confirmed working`. Schema-one digest-only outcomes are not
trusted for promotion. AVB promotion specifically requires schema-three size/mtime-bound image
evidence; schema two may still explain local history but is insufficient for a new verified outcome.

## ROMVERSE Synapse

The repository implements the client evidence contract and a tamper-detecting local mirror. It
does **not** claim that the public Synapse service is deployed.

Knowledge advances through:

`Candidate → Verified Success → Strong/Corroborated → Trusted`

Only successful locally verified typed actions can promote knowledge. Independent evidence is
required for stronger states. Failure downgrades knowledge, and repeated failure or version drift
retires it from query results. A bounded match is visibly different from an exact scope match.

Contributions contain privacy-scrubbed summaries and content digests, not firmware, credentials,
raw home paths, device serials, or provider keys. Contribution preparation is opt-in in Settings.
The private Archives evidence viewer can prepare a Contribution Passport for one selected learned
outcome. The exact bytes are displayed before the user may save a local review envelope. That
envelope contains only bounded compatibility scope, a re-scrubbed outcome summary, aggregate
verification state/counts, source-family labels, and observation times. Raw error/build
fingerprints, knowledge/contribution IDs, action/evidence receipt identifiers, device/account
identifiers, paths, email addresses, credentials, logs, firmware, and phone data are excluded. Its
content digest is revalidated before the atomic private write, and extra or altered record fields
are rejected. Preparing or saving this envelope starts no network request and permanently records
that upload is not authorised, phone action is not allowed, and execution authority is
guidance-only.
Authenticated upload, server validation, moderation, retention, and deletion remain production
backend release gates.

## AI Usage Governor

The in-process governor provides a client safety and capacity boundary that a production service
must also enforce server-side:

- daily reasoning budget;
- per-request token maximum;
- concurrent request maximum;
- shared rate limit;
- anonymized member fair-use throttling.

If a capacity or cost boundary is reached, ROMVERSE stops with an explanation. It never lowers
confidence requirements, skips evidence, or weakens Guardian to save cost.

## Provider and member security

- Members never enter third-party provider accounts or API keys.
- Provider credentials belong only in the future server-side gateway.
- Studio uses passwordless OAuth device authorization against a configured public HTTPS issuer.
- Access tokens remain in memory until an operating-system credential vault is implemented.
- Subscription state and feature entitlements are accepted only from the server-issued profile.
- The confirmed launch offer is A$14.99 AUD per month with a seven-day full-access trial.

## Live Console

Online remediation creates a genuine Live Console mission. The console records research start,
source-ranked completion, no-match attention, or failure. A verified typed repair can produce a
privacy-safe Synapse preparation event. Research success never masquerades as repair success.

Recovery Bay consumes the same remediation contract automatically for real diagnostic and ADB
failures. An optional exact user symptom is normalized into an error fingerprint; local paths,
email addresses, credential-like values, IP addresses, serial-like identifiers, and long digests
are removed before provider lookup. The card shows the best candidate's authority, explicit source
date/freshness, device/build scope, independent corroboration, confidence, and confidence reason.
Settings changes fail closed: an in-flight result from a disabled or replaced provider set is not
accepted. Only a matching built-in typed action and its successful local receipt can produce a
verified-fix outcome; remote instructions retain `execution_authority: guidance-only`.

## Production gates still open

- public Synapse API and authenticated contribution service;
- production AI provider adapters, metering, abuse controls, and independent corroboration;
- deployed Members issuer, subscription billing, signed entitlements, and reasonable offline
  authorization;
- TLS-pinned or equivalently hardened public API transport and formal threat model;
- public community moderation, reporting, privacy, retention, and deletion controls;
- measured VPS/object-storage/CDN/backups and disaster-recovery validation.
