import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from crew.observability import init_observability
from crew.supervisor import Supervisor

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Pergunta sobre Copa do Mundo.")
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Filtros opcionais para RAG (path_contains, keywords, etc.).",
    )


class BatchChatRequest(BaseModel):
    items: List[ChatRequest] = Field(..., min_length=1, max_length=20)


def _build_supervisor_from_env() -> Supervisor:
    num_workers_raw = os.getenv("NUM_WORKERS", "2")
    try:
        num_workers = max(1, int(num_workers_raw))
    except ValueError:
        logger.warning(
            "NUM_WORKERS invalido (%s), usando padrao=2", num_workers_raw
        )
        num_workers = 2
    return Supervisor(num_workers=num_workers)


def _get_supervisor() -> Supervisor:
    supervisor = getattr(app.state, "supervisor", None)
    if supervisor is None:
        supervisor = _build_supervisor_from_env()
        app.state.supervisor = supervisor
    return supervisor


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_observability()
    _app.state.supervisor = _build_supervisor_from_env()
    logger.info("fastapi_startup_complete")
    yield

def _to_task(payload: ChatRequest) -> Any:
    if payload.filters:
        return {"query": payload.query, "filters": payload.filters}
    return payload.query


app = FastAPI(
    title="FIFA World Cup Chatbot API",
    description="API para perguntas sobre Copa do Mundo com roteamento RAG/Web.",
    version="1.0.0",
    lifespan=_lifespan,
)


@app.get("/")
async def root() -> Dict[str, str]:
    return {
        "name": "fifa-world-cup-chatbot-api",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    supervisor = _get_supervisor()
    workers = await supervisor.health_check()
    return {"status": "ok", **workers}


@app.post("/chat")
async def chat(payload: ChatRequest) -> Dict[str, Any]:
    supervisor = _get_supervisor()
    task = _to_task(payload)
    result = (await supervisor.dispatch([task]))[0]
    return {"ok": "error" not in result, "result": result}


@app.post("/chat/batch")
async def chat_batch(payload: BatchChatRequest) -> Dict[str, Any]:
    supervisor = _get_supervisor()
    tasks = [_to_task(item) for item in payload.items]
    results = await supervisor.dispatch(tasks)
    return {"count": len(results), "results": results}


async def run_demo() -> None:
    init_observability()
    demo_supervisor = Supervisor(num_workers=3)
    tasks = [
        "buscar histórico da Copa",
        "consultar estádios 2026",
        "verificar regras de viagem",
        "pesquisar cidades-sede",
    ]
    results = await demo_supervisor.dispatch(tasks)
    for result in results:
        logger.info(result)


if __name__ == "__main__":
    asyncio.run(run_demo())
