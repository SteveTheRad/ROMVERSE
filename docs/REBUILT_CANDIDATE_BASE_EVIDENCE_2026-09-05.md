# Rebuilt-candidate base-image evidence — 2026-09-05

## Result and scope

All **48 required unchanged base images** in the recognized custom OS4.0.0.23
package match the same-named OS4.0.0.23 OTA `new_partition_info` **size and
SHA-256**. These are the 47 physical images declared by
`POPSICLE_PHYSICAL_PARTITIONS` in `src/romverse/rom/source_installation.py`, plus
the stock root `vbmeta` image.

Every package image was freshly stream-hashed. Every measured hash also matched
the custom package's `SHA256SUMS`. There were **zero missing partitions, zero
size mismatches, zero hash mismatches, and zero package-checksum mismatches**.
The total freshly hashed image content was **857,538,560 bytes**.

This supplies concrete base-image equivalence evidence for a future composition
of the existing verified local rebuild with this installation procedure. It is
**not an implemented candidate-composition route, a flash compatibility
certificate, production certification, physical boot proof, or completion of
Stage 1**. No source/runtime/test files were changed by the measurement. This
document is a subsequently authorized record of the result.

## Exact sources and existing project contract

The bounded measurement used only these two existing protected archive files:

- OTA: `/run/media/stevetherad/Data/ROMVERSE-Recovered-2026-09-01/workspace/original_roms/a58f2f3b876283d8-popsicle-ota_full-OS4.0.0.23.XPBCNXM-user-17.0-44eb547903.zip`
- Custom package: `/run/media/stevetherad/Data/ROMVERSE-Recovered-2026-09-01/workspace/original_roms/adbb99b9d6e6c3e6-HyperOS4-Xiaomi17ProMax-Debloated-CustomRom.zip`

The custom package's exact image-member prefix is:

`outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/images/`

Its checksum member is:

`outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/SHA256SUMS`

The OTA's metadata members are `payload.bin`, `payload_properties.txt`, and
`META-INF/com/android/metadata`. The package's `BUILD-INFO.txt` declares the same
base version, Android 17, security patch 2026-08-01, slot A, and a stock signed
root with a custom unsigned `vbmeta_system`. Those text declarations are context;
they were not substituted for the per-image comparison below.

The existing packaged build contract is
`popsicle-os4.0.0.23-product-super` in
`src/romverse/assets/device_packs/xiaomi-popsicle-hyperos4.json`. It binds an OTA
project's protected original to OS4.0.0.23.XPBCNXM. This measurement did not create
or use a live workspace project, create a build receipt, or assign a project ID.
A future composed installation must bind its actual build project and procedure
source separately rather than treating these different archives as one source.

### Previously recorded identifiers, not freshly rehashed whole files

| Object | SHA-256 | Basis in this audit |
| --- | --- | --- |
| OTA archive | a58f2f3b876283d88031acbb18859b6b8a19212d9c214d4dc06c6ceb01d45c55 | Existing exact build-contract value; whole archive not rehashed in this measurement |
| OTA payload | b614dabafabff794177e24f5ae3f3ef251043527122f2b6e4da535d6473155c4 | Existing exact build-contract value; whole payload not rehashed in this measurement |
| Custom package archive | adbb99b9d6e6c3e62520c144d8b841ff6f34543feddf2969cfc38f4acf90f89a | Previously fully streamed and verified during the protected-source audit; not repeated here |
| Recognized complete `flash_all.sh` | 589afffba7bc1e3528f936caeb9fe3bfd43da8d4017d0b5d4562c6f9e2be41ac | Existing reviewed adapter/fixture identity; script not executed or rehashed in this measurement |

The preceding custom-package audit also verified all source-manifest member
hashes through the production source parser. That prior result is distinct from
the fresh, specifically scoped 48-image comparison recorded here.

## Fresh measurement method

1. Opened the OTA with Python's ZIP reader and read only the payload header,
   manifest, and metadata-signature bytes. No OTA image operation blobs were
   read or reconstructed.
2. Passed those bounded bytes through an anonymous in-memory file to the existing
   installed Payload Dumper's read-only partition-list mode. It listed the 58
   partitions and their sizes. Its public CLI does not expose partition hashes;
   ROMVERSE's existing `PayloadService` retains extracted-image hashes, not these
   declared expected hashes. No local `protoc`, Python protobuf runtime, or
   generated update-metadata schema module was available in the scoped source,
   tools, and checked Python environments.
