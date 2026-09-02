from __future__ import annotations

import fnmatch
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from urllib.parse import urlsplit

from romverse.device.models import AndroidDevice
from romverse.device_packs.models import (
    AvbExecutionPolicy,
    AvbHashtreeParameters,
    AvbPolicyAuthority,
    AvbPolicyMode,
    CapabilityStatus,
    DeviceBuildContract,
    DevicePack,
    DeviceWriteContract,
    DeviceWriteTransport,
    DynamicPartitionGroup,
    ErofsRebuildParameters,
    FileContextSource,
    FirmwareSourceContract,
    KnowledgeSource,
    PackCapability,
    PackLoadIssue,
    PackResolution,
    PartitionBuildRule,
    PartitionWriteRule,
)
from romverse.infrastructure.provisioning import (
    ROM_STUDIO_CONTRACT_MINIMUM_TOOLS,
    ROM_STUDIO_TOOL_CATALOG,
)


class PackResource(Protocol):
    name: str

    def joinpath(self, *descendants: str) -> PackResource: ...
    def read_text(self, encoding: str = "utf-8") -> str: ...


@dataclass(frozen=True, slots=True)
class DevicePackRegistry:
    packs: tuple[DevicePack, ...]
    issues: tuple[PackLoadIssue, ...] = ()

    @classmethod
    def load(cls, root: PackResource) -> DevicePackRegistry:
        issues: list[PackLoadIssue] = []
        packs: list[DevicePack] = []
        try:
            index = json.loads(root.joinpath("index.json").read_text(encoding="utf-8"))
            if index.get("schema_version") != 1:
                raise ValueError("unsupported index schema")
            entries = index["packs"]
            if not isinstance(entries, list):
                raise TypeError("index packs must be a list")
        except (
            OSError,
            json.JSONDecodeError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            return cls((), (PackLoadIssue("index.json", str(exc)),))

        for entry in entries:
            filename = "<unnamed>"
            try:
                if not isinstance(entry, dict):
                    raise TypeError("pack index entry must be an object")
                filename = str(entry.get("file", ""))
                if not filename.endswith(".json") or "/" in filename or "\\" in filename:
                    raise ValueError("unsafe pack filename")
                raw = root.joinpath(filename).read_text(encoding="utf-8")
                digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                if digest != entry["sha256"]:
                    raise ValueError("SHA-256 mismatch")
                pack = cls._parse(json.loads(raw), digest)
            except (
                OSError,
                json.JSONDecodeError,
                AttributeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                issues.append(PackLoadIssue(filename or "<unnamed>", str(exc)))
                continue
            packs.append(pack)
        duplicate_ids = {
            pack_id
            for pack_id, count in Counter(pack.pack_id for pack in packs).items()
            if count > 1
        }
        if duplicate_ids:
            packs = [pack for pack in packs if pack.pack_id not in duplicate_ids]
            issues.extend(
                PackLoadIssue(pack_id, "duplicate Device Pack id; all conflicting copies rejected")
                for pack_id in sorted(duplicate_ids)
            )
        return cls(
            tuple(sorted(packs, key=lambda item: item.priority, reverse=True)), tuple(issues)
        )

    def resolve(self, device: AndroidDevice) -> PackResolution:
        manufacturer = device.manufacturer.casefold().strip()
        brand = device.brand.casefold().strip()
        model = device.model.casefold().strip()
        product = device.product.casefold().strip()
        codename = device.codename.casefold().strip()
        if not manufacturer and not brand:
            product_only = self._resolve_literal_product_identity(product, codename)
            if product_only is not None:
                return product_only
        candidates: list[DevicePack] = []
        for pack in self.packs:
            if not (
                self._matches(manufacturer, pack.manufacturers)
                or self._matches(brand, pack.manufacturers)
            ):
                continue
            if pack.model_patterns and not self._matches(model, pack.model_patterns):
                continue
            if pack.product_patterns and not (
                self._matches(product, pack.product_patterns)
                or self._matches(codename, pack.product_patterns)
            ):
                continue
            candidates.append(pack)
        if not candidates:
            return PackResolution(None, False, "No valid Device Pack matched this device")
        highest_priority = max(pack.priority for pack in candidates)
        leaders = tuple(pack for pack in candidates if pack.priority == highest_priority)
        if len(leaders) != 1:
            identities = ", ".join(sorted(pack.pack_id for pack in leaders))
            return PackResolution(
                None,
                False,
                f"Ambiguous Device Pack match at priority {highest_priority}: {identities}",
            )
        pack = leaders[0]
        specific = pack.manufacturers != ("*",)
        reason = (
            f"Retail brand matched {device.brand}"
            if specific
            and self._matches(brand, pack.manufacturers)
            and not self._matches(manufacturer, pack.manufacturers)
            else f"Manufacturer matched {device.manufacturer or 'reported OEM'}"
            if specific
            else "Generic Android fallback"
        )
        return PackResolution(pack, True, reason)

    def _resolve_literal_product_identity(
        self,
        product: str,
        codename: str,
    ) -> PackResolution | None:
        """Use an unambiguous literal Pack product when Fastboot cannot report an OEM."""

        identities = {value for value in (product, codename) if value}
        if not identities:
            return None
        candidates = tuple(
            pack
            for pack in self.packs
            if pack.manufacturers != ("*",)
            and any(
                pattern.casefold() in identities
                for pattern in pack.product_patterns
                if pattern and not any(marker in pattern for marker in "*?[]")
            )
        )
        if not candidates:
            return None
        highest_priority = max(pack.priority for pack in candidates)
        leaders = tuple(pack for pack in candidates if pack.priority == highest_priority)
        if len(leaders) != 1:
            names = ", ".join(sorted(pack.pack_id for pack in leaders))
            return PackResolution(
                None,
                False,
                f"Ambiguous literal product identity at priority {highest_priority}: {names}",
            )
        pack = leaders[0]
        observed = product or codename
        return PackResolution(
            pack,
            True,
            f"Exact literal product identity matched {observed}; OEM was not reported in Fastboot",
        )

    def resolve_source(
        self,
        archive_sha256: str,
        payload_sha256: str = "",
    ) -> PackResolution:
        """Resolve one build pack by immutable firmware evidence, never by a guess."""

        archive_digest = str(archive_sha256).casefold().strip()
        payload_digest = str(payload_sha256).casefold().strip()
        if not _is_sha256(archive_digest):
            return PackResolution(None, False, "Protected source SHA-256 is invalid")
        if payload_digest and not _is_sha256(payload_digest):
            return PackResolution(None, False, "Payload SHA-256 is invalid")
        matches = tuple(
            pack
            for pack in self.packs
            if pack.build_contract is not None
            and pack.build_contract.source.archive_sha256 == archive_digest
            and (not payload_digest or pack.build_contract.source.payload_sha256 == payload_digest)
        )
        if not matches:
            return PackResolution(
                None,
                False,
                "No Device Pack has a build contract for this exact protected source",
            )
        if len(matches) != 1:
            return PackResolution(
                None,
                False,
                "More than one Device Pack claims this source; automatic association is blocked",
            )
        return PackResolution(
            matches[0],
            True,
            "Exact protected firmware SHA-256 matched a unique build contract",
        )

    def resolve_knowledge(self, device: AndroidDevice) -> PackResolution:
        """Resolve the best non-executing knowledge pack for an unmatched source.

        A model-specific build pack must never be retained merely because the live phone
        matches when the project's immutable firmware digest does not. This resolver
        deliberately excludes every source-bound build contract.
        """

        manufacturer = device.manufacturer.casefold().strip()
        brand = device.brand.casefold().strip()
        model = device.model.casefold().strip()
        product = device.product.casefold().strip()
        codename = device.codename.casefold().strip()
        candidates = tuple(
            pack
            for pack in self.packs
            if pack.build_contract is None
            and (
                self._matches(manufacturer, pack.manufacturers)
                or self._matches(brand, pack.manufacturers)
            )
            and (not pack.model_patterns or self._matches(model, pack.model_patterns))
            and (
                not pack.product_patterns
                or self._matches(product, pack.product_patterns)
                or self._matches(codename, pack.product_patterns)
            )
        )
        if not candidates:
            return PackResolution(None, False, "No read-only knowledge pack matched this device")
        highest_priority = max(pack.priority for pack in candidates)
        leaders = tuple(pack for pack in candidates if pack.priority == highest_priority)
        if len(leaders) != 1:
            identities = ", ".join(sorted(pack.pack_id for pack in leaders))
            return PackResolution(
                None,
                False,
                f"Ambiguous knowledge Pack match at priority {highest_priority}: {identities}",
            )
        return PackResolution(
            leaders[0],
            True,
            "Read-only OEM knowledge matched; no exact firmware build contract was claimed",
        )

    @staticmethod
    def _matches(value: str, patterns: tuple[str, ...]) -> bool:
        return any(pattern == "*" or fnmatch.fnmatchcase(value, pattern) for pattern in patterns)

    @staticmethod
    def _parse(data: dict, digest: str) -> DevicePack:
        publication_status = data.get("publication_status")
        if publication_status not in {None, "published"}:
            raise ValueError("unpublished Device Pack drafts cannot activate")
        schema_version = data.get("schema_version")
        if schema_version not in {1, 2}:
            raise ValueError("unsupported pack schema")
        pack_id = _safe_identifier(data["pack_id"], "pack id")
        version = _safe_identifier(data["version"], "pack version")
        display_name = _bounded_text(data["display_name"], "pack display name")
        priority = int(data.get("priority", 0))
        if not 0 <= priority <= 1000:
            raise ValueError("priority outside accepted range")
        match = data["match"]
        manufacturers = tuple(
            _bounded_text(value, "manufacturer matcher").casefold()
            for value in match["manufacturers"]
        )
        if not manufacturers:
            raise ValueError("at least one manufacturer matcher is required")
        capabilities = tuple(
            PackCapability(
                capability_id=str(item["capability_id"]),
                label=str(item["label"]),
                status=CapabilityStatus(str(item["status"])),
                scope=str(item["scope"]),
                detail=str(item["detail"]),
            )
            for item in data["capabilities"]
        )
        if not capabilities:
            raise ValueError("pack must declare capabilities")
        contract_data = data.get("build_contract")
        if contract_data is not None and schema_version != 2:
            raise ValueError("build contracts require pack schema 2")
        build_contract = (
            DevicePackRegistry._parse_build_contract(contract_data)
            if contract_data is not None
            else None
        )
        compatible_digests = tuple(
            _sha256(value, "build-compatible Pack")
            for value in data.get("build_compatible_pack_sha256", ())
        )
        if len(set(compatible_digests)) != len(compatible_digests):
            raise ValueError("build-compatible Pack digests must be unique")
        if compatible_digests and build_contract is None:
            raise ValueError("build-compatible Pack digests require a build contract")
        knowledge_sources = tuple(
            KnowledgeSource(
                source_id=_safe_identifier(item["source_id"], "knowledge source id"),
                label=_bounded_text(item["label"], "knowledge source label"),
                url=_knowledge_url(item["url"]),
                authority=_bounded_text(item["authority"], "knowledge source authority"),
                scope=_bounded_text(item["scope"], "knowledge source scope"),
                verified_on=_verified_date(item["verified_on"]),
            )
            for item in _object_list(
                data.get("knowledge_sources", []), "knowledge sources", allow_empty=True
            )
        )
        if len({source.source_id for source in knowledge_sources}) != len(knowledge_sources):
            raise ValueError("knowledge source ids must be unique")
        return DevicePack(
            pack_id=pack_id,
            version=version,
            display_name=display_name,
            priority=priority,
            manufacturers=manufacturers,
            model_patterns=tuple(
                _bounded_text(value, "model matcher").casefold()
                for value in match.get("model_patterns", ())
            ),
            product_patterns=tuple(
                _bounded_text(value, "product matcher").casefold()
                for value in match.get("product_patterns", ())
            ),
            capabilities=capabilities,
            notes=tuple(str(value) for value in data.get("notes", ())),
            sha256=digest,
            build_contract=build_contract,
            build_compatible_pack_sha256=compatible_digests,
            knowledge_sources=knowledge_sources,
        )

    @staticmethod
    def _parse_build_contract(data: object) -> DeviceBuildContract:
        if not isinstance(data, dict) or data.get("schema_version") not in {1, 2}:
            raise ValueError("unsupported build contract schema")
        schema_version = int(data["schema_version"])
        contract_id = _safe_identifier(data["contract_id"], "contract id")
        source_data = data["source"]
        if not isinstance(source_data, dict):
            raise TypeError("build contract source must be an object")
        source = FirmwareSourceContract(
            build_id=_bounded_text(source_data["build_id"], "source build id"),
            archive_sha256=_sha256(source_data["archive_sha256"], "source archive"),
            payload_sha256=_sha256(source_data["payload_sha256"], "source payload"),
        )
        dynamic = data["dynamic_partitions"]
        if not isinstance(dynamic, dict):
            raise TypeError("dynamic partition contract must be an object")
        super_size = _bounded_size(dynamic["super_size_bytes"], "super size", 128 << 30)
        metadata_size = _bounded_size(dynamic["metadata_size_bytes"], "metadata size", 16 << 20)
        metadata_slots = int(dynamic["metadata_slots"])
        if metadata_slots not in {2, 3, 4}:
            raise ValueError("metadata slot count must be 2, 3, or 4")
        virtual_ab = dynamic["virtual_ab"]
        if not isinstance(virtual_ab, bool):
            raise TypeError("virtual_ab must be a boolean")
        groups = tuple(
            DynamicPartitionGroup(
                _safe_identifier(item["name"], "group name"),
                _bounded_size(item["maximum_size_bytes"], "group size", super_size),
            )
            for item in _object_list(dynamic["groups"], "partition groups")
        )
        if not groups or len({group.name for group in groups}) != len(groups):
            raise ValueError("partition groups must be non-empty and unique")
        group_names = {group.name for group in groups}
        partitions = tuple(
            DevicePackRegistry._parse_partition_rule(item, super_size)
            for item in _object_list(dynamic["partitions"], "partitions")
        )
        if not partitions or len({rule.name for rule in partitions}) != len(partitions):
            raise ValueError("partitions must be non-empty and unique")
        for rule in partitions:
            if rule.group not in group_names:
                raise ValueError(f"partition {rule.name} references an unknown group")
            if rule.filesystem not in {"erofs", "ext4", "opaque"}:
                raise ValueError(f"partition {rule.name} has an unsupported filesystem")
            if rule.mode not in {"rebuild", "passthrough"}:
                raise ValueError(f"partition {rule.name} has an unsupported build mode")
        for group in groups:
            allocated = sum(rule.size_bytes for rule in partitions if rule.group == group.name)
            if allocated > group.maximum_size_bytes:
                raise ValueError(f"partitions exceed group {group.name} capacity")
        editable = tuple(rule for rule in partitions if rule.mode == "rebuild")
        if len(editable) != 1:
            raise ValueError("build contract must declare exactly one editable partition")
        allowed_outputs = tuple(str(value) for value in data["allowed_outputs"])
        allowed_names = {f"{rule.name}.img" for rule in editable} | {
            "super.img",
            "vbmeta_system.img",
        }
        if (
            not allowed_outputs
            or len(set(allowed_outputs)) != len(allowed_outputs)
            or any(name not in allowed_names for name in allowed_outputs)
        ):
            raise ValueError("build contract contains an unsupported output")
        descriptor_partitions = tuple(
            _safe_identifier(value, "vbmeta descriptor partition")
            for value in data["vbmeta_descriptor_partitions"]
        )
        partition_names = {rule.name for rule in partitions}
        if (
            not descriptor_partitions
            or len(set(descriptor_partitions)) != len(descriptor_partitions)
            or any(name not in partition_names for name in descriptor_partitions)
            or any(rule.name not in descriptor_partitions for rule in editable)
        ):
            raise ValueError("invalid vbmeta descriptor partition set")
        required_tools = tuple(str(value) for value in data["required_tools"])
        if (
            not required_tools
            or len(set(required_tools)) != len(required_tools)
            or any(name not in ROM_STUDIO_TOOL_CATALOG for name in required_tools)
            or not set(ROM_STUDIO_CONTRACT_MINIMUM_TOOLS).issubset(required_tools)
        ):
            raise ValueError("invalid or incomplete ROM Studio tool profile")
        if virtual_ab:
            a_groups = tuple(group for group in groups if group.name.endswith("_a"))
            b_groups = tuple(group for group in groups if group.name.endswith("_b"))
            if len(a_groups) != 1 or len(b_groups) != 1:
                raise ValueError("virtual A/B contracts require one _a and one _b group")
        context_sources = tuple(
            FileContextSource(
                partition=_safe_identifier(item["partition"], "file-context partition"),
                candidate_paths=tuple(
                    _safe_relative_path(value, "file-context candidate")
                    for value in item["candidate_paths"]
                ),
            )
            for item in _object_list(data["file_context_sources"], "file-context sources")
        )
        if (
            len({source.partition for source in context_sources}) != len(context_sources)
            or any(source.partition not in partition_names for source in context_sources)
            or any(not source.candidate_paths for source in context_sources)
        ):
            raise ValueError("invalid file-context source set")
        if (
            any(rule.erofs is not None and rule.erofs.require_file_contexts for rule in editable)
            and not context_sources
        ):
            raise ValueError("editable EROFS partitions require file-context sources")
        avb_policy = DevicePackRegistry._parse_avb_policy(data.get("avb_execution_policy"), source)
        raw_write_contract = data.get("partition_write_contract")
        if schema_version == 1 and raw_write_contract is not None:
            raise ValueError("partition-write contracts require build contract schema 2")
        if schema_version == 2 and raw_write_contract is None:
            raise ValueError("build contract schema 2 requires a partition-write contract")
        write_contract = (
            DevicePackRegistry._parse_partition_write_contract(
                raw_write_contract,
                source,
                allowed_outputs,
                avb_policy,
            )
            if raw_write_contract is not None
            else None
        )
        return DeviceBuildContract(
            contract_id=contract_id,
            version=schema_version,
            source=source,
            super_size_bytes=super_size,
            metadata_size_bytes=metadata_size,
            metadata_slots=metadata_slots,
            virtual_ab=virtual_ab,
            groups=groups,
            partitions=partitions,
            vbmeta_descriptor_partitions=descriptor_partitions,
            vbmeta_system_sha256=_sha256(data["vbmeta_system_sha256"], "vbmeta_system source"),
            top_level_vbmeta_sha256=_sha256(
                data["top_level_vbmeta_sha256"], "top-level vbmeta source"
            ),
            allowed_outputs=allowed_outputs,
            required_tools=required_tools,
            file_context_sources=context_sources,
            avb_execution_policy=avb_policy,
            partition_write_contract=write_contract,
        )

    @staticmethod
    def _parse_partition_write_contract(
        data: object,
        source: FirmwareSourceContract,
        allowed_outputs: tuple[str, ...],
        avb_policy: AvbExecutionPolicy | None,
    ) -> DeviceWriteContract:
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unsupported partition-write contract schema")
        expected_fields = {
            "schema_version",
            "contract_id",
            "source_build_id",
            "attestation_sha256",
            "require_unlocked_bootloader",
            "require_critical_unlocked",
            "preserve_user_data_supported",
            "wipe_user_data_supported",
            "bootloader_relock_allowed",
            "writes",
        }
        if set(data) != expected_fields:
            raise ValueError("partition-write contract fields are incomplete or unsupported")
        contract_id = _safe_identifier(data["contract_id"], "partition-write contract id")
        source_build_id = _bounded_text(data["source_build_id"], "partition-write source build id")
        attestation_sha256 = _sha256(data["attestation_sha256"], "partition-write attestation")
        require_unlocked = _strict_bool(
            data["require_unlocked_bootloader"], "require_unlocked_bootloader"
        )
        require_critical = _strict_bool(
            data["require_critical_unlocked"], "require_critical_unlocked"
        )
        preserve_supported = _strict_bool(
            data["preserve_user_data_supported"], "preserve_user_data_supported"
        )
        wipe_supported = _strict_bool(data["wipe_user_data_supported"], "wipe_user_data_supported")
        relock_allowed = _strict_bool(
            data["bootloader_relock_allowed"], "bootloader_relock_allowed"
        )
        if source_build_id != source.build_id:
            raise ValueError("partition-write contract must bind the exact source build")
        if not require_unlocked:
            raise ValueError("partition-write contract must require an unlocked bootloader")
        if relock_allowed:
            raise ValueError("bootloader relocking is permanently prohibited")
        if not preserve_supported and not wipe_supported:
            raise ValueError("partition-write contract must support at least one data mode")
        if (
            avb_policy is None
            or avb_policy.authority is not AvbPolicyAuthority.FLASH_VALIDATED
            or avb_policy.evidence_build_id != source.build_id
            or avb_policy.attestation_sha256 != attestation_sha256
        ):
            raise ValueError(
                "partition-write contract requires exact flash-validated AVB attestation"
            )
        if (
            not avb_policy.require_unlocked_bootloader
            or avb_policy.require_critical_unlocked != require_critical
        ):
            raise ValueError("partition-write and AVB boot-state requirements must agree")
        raw_writes = _object_list(data["writes"], "partition writes")
        if len(raw_writes) > 32:
            raise ValueError("partition-write contract exceeds the 32-write limit")
        writes = tuple(
            DevicePackRegistry._parse_partition_write_rule(item, allowed_outputs)
            for item in raw_writes
        )
        if len({item.partition for item in writes}) != len(writes):
            raise ValueError("partition-write targets must be unique")
        if len({item.artifact for item in writes}) != len(writes):
            raise ValueError("partition-write artifacts must be unique")
        return DeviceWriteContract(
            contract_id=contract_id,
            version=1,
            source_build_id=source_build_id,
            attestation_sha256=attestation_sha256,
            require_unlocked_bootloader=require_unlocked,
            require_critical_unlocked=require_critical,
            preserve_user_data_supported=preserve_supported,
            wipe_user_data_supported=wipe_supported,
            writes=writes,
            bootloader_relock_allowed=False,
        )

    @staticmethod
    def _parse_partition_write_rule(
        data: dict, allowed_outputs: tuple[str, ...]
    ) -> PartitionWriteRule:
        if set(data) != {
            "partition",
            "artifact",
            "transport",
            "target_slot",
            "verify_after_write",
        }:
            raise ValueError("partition-write rule fields are incomplete or unsupported")
        partition = _safe_identifier(data["partition"], "partition-write target")
        if partition != partition.casefold() or _unsafe_write_partition(partition):
            raise ValueError(f"unsafe partition-write target: {partition}")
        if partition.endswith(("_a", "_b")):
            raise ValueError("partition-write target must omit the slot suffix")
        artifact = _safe_relative_path(data["artifact"], "partition-write artifact")
        if "/" in artifact or not artifact.endswith(".img") or artifact not in allowed_outputs:
            raise ValueError("partition-write artifact is not an allowed image output")
        target_slot = str(data["target_slot"])
        if target_slot not in {"a", "b", "none"}:
            raise ValueError("partition-write target slot must be a, b, or none")
        verify_after_write = _strict_bool(data["verify_after_write"], "verify_after_write")
        if not verify_after_write:
            raise ValueError("partition-write contract must verify every written image")
        return PartitionWriteRule(
            partition=partition,
            artifact=artifact,
            transport=DeviceWriteTransport(str(data["transport"])),
            target_slot=target_slot,
            verify_after_write=True,
        )

    @staticmethod
    def _parse_avb_policy(
        data: object, source: FirmwareSourceContract
    ) -> AvbExecutionPolicy | None:
        if data is None:
            return None
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unsupported AVB execution policy schema")
        mode = AvbPolicyMode(str(data["mode"]))
        authority = AvbPolicyAuthority(str(data["authority"]))
        evidence_build_id = _bounded_text(data["evidence_build_id"], "AVB evidence build id")
        top_level_strategy = str(data["top_level_strategy"])
        if top_level_strategy != "preserve_exact_source":
            raise ValueError("unsupported AVB top-level strategy")
        chain_partition = _safe_identifier(data["chain_partition"], "AVB chain partition")
        candidate_algorithm = str(data["candidate_algorithm"])
        if candidate_algorithm not in {"NONE", "SHA256_RSA2048", "SHA256_RSA4096"}:
            raise ValueError("unsupported candidate AVB algorithm")
        rollback_index = int(data["candidate_rollback_index"])
        rollback_location = int(data["candidate_rollback_index_location"])
        flags = int(data["candidate_flags"])
        if rollback_index < 0 or not 0 <= rollback_location <= 31 or not 0 <= flags <= 3:
            raise ValueError("invalid candidate AVB header policy")
        booleans = (
            data["require_unlocked_bootloader"],
            data["require_critical_unlocked"],
            data["require_verity_mode"],
        )
        if any(not isinstance(value, bool) for value in booleans):
            raise TypeError("AVB boot-state requirements must be booleans")
        target_slot = str(data["target_slot"])
        recovery_slot = str(data["recovery_bootloader_slot"])
        if target_slot not in {"a", "b"} or recovery_slot not in {"a", "b"}:
            raise ValueError("invalid AVB slot policy")
        attestation = str(data.get("attestation_sha256", "")).casefold()
        if attestation and not _is_sha256(attestation):
            raise ValueError("invalid AVB policy attestation SHA-256")
        signing_key = str(data.get("signing_public_key_sha1", "")).casefold()
        if signing_key and (
            len(signing_key) != 40
            or any(character not in "0123456789abcdef" for character in signing_key)
        ):
            raise ValueError("invalid AVB signing public-key SHA-1")
        if authority is AvbPolicyAuthority.FLASH_VALIDATED and (
            evidence_build_id != source.build_id or not attestation
        ):
            raise ValueError(
                "flash-validated AVB policy requires exact-source evidence and attestation"
            )
        if mode is AvbPolicyMode.UNLOCKED_UNSIGNED_CHILD:
            if candidate_algorithm != "NONE" or not all(booleans[:2]):
                raise ValueError(
                    "unlocked unsigned-child policy requires Algorithm NONE and both unlock checks"
                )
        elif candidate_algorithm == "NONE":
            raise ValueError("signed AVB policies cannot require Algorithm NONE")
        if mode is AvbPolicyMode.SIGNED_CUSTOM_RECHAIN and not signing_key:
            raise ValueError("custom re-chaining policy requires an exact signing public key")
        return AvbExecutionPolicy(
            mode,
            authority,
            evidence_build_id,
            top_level_strategy,
            chain_partition,
            candidate_algorithm,
            rollback_index,
            rollback_location,
            flags,
            bool(booleans[0]),
            bool(booleans[1]),
            bool(booleans[2]),
            target_slot,
            recovery_slot,
            attestation,
            signing_key,
        )

    @staticmethod
    def _parse_partition_rule(item: dict, super_size: int) -> PartitionBuildRule:
        filesystem = str(item["filesystem"])
        mode = str(item["mode"])
        erofs_data = item.get("erofs")
        avb_data = item.get("avb_hashtree")
        erofs = None
        if erofs_data is not None:
            if not isinstance(erofs_data, dict):
                raise TypeError("EROFS parameters must be an object")
            compression = str(erofs_data["compression"])
            level = int(erofs_data["compression_level"])
            timestamp = int(erofs_data["timestamp"])
            filesystem_uuid = str(erofs_data["filesystem_uuid"]).casefold()
            mount_point = str(erofs_data["mount_point"])
            if compression not in {"lz4", "lz4hc"} or not 0 <= level <= 12:
                raise ValueError("unsupported EROFS compression parameters")
            if timestamp < 0 or timestamp > 4_102_444_800:
                raise ValueError("invalid EROFS timestamp")
            if not _uuid(filesystem_uuid):
                raise ValueError("invalid EROFS filesystem UUID")
            if not mount_point.startswith("/") or ".." in mount_point.split("/"):
                raise ValueError("unsafe EROFS mount point")
            erofs = ErofsRebuildParameters(
                compression,
                level,
                _strict_bool(erofs_data["legacy_compress"], "legacy_compress"),
                timestamp,
                filesystem_uuid,
                mount_point,
                _strict_bool(erofs_data["require_fakeroot_state"], "require_fakeroot_state"),
                _strict_bool(erofs_data["require_file_contexts"], "require_file_contexts"),
            )
        avb = None
        if avb_data is not None:
            if not isinstance(avb_data, dict):
                raise TypeError("AVB hashtree parameters must be an object")
            algorithm = str(avb_data["hash_algorithm"])
            if algorithm != "sha256":
                raise ValueError("unsupported AVB hash algorithm")
            avb = AvbHashtreeParameters(
                algorithm,
                _sha256(avb_data["salt"], "AVB salt"),
                _strict_bool(avb_data["generate_fec"], "generate_fec"),
            )
        if mode == "rebuild" and filesystem == "erofs" and (erofs is None or avb is None):
            raise ValueError("editable EROFS partitions require rebuild and AVB parameters")
        if mode == "passthrough" and (erofs is not None or avb is not None):
            raise ValueError("passthrough partitions cannot declare rebuild parameters")
        return PartitionBuildRule(
            name=_safe_identifier(item["name"], "partition name"),
            source_size_bytes=_bounded_size(
                item.get("source_size_bytes", item["size_bytes"]),
                "partition source size",
                super_size,
            ),
            size_bytes=_bounded_size(item["size_bytes"], "partition size", super_size),
            group=_safe_identifier(item["group"], "partition group"),
            filesystem=filesystem,
            mode=mode,
            source_sha256=_sha256(item["source_sha256"], "partition source"),
            erofs=erofs,
            avb_hashtree=avb,
        )


def _object_list(value: object, label: str, *, allow_empty: bool = False) -> tuple[dict, ...]:
    if (
        not isinstance(value, list)
        or (not value and not allow_empty)
        or any(not isinstance(item, dict) for item in value)
    ):
        raise TypeError(f"{label} must be a non-empty object list")
    return tuple(value)


def _knowledge_url(value: object) -> str:
    text = str(value).strip()
    parsed = urlsplit(text)
    if (
        len(text) > 500
        or parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError("invalid knowledge source URL")
    return text


def _verified_date(value: object) -> str:
    text = str(value)
    try:
        verified = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("invalid knowledge source verification date") from exc
    if verified > date.today():
        raise ValueError("knowledge source verification date cannot be in the future")
    return text


def _safe_identifier(value: object, label: str) -> str:
    text = str(value)
    if not text or len(text) > 80 or any(not (char.isalnum() or char in "._-") for char in text):
        raise ValueError(f"unsafe {label}")
    return text


def _safe_relative_path(value: object, label: str) -> str:
    text = str(value).strip().replace("\\", "/")
    parts = text.split("/")
    if (
        not text
        or len(text) > 240
        or text.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError(f"unsafe {label}")
    return text


def _bounded_text(value: object, label: str) -> str:
    text = str(value).strip()
    if not text or len(text) > 160 or any(ord(char) < 32 for char in text):
        raise ValueError(f"invalid {label}")
    return text


def _sha256(value: object, label: str) -> str:
    digest = str(value).casefold()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"invalid {label} SHA-256")
    return digest


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _bounded_size(value: object, label: str, maximum: int) -> int:
    size = int(value)
    if size <= 0 or size > maximum or size % 512:
        raise ValueError(f"invalid {label}")
    return size


def _strict_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be a boolean")
    return value


def _unsafe_write_partition(partition: str) -> bool:
    """Reject destructive control/data targets from the bounded V1 contract."""

    blocked_exact = {
        "userdata",
        "metadata",
        "frp",
        "misc",
        "persist",
        "persistent",
        "keystore",
    }
    blocked_tokens = (
        "bootloader",
        "relock",
        "unlock",
        "flashing",
        "userdata",
        "metadata",
        "erase",
        "wipe",
    )
    return partition in blocked_exact or any(token in partition for token in blocked_tokens)


def _uuid(value: str) -> bool:
    parts = value.split("-")
    return [len(part) for part in parts] == [8, 4, 4, 4, 12] and all(
        character in "0123456789abcdef" for part in parts for character in part
    )
