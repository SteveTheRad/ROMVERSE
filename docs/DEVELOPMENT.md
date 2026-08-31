# ROMVERSE Development Workflow

## Repository role

This private repository is the authoritative technical source of truth for ROMVERSE development. Important decisions, setup knowledge, architecture, implementation status, and release context must not live only in chat history or on one computer.

## Branching model

- `main` — stable project baseline.
- `develop` — integration branch for ongoing work.
- `feature/<name>` — short-lived feature branches from `develop`.
- `fix/<name>` — bug-fix branches from `develop`.
- `release/<version>` — release preparation when needed.
- `hotfix/<name>` — urgent production fixes from `main`.

Merge through pull requests where practical. Avoid doing normal feature development directly on `main`.

## Commit discipline

Commits should be small enough to understand and review, with messages that explain intent. Prefer conventional prefixes where useful, for example:

- `feat:` new capability
- `fix:` bug correction
- `docs:` documentation
- `refactor:` structural change without intended behavior change
- `test:` tests/fixtures
- `build:` build/tooling changes
- `chore:` maintenance

## Status discipline

Never report a planned, approved, or designed feature as implemented.

Use these concepts consistently:

- Planned / proposed
- Confirmed Commitment
- In Progress
- Implemented
- Implemented and Verified

`Implemented and Verified` requires repository evidence plus proportionate build, test, fixture, or runtime evidence.

## Development cycle

For material changes:

1. Inspect existing code and overlapping concepts before creating new types or systems.
2. Confirm the intended behavior and safety implications.
3. Implement on an appropriate branch.
4. Add or update tests/fixtures.
5. Run proportionate verification.
6. Update affected documentation in the same cycle.
7. Record limitations, known risks, and unverified assumptions.
8. Merge only after the change meets the intended quality/safety bar.

## Device DNA rule

Search existing repository concepts such as Device DNA, DeviceDNA, capability map, device profile, and detection logic before introducing new names or duplicate models. Consumers should use the authoritative profile rather than independently guessing the same facts.

## Guardian rule

Any feature capable of modifying firmware, devices, partitions, boot state, security-sensitive configuration, recovery state, or user data must define the Guardian authorization/readiness path.

## Documentation rule

Update the appropriate docs when changing:

- product purpose or scope
- architecture/subsystem boundaries
- feature commitments/status
- UI/navigation/terminology
- Guardian behavior
- roadmap order
- prerequisites/build steps
- branching/development process
- versioning/release process

## Secrets and local configuration

Never commit real credentials, tokens, API keys, signing/private keys, certificates, production secrets, sensitive device/user data, or populated `.env` files.

Document required configuration names and setup procedures, not secret values.

## Cross-machine continuity

Avoid undocumented absolute paths, machine-only assumptions, hidden local dependencies, or tooling that cannot be reconstructed from repository documentation. When a local-only dependency is unavoidable, document exactly how to obtain or recreate it safely.

## Handoffs

A development handoff should separate:

- confirmed decisions
- implemented/verified work
- in-progress work
- blockers/unproven claims
- tests performed
- superseded decisions

This helps ROMVERSE development continue accurately across PCs, sessions, and tools.
