# Forge Bundle

Forge Bundle is ROMVERSE's first real, reproducible ROM Studio output. It packages the exact
contents of a verified isolated working tree into a content-addressed ZIP while preserving the
protected original outside the archive.

It is deliberately an intermediate artifact—not a ROM that can be flashed.

## Safety contract

Every embedded manifest and external receipt states:

- protected original included: false
- signed: false
- bootable: false
- flashable: false
- phone changed: false

ROMVERSE refuses creation when the build plan is missing, the file set changed, a source path is
unsafe, a symbolic link is present, or an input changes while it is being copied.

## Reproducibility

- Inputs are ordered exactly as frozen in the deterministic build plan.
- ZIP timestamps and Unix permissions are fixed.
- Files are stored without compression to avoid platform-specific compressor output.
- The manifest records each relative path, byte size, and SHA-256.
- The final archive is named from its own SHA-256.
- Repeating the operation with unchanged inputs produces the same archive hash and output path.

## Verification

Verify Forge Bundle re-checks:

1. the content-addressed archive SHA-256;
2. the bounded embedded manifest and its SHA-256;
3. project identity and the build-plan tree fingerprint;
4. the exact archive member set with no duplicates or symbolic links;
5. every member size and SHA-256; and
6. the explicit non-flashable safety contract.

The latest receipt is stored at
`projects/<project-id>/latest-forge-bundle.romverse`, and the archive is stored under
`builds/<project-id>/`.

Signing, boot-image assembly, device-specific compilation, and flashing remain separate Guardian
gates and are not implied by a successful Forge Bundle.
