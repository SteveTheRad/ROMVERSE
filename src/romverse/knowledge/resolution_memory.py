"""Local, non-causal Archives memory compiled from verified guided comparisons."""

from __future__ import annotations

from dataclasses import dataclass

from romverse.knowledge.advisor import article_for_key
from romverse.repair.sessions import RepairSession, RepairSessionStore


@dataclass(frozen=True, slots=True)
class ArticleResolutionMemory:
    article_key: str
    comparisons: int
    improved: int
    unchanged: int
    needs_attention: int
    last_observed_at: str

    @property
    def plain_text(self) -> str:
        noun = "comparison" if self.comparisons == 1 else "comparisons"
        return (
            "LOCAL RESOLUTION MEMORY\n"
            f"{self.comparisons} integrity-verified guided {noun} recommended this article "
            "for the same typed concern.\n"
            f"Fresh evidence afterward: {self.improved} improved • {self.unchanged} unchanged • "
            f"{self.needs_attention} needed more attention.\n"
            f"Last observed: {self.last_observed_at}\n\n"
            "INTERPRETATION BOUNDARY\n"
            "This is private local correlation after a user-guided session. It does not prove "
            "that this article or any reviewed step caused the change, does not describe an "
            "unrecorded phone action, and grants no automatic execution authority."
        )


class ArchivesResolutionMemory:
    """Compile only schema-two, integrity-verified repair comparisons."""

    def __init__(self, session_store: RepairSessionStore) -> None:
        self.session_store = session_store

    def for_article(self, article_key: str) -> ArticleResolutionMemory | None:
        if article_for_key(article_key) is None:
            return None
        sessions = tuple(
            session
            for session in self.session_store.list_recent()
            if self._eligible(session, article_key)
        )
        if not sessions:
            return None
        return ArticleResolutionMemory(
            article_key=article_key,
            comparisons=len(sessions),
            improved=sum(session.verification_direction == "improved" for session in sessions),
            unchanged=sum(session.verification_direction == "unchanged" for session in sessions),
            needs_attention=sum(
                session.verification_direction == "needs more attention" for session in sessions
            ),
            last_observed_at=max(session.updated_at for session in sessions),
        )

    @staticmethod
    def _eligible(session: RepairSession, article_key: str) -> bool:
        return (
            session.integrity_verified
            and session.status == "verified"
            and session.verification_direction in {"improved", "unchanged", "needs more attention"}
            and article_key in session.archive_article_keys
        )
