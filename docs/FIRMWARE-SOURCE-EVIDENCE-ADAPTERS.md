# Firmware Source Evidence Adapters

ROMVERSE classifies firmware source material through one closed, deterministic evidence registry.
The registry contains exactly the three source representations that already existed at the
5 September 2026 feature freeze:

- Android OTA `payload.bin`;
- Fastboot `super.img`;
- extracted partition-image bundle.

This boundary is deliberately evidence-only. It can inspect an immutable snapshot, prepare a
source-bound blueprint, or load and revalidate a durable blueprint. It cannot build, flash,
install, select a device, dispatch a command, approve an operation, retry an operation, or grant
Guardian authority. Production service construction is closed and provides no adapter injection,
entry-point discovery, arbitrary import, vendor plug-in, or free-form command path.

## Deterministic classification

The service makes one sorted workspace-relative snapshot of the isolated source tree. Every
registered adapter sees that same immutable snapshot. Registry order is derived from the stable
adapter identity, never caller order or filesystem enumeration order.

An exact single match selects the corresponding evidence handler. No match remains unsupported by
the current bounded source inspection. Multiple matches, multiple `payload.bin` files, multiple
`super.img` files, duplicate adapter identities, missing registered identities, or an unknown
identity fail closed as ambiguous or invalid. A partition bundle is a fallback only when neither
an OTA payload nor a Fastboot super image is present; this preserves the existing interpretation
of Fastboot packages containing `super.img` alongside other partition images.

Durable loading has no priority fallback. If more than one independently valid blueprint is
present, ROMVERSE reports ambiguity instead of silently choosing one.

## Evidence boundary

Every prepared or loaded blueprint is rechecked against its exact project, adapter identity,
evidence-only authority label, unchanged-phone marker, and ready baseline state. The retained
blueprint formats, schemas, fields, digests, and existing source-specific verification remain
unchanged:

- `romverse.source-blueprint` version 1;
- `romverse.ota-source-blueprint` version 1;
- `romverse.partition-bundle-blueprint` version 1.

The registry adds no firmware format, vendor, Device Pack, route, UI, execution capability, or
physical-device operation. Guardian remains the only execution gate. Bootloader locking and
relocking remain permanently prohibited and have no adapter or registry path.
