# engine/orchestration/request.py
"""OrchestrationRequest — the single entry point for all orchestration calls.

Every source (chat, runner, evolution, sentinel) builds an
``OrchestrationRequest`` that carries task description, org context,
and execution preferences.  Class methods provide ergonomic constructors
for common callers.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from core.engine.orchestration.agent import AgentConfig


class OrchestrationRequest(BaseModel):
    """Unified request envelope for ``orchestrate()``."""

    description: str
    product_id: str
    workspace_id: str
    user_id: str
    source: Literal["chat", "direct", "runner", "evolution", "sentinel"] = "direct"

    # Optional pre-created durable receipt.  Public asynchronous callers create
    # the task row before execution so a dropped HTTP connection cannot erase
    # the task identity.  Other callers continue to let the executor create the
    # row at completion.
    task_id: str | None = None

    # Model / skill overrides
    model: str | None = None
    force_skill: str | None = None
    force_frameworks: bool = False
    frameworks_hint: list[str] | None = None

    # Conversation context (chat source)
    conversation_messages: list[dict[str, Any]] | None = None

    # Pattern & agent overrides
    pattern: Literal["independent", "team", "pipeline", "adversarial", "fanout"] | None = None
    use_agent_sdk: bool = False
    agent_configs: list[AgentConfig] | None = None

    # Execution flags
    persist_task: bool = True
    persist_events: bool = False
    run_post_hooks: bool = True
    stream_tokens: bool = False
    shadow_run: bool = False  # True in A/B shadow execution — disables further shadow triggers

    # Phase overrides (skip classification / intelligence)
    classification_override: dict[str, Any] | None = None
    intelligence_override: dict[str, Any] | None = None
    # Evaluation-only ablation. This is intentionally absent from public API/MCP.
    eval_no_calibration: bool = False

    # System prompt override (idea-scoped chat sessions)
    system_prompt_override: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_chat(
        cls,
        session_id: str,
        message: str,
        product_id: str,
        workspace_id: str,
        user_id: str,
        conversation_messages: list[dict[str, Any]] | None = None,
        system_prompt_override: str | None = None,
    ) -> OrchestrationRequest:
        """Build a request from a portal chat interaction."""
        return cls(
            description=message,
            product_id=product_id,
            workspace_id=workspace_id,
            user_id=user_id,
            source="chat",
            conversation_messages=conversation_messages,
            persist_task=False,
            stream_tokens=True,
            system_prompt_override=system_prompt_override,
        )

    @classmethod
    def from_runner(cls, queue_item: dict[str, Any], product_id: str) -> OrchestrationRequest:
        """Build a request from a runner queue item."""
        return cls(
            description=queue_item.get("description", ""),
            product_id=product_id,
            workspace_id="workspace:default",
            user_id="user:runner",
            source="runner",
        )

    @classmethod
    def from_evolution(
        cls,
        system_prompt: str,
        task_prompt: str,
        pattern: str,
        product_id: str,
        agent_configs: list[AgentConfig] | None = None,
        use_agent_sdk: bool = True,
    ) -> OrchestrationRequest:
        """Build a request for the evolution engine's reflective cycles."""
        return cls(
            description=task_prompt,
            product_id=product_id,
            workspace_id="workspace:default",
            user_id="user:evolution",
            source="evolution",
            pattern=pattern,  # type: ignore[arg-type]
            use_agent_sdk=use_agent_sdk,
            agent_configs=agent_configs,
            persist_task=False,
            persist_events=True,
            run_post_hooks=False,
            classification_override={
                "domain_path": "self_reflection.system_health",
                "archetype": "sentinel",
                "mode": "reflective",
                "complexity": "complex",
            },
        )
