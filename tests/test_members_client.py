from __future__ import annotations

import pytest

from romverse.members.client import (
    MembersClient,
    MembersConfiguration,
    MembersError,
    MemberSession,
    PollResult,
)


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, str] | None, dict[str, str] | None]] = []
        self.token_pending = True

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        form: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        maximum_bytes: int = 512 * 1024,
    ) -> dict[str, object]:
        del maximum_bytes
        self.requests.append((url, method, form, headers))
        if url.endswith("openid-configuration"):
            return {
                "issuer": "https://members.example.test",
                "device_authorization_endpoint": "https://members.example.test/oauth/device",
                "token_endpoint": "https://members.example.test/oauth/token",
                "userinfo_endpoint": "https://members.example.test/oauth/userinfo",
            }
        if url.endswith("/oauth/device"):
            return {
                "device_code": "device-secret-value",
                "user_code": "ROM-VERSE",
                "verification_uri": "https://members.example.test/activate",
                "verification_uri_complete": "https://members.example.test/activate?code=ROM-VERSE",
                "expires_in": 600,
                "interval": 5,
            }
        if url.endswith("/oauth/token"):
            if self.token_pending:
                self.token_pending = False
                raise MembersError("Members service rejected the request (authorization_pending).")
            return {"access_token": "a" * 32, "token_type": "Bearer", "expires_in": 3600}
        if url.endswith("/oauth/userinfo"):
            assert headers == {"Authorization": f"Bearer {'a' * 32}"}
            return {
                "sub": "member-123",
                "name": "Nova Builder",
                "email": "nova@example.test",
                "romverse_membership": {
                    "plan": "ROMVERSE One",
                    "status": "trial",
                    "trial_ends_at": "2026-09-05T00:00:00Z",
                    "entitlements": ["studio", "companion", "nexus", "guardian"],
                },
            }
        raise AssertionError(url)


def test_device_sign_in_accepts_only_server_issued_profile_and_entitlement() -> None:
    transport = FakeTransport()
    client = MembersClient(
        MembersConfiguration("https://members.example.test", "desktop-public-client"),
        transport,
        clock=lambda: 1_000,
    )

    authorization = client.begin_sign_in()
    pending, no_session = client.poll(authorization)
    authorized, session = client.poll(authorization)

    assert pending is PollResult.PENDING
    assert no_session is None
    assert authorized is PollResult.AUTHORIZED
    assert isinstance(session, MemberSession)
    assert session.profile.display_name == "Nova Builder"
    assert session.profile.plan_name == "ROMVERSE One"
    assert session.profile.membership_status == "trial"
    assert session.profile.access_active
    assert session.profile.entitlements == ("studio", "companion", "nexus", "guardian")
    assert session.expires_at_epoch == 4_600
    assert all("device-secret-value" not in url for url, *_ in transport.requests)


@pytest.mark.parametrize(
    "issuer",
    (
        "http://members.example.test",
        "https://localhost:8080",
        "https://127.0.0.1",
        "https://user:password@members.example.test",
        "https://members.example.test/#fragment",
    ),
)
def test_members_configuration_rejects_insecure_or_local_issuers(issuer: str) -> None:
    with pytest.raises(MembersError):
        MembersConfiguration(issuer, "desktop-public-client").validated()


def test_members_configuration_never_accepts_password_or_missing_openid_scope() -> None:
    with pytest.raises(MembersError):
        MembersConfiguration("https://members.example.test", "bad client").validated()
    with pytest.raises(MembersError):
        MembersConfiguration(
            "https://members.example.test", "desktop-client", "profile email"
        ).validated()
