# Windows Recovery trusted-launch contract

## Status and scope

This contract defines the Windows anti-TOCTOU boundary behind the existing Guardian Recovery
process-runner protocol. It is a software correctness boundary only. It does not enroll a production
adapter, grant execution authority, connect to a phone, enable physical Recovery, or claim hardware
or release verification.

The approved implementation is `WindowsSubprocessRecoveryAdapterProcessRunner`. Callers provide
only a previously verified package, canonical request bytes, and a bounded timeout. They cannot
provide an executable path, command, arguments, working directory, environment, retry policy, or
bootloader action.

## Preconditions

Before process creation, the launcher must fail closed unless all of these remain true:

- the host is CPython `win32` on Windows and the package platform is exactly `windows-x86_64`;
- the release signature, signer identity, manifest, package digest, adapter identity/version,
  protocol/schema versions, action allowlist, artifact filename, byte length, and SHA-256 revalidate;
- the artifact is the exact `.exe` named by the signed manifest;
- every component of the artifact path is non-reparse and the artifact is one regular file with a
  single hard-link identity;
- a Windows handle is opened without following the final reparse point and denies write/delete
  sharing while allowing read sharing;
- the opened handle identity, link count, length, write/create timestamps, and path time remain
  unchanged while the bytes are hashed;
- the path still names that exact open handle immediately before process creation;
- request size is 1–65,536 bytes and timeout is an integer from 1–3,600 seconds.

The verified handle remains open through process creation. Because it denies write and delete
sharing, the verified path cannot be rewritten, renamed away, or replaced between the final identity
check and launch. Any sharing conflict or unverifiable state stops before dispatch.

## Fixed launch surface

The launcher executes exactly:

`<signed-artifact.exe> --romverse-recovery-protocol 1`

It uses no shell, inherits no caller file descriptors, creates no visible console, and passes only a
fixed environment containing the Windows directory as `SystemRoot`/`WINDIR` plus `LANG=C` and
`LC_ALL=C`. The Windows directory is resolved through the operating-system API, not caller input.

The production trust boundary accepts only the exact platform launcher class. A Windows production
package cannot use the Linux launcher or an injected/fake runner. Test-only trust remains explicitly
separate and is used only by deterministic tests.

## Bounded protocol result

- Standard input is the canonical request and is written once.
- Standard output and standard error are independently capped at 65,536 bytes and drained
  concurrently.
- Timeout kills the direct adapter process and produces an uncertain result.
- Start failure is returned once; the launcher never retries automatically.
- Timeout, truncation, start failure, malformed JSON, duplicate/extra/missing fields, non-canonical
  JSON, wrong request/package/signer/action identity, contradictory process facts, or ambiguous
  output can never become success. Post-dispatch ambiguity becomes `UNKNOWN`.

Raw output and return code are evidence inputs only. They do not grant execution, Recovery success,
repair, verification, retry, release, or publication authority.

## Permanent safety invariants

- `automatic_retry_allowed` is always false.
- `bootloader_relock_allowed` is always false.
- Lock/relock action identifiers are rejected before the process runner is called.
- Guardian remains the only higher-level admission boundary.
- Production adapter enrollment and physical Android verification remain separately reviewed gates.

## Deterministic evidence

`tests/test_guardian_recovery_windows_launcher.py` uses inert local artifacts and fake process
objects only. It covers exact package/artifact binding; hash and size drift; reparse, path,
hard-link, identity, and timing substitution; wrong platform/launcher; bounded request/output and
timeout behavior; malformed results becoming `UNKNOWN`; one-attempt behavior; absence of caller
command authority; and permanent bootloader-relock rejection.

Passing those tests is Windows-hosted software evidence when run on Windows. It is not a real
Recovery command, phone operation, production-adapter verification, or physical-device evidence.
