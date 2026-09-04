# ROMVERSE Privacy Notice

**Version:** draft-2026-09-05
**Status:** INTERNAL REVIEW DRAFT — NOT YET EFFECTIVE  
**Product:** ROMVERSE Desktop and ROMVERSE Companion

This document describes the current ROMVERSE development build. It is written to make the product's real information flows visible before public release. It is not an effective public privacy policy and has not received legal approval. The provider's final legal identity, privacy contact details, complaint process, supported countries, production services and effective date must be completed and reviewed before release.

## 1. Plain-language summary

ROMVERSE is local-first. Firmware files, ROM projects, recovery evidence, diagnostics, audit records, local Galaxy topics and local Synapse memory stay in the workspace selected on the user's computer unless the user starts a clearly named feature that needs another destination or network service.

ROMVERSE reads technical information from a connected Android device only for the feature the user starts. The Desktop masks serial numbers in its interface and normally stores a workspace-specific pseudonym instead of the raw serial. A raw serial may exist briefly in memory when it is required to address the selected device through ADB or Fastboot; it is not a public identity and must not be uploaded as knowledge-bank data.

Online intelligence, community research, verified tool downloads, update checks, Members configuration, wireless Companion pairing and Galaxy contribution are separate controls or explicit workflows. Opening About or reading this notice starts none of them. Galaxy contribution is off by default. ROMVERSE does not currently operate a public account, Galaxy, Synapse or firmware-hosting service, and the production Galaxy endpoint and public trust keys are not enrolled in this build.

## 2. Information the current apps may handle

Depending on the feature used, ROMVERSE may handle:

- Android technical identity, including manufacturer, brand, retail model name, product and device codenames, hardware or SKU, Android/API version, build identifiers, firmware channel evidence, security patch, ABI, kernel, partition capabilities, A/B slot state, dynamic-partition signals, bootloader-lock state and Verified Boot state;
- operational health signals such as battery level/status/temperature, storage, memory, uptime, boot completion and bounded root-manager presence signals;
- the presence and version status of ROMVERSE Companion and narrowly allowlisted Android tooling used by a requested workflow;
- user-selected firmware packages, APKs, ROM project files, build outputs, recovery snapshots, backup destinations and shared-storage backup content;
- local settings, feature choices, warnings acknowledged for a specific high-risk plan, integrity receipts, operation outcomes and audit metadata;
- local Companion telemetry that is deliberately bounded and rejects accounts, IMEI, raw serials, package lists, files, shell commands and other prohibited fields;
- user-confirmed backup status, a privacy-reduced last-known Device DNA summary, reviewed first-boot guide steps, and user-selected Desktop-to-Companion transfer metadata and bytes; and
- account identifiers or service configuration only if a future production Members service is configured and the user explicitly signs in.

ROMVERSE is not designed to collect contacts, messages, call history, photographs, documents, precise location, advertising identifiers, IMEI or unrelated installed-app inventories for diagnostics or knowledge contribution. A user-selected phone-media backup can copy the chosen shared-storage folders to the user's chosen local destination; that content is backup data, not diagnostic or knowledge-bank data.

## 3. How information is obtained

Information may come directly from the user, from files the user selects, from read-only allowlisted ADB or Fastboot probes, from ROMVERSE Companion over an authenticated Link session, or from a named online source used by an enabled research, catalog, tool-download or update workflow.

USB detection alone does not authorise a device-changing action. Firmware compatibility, build readiness and Guardian decisions are automated technical assessments based on the available evidence. Unknown or conflicting evidence must remain visible and cannot be silently converted into permission.

## 4. Why ROMVERSE handles it

ROMVERSE uses the information to identify the selected Android device and firmware, diagnose problems, explain compatibility, prepare backups and recovery plans, inspect or build user-selected ROM material, verify artifacts, show local history, pair the Companion, and apply Guardian safety controls. It may also use privacy-filtered technical evidence to improve local guidance.

The current build does not sell personal information, build advertising profiles or use device evidence for targeted advertising. Future analytics, hosted accounts, billing, public community features, cloud knowledge contribution or AI services must remain disabled until their exact information flows, providers, retention and user choices are implemented and this notice is updated.

## 5. Local storage and security

The Desktop stores projects and most records in the selected ROMVERSE workspace. Settings are stored in the operating system's application-configuration area. Sensitive local records use bounded schemas, integrity digests, atomic writes and link/path checks. Device-facing audit and diagnostic records use a workspace-specific pseudonym where a stable device reference is needed.

ROMVERSE Link uses a short-lived pairing flow and authenticated encrypted transport. Companion credentials are protected by Android Keystore where available, Android backup is disabled for those credentials, and resetting Link revokes the remembered local session. These controls reduce risk but do not make a compromised computer, phone, operating system or network safe.

For Secure Handoff, Desktop first hashes a file without retaining it. Only after the user confirms
the exact filename, type, size and digest does Desktop create a private content-addressed copy and a
24-hour offer that omits the original path. The authenticated phone asks again and uses Android's
document picker for the destination. It verifies TLS identity, response metadata, byte length and
SHA-256 and removes partial output after failure. ROMVERSE does not automatically open, install,
execute or flash a transferred file. Reset Link revokes offer manifests; private inert staged bytes
are not represented as user backups and are not automatically deleted in this development build.

