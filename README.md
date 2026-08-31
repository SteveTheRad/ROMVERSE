# ROMVERSE

> **Private proprietary software.** This repository is not open source and is intended only for authorized ROMVERSE development.

**Build. Optimize. Perfect.**

ROMVERSE is a software project focused on providing a polished, dependable platform for Android ROM building, diagnostics, customization, recovery preparation, and controlled flashing.

## Authoritative project source

This private repository is the authoritative technical source of truth for ROMVERSE development. Alongside source code, it must maintain enough architecture, product, setup, workflow, roadmap, release, and implementation context that development can be resumed on another correctly configured computer without depending on one particular PC.

A planned, approved, or designed feature is not automatically implemented. Work is only considered **Implemented and Verified** after repository inspection plus proportionate build, test, or runtime evidence.

## Project status

ROMVERSE is under active private development. Product internals, implementation details, security-sensitive design information, private roadmaps, credentials, signing material, and unpublished technical documentation must not be committed to public repositories or shared outside authorized project channels.

## Current source baseline

The repository now contains the Python/PySide6 desktop application, native Kotlin Android
Companion, tests, build scripts, Device Packs, Guardian safety domains, ROM workspace domains, and
the maintained private documentation.

The isolated Ubuntu migration baseline passed 956 Python tests, Ruff lint/format checks, wheel
build and installed-package smoke, Companion JVM tests, and debug APK assembly. This does not prove
Windows, physical-device, production-service, release-signing, or flashing behavior. See
[`docs/FEATURES.md`](docs/FEATURES.md) for status and verification scope.

## Quick start

```bash
git clone git@github.com:SteveTheRad/ROMVERSE.git
cd ROMVERSE
./scripts/bootstrap.sh
source .venv/bin/activate
romverse
```

See [`docs/BUILDING.md`](docs/BUILDING.md) for Linux, Windows, packaging, Companion, optional ROM
tools, local configuration, and clean-machine migration.

## Repository policy

- `main` contains the stable project baseline.
- `develop` is the integration branch for ongoing development.
- New work should use short-lived `feature/<name>` branches from `develop`.
- Bug fixes should use `fix/<name>` branches from `develop`.
- Release preparation may use `release/<version>` branches when needed.
- Emergency production fixes may use `hotfix/<name>` branches from `main`.
- Merge work through pull requests where practical; avoid direct feature development on `main`.
- Keep this repository private and do not expose proprietary ROMVERSE internals publicly.

## Documentation

The maintained private technical documentation lives under [`docs/`](docs/):

- `PRODUCT_VISION.md` — product purpose, principles, scope, and commercial direction.
- `ARCHITECTURE.md` — major subsystems, relationships, data flows, and architectural rules.
- `FEATURES.md` — feature inventory and implementation-status discipline.
- `UI_UX.md` — visual identity, interaction principles, desktop/Companion UX decisions.
- `GUARDIAN.md` — Guardian safety model, authorization gates, and non-negotiable protections.
- `ROADMAP.md` — ordered development priorities and milestones.
- `BUILDING.md` — prerequisites, setup, build, test, and machine-migration instructions.
- `DEVELOPMENT.md` — branching, commits, testing, review, documentation, and handoff workflow.
- `RELEASES.md` — versioning, release process, verification, and release history.

These documents should evolve with the code. Material technical or product decisions should be reflected in the appropriate file rather than existing only in chat history or on one developer machine.

## Current development priority

Firmware detection → Device DNA → ROM Studio workspace → required tool resolution → extraction → modification/debloat → build validation → Guardian Readiness → local backup → controlled Guardian Flash.

## Security and confidentiality

Never commit passwords, API credentials, access tokens, signing/private keys, certificates, production secrets, customer/user data, sensitive device identifiers, generated secrets, `.env` files containing real values, or machine-local credentials.

Use environment variables or an approved secret-management mechanism for sensitive values. Repository documentation may describe required secret names and setup procedures, but never their real values. If a secret is committed accidentally, treat it as compromised and rotate it immediately rather than relying on commit deletion alone.

## Local development

Machine-specific configuration must remain outside version control. `docs/BUILDING.md` and related setup material should eventually provide enough information to clone the repository onto a supported development machine, restore required tooling/configuration safely, build ROMVERSE, run its tests, and continue work.

## Ownership

ROMVERSE — Created by SteveTheRad — A RadForge Labs Project.

Copyright © ROMVERSE. All rights reserved.

This codebase and its associated materials are proprietary and confidential. No permission is granted to copy, redistribute, sublicense, publish, reverse engineer, or reuse the software except where explicitly authorized in writing.
