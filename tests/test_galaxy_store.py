from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from romverse.galaxy.store import GalaxyCommunityStore, GalaxySort, GalaxyStoreError


def test_local_community_topics_comments_votes_and_search_round_trip(tmp_path) -> None:
    store = GalaxyCommunityStore(tmp_path)
    post = store.create_post("Xiaomi build notes", "Document the verified payload layout.")
    commented = store.add_comment(post.post_id, "Capture ROM DNA before edits.")
    voted = store.set_vote(post.post_id, 1)

    assert commented.comments[0].author == "You"
    assert voted.score == 1
    assert store.list_posts("payload")[0].post_id == post.post_id
    assert store.list_posts("ROM DNA")[0].comments[0].body.startswith("Capture")

    reloaded = GalaxyCommunityStore(tmp_path).get(post.post_id)
    assert reloaded.vote == 1
    assert len(reloaded.comments) == 1


def test_local_post_export_is_explicitly_offline(tmp_path) -> None:
    store = GalaxyCommunityStore(tmp_path)
    post = store.create_post("Recovery checklist", "Keep a tested rollback path.")
    destination = tmp_path / "exports" / "topic.json"

    assert store.export_post(post.post_id, destination) == destination.resolve()
    payload = json.loads(destination.read_text())
    assert payload["format"] == "romverse.galaxy.local-post"
    assert payload["mode"] == "offline-local"
    assert payload["post"]["post_id"] == post.post_id
    digest = payload.pop("record_digest")
    assert digest == _digest(payload)


def test_saved_community_data_is_integrity_bound_and_tampering_is_preserved(tmp_path) -> None:
    store = GalaxyCommunityStore(tmp_path)
    store.create_post("Verified topic", "Keep this exact evidence intact.")

    status = store.status()
    assert status.integrity_verified
    assert len(status.digest) == 64
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["posts"][0]["body"] = "silently changed"
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(GalaxyStoreError, match="integrity mismatch"):
        store.list_posts()
    assert "silently changed" in store.path.read_text(encoding="utf-8")


def test_legacy_community_data_remains_readable_and_upgrades_on_save(tmp_path) -> None:
    store = GalaxyCommunityStore(tmp_path)
    post = store.create_post("Legacy topic", "Created before integrity fingerprints.")
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload.pop("integrity_version")
    payload.pop("community_digest")
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.get(post.post_id).title == "Legacy topic"
    assert not store.status().integrity_verified

    store.add_comment(post.post_id, "This save upgrades the complete collection.")
    assert store.status().integrity_verified


def test_community_store_rejects_symlinks_oversized_files_and_duplicate_ids(tmp_path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    symlink_store = GalaxyCommunityStore(tmp_path / "symlink")
    symlink_store.root.mkdir(parents=True)
    symlink_store.path.symlink_to(outside)
    with pytest.raises(GalaxyStoreError, match="regular local file"):
        symlink_store.list_posts()

    oversized = GalaxyCommunityStore(tmp_path / "oversized")
    oversized.root.mkdir(parents=True)
    oversized.path.write_text("x" * 64, encoding="utf-8")
    oversized.MAX_FILE_BYTES = 32
    with pytest.raises(GalaxyStoreError, match="size"):
        oversized.list_posts()

    duplicate = GalaxyCommunityStore(tmp_path / "duplicate")
    post = duplicate.create_post("Duplicates", "Reject ambiguous reply identities.")
    duplicate.add_comment(post.post_id, "One reply")
    payload = json.loads(duplicate.path.read_text(encoding="utf-8"))
    payload["posts"][0]["comments"].append(payload["posts"][0]["comments"][0])
    payload["community_digest"] = _digest(
        {key: value for key, value in payload.items() if key != "community_digest"}
    )
    duplicate.path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GalaxyStoreError, match="Duplicate local reply"):
        duplicate.list_posts()


def test_community_store_rejects_future_dated_integrity_valid_data(tmp_path) -> None:
    store = GalaxyCommunityStore(tmp_path)
    store.create_post("Time evidence", "Timestamps cannot arrive from the future.")
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    payload["posts"][0]["created_at"] = future
    payload["posts"][0]["updated_at"] = future
    payload["community_digest"] = _digest(
        {key: value for key, value in payload.items() if key != "community_digest"}
    )
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(GalaxyStoreError, match="future"):
        store.list_posts()


def test_invalid_or_corrupt_community_data_is_never_silently_replaced(tmp_path) -> None:
    store = GalaxyCommunityStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text("{broken", encoding="utf-8")

    with pytest.raises(GalaxyStoreError, match="unreadable"):
        store.list_posts()
    with pytest.raises(GalaxyStoreError, match="unreadable"):
        store.create_post("Do not overwrite", "The corrupt evidence must be preserved.")
    assert store.path.read_text(encoding="utf-8") == "{broken"


def test_local_community_validation_and_deletion(tmp_path) -> None:
    store = GalaxyCommunityStore(tmp_path)
    with pytest.raises(GalaxyStoreError, match="cannot be empty"):
        store.create_post(" ", "body")
    post = store.create_post("Local only", "No online synchronization is implied.")
    with pytest.raises(GalaxyStoreError, match="-1, 0, or 1"):
        store.set_vote(post.post_id, 2)
    store.delete_post(post.post_id)
    assert store.list_posts() == ()


def test_local_topics_support_deterministic_user_selected_ordering(tmp_path) -> None:
    store = GalaxyCommunityStore(tmp_path)
    first = store.create_post("First topic", "Created first and active again later.")
    second = store.create_post("Second topic", "Created most recently.")
    store.add_comment(first.post_id, "This makes the first topic recently active.")
    store.set_vote(second.post_id, 1)

    assert [post.post_id for post in store.list_posts(order=GalaxySort.RECENTLY_ACTIVE)] == [
        first.post_id,
        second.post_id,
    ]
    assert [post.post_id for post in store.list_posts(order=GalaxySort.NEWEST)] == [
        second.post_id,
        first.post_id,
    ]
    assert [post.post_id for post in store.list_posts(order=GalaxySort.MOST_HELPFUL)] == [
        second.post_id,
        first.post_id,
    ]
    with pytest.raises(GalaxyStoreError, match="ordering"):
        store.list_posts(order="unknown")  # type: ignore[arg-type]


def test_local_topic_draft_is_integrity_bound_restored_and_cleared(tmp_path) -> None:
    store = GalaxyCommunityStore(tmp_path)

    saved = store.save_draft("Draft title\x00", "Evidence in progress")

    assert saved is not None
    assert saved.title == "Draft title"
    assert store.load_draft() == saved
    payload = json.loads(store.draft_path.read_text(encoding="utf-8"))
    assert len(payload["draft_digest"]) == 64

    store.save_draft("", "")
    assert store.load_draft() is None
    assert not store.draft_path.exists()


def test_corrupt_local_draft_is_preserved_without_blocking_topics(tmp_path) -> None:
    store = GalaxyCommunityStore(tmp_path)
    post = store.create_post("Safe topic", "Community data remains independent of the draft.")
    store.save_draft("Draft", "Do not silently replace this")
    payload = json.loads(store.draft_path.read_text(encoding="utf-8"))
    payload["body"] = "tampered"
    store.draft_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(GalaxyStoreError, match="integrity mismatch"):
        store.load_draft()
    with pytest.raises(GalaxyStoreError, match="integrity mismatch"):
        store.save_draft("Replacement", "Must not overwrite corrupt evidence")
    assert store.get(post.post_id).title == "Safe topic"
    assert "tampered" in store.draft_path.read_text(encoding="utf-8")


def _digest(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
