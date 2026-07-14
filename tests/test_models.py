import pytest
from pydantic import ValidationError
from opportunityos.domain.models import OpportunityInput
def test_opportunity_input_requires_url_or_text():
    with pytest.raises(ValidationError):OpportunityInput()
def test_opportunity_input_accepts_text():assert OpportunityInput(raw_text='A legitimate opportunity description').raw_text
