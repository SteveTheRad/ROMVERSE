from __future__ import annotations

import hashlib
import hmac
import json
import os
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from threading import RLock
from uuid import uuid4


class GalaxyStoreError(RuntimeError):
    """Raised when local community data is invalid or cannot be preserved safely."""


class GalaxySort(StrEnum):
    RECENTLY_ACTIVE = "recently-active"
    NEWEST = "newest"
    MOST_HELPFUL = "most-helpful"


@dataclass(frozen=True, slots=True)
class CommunityComment:
    comment_id: str
    body: str
    author: str
    created_at: str


@dataclass(frozen=True, slots=True)
class CommunityPost:
    post_id: str
    title: str
    body: str
    author: str
    created_at: str
    updated_at: str
    vote: int = 0
    comments: tuple[CommunityComment, ...] = ()

    @property
    def score(self) -> int:
        return self.vote


@dataclass(frozen=True, slots=True)
class CommunityStoreStatus:
    exists: bool
    integrity_verified: bool
    reason: str
    post_count: int
    digest: str = ""


@dataclass(frozen=True, slots=True)
class CommunityDraft:
    title: str
    body: str
    updated_at: str


class GalaxyCommunityStore:
    """Atomic local forum store designed for a future explicit sync adapter."""

    SCHEMA_VERSION = 1
    FORMAT = "romverse.galaxy.community"
    INTEGRITY_VERSION = 1
    MAX_POSTS = 500
    MAX_COMMENTS_PER_POST = 1_000
    MAX_TOTAL_COMMENTS = 5_000
    MAX_FILE_BYTES = 16 * 1024 * 1024
    MAX_TITLE = 120
    MAX_BODY = 10_000
    MAX_COMMENT = 4_000
    DRAFT_FORMAT = "romverse.galaxy.local-draft"
    MAX_DRAFT_FILE_BYTES = 32 * 1024

    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "galaxy"
        self.path = self.root / "community-v1.json"
        self.draft_path = self.root / "topic-draft-v1.json"
        # Saving performs a post-write readback while callers already hold this lock.
        # A re-entrant lock keeps the transaction serialized without deadlocking.
        self._lock = RLock()

    def list_posts(
        self,
        query: str = "",
        order: GalaxySort = GalaxySort.RECENTLY_ACTIVE,
    ) -> tuple[CommunityPost, ...]:
        with self._lock:
            posts = self._load()
        normalized = query.casefold().strip()
        if normalized:
            posts = tuple(
                post
                for post in posts
                if normalized in post.title.casefold()
                or normalized in post.body.casefold()
                or any(normalized in item.body.casefold() for item in post.comments)
            )
        try:
            resolved_order = GalaxySort(order)
        except ValueError as exc:
            raise GalaxyStoreError("Unknown Galaxy topic ordering") from exc
        if resolved_order is GalaxySort.NEWEST:
            return tuple(
                sorted(posts, key=lambda item: (item.created_at, item.post_id), reverse=True)
            )
        if resolved_order is GalaxySort.MOST_HELPFUL:
            return tuple(
                sorted(
                    posts,
                    key=lambda item: (
                        item.score,
                        item.updated_at,
                        item.created_at,
                        item.post_id,
                    ),
                    reverse=True,
                )
            )
        return tuple(
            sorted(
                posts,
                key=lambda item: (item.updated_at, item.created_at, item.post_id),
                reverse=True,
            )
        )

    def status(self) -> CommunityStoreStatus:
        with self._lock:
            _posts, status = self._load_with_status()
        return status

    def load_draft(self) -> CommunityDraft | None:
        with self._lock:
            if not self.draft_path.exists():
                return None
            try:
                if self.draft_path.is_symlink() or not self.draft_path.is_file():
                    raise ValueError("draft is not a regular local file")
                size = self.draft_path.stat().st_size
                if size <= 0 or size > self.MAX_DRAFT_FILE_BYTES:
                    raise ValueError("draft size is outside the accepted boundary")
                payload = json.loads(self.draft_path.read_text(encoding="utf-8"))
                if (
                    not isinstance(payload, dict)
                    or payload.get("format") != self.DRAFT_FORMAT
                    or payload.get("schema_version") != self.SCHEMA_VERSION
                    or payload.get("mode") != "offline-local"
                ):
                    raise ValueError("unsupported local draft schema")
                expected = str(payload.get("draft_digest", ""))
                unsigned = dict(payload)
                unsigned.pop("draft_digest", None)
                actual = hashlib.sha256(_canonical(unsigned)).hexdigest()
                if len(expected) != 64 or not hmac.compare_digest(expected, actual):
                    raise ValueError("local draft integrity mismatch")
                title = self._draft_text(payload.get("title"), self.MAX_TITLE)
                body = self._draft_text(payload.get("body"), self.MAX_BODY)
                updated_at = self._timestamp(payload.get("updated_at"))
                if not title and not body:
                    return None
                return CommunityDraft(title, body, updated_at)
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise GalaxyStoreError(f"Local Galaxy draft is unreadable: {exc}") from exc

    def save_draft(self, title: str, body: str) -> CommunityDraft | None:
        clean_title = self._draft_text(title, self.MAX_TITLE)
        clean_body = self._draft_text(body, self.MAX_BODY)
        with self._lock:
            if self.draft_path.exists():
                # Never silently replace an unreadable or altered draft. The user can
                # explicitly discard it after seeing the integrity warning.
                self.load_draft()
            if not clean_title and not clean_body:
                self.clear_draft()
                return None
            draft = CommunityDraft(clean_title, clean_body, datetime.now(UTC).isoformat())
            payload = {
                "format": self.DRAFT_FORMAT,
                "schema_version": self.SCHEMA_VERSION,
                "mode": "offline-local",
                "title": draft.title,
                "body": draft.body,
                "updated_at": draft.updated_at,
            }
            payload["draft_digest"] = hashlib.sha256(_canonical(payload)).hexdigest()
            self.root.mkdir(parents=True, exist_ok=True)
            try:
                self._atomic_write(
                    self.draft_path,
                    json.dumps(payload, indent=2, sort_keys=True) + "\n",
                )
            except OSError as exc:
                raise GalaxyStoreError(f"Could not save local Galaxy draft: {exc}") from exc
            return draft

    def clear_draft(self) -> None:
        with self._lock:
            try:
                self.draft_path.unlink(missing_ok=True)
            except OSError as exc:
                raise GalaxyStoreError(f"Could not clear local Galaxy draft: {exc}") from exc

    def create_post(
        self,
        title: str,
        body: str,
        author: str = "You",
    ) -> CommunityPost:
        clean_title = self._clean_text(title, "Topic title", self.MAX_TITLE)
        clean_body = self._clean_text(body, "Topic body", self.MAX_BODY)
        clean_author = self._clean_text(author, "Author", 80)
        now = datetime.now(UTC).isoformat()
        post = CommunityPost(
            post_id=uuid4().hex,
            title=clean_title,
            body=clean_body,
            author=clean_author,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            posts = self._load()
            if len(posts) >= self.MAX_POSTS:
                raise GalaxyStoreError("Local Community Lab has reached its 500-topic limit")
            self._save((post, *posts))
        return post

    def add_comment(
        self,
        post_id: str,
        body: str,
        author: str = "You",
    ) -> CommunityPost:
        clean_body = self._clean_text(body, "Comment", self.MAX_COMMENT)
        clean_author = self._clean_text(author, "Author", 80)
        comment = CommunityComment(
            comment_id=uuid4().hex,
            body=clean_body,
            author=clean_author,
            created_at=datetime.now(UTC).isoformat(),
        )
        return self._update(
            post_id,
            lambda post: replace(
                post,
                comments=(*post.comments, comment),
                updated_at=comment.created_at,
            ),
        )

    def set_vote(self, post_id: str, vote: int) -> CommunityPost:
        if vote not in {-1, 0, 1}:
            raise GalaxyStoreError("A local vote must be -1, 0, or 1")
        return self._update(post_id, lambda post: replace(post, vote=vote))

    def delete_post(self, post_id: str) -> None:
        with self._lock:
            posts = self._load()
            retained = tuple(post for post in posts if post.post_id != post_id)
            if len(retained) == len(posts):
                raise GalaxyStoreError("Community topic was not found")
            self._save(retained)

    def export_post(self, post_id: str, destination: Path) -> Path:
        post = self.get(post_id)
        payload = {
            "format": "romverse.galaxy.local-post",
            "schema_version": self.SCHEMA_VERSION,
            "mode": "offline-local",
            "post": self._post_mapping(post),
        }
        payload["record_digest"] = hashlib.sha256(_canonical(payload)).hexdigest()
        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(destination, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return destination

    def get(self, post_id: str) -> CommunityPost:
        with self._lock:
            return self._find(self._load(), post_id)

    def _update(self, post_id: str, update) -> CommunityPost:
        with self._lock:
            posts = self._load()
            current = self._find(posts, post_id)
            updated = update(current)
            self._save(tuple(updated if item.post_id == post_id else item for item in posts))
            return updated

    def _load(self) -> tuple[CommunityPost, ...]:
        posts, _status = self._load_with_status()
        return posts

    def _load_with_status(self) -> tuple[tuple[CommunityPost, ...], CommunityStoreStatus]:
        if not self.path.exists():
            return (), CommunityStoreStatus(False, False, "No local Galaxy data saved yet", 0)
        try:
            if self.path.is_symlink() or not self.path.is_file():
                raise ValueError("community store is not a regular local file")
            size = self.path.stat().st_size
            if size <= 0 or size > self.MAX_FILE_BYTES:
                raise ValueError("community store size is outside the accepted boundary")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != self.FORMAT
                or payload.get("schema_version") != self.SCHEMA_VERSION
                or payload.get("mode") != "offline-local"
            ):
                raise ValueError("unsupported community schema")
            integrity_keys = {"integrity_version", "community_digest"}
            present_integrity = integrity_keys.intersection(payload)
            if present_integrity and present_integrity != integrity_keys:
                raise ValueError("community integrity envelope is incomplete")
            integrity_verified = bool(present_integrity)
            digest = ""
            reason = "Legacy local Galaxy data; integrity fingerprint unavailable"
            if integrity_verified:
                if payload.get("integrity_version") != self.INTEGRITY_VERSION:
                    raise ValueError("unsupported community integrity format")
                digest = str(payload.get("community_digest", ""))
                unsigned = dict(payload)
                unsigned.pop("community_digest", None)
                actual = hashlib.sha256(_canonical(unsigned)).hexdigest()
                if len(digest) != 64 or not hmac.compare_digest(digest, actual):
                    raise ValueError("community data integrity mismatch")
                reason = "SHA-256 community data integrity verified"
            raw_posts = payload.get("posts")
            if not isinstance(raw_posts, list) or len(raw_posts) > self.MAX_POSTS:
                raise ValueError("invalid post collection")
            posts = tuple(self._parse_post(item) for item in raw_posts)
            self._validate_collection(posts)
            return posts, CommunityStoreStatus(
                True,
                integrity_verified,
                reason,
                len(posts),
                digest,
            )
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            GalaxyStoreError,
        ) as exc:
            raise GalaxyStoreError(f"Local Community Lab data is unreadable: {exc}") from exc

    def _save(self, posts: tuple[CommunityPost, ...]) -> None:
        self._validate_collection(posts)
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "mode": "offline-local",
            "integrity_version": self.INTEGRITY_VERSION,
            "posts": [self._post_mapping(post) for post in posts],
        }
        payload["community_digest"] = hashlib.sha256(_canonical(payload)).hexdigest()
        try:
            self._atomic_write(
                self.path,
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
            )
            _posts, status = self._load_with_status()
            if not status.integrity_verified:
                raise OSError("community data failed post-write verification")
        except (OSError, GalaxyStoreError) as exc:
            raise GalaxyStoreError(f"Could not save local Community Lab data: {exc}") from exc

    def _validate_collection(self, posts: tuple[CommunityPost, ...]) -> None:
        if len(posts) > self.MAX_POSTS:
            raise GalaxyStoreError("Local Community Lab has reached its 500-topic limit")
        if len({post.post_id for post in posts}) != len(posts):
            raise GalaxyStoreError("Duplicate local topic identifiers were rejected")
        comment_ids: list[str] = []
        for post in posts:
            if len(post.comments) > self.MAX_COMMENTS_PER_POST:
                raise GalaxyStoreError("A local reply list exceeds the safe limit")
            comment_ids.extend(comment.comment_id for comment in post.comments)
        if len(comment_ids) > self.MAX_TOTAL_COMMENTS:
            raise GalaxyStoreError("The local reply collection exceeds the safe limit")
        if len(set(comment_ids)) != len(comment_ids):
            raise GalaxyStoreError("Duplicate local reply identifiers were rejected")

    def _parse_post(self, payload: object) -> CommunityPost:
        if not isinstance(payload, dict):
            raise TypeError("post must be an object")
        comments = payload.get("comments")
        if not isinstance(comments, list) or len(comments) > self.MAX_COMMENTS_PER_POST:
            raise TypeError("comments must be a list")
        post = CommunityPost(
            post_id=self._identifier(payload["post_id"]),
            title=self._clean_text(payload["title"], "Topic title", self.MAX_TITLE),
            body=self._clean_text(payload["body"], "Topic body", self.MAX_BODY),
            author=self._clean_text(payload["author"], "Author", 80),
            created_at=self._timestamp(payload["created_at"]),
            updated_at=self._timestamp(payload["updated_at"]),
            vote=int(payload.get("vote", 0)),
            comments=tuple(self._parse_comment(item) for item in comments),
        )
        if post.vote not in {-1, 0, 1}:
            raise ValueError("invalid local vote")
        if datetime.fromisoformat(post.updated_at) < datetime.fromisoformat(post.created_at):
            raise ValueError("topic update time predates its creation")
        return post

    def _parse_comment(self, payload: object) -> CommunityComment:
        if not isinstance(payload, dict):
            raise TypeError("comment must be an object")
        return CommunityComment(
            comment_id=self._identifier(payload["comment_id"]),
            body=self._clean_text(payload["body"], "Comment", self.MAX_COMMENT),
            author=self._clean_text(payload["author"], "Author", 80),
            created_at=self._timestamp(payload["created_at"]),
        )

    @staticmethod
    def _post_mapping(post: CommunityPost) -> dict[str, object]:
        data = asdict(post)
        data["comments"] = [asdict(comment) for comment in post.comments]
        return data

    @staticmethod
    def _find(posts: tuple[CommunityPost, ...], post_id: str) -> CommunityPost:
        try:
            return next(post for post in posts if post.post_id == post_id)
        except StopIteration as exc:
            raise GalaxyStoreError("Community topic was not found") from exc

    @staticmethod
    def _clean_text(value: object, label: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise GalaxyStoreError(f"{label} must be text")
        clean = value.replace("\x00", "").strip()
        if not clean:
            raise GalaxyStoreError(f"{label} cannot be empty")
        if len(clean) > maximum:
            raise GalaxyStoreError(f"{label} must be {maximum} characters or fewer")
        return clean

    @staticmethod
    def _draft_text(value: object, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValueError("draft content must be text")
        return value.replace("\x00", "")[:maximum]

    @staticmethod
    def _identifier(value: object) -> str:
        if not isinstance(value, str) or not value or len(value) > 80:
            raise ValueError("invalid identifier")
        return value

    @staticmethod
    def _timestamp(value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("invalid timestamp")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        if parsed > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("timestamp is in the future")
        return value

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            # Windows does not permit opening a directory with this POSIX
            # durability pattern.  The file itself is still flushed above;
            # directory metadata syncing remains enabled where supported.
            if os.name != "nt":
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
