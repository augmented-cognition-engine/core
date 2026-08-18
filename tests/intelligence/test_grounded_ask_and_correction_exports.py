from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_ask_contracts_are_exported_from_ace_intelligence() -> None:
    from ace.intelligence import AskAnswerV1Alpha1, AskNoAnswerV1Alpha1, AskQuestionV1Alpha1  # noqa: F401


def test_correction_contracts_are_exported_from_ace_intelligence() -> None:
    from ace.intelligence import ClaimCorrectionAdmissionV1Alpha1, ClaimCorrectionRequestV1Alpha1  # noqa: F401


def test_ask_and_correction_services_are_exported_from_ace_application() -> None:
    from ace.application import (  # noqa: F401
        ClaimBoundCorrectionError,
        ClaimBoundCorrectionNotFound,
        ClaimBoundCorrectionService,
        GroundedAskError,
        GroundedAskService,
    )


def test_ask_and_correction_contracts_are_reexported_from_ace_application() -> None:
    from ace.application import (  # noqa: F401
        AskAnswerV1Alpha1,
        AskNoAnswerV1Alpha1,
        AskQuestionV1Alpha1,
        ClaimCorrectionAdmissionV1Alpha1,
        ClaimCorrectionRequestV1Alpha1,
    )
