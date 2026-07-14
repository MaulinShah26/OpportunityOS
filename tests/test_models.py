import pytest
from pydantic import ValidationError

from opportunityos.domain.models import OpportunityInput


def test_opportunity_input_requires_url_or_text() -> None:
    with pytest.raises(ValidationError):
        OpportunityInput()


def test_opportunity_input_accepts_text() -> None:
    model = OpportunityInput(raw_text="A legitimate opportunity description")
    assert model.raw_text is not None
