import json
import logging
import os
import re
import time

from .crewai_tools import RagTool, SearchTool
from .observability import get_observability_manager

logger = logging.getLogger(__name__)


def _parse_payload(raw: str) -> dict | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None


def _fallback_tool(query: str, prefer: str | None, obs) -> str:
    order = []
    if prefer == "rag":
        order = [RagTool(), SearchTool()]
    elif prefer == "search":
        order = [SearchTool(), RagTool()]
    else:
        order = [RagTool(), SearchTool()]

    for tool in order:
        tool_name = "rag" if isinstance(tool, RagTool) else "search"
        try:
            raw = tool._run(query)
            payload = _parse_payload(raw)
            if payload and payload.get("context"):
                payload["fallback_used"] = True
                payload.setdefault("source", tool_name)
                obs.log_event(
                    logger,
                    "crewai_fallback_success",
                    component="crewai_executor",
                    tool=tool_name,
                )
                return json.dumps(payload, ensure_ascii=True)
            obs.log_event(
                logger,
                "crewai_fallback_empty",
                component="crewai_executor",
                tool=tool_name,
            )
        except Exception as exc:
            obs.log_event(
                logger,
                "crewai_fallback_error",
                component="crewai_executor",
                tool=tool_name,
                error=str(exc),
            )

    payload = {
        "source": "fallback_error",
        "context": "",
        "error": "fallback_failed",
        "fallback_used": True,
    }
    return json.dumps(payload, ensure_ascii=True)


def run_crewai(query: str, scope_hint: str | None = None) -> str:
    """Executa orquestração via CrewAI e retorna contexto para o LLM."""
    # Importa CrewAI somente quando necessário para evitar custo/erros na carga.
    from crewai import Agent, Crew, Process, Task

    model_name = os.getenv("LLM_MODEL", "gpt-4.1-nano")
    obs = get_observability_manager()
    scope_value = (scope_hint or "").lower().strip()

    supervisor = Agent(
        role="Supervisor",
        goal="Delegar a consulta ao worker correto e devolver contexto útil.",
        backstory=(
            "Você coordena RAG e Search para perguntas sobre a Copa do Mundo. "
            "Escolha a ferramenta adequada e devolva apenas o contexto encontrado."
        ),
        allow_delegation=True,
        verbose=False,
        llm=model_name,
    )

    rag_agent = Agent(
        role="RAGWorker",
        goal="Buscar contexto na base interna (RAG).",
        backstory="Especialista em consulta à base local.",
        tools=[RagTool()],
        verbose=False,
        llm=model_name,
    )

    search_agent = Agent(
        role="SearchWorker",
        goal="Buscar contexto atualizado na web.",
        backstory="Especialista em pesquisa web.",
        tools=[SearchTool()],
        verbose=False,
        llm=model_name,
    )

    allowed_agents = [rag_agent, search_agent]
    prefer_tool = None
    if scope_value in {"rag_only", "rag"}:
        allowed_agents = [rag_agent]
        prefer_tool = "rag"
    elif scope_value in {"web_only", "web", "search"}:
        allowed_agents = [search_agent]
        prefer_tool = "search"

    task = Task(
        description=(
            f"Pergunta do usuário: {query}\n"
            f"Escopo validado: {scope_value or 'both'}.\n"
            "Se o escopo for RAG_ONLY, use RAG. Se for WEB_ONLY, use Search.\n"
            "Chame apenas UMA ferramenta e retorne EXATAMENTE o JSON retornado pela ferramenta, sem texto extra."
        ),
        expected_output="JSON da ferramenta com source/context/error.",
        agent=supervisor,
    )

    crew = Crew(
        agents=allowed_agents,
        tasks=[task],
        process=Process.hierarchical,
        manager_agent=supervisor,
        tracing=True,
    )

    obs.log_event(
        logger,
        "crewai_kickoff_started",
        component="crewai_executor",
        scope_hint=scope_value or "both",
    )
    start = time.perf_counter()
    try:
        result = crew.kickoff()
    except Exception as exc:
        obs.log_event(
            logger,
            "crewai_kickoff_error",
            component="crewai_executor",
            error=str(exc),
        )
        return _fallback_tool(query, prefer_tool, obs)
    finally:
        obs.log_event(
            logger,
            "crewai_kickoff_finished",
            component="crewai_executor",
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    raw = str(result)
    payload = _parse_payload(raw)
    if payload:
        payload.setdefault("fallback_used", False)
        tool = payload.get("source", "unknown")
        obs.log_event(
            logger,
            "crewai_output_parsed",
            component="crewai_executor",
            tool=tool,
        )
        if payload.get("error") or not payload.get("context"):
            obs.log_event(
                logger,
                "crewai_tool_failed",
                component="crewai_executor",
                tool=tool,
                error=str(payload.get("error")),
            )
            if prefer_tool:
                return _fallback_tool(query, prefer_tool, obs)
            return _fallback_tool(query, tool if tool in {"rag", "search"} else None, obs)
        return json.dumps(payload, ensure_ascii=True)

    obs.log_event(
        logger,
        "crewai_output_unparsed",
        component="crewai_executor",
    )
    return _fallback_tool(query, prefer_tool, obs)
