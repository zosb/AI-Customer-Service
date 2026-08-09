from __future__ import annotations

from app.core.config import Settings


def test_agent_agent_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.agent_requirement_max_chars == 4000
    assert settings.agent_system_context_max_chars == 24000
    assert settings.agent_max_services == 12
    assert settings.agent_max_tasks == 30
    assert settings.agent_planner_temperature == 0.1
    assert settings.agent_planner_repair_attempts == 2
