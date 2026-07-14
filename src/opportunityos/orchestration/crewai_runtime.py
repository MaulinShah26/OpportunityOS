from __future__ import annotations

from typing import Any

from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.domain.models import AnalysisRequest, AnalysisResult


class CrewAIUnavailableError(RuntimeError):
    pass


def execute_with_crewai(
    service: AnalyseOpportunityService,
    request: AnalysisRequest,
) -> AnalysisResult:
    """Run the typed vertical slice inside a CrewAI Flow.

    Imports are lazy so deterministic development and tests do not require CrewAI to be installed.
    The application service remains the source of business truth; CrewAI owns orchestration only.
    """
    try:
        from crewai.flow.flow import Flow, start
    except ImportError as exc:
        raise CrewAIUnavailableError(
            "CrewAI is not installed. Install project dependencies or set ORCHESTRATOR=local."
        ) from exc

    class OpportunityFlow(Flow[dict[str, Any]]):
        @start()
        def analyse(self) -> dict[str, Any]:
            return service.execute(request).model_dump(mode="json")

    result = OpportunityFlow().kickoff()
    return AnalysisResult.model_validate(result)
