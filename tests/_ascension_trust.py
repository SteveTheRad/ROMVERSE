from __future__ import annotations

from pathlib import Path

from romverse.ascension.models import AscensionMethod, OfficialRootRelease


class ExplicitTestRootReleaseService:
    """Test-only pinned-signer boundary for synthetic manager fixtures.

    Real application code always uses OfficialRootReleaseService and APK Signer. Tests
    concerned with later Ascension stages use deliberately synthetic manager bytes, so
    they must opt into this explicit fake rather than weakening the production default.
    """

    def __init__(self, release: OfficialRootRelease, path: Path) -> None:
        self.set_verified(release, path)

    def set_verified(self, release: OfficialRootRelease, path: Path) -> None:
        self.release = release
        self.path = path.resolve()

    def load_verified(
        self,
        method: AscensionMethod,
    ) -> tuple[OfficialRootRelease, Path] | None:
        if self.release.provider is not method or self.release.asset.provider is not method:
            return None
        return self.release, self.path
