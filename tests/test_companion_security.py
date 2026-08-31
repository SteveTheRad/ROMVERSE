from __future__ import annotations

import os
import ssl

import pytest

from romverse.companion.security import LinkSecurityError, LinkTlsIdentity, safety_code


def test_link_tls_identity_is_persistent_private_and_revalidated(tmp_path) -> None:
    identity = LinkTlsIdentity.load_or_create(tmp_path)
    restored = LinkTlsIdentity.load_or_create(tmp_path)

    assert restored.certificate_sha256 == identity.certificate_sha256
    assert restored.safety_code == safety_code(identity.certificate_sha256)
    assert restored.safety_code.count("-") == 5
    assert len(identity.certificate_sha256) == 64
    if os.name != "nt":
        assert identity.private_key_path.stat().st_mode & 0o077 == 0
        assert tmp_path.stat().st_mode & 0o077 == 0

    context = identity.server_context()
    assert context.minimum_version is ssl.TLSVersion.TLSv1_2


def test_link_tls_identity_rejects_an_incomplete_or_tampered_identity(tmp_path) -> None:
    identity = LinkTlsIdentity.load_or_create(tmp_path)
    identity.certificate_path.write_text("not a certificate", encoding="utf-8")

    with pytest.raises(LinkSecurityError, match="failed validation"):
        LinkTlsIdentity.load_or_create(tmp_path)

    assert identity.private_key_path.exists()
    assert identity.certificate_path.read_text(encoding="utf-8") == "not a certificate"


@pytest.mark.parametrize("value", ["", "a" * 63, "g" * 64, "00:11"])
def test_link_safety_code_rejects_invalid_fingerprints(value: str) -> None:
    with pytest.raises(LinkSecurityError, match="fingerprint"):
        safety_code(value)
