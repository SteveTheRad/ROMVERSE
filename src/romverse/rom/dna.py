from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.recipes import RecipeStore


@dataclass(frozen=True, slots=True)
class RomDNA:
    project_id: str
    device_pack_id: str
    original_sha256: str
    tree_sha256: str
    recipe_digest: str
    fingerprint: str
    schema_version: int = 1
    record_digest: str = ""


def derive_dna(store: RomProjectStore, project_id: str) -> RomDNA:
    project = store.get(project_id)
    if project.original is None:
        raise ProjectError("Import a protected original before deriving ROM DNA")
    plan = RomBuildPlanner(store).load(project_id)
    if plan is None:
        raise ProjectError("Create a build plan before deriving ROM DNA")
    recipe = RecipeStore().load(store.projects_root / project_id)
    recipe_digest = recipe.digest() if recipe is not None else ""
    canonical = json.dumps(
        {
            "project_id": project_id,
            "device_pack_id": project.device_pack_id,
            "original_sha256": project.original.sha256,
            "tree_sha256": plan.tree_sha256,
            "recipe_digest": recipe_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return _seal(
        RomDNA(
            project_id,
            project.device_pack_id,
            project.original.sha256,
            plan.tree_sha256,
            recipe_digest,
            hashlib.sha256(canonical.encode()).hexdigest(),
            schema_version=2,
        )
    )


class DnaStore:
    NAME = "rom-dna.romverse"
    FORMAT = "romverse.dna"
    MAX_BYTES = 64 * 1024

    def save(self, store: RomProjectStore, dna: RomDNA) -> Path:
        current = derive_dna(store, dna.project_id)
        if _semantic(dna) != _semantic(current):
            raise ProjectError("ROM DNA does not match current project provenance")
        dna = _seal(dna)
        if not _valid(dna):
            raise ProjectError("ROM DNA metadata is invalid")
        path = store.projects_root / dna.project_id / self.NAME
        atomic_write_json(
            path,
            {"format": self.FORMAT, **asdict(dna)},
            boundary=store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )
        return path

    def load(self, store: RomProjectStore, project_id: str) -> RomDNA | None:
        try:
            store.get(project_id)
        except ProjectError:
            return None
        path = store.projects_root / project_id / self.NAME
        try:
            data = read_json_object(
                path,
                boundary=store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            schema_version = data.get("schema_version")
            legacy_fields = {
                "format",
                "project_id",
                "device_pack_id",
                "original_sha256",
                "tree_sha256",
                "recipe_digest",
                "fingerprint",
            }
            current_fields = {"schema_version", "record_digest", *legacy_fields}
            if (
                set(data) != (legacy_fields if schema_version is None else current_fields)
                or data.pop("format") != self.FORMAT
            ):
                return None
            legacy = schema_version is None
            if not all(
                isinstance(data.get(key), str)
                for key in (
                    "project_id",
                    "device_pack_id",
                    "original_sha256",
                    "tree_sha256",
                    "recipe_digest",
                    "fingerprint",
                )
            ):
                return None
            dna = RomDNA(
                project_id=data["project_id"],
                device_pack_id=data["device_pack_id"],
                original_sha256=data["original_sha256"],
                tree_sha256=data["tree_sha256"],
                recipe_digest=data["recipe_digest"],
                fingerprint=data["fingerprint"],
                schema_version=1 if legacy else data["schema_version"],
                record_digest="" if legacy else data["record_digest"],
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        try:
            current = derive_dna(store, project_id)
        except ProjectError:
            return None
        if not _valid(dna) or dna.project_id != project_id or _semantic(dna) != _semantic(current):
            return None
        return dna

    def verify(self, store: RomProjectStore, project_id: str) -> bool:
        return self.load(store, project_id) is not None


def _seal(dna: RomDNA) -> RomDNA:
    unsigned = replace(dna, schema_version=2, record_digest="")
    payload = asdict(unsigned)
    payload.pop("record_digest")
    return replace(unsigned, record_digest=_digest(payload))


def _valid(dna: RomDNA) -> bool:
    unsigned = asdict(dna)
    digest = unsigned.pop("record_digest")
    return bool(
        type(dna.schema_version) is int
        and dna.schema_version in {1, 2}
        and re.fullmatch(r"[a-z0-9-]{1,64}", dna.project_id)
        and (
            not dna.device_pack_id
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", dna.device_pack_id)
        )
        and _sha256(dna.original_sha256)
        and _sha256(dna.tree_sha256)
        and (not dna.recipe_digest or _sha256(dna.recipe_digest))
        and _sha256(dna.fingerprint)
        and (
            (dna.schema_version == 1 and not digest)
            or (dna.schema_version == 2 and _sha256(digest) and digest == _digest(unsigned))
        )
    )


def _semantic(dna: RomDNA) -> tuple[str, str, str, str, str, str]:
    return (
        dna.project_id,
        dna.device_pack_id,
        dna.original_sha256,
        dna.tree_sha256,
        dna.recipe_digest,
        dna.fingerprint,
    )


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))
