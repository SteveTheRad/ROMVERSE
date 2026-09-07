# ROMVERSE Product Assurance

## Reviewed checkpoint: 08aaa64

- Handoff commit: `08aaa6489608ff73acb3c08224ddb071a97784c2`
- Prior Product Assurance authorization:
  `972ab5a5b62ded74846cdec2cdf8e5465b60a00d`
- Title: `Record Companion emulator launch blocker`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — EXTERNAL HOST-RUNTIME BLOCKER VALIDATED; ONE HOST-GPU ATTEMPT AUTHORIZED**

### Decision

Build complied with the exact failure-stop requirement. The approved application and
instrumentation APKs were not installed or executed, no Android target was admitted, no ROMVERSE
source or configuration changed, and no physical device was connected. The two failures occurred
inside Android Emulator 37.1.11's rendering process before Android boot and therefore do not count
as a ROMVERSE application or instrumentation failure.

Product Assurance independently confirms the abnormal terminations and the immediately preceding
Fedora SELinux denials. The current evidence supports an external emulator/host-policy
incompatibility classification, but not a conclusive root cause. Runtime verification remains
outstanding and no pass claim is permitted.

One minimum, bounded remediation is approved: run the existing clean AVD once with the current
official emulator's visible window and host GPU renderer. This exercises the available AMD/Mesa
graphics path instead of the two failed headless software-rendering paths. It must not weaken the
host or guest security posture and must stop on any pre-ADB failure.

### Independent repository and host evidence

- The handoff commit changes only `docs/sync/BUILD-STATUS.md` and descends from the approved
  `972ab5a` checkpoint.
- The dedicated Linux worktree is clean and exactly matches
  `origin/linux/stage1-desktop-readiness` at `08aaa64` before this review.
- The protected original-checkout Companion changes and old Windows launcher drafts remain
  isolated and untouched.
- Android Emulator identity independently confirmed:
  `37.1.11.0`, build `15917651`.
- Current host: Fedora 44, kernel `7.1.13-200.fc44.x86_64`, SELinux enforcing, KVM available.
- Available graphics include AMD Radeon RX 9070/9070 XT/9070 GRE and integrated Radeon graphics,
  both using the `amdgpu` driver; the active desktop session is Wayland with an X display also
  available.

### Independent failure-evidence verification

System coredump metadata independently confirms:

- PID 178629: `qemu-system-x86_64-headless`, exact `romverse_api35_clean` launch with
  `-gpu swiftshader_indirect`, terminated by SIGSEGV; retained coredump 351.3 MiB.
- PID 179962: `qemu-system-x86_64-headless`, exact clean launch with `-gpu off`, terminated by
  SIGSEGV; retained coredump 353.2 MiB.
- Both failures occurred in `RenderThread` before any ADB-visible target appeared.
- The Fedora audit journal records repeated enforcing-mode `{ execheap }` denials for the exact
  process immediately before each abnormal termination.
- The second coredump loaded Lavapipe/LLVM rendering modules despite `-gpu off`, explaining why
  that attempt did not establish an independent hardware-rendering path.

No finding authorizes disabling SELinux, changing SELinux enforcement, adding an allow rule,
granting executable-heap permission, or treating the denial as a ROMVERSE defect.

### Evidence integrity and safety judgment

- The application APK remains exactly
  `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`.
- The instrumentation APK remains exactly
  `ec6776528384b26c29b748299f80285474cc64ed40fe2b2519efa6b4040a86b5`.
- Instrumentation result remains **0 run / 0 pass / 0 fail / 0 skip**.
- No static or packaging result may be substituted for missing runtime evidence.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, and independent verification remain unchanged.
- Bootloader locking and relocking remain permanently prohibited with no override.
- The pre-v1.0 feature freeze is preserved.

### Minimum acceptance criteria for the approved attempt

1. Revalidate both approved APK hashes and confirm `adb devices -l` reports no target before launch.
2. Use the existing isolated toolchain, exact API-35 AVD, port 5556, clean wiped data, no snapshot,
   no audio, no metrics, and **one visible-window `-gpu host` launch**. Do not use `-no-window`,
   SwiftShader, Lavapipe, GPU-off, or a second renderer variant in this task.
3. Keep SELinux enforcing. Do not change host policy, create an allow rule, set permissive mode,
   grant executable-heap authority, use a container to evade policy, or modify the emulator or
   system image.
4. If the emulator fails before one exact ADB target becomes available, preserve the exact command,
   logs, journal evidence, and any coredump, confirm no target remains, and return immediately for
   Product Assurance. Do not change ROMVERSE or try another emulator revision.
5. If it boots, require exactly one unambiguous `emulator-5556` target and reject every physical,
   simultaneous, unauthorized, or changing target. Revalidate the APK hashes immediately before
   installation.
6. Install only those two exact debug APKs, run the exact
   `com.radforge.romverse.companion.test/androidx.test.runner.AndroidJUnitRunner` suite, and record
   the complete runner output and honest pass/fail/skip count.
7. Launch the application and capture readable visible-window evidence of the existing branding,
   Guided shell, navigation, privacy curtain, and Guided/Expert continuity already covered by the
   packaged tests. Do not change the app to obtain a pass.
8. Confirm that no phone, Recovery adapter, production trust, production signing, device mutation,
   publication, release, protected-file change, or platform merge occurred.

### Approved next bounded task

Perform exactly the one host-GPU emulator attempt defined above. A successful boot may continue
directly through installation, all 12 existing instrumentation tests, application launch, and the
bounded visible smoke in the same isolated emulator session. A pre-ADB launch failure, ambiguous
target, APK mismatch, test failure, or runtime failure ends the task and requires a new Product
Assurance checkpoint before any further remediation.

Update `docs/sync/BUILD-STATUS.md`, commit and push the exact checkpoint on
`linux/stage1-desktop-readiness`, then stop for independent Product Assurance review.

### Gate status

- v0.2 Golden Foundation: **CLOSED**
- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Companion debug and instrumentation APK artifact readiness: **VERIFIED**
- Companion emulator runtime verification: **OUTSTANDING; ONE HOST-GPU ATTEMPT AUTHORIZED**
- Companion physical-device verification: outstanding; not authorized
- Windows runnable development build and inert journey: separate Windows track
- Production Recovery, signing, publication, and release: outstanding and not authorized
