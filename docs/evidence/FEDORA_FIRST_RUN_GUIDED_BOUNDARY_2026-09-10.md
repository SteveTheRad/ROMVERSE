# Fedora first-run setup to Guided Command Deck boundary

## Scope

- Authoritative approved base:
  `9f2bf11eca9b5f13859d66b43c1a79c8e9f928a8`.
- Corrected unsigned package: `build/fedora-asset-boundary-v2/ROMVERSE`.
- Executable: **6,337,072 bytes**, SHA-256
  `4fbfed3244d93ba535413151c26f5fe53ef526d402f638a5e81e662f8b562500`.
- Fresh private disposable root: `/tmp/romverse-linux-first-run-yjli68`, mode `0700`.
- Before first launch, the new profile contained only a mode-`0600` settings file with onboarding
  incomplete, Guided selected, online/community intelligence disabled and automatic verified-tool
  acquisition disabled. Its SHA-256 was
  `90b3cac99a99821e3a6e57ff5bf4b187c6d55a2163e5b87b649dca1440f9fd10`.
- The process-local `PATH` named an empty private directory. The package ran inside a Bubblewrap
  network namespace different from the host namespace; its network inventory contained only a
  zero-byte loopback interface. No phone, emulator or development device simulation was present.

## Product-as-user journey

1. The genuine packaged first-run dialog opened as **Welcome to ROMVERSE** and identified the
   current build as **0.2.0-alpha.1 • INTERNAL DEVELOPMENT**.
2. The dialog explained that no phone is required and that setup cannot scan, flash, unlock,
   reboot, install, delete or modify a phone.
3. Tool readiness truthfully reported **Host tools ready: 1 of 21**. Python 3.14.7 was the only
   ready item; ADB, Fastboot and all other optional host tools were explicitly not ready.
4. The complete bounded inventory exposed exactly these 21 readable rows: Python, ADB, Fastboot,
   Git, 7-Zip, Unzip, LZ4, simg2img, EXT4 Browser, AVBTool, Payload Dumper, Make, Java, EROFS
   Builder, EROFS Verifier, LP Make, LP Unpack, LP Dump, Fakeroot, AAPT2 and APK Signer. Every row
   was present in the accessibility tree with its readiness explanation.
5. **Browse…** and **Continue in Guided Mode** remained showing and enabled while the bounded tool
   inventory was present. No browse, manual-source, download or installation action was invoked.
6. The default selected workspace was the new disposable profile's
   `/tmp/romverse-linux-first-run-yjli68/data/workspace`. The existing
   **Continue in Guided Mode** action was invoked exactly once.
7. The first-run dialog transitioned directly to the genuine Command Deck page. It reported
   **DEVICE: NOT CONNECTED • PROJECT: NONE • MISSION: IDLE • GUARDIAN: VERIFY REQUIRED** and
   truthfully explained that verified Android Platform Tools were not active.

## Durable evidence and limits

- Acceptance persisted a mode-`0600`, 664-byte settings file with onboarding complete, Guided
  retained, the exact disposable workspace path, online/community intelligence still disabled and
  automatic verified-tool acquisition still disabled. Its SHA-256 is
  `a309b915233ee9db53f175beb611041683fb7d63c024cebfe0c9dc6bc2d525e2`.
- The new 431-byte workspace marker has SHA-256
  `a3b88e6c6c23d9d3e232b936394fbba856c2adc962f65abb063c8bd2e0262838`.
- The corrected package created its packaged **880,760-byte** offline archive, SHA-256
  `2384ebb6ce9616af2270991da2c7b594d08b7534e71bf819549c92c091e27764`. No external device
  catalog or other network content was fetched.
- Workspace initialization created a local ROMVERSE Link certificate and mode-`0600` private key.
  Neither was opened, transmitted or used for device, build, Guardian, Recovery or execution
  authority.
- The workspace contains no project manifest, Activity JSONL record, Guardian ledger, Recovery
  incident/result, device evidence, installation plan or managed tool. The `tools` directory is
  empty; Activity and Live Console contain only empty lock files.
- No Stage 1 setup-transition defect was reproduced, so no application, test, package, Companion,
  Windows, Device Intelligence, Guardian, Recovery or adapter source changed and no rebuild was
  performed.
- The earlier **56/56** focused package/knowledge regression remains the source baseline and was
  not rerun or double-counted. This checkpoint adds one genuine packaged Fedora first-run runtime
  acceptance journey.
- Fedora accessibility again exposed no compositor-owned close action. After the completed inert
  transition and final evidence inspection, the exact disposable ROMVERSE process received
  `SIGTERM`, exited 143 and left only its runtime start marker. **No clean-shutdown or restart-
  persistence claim is made.** GNOME toolkit accessibility was restored to its original disabled
  state.
- **Implemented:** evidence-only checkpoint; production and test bits are unchanged.
- **Simulated/Tested:** genuine corrected-package first-run UI transition using a fresh disposable
  profile, no network, no phone/emulator and no Android device simulation.
- **Hardware Verified:** no.
- **Released:** no. The package remains unsigned, local and unpublished.
- No network request, tool/catalog/dependency download, installation, PATH mutation by ROMVERSE,
  phone/emulator operation, ADB/Fastboot invocation, APK/firmware operation, Guardian/Recovery
  execution, flash, wipe, unlock/root, lock/relock, signing, publication, release, hosted CI or
  Forgejo Action occurred. Guardian-only authority, exact evidence, durable `UNKNOWN`, no blind
  retry, independent verification and permanent no-relock remain unchanged.
