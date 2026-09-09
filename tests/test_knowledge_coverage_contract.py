from __future__ import annotations

import pytest

from romverse.knowledge.coverage_contract import (
    KnowledgeCoverageError,
    KnowledgeField,
    coverage_rule,
    coverage_rules,
    require_claim_coverage,
)
from romverse.knowledge.online_evidence import EvidenceConsumer


def test_every_approved_field_has_one_exact_non_empty_rule() -> None:
    rules = coverage_rules()

    assert {rule.field for rule in rules} == set(KnowledgeField)
    assert len({rule.field for rule in rules}) == len(rules)
    assert len({rule.claim_key for rule in rules}) == len(rules)
    assert all(
        rule.claim_key and rule.consumers and rule.decision_improved.strip() for rule in rules
    )


def test_identity_rules_name_device_dna_and_compatibility_matrix() -> None:
    for field in (
        KnowledgeField.IDENTITY_MANUFACTURER,
        KnowledgeField.IDENTITY_MARKETING_NAME,
        KnowledgeField.IDENTITY_MODEL,
        KnowledgeField.IDENTITY_CODENAME,
    ):
        rule = coverage_rule(field)
        assert EvidenceConsumer.DEVICE_DNA in rule.consumers
        assert EvidenceConsumer.COMPATIBILITY_MATRIX in rule.consumers


def test_unknown_field_and_contract_drift_fail_closed() -> None:
    with pytest.raises(KnowledgeCoverageError, match="outside current-product coverage"):
        coverage_rule("marketing.popularity")

    rule = coverage_rule(KnowledgeField.IDENTITY_MODEL)
    with pytest.raises(KnowledgeCoverageError, match="Claim key"):
        require_claim_coverage(rule.field, "device.identity.adjacent-model", rule.consumers)
    with pytest.raises(KnowledgeCoverageError, match="consumers"):
        require_claim_coverage(
            rule.field,
            rule.claim_key,
            (EvidenceConsumer.GUARDIAN,),
        )
