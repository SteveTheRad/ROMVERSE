# Building ROMVERSE

## Goal

This document must evolve into the authoritative machine-setup and build guide for ROMVERSE. The long-term requirement is that a developer can clone the private repository onto another supported computer, restore the required non-secret configuration safely, install the documented toolchain, build the project, run tests, and continue development without depending on one specific PC.

## Current state

The repository documentation baseline is being established before the full source tree and exact toolchain are available here. Therefore, this file intentionally does **not** invent package versions, SDK paths, build commands, signing procedures, or platform prerequisites that have not yet been verified from the real project.

## Required contents as implementation lands

Keep this file updated with:

- Supported development operating systems.
- Required runtimes, SDKs, compilers, package managers, and exact supported versions.
- Android SDK/ADB/Fastboot requirements where applicable.
- Desktop UI/framework prerequisites.
- Required third-party ROM tooling and how ROMVERSE resolves or installs it.
- Repository clone instructions.
- Dependency installation commands.
- Local configuration steps.
- Required environment variable **names only** and their purpose.
- How to obtain/store secrets securely without committing them.
- Build commands for development and release configurations.
- Test commands.
- Lint/static-analysis commands.
- Packaging commands.
- Companion build/install procedure.
- Any platform-specific notes for Windows and Linux development.
- Troubleshooting for common setup/build failures.

## Secret handling

Never place real passwords, API keys, access tokens, private/signing keys, production credentials, certificates, or sensitive values in this repository.

Use secure local secret storage or the approved deployment secret mechanism. Documentation may include placeholders such as:

```text
ROMVERSE_API_BASE_URL=<configured value>
ROMVERSE_SERVICE_TOKEN=<stored securely; never commit>
```

Do not include the real value.

## Machine migration checklist

When the real build process is fully documented, a migration to a new machine should be verifiable by performing a clean-room setup:

1. Clone the private repository.
2. Install documented prerequisites.
3. Restore required non-versioned secrets/configuration from secure storage.
4. Run dependency/tool verification.
5. Build the desktop application.
6. Build the Companion if applicable.
7. Run the documented test suite.
8. Launch the application in a safe development configuration.
9. Confirm critical development workflows and local paths are not tied to the previous computer.

A setup is not considered portable until this has been demonstrated successfully on a second clean development environment.
