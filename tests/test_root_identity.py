from romverse.device.root_identity import RootIdentityState, review_root_identity


def test_uid_zero_and_one_manager_produce_a_strong_candidate_not_method_proof() -> None:
    review = review_root_identity(
        True,
        "magisk",
        root_signal_source="adb-shell-uid-0",
        manager_evidence="allowlisted-package-presence",
    )

    assert review.state is RootIdentityState.OBSERVED
    assert review.manager_candidate == "magisk"
    assert review.confidence == "strong"
    assert "does not prove" in review.summary
    assert review.execution_authority == "none"
    assert not review.phone_changed
    assert not review.bootloader_relock_allowed


def test_manager_presence_without_root_signal_remains_caution() -> None:
    review = review_root_identity(
        False,
        "kernelsu_lkm",
        root_signal_source="adb-shell-id",
        manager_evidence="allowlisted-package-presence",
    )

    assert review.state is RootIdentityState.MANAGER_CANDIDATE
    assert review.confidence == "caution"
    assert "active root unconfirmed" in review.title
    assert "package presence does not prove" in review.summary


def test_non_root_adb_shell_never_claims_the_phone_is_unrooted() -> None:
    review = review_root_identity(
        False,
        "none",
        root_signal_source="adb-shell-id",
        manager_evidence="allowlisted-package-presence",
    )

    assert review.state is RootIdentityState.NOT_CONFIRMED
    assert review.confidence == "unconfirmed"
    assert "not proof" in review.summary


def test_two_manager_candidates_are_exposed_as_a_conflict() -> None:
    review = review_root_identity(
        True,
        "conflict",
        root_signal_source="companion-local-indicators",
        manager_evidence="official-signer-check",
    )

    assert review.state is RootIdentityState.OBSERVED
    assert review.manager_candidate == "conflict"
    assert review.confidence == "caution"
    assert "both allowlisted Manager packages" in review.summary
