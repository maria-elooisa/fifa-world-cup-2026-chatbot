import asyncio
import logging
import os
import requests
import time
from typing import Any, Dict
from dotenv import load_dotenv
from .observability import get_observability_manager

load_dotenv()
logger = logging.getLogger(__name__)

class SearchWorker:
	"""
	Worker especializado em pesquisa na web usando Google Serper API.
	"""
	def __init__(self, worker_id: int):
		self.id = worker_id
		self.serper_api_key = os.getenv("SERPER_API_KEY")
		self.obs = get_observability_manager()
		self.cache_enabled = os.getenv("CACHE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
		self.cache_ttl = int(os.getenv("SEARCH_CACHE_TTL_SECONDS", os.getenv("CACHE_TTL_SECONDS", "300")))
		self._cache: Dict[str, Dict[str, Any]] = {}
		try:
			self.search_top_k = int(os.getenv("SEARCH_TOP_K", "3"))
		except Exception:
			self.search_top_k = 3
		
	async def exec_task(self, query: Any) -> dict:
		"""
		Executa uma pesquisa na web usando a query fornecida.
		"""
		obs = getattr(self, "obs", get_observability_manager())
		start_time = time.perf_counter()
		logger.info("SearchWorker %s starting search for: %s", self.id, query)
		obs.log_event(
			logger,
			"search_task_started",
			component="search_worker",
			worker_id=self.id,
			worker_type="search",
			source="serper",
		)
		
		query_text = str(query)
		cache_key = None
		if self.cache_enabled:
			cache_key = query_text
			cached = self._cache.get(cache_key)
			if cached and (time.time() - cached.get("ts", 0)) < self.cache_ttl:
				payload = dict(cached.get("value", {}))
				payload["cache_hit"] = True
				return payload

		with obs.span(
			"search_worker.exec_task",
			{"worker.id": self.id, "worker.type": "search"},
			span_kind="TOOL",
		):
			if not self.serper_api_key or self.serper_api_key == "sua_chave_serper_aqui":
				logger.warning("SERPER_API_KEY não configurada. Usando resultados simulados.")
				# Fallback: simulação de resultados
				await asyncio.sleep(0.3)
				duration_ms = obs.elapsed_ms(start_time)
				obs.log_event(
					logger,
					"search_task_finished",
					component="search_worker",
					worker_id=self.id,
					worker_type="search",
					source="simulated",
					duration_ms=duration_ms,
				)
				payload = {
					"worker_id": self.id,
					"worker_type": "search",
					"task": query,
					"result": f"[SIMULADO] Resultados de pesquisa para '{query}': A Copa do Mundo de 2026 será realizada nos EUA, Canadá e México.",
					"source": "simulated",
					"duration_ms": duration_ms,
				}
				if cache_key:
					self._cache[cache_key] = {"ts": time.time(), "value": payload}
				return payload
			
			# Pesquisa real usando Google Serper API
			try:
				search_payload = await self._search_serper(str(query))
				result_text = ""
				links = []
				if isinstance(search_payload, dict):
					result_text = search_payload.get("text", "")
					links = search_payload.get("links") or []
				else:
					result_text = search_payload
				duration_ms = obs.elapsed_ms(start_time)
				obs.log_event(
					logger,
					"search_task_finished",
					component="search_worker",
					worker_id=self.id,
					worker_type="search",
					source="serper",
					duration_ms=duration_ms,
				)
				payload = {
					"worker_id": self.id,
					"worker_type": "search",
					"task": query,
					"result": result_text,
					"links": links,
					"source": "serper",
					"duration_ms": duration_ms,
				}
				if cache_key:
					self._cache[cache_key] = {"ts": time.time(), "value": payload}
				return payload
			except Exception as e:
				logger.exception("Erro na pesquisa: %s", e)
				duration_ms = obs.elapsed_ms(start_time)
				obs.log_event(
					logger,
					"search_task_failed",
					level=logging.ERROR,
					component="search_worker",
					worker_id=self.id,
					worker_type="search",
					source="serper",
					duration_ms=duration_ms,
					error=str(e),
				)
				return {
					"worker_id": self.id,
					"worker_type": "search",
					"task": query,
					"error": str(e),
					"duration_ms": duration_ms,
				}
	
	async def _search_serper(self, query: str) -> dict | str:
		"""
		Faz a pesquisa usando Google Serper API.
		"""
		obs = getattr(self, "obs", get_observability_manager())
		url = "https://google.serper.dev/search"
		headers = {
			"X-API-KEY": self.serper_api_key,
			"Content-Type": "application/json"
		}
		top_k = max(1, int(getattr(self, "search_top_k", 3) or 3))
		payload = {
			"q": query,
			"num": max(1, top_k)  # número de resultados
		}
		
		with obs.span(
			"search_worker.serper_request",
			{"worker.id": self.id, "query.length": len(query)},
			span_kind="TOOL",
		):
			# Executa a requisição de forma assíncrona
			loop = asyncio.get_event_loop()
			response = await loop.run_in_executor(
				None,
				lambda: requests.post(url, json=payload, headers=headers, timeout=10)
			)
		
		if response.status_code != 200:
			raise Exception(f"Serper API retornou status {response.status_code}: {response.text}")
		
		data = response.json()
		
		# Extrai os principais resultados
		results = []
		links = []
		if "organic" in data:
			for item in data["organic"][:top_k]:
				title = item.get("title", "")
				snippet = item.get("snippet", "")
				link = item.get("link", "")
				results.append(f"- {title}: {snippet}")
				if link:
					links.append(link)
		
		if not results:
			return {"text": "Nenhum resultado encontrado.", "links": []}
		
		return {"text": "\n".join(results), "links": links}
