"""One-candidate structured SQL generator."""

from agentic_text2sql.adapters.llm.base import StructuredLLM
from agentic_text2sql.contracts.sql import SqlCandidate


class GeneratorAgent:
    def __init__(self, provider: StructuredLLM) -> None:
        self.provider = provider

    def generate(self, prompt: str) -> SqlCandidate:
        return self.provider.generate_structured(prompt=prompt, response_model=SqlCandidate)