3. Used an explicitly authorized one-off read-only protobuf wire decoder to
   retrieve the schema-defined partition names, expected sizes, and expected
   hashes. The decoder was transient analysis code, not added to the application
   or installed as a runtime parser.
4. Verified the SHA-256 of the complete header plus manifest against the
   base64-decoded `METADATA_HASH` in `payload_properties.txt`, and checked its
   length against `METADATA_SIZE`.
5. Opened each of the 48 exact custom-package image members and streamed all
   bytes in 1 MiB chunks through SHA-256. Compared actual byte count and digest
   with both the OTA declaration and the corresponding package checksum entry.
   Reading each entire ZIP member also completed the ZIP reader's CRC check.

The decoder accepted only major-version-2 payload framing, bounded the manifest
to 2 MiB and metadata signatures to 64 KiB, and decoded only three nested message
levels. It bounded partition count to 256, field count per message to 300,000,
varints to uint64, names to a restricted 64-character partition grammar, and
expected image sizes to 128 GiB. It checked required fields, duplicate selected
fields, wire types, length boundaries, and 32-byte hashes; unsupported protobuf
group wire types were rejected. It found no old-partition dependency, required
full-payload minor version 0, and rejected a partial-update declaration. These
are the bounds used for this measurement, not a claim of a shipped or
adversarially certified protobuf parser.

Package handling rejected duplicate normalized ZIP member names, absolute or
parent-traversing paths and backslashes. The checksum member was bounded to
1 MiB, checksum names were normalized consistently, and duplicate checksum
entries were rejected. Each selected physical/root image was bounded to
512 MiB; measured bytes could not exceed the ZIP member's declared size.

### Schema provenance

