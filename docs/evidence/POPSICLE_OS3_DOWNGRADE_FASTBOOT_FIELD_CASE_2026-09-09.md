# Xiaomi `popsicle` OS3 downgrade and Fastboot transport field case

## Classification

- Evidence class: ROMVERSE-verified, one-device field outcome.
- Observation date: 2026-09-09 (Australia/Brisbane).
- Device scope: Xiaomi 17 Pro Max, product/codename `popsicle`.
- Observed transition: customized HyperOS 4 `OS4.0.0.32.XPBCNXM`, Android 17, to Xiaomi.eu `OS3.0.319.0.WPBCNXM`, Android 16.
- Validated installation scope: active slot A only. Slot B was not refreshed or validated.
- Outcome: the user explicitly confirmed that Android booted successfully.
- Execution authority: none. This record is evidence for diagnosis and planning; Guardian must independently authorize any future device action from fresh exact-target, exact-package, consent, and recovery evidence.

No device serial is retained in this record.

## Integrity-bound source artifacts

The private originals remain outside the repository. These digests bind this redacted case to the reviewed evidence without publishing a device identifier.

| Artifact | SHA-256 |
|---|---|
| Engineering report | `edaca784c521b5cc2ba01ce9428501a820f4491322184c48225480f056727594` |
| Redacted command/result transcript | `8ed2712d5df930cd5fff1794f4725b2bc743fa23411062e7f68239723d997e64` |
| Bounded helper source | `0f19f4193a76943de9ac3cc40de58aef6e628a670a3e3962a03e73ea7b42dfa1` |
| Reviewed helper binary | `a7e8849449bfe75b063fd0a509276af59cec6127554eb604e18967cb2b983a2c` |
| Per-image SHA-256 manifest | `dfa1cfe2b9500fb0edf706e05c5bd35ad7258c9d7a4903af830aae501a6fa335` |

## Confirmed write and cleanup outcome

The redacted transcript contains exactly 63 successful writes in the package-prescribed order:

- 49 ordinary firmware and boot images: `abl`, `aop`, `aop_config`, `bluetooth`, `cpucp`, `cpucp_dtb`, `dcp`, `devcfg`, `dsp`, `dtbo`, `featenabler`, `hyp`, `hyp_ac_config`, `idmanager`, `imagefv`, `keymaster`, `modem`, `modemfirmware`, `multiimgqti`, `pdp`, `pdp_cdb`, `pvmfw`, `qtvm_dtbo`, `qupfw`, `secretkeeper`, `shrm`, `soccp`, `soccp_dcd`, `soccp_debug`, `spuservice`, `tme_config`, `tme_fw`, `tme_seq_patch`, `tz`, `tz_ac_config`, `tz_qti_config`, `uefi`, `uefisecapp`, `vbmeta`, `vbmeta_system`, `vm-bootsys`, `xbl`, `xbl_ac_config`, `xbl_config`, `xbl_ramdump`, `boot`, `init_boot`, `vendor_boot`, and `recovery`.
- 14 Android sparse pieces, `super.img.0` through `super.img.13`, written to `super` in numeric order.

Only after all 63 writes had explicit success results and product `popsicle` plus current slot `a` were revalidated:

- `metadata` erase returned `OKAY`.
- `userdata` erase returned `OKAY`.
- reboot returned `OKAY`.

This was a full wipe. ROMVERSE must not infer that prior user data, Android Auto configuration, Gboard configuration, or any other user integration survived.

## Diagnosed standard-client failure

The normal Fastboot client was preferred first but was unreliable for this exact device/package/host interaction. Observed failures included:

- aggregate `_ab` targets reporting `Device does not support slots`;
- partition size reported as zero;
- `Invalid argument size`;
- failure of the higher-level partition-size and slot-query path even when an unsuffixed target was attempted.

These symptoms do not prove that another `popsicle`, host, cable, tool version, or firmware package requires the fallback.

## Confirmed protocol quirk

For a 335,872-byte `abl` image, the bootloader's fixed 12-byte Fastboot response `DATA00052000` arrived as two USB reads: `DATA000520` followed by `00`. A single-read parser misread the six visible hex digits as 1,312 bytes and stopped before sending the image.

The successful parser behavior was:

1. Reassemble the complete fixed 12-byte `DATA%08x` response across USB reads.
2. Parse exactly eight hexadecimal length digits.
3. Require the accepted length to equal the verified input byte count.
4. Stop on malformed, short, oversized, or mismatched responses.

This is reusable Fastboot protocol evidence, but the need for this fallback is presently verified only for the exact field case above.

## Staged-state and timeout evidence

An early `aop` attempt used 1 MiB chunks and a short timeout. The host sent all 389,120 bytes but timed out before the download-complete `OKAY`. The helper had not sent `flash:aop`, so this failed attempt did not write `aop`.

The successful fallback used:

- 64 KiB USB chunks;
- 120-second command and data-completion timeouts;
- binding to one exact USB serial in memory while omitting it from persistent logs;
- Google Fastboot USB VID:PID `18d1:d00d` only;
- explicit stage reporting that distinguished command accepted, bytes sent, download complete, `flash:<partition>` sent, and final write result;
- unsuffixed `flash:<partition>` only after selecting and verifying active slot A.

The helper intentionally supported only `getvar`, `set-active a`, and `flash PARTITION IMAGE`. It contained no erase, format, slot-B, unlock, relock, script, or arbitrary-command capability.

## Failure-state rule

- Before `flash:<partition>` is sent, evidence can establish that the target partition was not written.
- After `flash:<partition>` is sent, loss of a trustworthy final result is `UNKNOWN`.
- `UNKNOWN` must stop advancement. It does not authorize an automatic retry.
- A possible later retry requires fresh exact-target observation, investigation of the uncertain state, unchanged verified input, a recovery assessment, and a newly governed decision for that exact step.

This corrects the field report's informal “retry the same partition” wording to ROMVERSE's stronger global rule: no blind retry on uncertainty.

## USB recovery observation

For kernel USB errors `-71` and `-110`, the successful physical recovery was to disconnect USB, hold Power for about 20 seconds, immediately enter FASTBOOT with Volume Down, and reconnect through a different direct rear motherboard USB port with a known-good cable. This is a diagnostic recovery observation, not proof that every `-71` or `-110` event has the same cause.

## Durable safety boundaries

- Prefer current official/standard Fastboot when its exact-device behavior is normal.
- Never generalize this fallback from a marketing name alone.
- Require exact `popsicle` identity, exact firmware/package hashes, observed slot, unlock state, rollback constraints, partition map, complete recovery material, and fresh consent before any future write authority is considered.
- Preserve package order and fail closed after every step; never run a non-fail-fast vendor/community script as one opaque consequential action.
- Do not erase `metadata` or `userdata` until every required write has a durable exact-success result and the exact product/slot are freshly revalidated.
- Never lock or relock the bootloader.
- Never imply that slot B was updated or is safe to activate.
- A successful boot is one observed outcome, not universal compatibility proof.
