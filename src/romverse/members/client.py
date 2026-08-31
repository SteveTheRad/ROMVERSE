from __future__ import annotations

import ipaddress
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class MembersError(RuntimeError):
    """A bounded, user-displayable Members service failure."""


class PollResult(StrEnum):
    AUTHORIZED = "authorized"
    PENDING = "pending"
    SLOW_DOWN = "slow_down"
    EXPIRED = "expired"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class MembersConfiguration:
    issuer: str
    client_id: str
    scope: str = "openid profile email offline_access"

    def validated(self) -> MembersConfiguration:
        issuer = _trusted_https_url(self.issuer, "Members issuer").rstrip("/")
        client_id = self.client_id.strip()
        if not client_id or len(client_id) > 200 or any(char.isspace() for char in client_id):
            raise MembersError("The Members client ID is missing or invalid.")
        scopes = tuple(dict.fromkeys(self.scope.split()))
        if "openid" not in scopes or len(scopes) > 12:
            raise MembersError("The Members scope must be bounded and include openid.")
        return MembersConfiguration(issuer, client_id, " ".join(scopes))


@dataclass(frozen=True, slots=True)
class DeviceAuthorization:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_at_epoch: int
    interval_seconds: int


@dataclass(frozen=True, slots=True)
class MemberProfile:
    subject: str
    display_name: str
    email: str
    plan_name: str
    membership_status: str
    trial_ends_at: str = ""
    renews_at: str = ""
    entitlements: tuple[str, ...] = ()

    @property
    def access_active(self) -> bool:
        return self.membership_status in {"active", "trial"}


@dataclass(frozen=True, slots=True)
class MemberSession:
    access_token: str
    token_type: str
    expires_at_epoch: int
    profile: MemberProfile


@dataclass(frozen=True, slots=True)
class _Discovery:
    issuer: str
    device_authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str


class JsonTransport(Protocol):
    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        form: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        maximum_bytes: int = 512 * 1024,
    ) -> dict[str, object]: ...


