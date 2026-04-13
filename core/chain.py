"""
Chain modes — compose multiple agents into a pipeline.

Modes
-----
SEQUENTIAL  A → B → C          Each agent's output is the next agent's input.
PARALLEL    [A, B, C] → merge  All agents run concurrently; outputs are merged.
ROUTER      router → A|B|C     A router agent picks which downstream agent(s) to call.

Each AgentChain is immutable after construction (steps added via add_step / add_agents).
"""
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from .agent import Agent, AgentResult


logger = logging.getLogger(__name__)


class ChainMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL   = "parallel"
    ROUTER     = "router"


@dataclass
class ChainStep:
    agent: Agent
    # Optional transform applied to the running input *before* calling this agent.
    # Signature: (current_input: str, last_result: AgentResult | None) -> str
    input_transform: Optional[Callable[[str, Optional[AgentResult]], str]] = None
    # Skip this step unless condition returns True for the previous result.
    condition: Optional[Callable[[Optional[AgentResult]], bool]] = None


@dataclass
class ChainResult:
    chain_id: str
    mode: ChainMode
    steps: list[AgentResult]
    final_output: str
    success: bool
    error: Optional[str] = None


class AgentChain:
    """
    Compose agents into a pipeline.

    Quick-start
    -----------
    chain = AgentChain("my-chain", ChainMode.SEQUENTIAL)
    chain.add_agents(researcher, writer, reviewer)
    result = await chain.run("Summarise recent AI news")
    print(result.final_output)
    """

    def __init__(self, chain_id: str, mode: ChainMode = ChainMode.SEQUENTIAL) -> None:
        self.chain_id = chain_id
        self.mode = mode
        self.steps: list[ChainStep] = []
        self._log = logging.getLogger(f"chain.{chain_id}")

    # ------------------------------------------------------------------
    # Builder
    # ------------------------------------------------------------------

    def add_step(
        self,
        agent: Agent,
        input_transform: Optional[Callable] = None,
        condition: Optional[Callable] = None,
    ) -> "AgentChain":
        self.steps.append(
            ChainStep(agent=agent, input_transform=input_transform, condition=condition)
        )
        return self

    def add_agents(self, *agents: Agent) -> "AgentChain":
        for agent in agents:
            self.add_step(agent)
        return self

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(
        self,
        initial_input: str,
        merge_agent: Optional[Agent] = None,
    ) -> ChainResult:
        dispatch = {
            ChainMode.SEQUENTIAL: self._run_sequential,
            ChainMode.PARALLEL:   self._run_parallel,
            ChainMode.ROUTER:     self._run_router,
        }
        fn = dispatch.get(self.mode)
        if not fn:
            raise ValueError(f"Unknown chain mode: {self.mode}")
        return await fn(initial_input, merge_agent=merge_agent)

    # ------------------------------------------------------------------
    # Sequential
    # ------------------------------------------------------------------

    async def _run_sequential(
        self, initial_input: str, **_
    ) -> ChainResult:
        results: list[AgentResult] = []
        current_input = initial_input

        for step in self.steps:
            prev = results[-1] if results else None

            # Skip if condition not met
            if step.condition and not step.condition(prev):
                self._log.debug("Skipping step %s (condition false)", step.agent.name)
                continue

            # Optionally transform input
            if step.input_transform and prev is not None:
                current_input = step.input_transform(current_input, prev)
            elif prev is not None:
                # Default: pass previous output + original request as context
                current_input = (
                    f"Previous agent ({step.agent.name}) output:\n{prev.content}\n\n"
                    f"Original request: {initial_input}"
                )

            result = await step.agent.run(current_input)
            results.append(result)

            if not result.success:
                return ChainResult(
                    chain_id=self.chain_id,
                    mode=self.mode,
                    steps=results,
                    final_output=result.error or "Chain step failed",
                    success=False,
                    error=result.error,
                )

        final = results[-1].content if results else ""
        return ChainResult(
            chain_id=self.chain_id,
            mode=self.mode,
            steps=results,
            final_output=final,
            success=True,
        )

    # ------------------------------------------------------------------
    # Parallel
    # ------------------------------------------------------------------

    async def _run_parallel(
        self, initial_input: str, merge_agent: Optional[Agent] = None, **_
    ) -> ChainResult:
        tasks = [step.agent.run(initial_input) for step in self.steps]
        results: list[AgentResult] = await asyncio.gather(*tasks)

        # Build merged text
        merged = "\n\n".join(
            f"**{self.steps[i].agent.name}**:\n{r.content}"
            for i, r in enumerate(results)
        )

        if merge_agent:
            merge_prompt = (
                "You are a synthesis agent. Combine the following independent expert "
                "responses into a single, coherent, comprehensive answer.\n\n"
                f"Original question: {initial_input}\n\n"
                f"Expert responses:\n{merged}"
            )
            merge_result = await merge_agent.run(merge_prompt)
            final_output = merge_result.content
            all_results = list(results) + [merge_result]
        else:
            final_output = merged
            all_results = list(results)

        return ChainResult(
            chain_id=self.chain_id,
            mode=self.mode,
            steps=all_results,
            final_output=final_output,
            success=all(r.success for r in results),
        )

    # ------------------------------------------------------------------
    # Router
    # ------------------------------------------------------------------

    async def _run_router(self, initial_input: str, **_) -> ChainResult:
        if not self.steps:
            return ChainResult(
                chain_id=self.chain_id, mode=self.mode, steps=[],
                final_output="", success=False, error="No steps defined"
            )

        router_step = self.steps[0]
        downstream_steps = self.steps[1:]
        if not downstream_steps:
            # Only one agent — just run it
            result = await router_step.agent.run(initial_input)
            return ChainResult(
                chain_id=self.chain_id, mode=self.mode, steps=[result],
                final_output=result.content, success=result.success,
            )

        agent_names = [s.agent.name for s in downstream_steps]
        routing_prompt = (
            f"Request: \"{initial_input}\"\n\n"
            f"Available agents: {', '.join(agent_names)}\n\n"
            "Which agent(s) should handle this request? "
            "Reply with ONLY the agent name(s) separated by commas. "
            "No explanation."
        )
        routing_result = await router_step.agent.run(routing_prompt)

        chosen_names = [n.strip().lower() for n in routing_result.content.split(",")]
        chosen = [
            s for s in downstream_steps
            if any(cn in s.agent.name.lower() for cn in chosen_names)
        ] or [downstream_steps[0]]  # fallback to first

        tasks = [s.agent.run(initial_input) for s in chosen]
        downstream_results: list[AgentResult] = await asyncio.gather(*tasks)

        all_results = [routing_result] + list(downstream_results)
        final = downstream_results[0].content if downstream_results else ""

        return ChainResult(
            chain_id=self.chain_id,
            mode=self.mode,
            steps=all_results,
            final_output=final,
            success=all(r.success for r in downstream_results),
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_info(self) -> dict:
        return {
            "chain_id": self.chain_id,
            "mode": self.mode,
            "steps": [s.agent.name for s in self.steps],
        }