The backup checkpoint stores and transmits only a user's statement that an external backup is
current and the confirmation time. It does not inspect the backup or prove it recoverable. The
last-known Device DNA cache excludes raw serial, IMEI, paths, full hashes, commands and authority.
First-boot guide progress records reviewed checklist steps, not subsystem test results. An emergency
guide remains reopenable inside Companion only when the user selected it and Android granted lasting
document access.

Firmware, build outputs and phone-media backups can contain sensitive user or device material. The user chooses their locations and is responsible for securing those locations and any additional copies. ROMVERSE does not automatically delete user backups or protected firmware sources.

## 6. Network features and third parties

When enabled or explicitly started, the current Desktop may connect directly to named sources such as Google/Android/AOSP services for device catalogs, platform tools and technical documentation; GitHub for selected open-source tooling or release metadata; and Reddit, Stack Exchange or a configured search provider for community remediation research. The interface must identify the purpose and source of an online workflow. Research queries are privacy-filtered and remote text is guidance, not executable authority.

Network providers can receive ordinary connection information such as the user's public IP address, request time, user agent and the query or artifact requested. Their own privacy terms apply. Processing may occur outside Australia. The production provider list, likely recipient countries and contracts are not final and must be completed before public release.

The local connectivity badge may contact Google's connectivity-check endpoint only while online sources are enabled. Disabling online sources stops that monitor and prevents catalog/research refreshes, while already verified local information remains usable.

## 7. Knowledge contribution and community reports

Local Synapse memory and local Galaxy topics are not public uploads. Galaxy contribution is off by default, and the current build has no configured production contribution backend. The Desktop can prepare a bounded technical contribution from selected Device DNA, exclude raw serials, IMEI, accounts, private paths, credentials, personal content and unreviewed logs, show the exact payload and destination, and queue or export it only after a separate choice. With the packaged trust file currently unconfigured, it cannot send that payload.

If a future legally reviewed release enrolls the official endpoint and public keys, a user who opts in and signs in through the matching ROMVERSE Members issuer can explicitly submit one reviewed payload. The client sends the in-memory access token to that named service for authentication but does not store it in the contribution or receipt. It requires a signed server receipt tied to the exact contribution. A separate signed-update workflow may download privacy-filtered technical knowledge, verify its publisher and show the proposed local changes; installing it requires another confirmation. These client controls do not replace the hosted service's still-required collection notice, retention/deletion rules, moderation, abuse prevention, access controls and incident response.

Official, maintainer and community evidence may inform the knowledge system. Its source, date, scope and confidence must remain attached. Community evidence never grants flash authority and must not expose a reporter's personal information without a lawful basis and clear notice.

## 8. Retention, access, correction and deletion

In the current local alpha, the user controls the workspace and backup locations. Closing ROMVERSE does not erase them. Link has an explicit reset control for remembered pairing state. ROMVERSE does not yet provide a complete one-button inventory/export/delete workflow for every local record, and no production hosted account record exists.

Before public release, ROMVERSE must define and test retention periods, secure deletion and backup behavior; provide an understandable way to locate, export, correct or delete applicable local and hosted information; and publish a contact process for access or correction requests. Deleting technical evidence may make a project unverifiable or require a fresh device scan, which must be explained before deletion.

## 9. Automated technical decisions

ROMVERSE automatically classifies device identity, firmware relationships, compatibility evidence, build readiness, diagnostic findings and Guardian safety gates. Those classifications affect what the app recommends or permits inside ROMVERSE; they do not decide employment, credit, insurance, healthcare, government benefits or another person's legal rights. The user can inspect the evidence and source behind a result. Unknown evidence remains unknown, and high-risk operations require separate plan-specific review.

The Privacy Act amendments concerning certain significant automated decisions commence on 10 December 2026. Before any production service uses personal information for a decision that could reasonably be expected to significantly affect a person's rights or interests, ROMVERSE must reassess that workflow and update the effective policy and collection notices.

## 10. Children and authorised use

ROMVERSE is specialist Android firmware and recovery software, not a service directed to children. A person must have authority to inspect or modify the device and data they place in a workflow. Public-release age requirements and any parental-consent process require legal and product review.

## 11. Incidents, questions and complaints

The final policy must name the legal provider and publish stable privacy contact details, an access/correction process, a complaint process and an incident-response route. Those details are intentionally not invented in this development draft. If this draft appears in a public production build without those fields completed, that build has failed its release gate.

Nothing in this notice limits privacy rights or remedies that cannot lawfully be limited. Applicable rights depend on the final provider, service, location and law.

## 12. Sources and release gate

This draft was structured against the Office of the Australian Information Commissioner's APP 1 guidance and the Australian Privacy Principles in Schedule 1 to the Privacy Act 1988 (Cth):

- https://www.oaic.gov.au/privacy/australian-privacy-principles/australian-privacy-principles-guidelines/chapter-1-app-1-open-and-transparent-management-of-personal-information
- https://www.oaic.gov.au/privacy/australian-privacy-principles/australian-privacy-principles-quick-reference
- https://www.legislation.gov.au/C2004A03712/latest/text

Before publication, qualified Australian privacy/legal review must confirm whether the provider is an APP entity and complete the provider identity, contact details, collection notices, processor/recipient inventory, overseas locations, retention schedule, access/correction/deletion and complaint procedures, breach response, age position, production security claims and effective date. The reviewed document digest must then be bound to the signed release. Reading this draft records no acceptance, changes no setting, starts no network request and grants no device or execution authority.