class UrllibJsonTransport:
    """Small HTTPS JSON transport with strict bounds and no credential logging."""

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        form: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        maximum_bytes: int = 512 * 1024,
    ) -> dict[str, object]:
        trusted_url = _trusted_https_url(url, "Members endpoint")
        body = urllib.parse.urlencode(form).encode() if form is not None else None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "ROMVERSE/0.1 Members",
            **(headers or {}),
        }
        if form is not None:
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(
            trusted_url,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                final_url = _trusted_https_url(response.geturl(), "Members response")
                if urllib.parse.urlsplit(final_url).hostname != urllib.parse.urlsplit(url).hostname:
                    raise MembersError("The Members service redirected to an untrusted host.")
                length = response.headers.get("Content-Length")
                if length and int(length) > maximum_bytes:
                    raise MembersError("The Members service response is too large.")
                payload = response.read(maximum_bytes + 1)
        except urllib.error.HTTPError as exc:
            payload = exc.read(min(maximum_bytes, 64 * 1024))
            try:
                error = json.loads(payload).get("error", "request_failed")
            except (ValueError, AttributeError):
                error = "request_failed"
            raise MembersError(f"Members service rejected the request ({error}).") from exc
        except (OSError, urllib.error.URLError, ValueError) as exc:
            raise MembersError("The Members service could not be reached securely.") from exc
        if len(payload) > maximum_bytes:
            raise MembersError("The Members service response is too large.")
        try:
            parsed = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MembersError("The Members service returned invalid JSON.") from exc
        if not isinstance(parsed, dict):
            raise MembersError("The Members service returned an invalid response.")
        return parsed


class MembersClient:
    """OAuth device authorization client with session-only access tokens.

    ROMVERSE never collects a password. Tokens deliberately stay in memory until
    an operating-system credential vault integration is available.
    """

    def __init__(
        self,
        configuration: MembersConfiguration,
        transport: JsonTransport | None = None,
        clock: callable = time.time,
    ) -> None:
        self.configuration = configuration.validated()
        self.transport = transport or UrllibJsonTransport()
        self.clock = clock
        self._discovery: _Discovery | None = None

    def discover(self) -> None:
        payload = self.transport.request(
            f"{self.configuration.issuer}/.well-known/openid-configuration"
        )
        issuer = str(payload.get("issuer", "")).rstrip("/")
        if issuer != self.configuration.issuer:
            raise MembersError("The Members issuer identity does not match its discovery record.")
        self._discovery = _Discovery(
            issuer,
            _trusted_https_url(
                payload.get("device_authorization_endpoint", ""),
                "Device authorization endpoint",
            ),
            _trusted_https_url(payload.get("token_endpoint", ""), "Token endpoint"),
            _trusted_https_url(payload.get("userinfo_endpoint", ""), "User profile endpoint"),
        )

    def begin_sign_in(self) -> DeviceAuthorization:
        discovery = self._require_discovery()
        payload = self.transport.request(
            discovery.device_authorization_endpoint,
            method="POST",
            form={"client_id": self.configuration.client_id, "scope": self.configuration.scope},
        )
        device_code = _required_text(payload, "device_code", 4096)
        user_code = _required_text(payload, "user_code", 80)
        verification_uri = _trusted_https_url(
            payload.get("verification_uri", ""), "Verification URL"
        )
        complete = str(payload.get("verification_uri_complete", "")).strip()
        if complete:
            complete = _trusted_https_url(complete, "Complete verification URL")
        expires_in = _bounded_integer(payload.get("expires_in"), 60, 1800, "expiry")
        interval = _bounded_integer(payload.get("interval", 5), 2, 30, "poll interval")
        return DeviceAuthorization(
            device_code,
            user_code,
            verification_uri,
            complete,
            int(self.clock()) + expires_in,
            interval,
        )

    def poll(self, authorization: DeviceAuthorization) -> tuple[PollResult, MemberSession | None]:
        if int(self.clock()) >= authorization.expires_at_epoch:
            return PollResult.EXPIRED, None
        discovery = self._require_discovery()
        try:
            payload = self.transport.request(
                discovery.token_endpoint,
                method="POST",
                form={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": authorization.device_code,
                    "client_id": self.configuration.client_id,
                },
            )
        except MembersError as exc:
            message = str(exc)
            for code, result in (
                ("authorization_pending", PollResult.PENDING),
                ("slow_down", PollResult.SLOW_DOWN),
                ("expired_token", PollResult.EXPIRED),
                ("access_denied", PollResult.DENIED),
            ):
                if code in message:
                    return result, None
            raise
        access_token = _required_text(payload, "access_token", 16_384)
        token_type = _required_text(payload, "token_type", 40)
        if token_type.casefold() != "bearer":
            raise MembersError("The Members service returned an unsupported token type.")
        expires_in = _bounded_integer(payload.get("expires_in"), 60, 86_400, "token expiry")
        profile = self._profile(access_token)
        return PollResult.AUTHORIZED, MemberSession(
            access_token,
            "Bearer",
            int(self.clock()) + expires_in,
            profile,
        )

    def _profile(self, access_token: str) -> MemberProfile:
        discovery = self._require_discovery()
        payload = self.transport.request(
            discovery.userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        subject = _required_text(payload, "sub", 240)
        membership = payload.get("romverse_membership", {})
        if not isinstance(membership, dict):
            membership = {}
        status = str(membership.get("status", "unverified")).strip().casefold()
        if status not in {"active", "trial", "past_due", "inactive", "unverified"}:
            status = "unverified"
        raw_entitlements = membership.get("entitlements", ())
        entitlements = (
            tuple(
                dict.fromkeys(
                    value.strip()
                    for value in raw_entitlements
                    if isinstance(value, str) and 1 <= len(value.strip()) <= 120
                )
            )[:40]
            if isinstance(raw_entitlements, list)
            else ()
        )
        return MemberProfile(
            subject=subject,
            display_name=_optional_text(payload.get("name"), 160) or "ROMVERSE Member",
            email=_optional_text(payload.get("email"), 320),
            plan_name=_optional_text(membership.get("plan"), 120) or "No verified plan",
            membership_status=status,
            trial_ends_at=_optional_text(membership.get("trial_ends_at"), 80),
            renews_at=_optional_text(membership.get("renews_at"), 80),
            entitlements=entitlements,
        )

    def _require_discovery(self) -> _Discovery:
        if self._discovery is None:
            self.discover()
        assert self._discovery is not None
        return self._discovery


def _trusted_https_url(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise MembersError(f"{label} is missing or invalid.")
    parsed = urllib.parse.urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise MembersError(f"{label} must be a clean HTTPS URL.")
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise MembersError(f"{label} cannot use a local address.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise MembersError(f"{label} cannot use a private or local address.")
    return urllib.parse.urlunsplit(parsed)


def _required_text(payload: dict[str, object], key: str, maximum: int) -> str:
    value = _optional_text(payload.get(key), maximum)
    if not value:
        raise MembersError(f"The Members response is missing {key}.")
    return value


def _optional_text(value: object, maximum: int) -> str:
    return value.strip() if isinstance(value, str) and len(value.strip()) <= maximum else ""


def _bounded_integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise MembersError(f"The Members {label} is outside the safe boundary.")
    return value
