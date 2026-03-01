import asyncio
import json
import logging
import os
import re
import time
from typing import List, Any
from .search_worker import SearchWorker
from .rag_worker import RAGWorker
from .scope_validator import get_scope_validator, QueryScope
from .llm_generator import get_llm_generator
from .observability import get_observability_manager

logger = logging.getLogger(__name__)

class Supervisor:
	"""
	Orquestrador assíncrono com validação de escopo.
	
	Fluxo:
	1. Valida se pergunta está no escopo permitido (Copa do Mundo)
	2. Classifica tarefa (RAG vs Search)
	3. Executa worker apropriado
	4. Valida resposta antes de retornar
	"""
	def __init__(self, num_workers: int = 2):
		# CrewAI habilitado por padrão; USE_CREWAI=false desativa explicitamente.
		self.use_crewai = os.getenv("USE_CREWAI", "true").lower() in {"1", "true", "yes", "on"}
		self.validator = get_scope_validator()
		self.llm_generator = get_llm_generator()
		self.obs = get_observability_manager()
		self.rag_worker = RAGWorker(worker_id=1)
		self.search_worker = SearchWorker(worker_id=2)
		
		self.workers = [self.rag_worker, self.search_worker]
		for i in range(2, num_workers):
			if i % 2 == 0:
				self.workers.append(RAGWorker(worker_id=i+1))
			else:
				self.workers.append(SearchWorker(worker_id=i+1))
		
		logger.info("Supervisor iniciado com %d workers (%d search, %d rag)", 
					len(self.workers),
					sum(1 for w in self.workers if isinstance(w, SearchWorker)),
					sum(1 for w in self.workers if isinstance(w, RAGWorker)))
		if self.use_crewai:
			logger.info("CrewAI habilitado como padrão para orquestração (USE_CREWAI opcional)")
		else:
			logger.info("CrewAI desativado via USE_CREWAI=false (usando roteamento interno)")

	async def _run_crewai(self, task_text: str, scope_hint: str | None = None) -> str | None:
		"""Executa CrewAI em thread separada para evitar conflito com event loop."""
		try:
			from .crewai_executor import run_crewai
		except Exception as exc:
			logger.warning("CrewAI indisponível: %s", exc)
			return None
		try:
			return await asyncio.to_thread(run_crewai, task_text, scope_hint)
		except Exception as exc:
			logger.exception("Falha ao executar CrewAI: %s", exc)
			return None

	def _parse_crewai_payload(self, raw: str | None) -> tuple[str | None, dict | None]:
		if not raw:
			return None, None
		try:
			payload = json.loads(raw)
		except Exception:
			return raw, None
		if isinstance(payload, dict):
			context = payload.get("context")
			return context if context is not None else "", payload
		return raw, None

	def _classify_task(self, task: str) -> str:
		"""Classifica a tarefa e decide qual worker usar."""
		task_lower = str(task).lower()
		
		current_info_keywords = [
			'hotel', 'hotéis', 'hospedagem', 'acomodação', 'acomodacao',
			'passagem', 'voo', 'transporte', 'uber', 'taxi', 'metro',
			'restaurante', 'comida', 'turismo', 'pontos turísticos',
			'clima', 'tempo', 'previsão', 'previsao', 'temperatura',
			'preço', 'preco', 'custo', 'ingresso', 'bilhete',
			'próximo', 'proximo', 'perto', 'distância', 'distancia',
			'onde ficar', 'onde comer', 'como chegar', 'agenda',
			'cronograma atual', 'programação', 'programacao',
			'vendas', 'comprar', 'reservar', 'booking'
		]
		
		for keyword in current_info_keywords:
			if keyword in task_lower:
				logger.info(f"  🌐 Keyword '{keyword}' → SearchWorker")
				return 'search'
		
		historical_keywords = [
			'história', 'historia', 'histórico', 'historico',
			'campeão', 'campeao', 'vencedor', 'ganhador',
			'venceu', 'campeã', 'campea', 'título', 'titulo', 'final',
			'primeira copa', 'primeiro mundial', '1930', '1934', '1938',
			'quantas vezes', 'qual seleção', 'seleção que mais',
			'estatística', 'estatistica', 'dados históricos', 'recordes',
			'artilheiro', 'gols', 'jogadores famosos'
		]
		
		copa_2026_mentioned = '2026' in task_lower
		is_historical_query = any(keyword in task_lower for keyword in historical_keywords)
		
		if copa_2026_mentioned and not is_historical_query:
			logger.info(f"  🌐 Copa 2026 → SearchWorker")
			return 'search'

		# Se contém ano histórico (1930-2022), preferir RAG
		historical_year = re.search(r"\b(19[3-9]\d|20[0-1]\d|202[0-2])\b", task_lower)
		if historical_year and not copa_2026_mentioned:
			logger.info(f"  🎯 Ano histórico {historical_year.group(0)} → RAGWorker")
			return 'rag'
		
		historical_copa_keywords = [
			'copa', 'mundial', 'world cup', 'fifa', 'estádio', 'estadio',
			'seleção', 'selecao', 'brasil', 'mexico', 'canadá', 'canada', 'eua',
			'sede', 'jogo', 'partida', 'grupo', 'classificação', 'classificacao'
		]
		
		for keyword in historical_copa_keywords:
			if keyword in task_lower and is_historical_query:
				logger.info(f"  🎯 Keyword '{keyword}' + histórico → RAGWorker")
				return 'rag'
		
		if any(keyword in task_lower for keyword in historical_copa_keywords):
			logger.info(f"  🌐 Copa sem contexto histórico → SearchWorker")
			return 'search'
		
		logger.info(f"  🌐 Consulta geral → SearchWorker")
		return 'search'
	
	async def dispatch(self, tasks: List[Any]) -> List[dict]:
		"""Processa tarefas com validação de escopo."""
		obs = getattr(self, "obs", get_observability_manager())
		dispatch_start = time.perf_counter()
		obs.log_event(
			logger,
			"dispatch_started",
			component="supervisor",
			task_count=len(tasks),
		)

		async def process_task_with_validation(task: Any):
			task_start = time.perf_counter()
			task_text = str(task.get("query", "")).strip() if isinstance(task, dict) else str(task)
			preferred_language = task.get("preferred_language") if isinstance(task, dict) else None
			logger.info("🔍 Supervisor analisando tarefa: '%s'", task_text)
			with obs.span(
				"supervisor.process_task",
				{"task.text": task_text},
				span_kind="CHAIN",
			) as span:
				def _record(worker_type: str, duration_ms: float, ok: bool, scope_value: str | None = None) -> None:
					try:
						obs.record_task_metrics(worker_type, duration_ms, ok, query_scope=scope_value)
					except Exception:
						pass

				def _attach_tokens(llm_payload: dict | None) -> None:
					if span is None or not llm_payload:
						return
					tokens = llm_payload.get("tokens_used")
					if tokens is None:
						return
					try:
						total_tokens = int(tokens)
						span.set_attribute("llm.token_count.total", total_tokens)
						span.set_attribute("llm.usage.total_tokens", total_tokens)
						span.set_attribute("llm.total_tokens", total_tokens)
						span.set_attribute("total_tokens", total_tokens)
					except Exception:
						pass

				def _attach_io_cost(prompt_text: str | None, response_text: str | None, llm_payload: dict | None) -> None:
					if span is None:
						return
					try:
						max_in = int(os.getenv("TRACE_INPUT_MAX_CHARS", "2000"))
					except Exception:
						max_in = 2000
					try:
						max_out = int(os.getenv("TRACE_OUTPUT_MAX_CHARS", "2000"))
					except Exception:
						max_out = 2000
					def _truncate(text: str | None, limit: int) -> str:
						if not text:
							return ""
						if limit <= 0:
							return ""
						if len(text) <= limit:
							return text
						return text[:limit] + " ..."
					try:
						input_value = _truncate(prompt_text, max_in)
						output_value = _truncate(response_text, max_out)
						span.set_attribute("input.value", input_value)
						span.set_attribute("output.value", output_value)
						span.set_attribute("input.mime_type", "text/plain")
						span.set_attribute("output.mime_type", "text/plain")
						# Compatibilidade adicional com variantes OpenInference
						span.set_attribute("openinference.input.value", input_value)
						span.set_attribute("openinference.output.value", output_value)
						span.set_attribute("openinference.input.mime_type", "text/plain")
						span.set_attribute("openinference.output.mime_type", "text/plain")
					except Exception:
						pass
					if llm_payload:
						cost = llm_payload.get("total_cost")
						if cost is not None:
							try:
								span.set_attribute("llm.total_cost", float(cost))
								span.set_attribute("llm.cost.total", float(cost))
								span.set_attribute("total_cost", float(cost))
							except Exception:
								pass
				def _record_quality_flags(
					has_source: bool | None,
					context_source: str | None = None,
					ambiguous: bool = False,
				) -> None:
					try:
						if ambiguous:
							obs.record_quality_flag("ambiguous", True, context_source)
						if has_source is not None:
							obs.record_quality_flag("has_source", bool(has_source), context_source)
					except Exception:
						pass
			
				# PASSO 1: Valida escopo
				scope, scope_reason = self.validator.validate_query(task_text)
				scope_value = scope.value if scope else None
				entities = getattr(self.validator, "last_entities", None) or {}
				rewritten_query = self.validator.rewrite_query(task_text, scope)
				worker_query: Any = rewritten_query
				if isinstance(task, dict):
					worker_query = dict(task)
					worker_query["query"] = rewritten_query
				rag_query: Any = worker_query
				search_query: Any = rewritten_query
				if rewritten_query and rewritten_query != task_text:
					obs.log_event(
						logger,
						"query_rewritten",
						component="supervisor",
						original=task_text,
						rewritten=rewritten_query,
						query_scope=scope_value,
					)
					if span is not None:
						try:
							span.set_attribute("query.rewritten", rewritten_query)
						except Exception:
							pass
				def _format_entities(entities_payload: dict) -> str:
					if not entities_payload:
						return ""
					label_map = {
						"years": "anos",
						"countries": "países",
						"cities": "cidades",
						"players": "jogadores",
						"tournament_terms": "termos",
						"stages": "fases",
					}
					parts = []
					for key, values in entities_payload.items():
						if not values:
							continue
						label = label_map.get(key, key)
						if isinstance(values, (list, tuple)):
							val_str = ", ".join(str(v) for v in values)
						else:
							val_str = str(values)
						if val_str:
							parts.append(f"{label}: {val_str}")
					if not parts:
						return ""
					return "Entidades detectadas: " + " | ".join(parts)
				def _with_entities(payload: dict) -> dict:
					if entities:
						payload["entities"] = entities
					return payload
				_missing = object()
				def _llm_response_payload(
					llm_result: dict,
					duration_ms: float,
					context_source: str,
					*,
					pages: Any = _missing,
					links: Any = _missing,
				) -> dict:
					payload = {
						"worker_id": "supervisor",
						"worker_type": "llm_generator",
						"task": task_text,
						"result": llm_result["response"],
						"model": llm_result.get("model", "gpt-4o-mini"),
						"tokens_used": llm_result.get("tokens_used", 0),
						"source": "llm",
						"context_source": context_source,
						"duration_ms": duration_ms,
					}
					if pages is not _missing:
						payload["pages"] = pages
					if links is not _missing:
						payload["links"] = links
					return _with_entities(payload)
				if scope_value:
					obs.record_scope_metrics(scope_value)
				
				if scope == QueryScope.OUT_OF_SCOPE:
					logger.warning(f"  ❌ Fora do escopo: {scope_reason}")
					duration_ms = obs.elapsed_ms(task_start)
					obs.log_event(
						logger,
						"task_rejected_out_of_scope",
						component="supervisor",
						query_scope=scope.value,
						duration_ms=duration_ms,
					)
					_record("validation", duration_ms, False, scope_value)
					obs.record_scope_rejection("out_of_scope")
					obs.record_response_source("validation", "out_of_scope")
					_record_quality_flags(False, "validation", ambiguous=False)
					return _with_entities({
						"worker_id": "supervisor",
						"worker_type": "validation",
						"task": task_text,
						"result": scope_reason,
						"source": "validator",
						"duration_ms": duration_ms,
					})
				
				if scope == QueryScope.CLARIFY:
					logger.info("  ℹ️  Pergunta ambígua - solicitando clarificação")
					duration_ms = obs.elapsed_ms(task_start)
					clarify_message = scope_reason
					entities_hint = _format_entities(entities)
					if entities_hint:
						clarify_message = f"{clarify_message}\n\n{entities_hint}"
					obs.log_event(
						logger,
						"task_requires_clarification",
						component="supervisor",
						query_scope=scope.value,
						duration_ms=duration_ms,
					)
					_record("clarification", duration_ms, True, scope_value)
					obs.record_response_source("clarification", "validation")
					_record_quality_flags(False, "validation", ambiguous=True)
					return _with_entities({
						"worker_id": "supervisor",
						"worker_type": "clarification",
						"task": task_text,
						"result": clarify_message,
						"source": "clarification",
						"duration_ms": duration_ms,
					})
				
				# PASSO 2: Classifica tarefa (ou delega ao CrewAI)
				if self.use_crewai:
					crewai_start = time.perf_counter()
					obs.log_event(
						logger,
						"crewai_dispatch_started",
						component="supervisor",
						worker_type="crewai",
					)
					crewai_raw = await self._run_crewai(rewritten_query, scope_value)
					obs.record_worker_latency("crewai", obs.elapsed_ms(crewai_start))
					if crewai_raw:
						crewai_context, payload = self._parse_crewai_payload(crewai_raw)
						payload_source = None
						payload_error = None
						payload_fallback = False
						context_source = None
						payload_pages = []
						payload_links = []
						if payload:
							payload_source = payload.get("source")
							payload_error = payload.get("error")
							payload_fallback = bool(payload.get("fallback_used"))
							payload_pages = payload.get("pages") or []
							payload_links = payload.get("links") or []
							if payload_source in {"search", "serper", "web"}:
								context_source = "web"
							elif payload_source == "rag":
								context_source = "rag"
							if context_source:
								obs.record_response_source(context_source, "crewai")
							if payload_fallback:
								obs.record_fallback("crewai_tool_fallback", context_source or "crewai")
							if payload_error:
								obs.log_event(
									logger,
									"crewai_context_error",
									component="supervisor",
									error=str(payload_error),
								)
						llm_result = await self.llm_generator.generate(
							query=task_text,
							context=crewai_context or None,
							language_request=preferred_language,
						)
						duration_ms = obs.elapsed_ms(task_start)
						obs.log_event(
							logger,
							"task_finished",
							component="supervisor",
							worker_type="crewai",
							source="llm",
							duration_ms=duration_ms,
						)
						_record("crewai", duration_ms, True, scope_value)
						obs.record_llm_metrics(
							"crewai",
							llm_result.get("tokens_used", 0),
							llm_result.get("response"),
						)
						_attach_tokens(llm_result)
						_attach_io_cost(task_text, llm_result.get("response"), llm_result)
						if not payload_source:
							obs.record_response_source(
								llm_result.get("source", "llm"),
								"crewai",
							)
						_record_quality_flags(
							bool(payload_pages or payload_links or context_source),
							context_source or payload_source or "crewai",
							ambiguous=False,
						)
						return _llm_response_payload(
							llm_result,
							duration_ms,
							context_source or payload_source or "crewai",
							pages=payload_pages,
							links=payload_links,
						)
					obs.log_event(
						logger,
						"crewai_dispatch_fallback",
						component="supervisor",
						worker_type="crewai",
					)
					obs.record_fallback("crewai_unavailable", "crewai")

				# PASSO 2 (fallback): Classifica tarefa localmente
				chosen_worker_type = self._classify_task(task_text)
				logger.info(f"  📋 Escopo: {scope.value} → Worker: {chosen_worker_type}")
				
				# PASSO 3: Executa worker
				if chosen_worker_type == 'rag':
					logger.info("  └─ Executando RAGWorker...")
					try:
						rag_start = time.perf_counter()
						result = await self.rag_worker.exec_task(rag_query)
						obs.record_worker_latency("rag", obs.elapsed_ms(rag_start))
						rag_pages = result.get("pages") or []
						is_valid, reason = self.validator.validate_response(
							task_text, result.get("result", ""), "rag"
						)
						
						if is_valid:
							logger.info("  ✅ Resposta válida")
							# PASSO 4: Gera resposta com LLM
							context = result.get("result", "")
							llm_result = await self.llm_generator.generate(
								query=task_text,
								context=context,
								language_request=preferred_language,
							)
							duration_ms = obs.elapsed_ms(task_start)
							obs.log_event(
								logger,
								"task_finished",
								component="supervisor",
								worker_type="rag",
								source="llm",
								duration_ms=duration_ms,
							)
							_record("rag", duration_ms, True, scope_value)
							obs.record_llm_metrics(
								"rag",
								llm_result.get("tokens_used", 0),
								llm_result.get("response"),
							)
							_attach_tokens(llm_result)
							_attach_io_cost(task_text, llm_result.get("response"), llm_result)
							obs.record_response_source(
								llm_result.get("source", "llm"),
								"rag",
							)
							_record_quality_flags(bool(rag_pages), "rag", ambiguous=False)
							return _llm_response_payload(
								llm_result,
								duration_ms,
								"rag",
								pages=rag_pages,
							)
						else:
							logger.warning(f"  ⚠️  Resposta inválida")
							result = await self.search_worker.exec_task(search_query)
							context = result.get("result", "")
							llm_result = await self.llm_generator.generate(
								query=task_text,
								context=context,
								language_request=preferred_language,
							)
							duration_ms = obs.elapsed_ms(task_start)
							obs.log_event(
								logger,
								"task_finished_with_fallback",
								component="supervisor",
								worker_type="search",
								source="llm",
								duration_ms=duration_ms,
							)
							_record("search_fallback", duration_ms, True, scope_value)
							obs.record_fallback("rag_invalid", "search")
							obs.record_llm_metrics(
								"search_fallback",
								llm_result.get("tokens_used", 0),
								llm_result.get("response"),
							)
							_attach_tokens(llm_result)
							_attach_io_cost(task_text, llm_result.get("response"), llm_result)
							obs.record_response_source(
								llm_result.get("source", "llm"),
								"web",
							)
							_record_quality_flags(bool(result.get("links")), "web", ambiguous=False)
							return _llm_response_payload(
								llm_result,
								duration_ms,
								"web",
								links=result.get("links") or [],
							)
						
					except Exception as e:
						logger.exception("  ❌ Erro no RAG: %s", e)
						result = await self.search_worker.exec_task(search_query)
						context = result.get("result", "")
						llm_result = await self.llm_generator.generate(
							query=task_text,
							context=context,
							language_request=preferred_language,
						)
						duration_ms = obs.elapsed_ms(task_start)
						obs.log_event(
							logger,
							"task_finished_after_rag_error",
							component="supervisor",
							worker_type="search",
							source="llm",
							duration_ms=duration_ms,
						)
						_record("search_fallback", duration_ms, True, scope_value)
						obs.record_fallback("rag_error", "search")
						obs.record_llm_metrics(
							"search_fallback",
							llm_result.get("tokens_used", 0),
							llm_result.get("response"),
						)
						_attach_tokens(llm_result)
						_attach_io_cost(task_text, llm_result.get("response"), llm_result)
						obs.record_response_source(
							llm_result.get("source", "llm"),
							"web",
						)
						_record_quality_flags(bool(result.get("links")), "web", ambiguous=False)
						return _llm_response_payload(
							llm_result,
							duration_ms,
							"web",
							links=result.get("links") or [],
						)
				
				else:
					logger.info("  └─ Executando SearchWorker...")
					try:
						search_start = time.perf_counter()
						result = await self.search_worker.exec_task(search_query)
						obs.record_worker_latency("search", obs.elapsed_ms(search_start))
						context = result.get("result", "")
						is_valid, reason = self.validator.validate_response(
							task_text, context, "serper"
						)
						if not is_valid:
							logger.warning(f"  ⚠️  Resposta inválida")
						
						# PASSO 4: Gera resposta com LLM
						llm_result = await self.llm_generator.generate(
							query=task_text,
							context=context,
							language_request=preferred_language,
						)
						logger.info("  ✅ Tarefa completada com LLM")
						duration_ms = obs.elapsed_ms(task_start)
						obs.log_event(
							logger,
							"task_finished",
							component="supervisor",
							worker_type="search",
							source="llm",
							duration_ms=duration_ms,
						)
						_record("search", duration_ms, True, scope_value)
						obs.record_llm_metrics(
							"search",
							llm_result.get("tokens_used", 0),
							llm_result.get("response"),
						)
						_attach_tokens(llm_result)
						_attach_io_cost(task_text, llm_result.get("response"), llm_result)
						obs.record_response_source(
							llm_result.get("source", "llm"),
							"web",
						)
						_record_quality_flags(bool(result.get("links")), "web", ambiguous=False)
						return _llm_response_payload(
							llm_result,
							duration_ms,
							"web",
							links=result.get("links") or [],
						)
					except Exception as e:
						logger.exception("  ❌ Erro no Search: %s", e)
						duration_ms = obs.elapsed_ms(task_start)
						obs.log_event(
							logger,
							"task_failed",
							level=logging.ERROR,
							component="supervisor",
							worker_type="search",
							source="supervisor",
							duration_ms=duration_ms,
							error=str(e),
						)
						_record("search", duration_ms, False, scope_value)
						obs.record_fallback("search_error", "search")
						return _with_entities({
							"worker_id": "supervisor",
							"task": task_text,
							"error": str(e),
							"result": "Não foi possível processar a consulta.",
							"duration_ms": duration_ms,
						})

		coros = [process_task_with_validation(task) for task in tasks]
		results = await asyncio.gather(*coros, return_exceptions=False)
		logger.info("✅ Dispatch complete: %d tasks processadas", len(tasks))
		obs.log_event(
			logger,
			"dispatch_finished",
			component="supervisor",
			task_count=len(tasks),
			duration_ms=obs.elapsed_ms(dispatch_start),
		)
		return results

	async def health_check(self) -> dict:
		"""Health-check dos workers."""
		status = {"workers": []}
		for w in self.workers:
			worker_type = "search" if isinstance(w, SearchWorker) else "rag"
			status["workers"].append({"id": w.id, "type": worker_type, "alive": True})
		return status
