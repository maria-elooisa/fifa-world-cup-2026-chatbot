import asyncio
import json
import logging

from crewai.tools.base_tool import BaseTool

from .rag_worker import RAGWorker
from .search_worker import SearchWorker

logger = logging.getLogger(__name__)


def _run_sync(coro):
    """Executa coroutine em contexto síncrono."""
    return asyncio.run(coro)

def _format_payload(source: str, context: str, error: str | None = None, **meta) -> str:
    payload = {
        "source": source,
        "context": context or "",
        "error": error,
    }
    if meta:
        payload.update(meta)
    return json.dumps(payload, ensure_ascii=True)


class RagTool(BaseTool):
    name: str = "RAG Tool"
    description: str = "Consulta a base RAG interna e retorna contexto relevante em JSON."

    def _run(self, query: str) -> str:
        try:
            result = _run_sync(RAGWorker(worker_id=1).exec_task(query))
            return _format_payload(
                "rag",
                result.get("result", ""),
                pages=result.get("pages") or [],
            )
        except Exception as exc:
            logger.exception("Falha no RAGTool: %s", exc)
            return _format_payload("rag", "", str(exc))


class SearchTool(BaseTool):
    name: str = "Search Tool"
    description: str = "Pesquisa informações atualizadas na web via Serper em JSON."

    def _run(self, query: str) -> str:
        try:
            result = _run_sync(SearchWorker(worker_id=2).exec_task(query))
            return _format_payload(
                "search",
                result.get("result", ""),
                links=result.get("links") or [],
            )
        except Exception as exc:
            logger.exception("Falha no SearchTool: %s", exc)
            return _format_payload("search", "", str(exc))
