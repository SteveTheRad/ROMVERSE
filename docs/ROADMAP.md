# ROMVERSE Roadmap

## Roadmap discipline

This roadmap records ordered development direction. A roadmap item is not implemented merely because it appears here. Status claims must be backed by repository and test/runtime evidence.

## Immediate priority

Build and verify the real functional chain before secondary ecosystem expansion:

1. Firmware detection
2. Device identification
3. Device DNA
4. Capability Map
5. ROM Studio workspace
6. Required tool resolution
7. Firmware extraction
8. Modification/debloat
9. Build validation
10. Guardian Readiness
11. Local backup
12. Controlled Guardian Flash

## Device DNA milestone

V1 targets include:

- Correct device marketing identity, model, and codename
- SoC/platform
- Android, ROM, build, region, and security information where available
- Firmware/package format
- Partition architecture
- A/B and Virtual A/B information
- Filesystem types
- Bootloader and active-slot state where obtainable
- Root state where safely identifiable
- Encryption and Verified Boot information
- Partition sizes
- Fastboot/recovery capabilities
- Compatibility warnings
- Evidence/source and confidence for important findings

Tests must cover SUPPORTED, CAUTION, UNSUPPORTED, and genuinely UNCONFIRMED paths.

## Intelligence milestones

Progressively establish:

- Compatibility Matrix
- Foresight
- Nexus orchestration
- Pathfinder Route Map
- Guardian integration
- Insight explainability
- Synapse verified-solution lifecycle
- AI Usage Governor
- provider-independent AI Gateway

## Companion milestones

Companion migration should preserve existing functionality and verify each stage incrementally:

- ROMVERSE Link
- Pulse
- Vitalis
- Lifeline
- Live Console
- Community/Account integration

## Infrastructure milestones

Start with a practical, separable deployment architecture for website, community/forum, accounts/subscriptions, ROMVERSE API/backend, Synapse, database/cache, monitoring/admin, object storage/CDN, and off-server backups. Scale from measured load rather than assumptions.

## Release progression

Current release direction remains staged:

closed beta → public beta → commercial launch

Guardian validation is required before commercial release readiness.

## Documentation milestone

The repository must mature alongside the implementation until a clean clone on another correctly configured development machine can be used to restore the toolchain, build the project, run tests, understand the architecture and current roadmap, and resume development safely.
