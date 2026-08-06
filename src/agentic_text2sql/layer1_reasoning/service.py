"""Layer 1 facade preserving deterministic routing before model planning."""

from agentic_text2sql.contracts.planning import LogicalPlan, RouteDecision, RouteIntent
from agentic_text2sql.layer1_reasoning.decomposer import Decomposer
from agentic_text2sql.layer1_reasoning.planner import PlannerAgent
from agentic_text2sql.layer1_reasoning.router import QueryRouter


class ReasoningService:
    def __init__(self, router: QueryRouter, decomposer: Decomposer, planner: PlannerAgent) -> None:
        self.router = router
        self.decomposer = decomposer
        self.planner = planner

    def run(self, question: str) -> tuple[RouteDecision, LogicalPlan | None]:
        route = self.router.route(question)
        if route.intent is not RouteIntent.QUERY:
            return route, None
        decomposition = self.decomposer.decompose(question)
        return route, self.planner.plan(question, decomposition)