Field meanings were grounded in the previously inspected primary
[AOSP `update_metadata.proto`](https://android.googlesource.com/platform/system/update_engine/+/refs/heads/main/update_metadata.proto):

| Message | Field | Wire type / meaning used |
| --- | --- | --- |
| `DeltaArchiveManifest` | 12, `minor_version` | uint32; 0 denotes a full payload |
| `DeltaArchiveManifest` | 13, `partitions` | Repeated length-delimited `PartitionUpdate` |
| `DeltaArchiveManifest` | 16, `partial_update` | Boolean; false here |
| `PartitionUpdate` | 1, `partition_name` | String |
| `PartitionUpdate` | 6, `old_partition_info` | Presence would reject this full-source measurement path |
| `PartitionUpdate` | 7, `new_partition_info` | Length-delimited `PartitionInfo` |
| `PartitionInfo` | 1, `size` | uint64 expected complete-image byte size |
| `PartitionInfo` | 2, `hash` | Bytes; all retrieved values were 32-byte SHA-256 digests |

The protobuf partition records provide image identity, not Fastboot partition
selection, slot selection, wipe rules, or an installation command sequence. The
recognized source script remains the separate origin of those instructions.

### Fresh metadata results

| Measurement | Result |
| --- | --- |
| Magic / major version | `CrAU` / 2 |
| Header bytes | 24 |
| Manifest bytes | 333,638 |
| Metadata signature bytes read | 267 |
| Header plus manifest / `METADATA_SIZE` | 333,662 bytes |
| Header plus manifest SHA-256 | c710c43f9851227bae4be196340dd29a516889b4d500a2e158d0b1d3b636ca5a |
| Matches `METADATA_HASH` | Yes |
| Minor version | 0, full payload |
| `partial_update` | False |
| OTA partition count | 58 |
| Required unchanged-image count | 48 |
| Exact size-and-hash matches | 48 |
| Missing or mismatched required images | None |

The signature bytes were read only to keep the bounded metadata framing
complete. **Their cryptographic signatures were not verified.** The metadata
hash and its expected value came from the same current ZIP; this is an internal
integrity check, not independent publisher authentication or a fresh whole-OTA
identity check.

## Complete 48-image comparison

Every row is **MATCH**: the listed byte size and SHA-256 are identical in the
OTA's `new_partition_info`, the freshly streamed package image, and, for the
digest, the package's `SHA256SUMS`. Each image member is the prefix above followed
by `<partition>.img`. None of these measurements used the custom `super` or
custom `vbmeta_system` as a substitute for a rebuilt candidate.

| Partition | Bytes | SHA-256 |
| --- | ---: | --- |
| abl | 335872 | a453d48e0d7009a74dedbb423e5c4593f1b7e1ecf0d53d5b44fb90fc3484597f |
| aop | 421888 | a73b3423cfd9d85a125c36e3003bc929ae2cf8dd98c896ac0d969f28b00f71bb |
| aop_config | 28672 | 435a9f97e8349b17261fb3c67d8bc5c846b6a6197edb5c49d9fe985dbfa4cd77 |
| bluetooth | 8388608 | 685d127df804b8b6ef47a6413c7766417cffa3f7483886c4cc6d068ee23e685f |
| boot | 100663296 | 26958e1c28a3662c0568a2c95c6ceb14c3d1043cf68b3dd31a62bd5fbd163846 |
| cpucp | 454656 | 2750792177f7cab92e51b8baa94e8577760e16ded223960ef7e1f80e823d6698 |
| cpucp_dtb | 12288 | cf9e78ffdf39cd4e687e8a25ce7b892572f0bce95ba1f0200f6aa484d6b524a7 |
| dcp | 8388608 | 4748b8c660dc996e68ae00ba95fc4e0024f13f0aa37c37e8dbf5fc4027fa4cdf |
| devcfg | 57344 | cc006009f63027ec7047b9015b99f3da5f6468adcc70fc2895fa78f64a60a8f8 |
| dsp | 77594624 | 69bb905cd2c2f74e88096a275f0ad0ff21f1b95943ab7b4d62719560dcb36f2c |
| dtbo | 23068672 | 97c1752f5caf47654e9d2347d117af518c41193d379eaf64bf090cefed70111e |
| featenabler | 106496 | 5d574cc3fac95cb126dde43d8befba3c18816be0753b9b705ebe12c19faa4d96 |
| hyp | 1531904 | fadc8ec88fe8042e7603f9d21565fc4d493928ff69f23bf04b2647440c41a94c |
| hyp_ac_config | 77824 | 6c323c4798de7df9d8313fc1d27889dac8a63726cc63a787815679f141289fa7 |
| idmanager | 69632 | 16a9224af704839e638e8b3cf6b34186bf1054df5017e8732c70094f34a4d732 |
| imagefv | 6299648 | 72bb84dc592b59ddf418bce40401292aa975bdc7e70e116b035d233a45daa5ed |
| init_boot | 8388608 | 1f6356f30d5800c2551c8ccdc1a9034e7aecfc7d26708a930c868da8c4e503cf |
| keymaster | 3162112 | bffce70795343f2f1e1485f691e1111e5ec76bbd18116a56e1cf3b01addf1383 |
| modem | 167772160 | 75f6f985f797106e0e5e4a2192eef5d53da25a356fe64940b02f6e5c47583604 |
| modemfirmware | 176435200 | 61232e5d978e221c7a0319f4ffc8c4ab4e8c2044f0fa40629029857a56e9ac1d |
| multiimgqti | 12288 | 2217be1cb14e8e4075f3071323909a1c26e58b627b24199586cad1a24d7a8847 |
| pdp | 376832 | 02072bc7d088bed2949101e1e5cbdb916245310fc95f8e48b899cdee2d1783f6 |
| pdp_cdb | 12288 | d32105f0ab72a623f01b2a930e8fc358915d90199f06566d0e82926c2162cd01 |
| pvmfw | 1048576 | 29f2e1354ee93e05d477fbe36a77eeaa719a26c5d87e41e680d8910874c5549e |
| qtvm_dtbo | 5242880 | 7d05f0b7c9ecf301f88441b5305765e5831d2e66a012694ef3088af08d977b5f |
| qupfw | 65536 | ad5a9d8d20cdf84c34a623d5fcb37e6158cb08d2b5e1e95501bdd1dbab052541 |
| recovery | 104857600 | 532c9bc0c536f1df628d9094e83125d13abcaa20812357d309b636abb4983b6f |
| secretkeeper | 1056768 | c175ce0b581cef02e7a70cf05f18de3aaeb2cae891e9a90cb20d1f9fe13c3485 |
| shrm | 184320 | 508b2c67f5299509d06f64e4738798a4dd8040a6d4db69a1832a647ea17137bd |
| soccp | 8388608 | 666358704671262bf90b46cebcc846773521ea7ec4e714aa74d188a6082fda76 |
| soccp_dcd | 20480 | 4d261d9b2639d614d51dce59d92ff2c18897d865072169c5c986de1c9a4ca16d |
| soccp_debug | 73728 | 1588652c313e891ddcfb0d25889266e2ab5eb9562cdb9ccbd28c1ec258285add |
| spuservice | 94208 | 4670de1608e9d459b2c9a95cc5ed22163998ef1ba2ff015692dfb25c03f52792 |
| tme_config | 45056 | 37070e18d5beb0e50d32f3b516613db0f85c978ef5900f845010421a19a78d10 |
| tme_fw | 208896 | ed5b4cac08b1ee5dd52b212ad8066bfa21dee1a8d3032c642fe0d0df49adc7e8 |
| tme_seq_patch | 8192 | 35d85544a793890932c877a5da14c63a6a539223c9929e00055318fe03063b9b |
| tz | 4231168 | 1461554223ca0d2a58022668e6fbf2551e83f0bb0a7e7606ad56edbc9b2483eb |
| tz_ac_config | 65536 | 1bcae448f6e6f524782b6faad1337b04c9faa127dacf3fa6b71590884a003f52 |
| tz_qti_config | 139264 | 54ce09da75ab937a017b485294bab31d789bc6fdf50aec1f44d9ae360aa52eda |
| uefi | 2793472 | 217435e5359d078ec3b7103880b908b64e3c516146dc8ccd94445d651b53671b |
| uefisecapp | 204800 | 0314ee99908b6fb9c5482992d689a20250ae3e8485c981b6daa240c7ae98542f |
| vendor_boot | 100663296 | a0fd0382965b8451f2bc2dded79520c0b161018e2032a3117d1fb282a4e17b1f |
| vm-bootsys | 41943040 | 18fe2fc7043999b54ed60753a68c3ef733940ae22b3e376da610fad98e59f0ee |
| xbl | 1187840 | b77e38b2df23c5d7ca2667aa9c76fbe2ece724705ffa3d578cfdf56a60779271 |
| xbl_ac_config | 45056 | e235290e415aef4132e7d51574dee1fea5a32312b530a2c5cc662ca9dddd95d2 |
| xbl_config | 397312 | 90e8966e816317221c2d3de31e17863696e9acd3515456a81d1ec4d6162bf9d9 |
| xbl_ramdump | 901120 | ca4ba1f9f33287c6d285aaf656215b7696dd9516be75b6a75cc33d3a6cda14cf |
| vbmeta | 12288 | 69c245f4a82a610125bb4563a1476aa299ac9bf4e8197f6bf88e21de54c271d4 |

## Safety and interpretation limits

- No phone transport, installation, unlock, slot change, wipe, reboot, or
  physical validation occurred. No archive script or executable was run.
- No firmware image was extracted to disk, copied into an output package, or
  modified. Only the bounded metadata existed in an anonymous in-memory file;
  the 48 package images were read as streams. No network operation was used for
  the measurement.
- This compares actual package bytes against OTA-declared complete-image hashes.
  It does not reconstruct and independently hash the OTA's image operations,
  rehash the full OTA payload or archives, or authenticate an OEM signing chain.
- The two changing candidate outputs, `super.img` and `vbmeta_system.img`, were
  deliberately outside this unchanged-base comparison. Their successful
  composition, image correctness, AVB relation, and installation remain separate
  work. The old custom package's versions of these two outputs must not silently
  replace the user's new build.
- No Device Pack authority, Guardian certificate, production-readiness flag, or
  flash-validated AVB policy was created. The earlier package's historical boot
  and Android Auto claims remain package-provided assertions, not fresh tests.
- Byte equality does not establish a particular phone's product, partition
  capacity, unlock state, critical unlock, rollback indexes, data compatibility,
  recovery availability, or successful boot. A matching version string is not
  used as a replacement for the measured evidence.
- The source procedure writes slot A and the complete super container. Existing
  local build assembly creates zero-sized B logical partitions; this evidence
  does not establish a preserved or bootable fallback slot B.
- This Markdown record is review evidence, not a service-owned execution receipt
  or exportable authority. Runtime must freshly revalidate its own exact sources
  and staged bytes before any future confirmed operation.

## Precise next composition and AVB work

The required unchanged base material is already present and measured. There is
no demonstrated need to obtain another firmware package for these 48 inputs.
The next implementation should complete the following bounded vertical slice,
not replace it with another version-only checklist.

1. **Persist measured source equivalence in a typed service receipt.** Add a
   `BaseImageCompatibilityReceipt` that binds the freshly verified complete OTA
   archive/payload identity, bounded metadata digest and schema, procedure
   archive/script identity, and all 48 partition-to-member size/hash comparisons.
   A production metadata reader must be bounded, strictly tested, and fail
   closed for unsupported/ambiguous inputs. The transient decoder used here is
   not already that implementation.
2. **Compose exactly two replacements.** Add
   `CandidateInstallationService.prepare(build_project_id, *,
   procedure_project_id, wipe, reboot)` and `verify(composition)`. Retain separate
   OTA/build and procedure-package provenance. Seal the current tree, user
   Recipe, build plan, pack, toolchain, build receipt, output hashes, and base
   receipt into a new composition digest. Bind the rebuilt `super` to the
   procedure's `super` write and the matching rebuilt `vbmeta_system` to
   `vbmeta_system_a`. Preserve all 48 measured base images and the declared
   action order. `product.img` is a verified input inside super, not an added
   physical flash operation. Missing/stale candidate outputs must reject; never
   silently fall back to untouched package images.
3. **Verify AVB content, not only descriptor names.** Existing
   `AvbEvidenceService` records algorithms, keys, header fields and descriptor
   partition names. Extend evidence to the actual chain key, rollback location,
   flags, and hash/hashtree descriptors. Verify rebuilt product against the
   candidate child, exact passthrough system/system_ext against their retained
   descriptors, and preserve the exact stock root bytes. AOSP describes chain
   descriptors as delegating a trusted signing key and provides image-content
   verification separately from informational inspection. See
   [AOSP AVB](https://android.googlesource.com/platform/external/avb/+/refs/heads/main/README.md).
   The current contract's unsigned-child policy is reference-only and references
   .20. Do not turn it or this .23 base comparison into `FLASH_VALIDATED` authority.
   A signed stock root does not make an unsigned child OEM-verified. Any supported
   local unlocked/experimental route must say so explicitly, without silently
   adding verification-disable flags, relocking, or asserting rollback bypass.
4. **Extend private staging and receipt linkage.** Use distinct typed origins
   for protected archive members and verified build outputs. Verify and retain
   all mixed-origin private image snapshots before the first slot change. Reuse
   the shared exact-phone lock, one-use review/consent, failure and cancellation
   behavior, and source procedure. Preserve its 50 writes and 53 default actions;
   wipe and final reboot remain explicit options. Store composition and both
   source identities in installation/history/boot linkage without rewriting
   prior protected-source records.
5. **Prove the actual rebuilt path in inert tests and the real UI.** Cover a
   genuine build-service fixture through composition and all ordered writes,
   checking that exactly the two rebuilt byte streams are used. Reject any base
   mismatch, missing member, changed source/tree/Recipe/build, restored-mtime
   byte mutation, counterfeit descriptor content, widened mapping, or altered
   action order before the first phone change. Repeat decline/cancel/failure
   and historical linkage tests across mixed origins. A separately measured
   stable boot window remains boot-observation evidence only: an unchanged base
   fingerprint/uptime cannot prove rebuilt product contents, image readback, or
   subsystem health.

Useful existing implementation/test entry points are
`src/romverse/rom/project_flash.py`, `src/romverse/rom/build_contracts.py`,
`src/romverse/rom/build_execution.py`, `src/romverse/rom/payloads.py`,
`src/romverse/rom/avb_evidence.py`,
`src/romverse/rom/source_installation.py`,
`src/romverse/guardian/source_installation.py`, and
`src/romverse/rom/local_boot.py`; plus `tests/test_build_contracts.py`,
`tests/test_project_flash.py`, `tests/test_avb_evidence.py`,
`tests/test_source_installation.py`, and
`tests/test_source_installation_integration.py`.
