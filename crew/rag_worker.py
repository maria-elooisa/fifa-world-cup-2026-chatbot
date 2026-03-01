import asyncio
import logging
import os
import json
import math
import re
import time
from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional
from functools import lru_cache
from dotenv import load_dotenv
from .observability import get_observability_manager

load_dotenv()
logger = logging.getLogger(__name__)

class RAGWorker:
	"""
	Worker especializado em consulta RAG (Retrieval-Augmented Generation).
	Consulta a base de conhecimento interna (embeddings).
	"""
	def __init__(self, worker_id: int, similarity_threshold: float = 0.5):
		self.id = worker_id
		self.openai_api_key = os.getenv("OPENAI_API_KEY")
		self.embeddings_path = Path(__file__).resolve().parents[1] / "data" / "embeddings.json"
		self.faiss_index_path = Path(__file__).resolve().parents[1] / "data" / "faiss" / "index.faiss"
		self.faiss_metadata_path = Path(__file__).resolve().parents[1] / "data" / "faiss" / "metadata.json"
		self.use_faiss = os.getenv("RAG_USE_FAISS", "true").lower() in {"1", "true", "yes", "on"}
		self.embeddings_data = self._load_embeddings()
		self.similarity_threshold = similarity_threshold
		self._embedding_cache: Dict[str, List[float]] = {}
		self._inverted_index: Dict[str, List[int]] = {}
		self._build_inverted_index()
		self.obs = get_observability_manager()
		self.faiss_index = None
		self.faiss_metadata: List[Dict[str, Any]] = []
		self._load_faiss_index()
		self.cache_enabled = os.getenv("CACHE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
		self.cache_ttl = int(os.getenv("RAG_CACHE_TTL_SECONDS", os.getenv("CACHE_TTL_SECONDS", "300")))
		self._cache: Dict[str, Dict[str, Any]] = {}
	
	def _load_embeddings(self) -> List[Dict]:
		"""Carrega embeddings do arquivo JSON."""
		if not self.embeddings_path.exists():
			logger.warning(f"Arquivo de embeddings não encontrado: {self.embeddings_path}")
			return []
		try:
			with open(self.embeddings_path, 'r', encoding='utf-8') as f:
				data = json.load(f)
			logger.info(f"Carregados {len(data)} chunks de embeddings")
			return data
		except Exception as e:
			logger.error(f"Erro ao carregar embeddings: {e}")
			return []
	
	@staticmethod
	def _tokenize(text: str) -> List[str]:
		"""Tokenização simples para BM25 (remove stop words)."""
		words = re.findall(r'\b\w+\b', text.lower())
		stop_words = {'o', 'a', 'de', 'que', 'e', 'do', 'da', 'em', 'um', 'para', 'é', 'com', 'não', 'uma', 'os', 'no', 'se', 'na', 'por', 'mais', 'as', 'dos', 'como', 'mas', 'foi', 'ao', 'ele', 'das', 'tem', 'à', 'seu', 'sua', 'ou', 'ser', 'quando', 'muito', 'há', 'nos', 'já', 'está', 'eu', 'também', 'só', 'pelo', 'pela', 'até', 'isso', 'ela', 'entre', 'era', 'depois', 'sem', 'mesmo', 'aos', 'ter', 'seus'}
		return [w for w in words if w not in stop_words and len(w) > 2]
	
	def _build_inverted_index(self) -> None:
		"""Constrói índice invertido para busca léxica (BM25)."""
		for idx, entry in enumerate(self.embeddings_data):
			words = self._tokenize(entry.get('text', ''))
			for word in set(words):
				if word not in self._inverted_index:
					self._inverted_index[word] = []
					self._inverted_index[word].append(idx)

	def _load_faiss_index(self) -> None:
		"""Carrega índice FAISS persistente (opcional)."""
		if not self.use_faiss:
			return
		if not self.faiss_index_path.exists() or not self.faiss_metadata_path.exists():
			logger.info("Índice FAISS não encontrado, usando busca linear híbrida.")
			return
		try:
			import faiss
			with open(self.faiss_metadata_path, "r", encoding="utf-8") as fh:
				self.faiss_metadata = json.load(fh)
			self.faiss_index = faiss.read_index(str(self.faiss_index_path))
			logger.info("FAISS carregado com %d vetores", len(self.faiss_metadata))
		except Exception as e:
			logger.warning("Falha ao carregar FAISS. Fallback para busca linear: %s", e)
			self.faiss_index = None
			self.faiss_metadata = []
	
	def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
		"""Calcula similaridade de cosseno entre dois vetores."""
		dot_product = sum(a * b for a, b in zip(vec1, vec2))
		magnitude1 = math.sqrt(sum(a * a for a in vec1))
		magnitude2 = math.sqrt(sum(b * b for b in vec2))
		if magnitude1 == 0 or magnitude2 == 0:
			return 0.0
		return dot_product / (magnitude1 * magnitude2)
	
	def _bm25_score(self, query_words: List[str], entry_idx: int) -> float:
		"""Calcula score BM25 para um documento (métrica padrão em busca textual)."""
		if entry_idx >= len(self.embeddings_data):
			return 0.0
		
		k1, b = 1.5, 0.75  # Parâmetros BM25 padrão
		entry = self.embeddings_data[entry_idx]
		doc_length = len(self._tokenize(entry.get('text', '')))
		avg_doc_length = sum(len(self._tokenize(e.get('text', ''))) for e in self.embeddings_data) / len(self.embeddings_data) if self.embeddings_data else 1
		
		doc_term_freqs = {}
		for word in self._tokenize(entry.get('text', '')):
			doc_term_freqs[word] = doc_term_freqs.get(word, 0) + 1
		
		idf_sum = 0
		for word in set(query_words):
			if word not in self._inverted_index:
				continue
			
			docs_with_term = len(self._inverted_index[word])
			total_docs = len(self.embeddings_data)
			idf = math.log(1 + (total_docs - docs_with_term + 0.5) / (docs_with_term + 0.5))
			
			tf = doc_term_freqs.get(word, 0)
			numerator = tf * (k1 + 1)
			denominator = tf + k1 * (1 - b + b * (doc_length / avg_doc_length))
			idf_sum += idf * (numerator / denominator)
		
		return idf_sum
	

	
	def _parse_query_input(self, query_input: Any) -> Tuple[str, Dict[str, Any]]:
		"""
		Aceita:
		- string simples
		- dict no formato {"query": "...", "filters": {...}}
		"""
		if isinstance(query_input, dict):
			query = str(query_input.get("query", "")).strip()
			filters = query_input.get("filters", {}) or {}
			return query, filters
		return str(query_input), {}

	def _matches_filters(self, entry: Dict[str, Any], filters: Optional[Dict[str, Any]]) -> bool:
		"""Valida metadados de um entry contra filtros opcionais."""
		if not filters:
			return True

		path = str(entry.get("path", "")).lower()
		text = str(entry.get("text", "")).lower()
		chunk_id = entry.get("chunk_id")

		path_contains = filters.get("path_contains")
		if path_contains and str(path_contains).lower() not in path:
			return False

		source_paths = filters.get("source_paths")
		if source_paths:
			normalized = {str(p).lower() for p in source_paths}
			if path not in normalized:
				return False

		min_chunk_id = filters.get("min_chunk_id")
		if min_chunk_id is not None and isinstance(chunk_id, int) and chunk_id < int(min_chunk_id):
			return False

		max_chunk_id = filters.get("max_chunk_id")
		if max_chunk_id is not None and isinstance(chunk_id, int) and chunk_id > int(max_chunk_id):
			return False

		keywords = filters.get("keywords")
		if keywords:
			for keyword in keywords:
				if str(keyword).lower() not in text:
					return False

		return True

	def _search_similar(
		self,
		query_embedding: List[float],
		query_text: str,
		top_k: int = 3,
		semantic_weight: float = 0.7,
		lexical_weight: float = 0.3,
		filters: Optional[Dict[str, Any]] = None,
	) -> List[tuple]:
		"""Busca híbrida: combina resultado semântico (embedding) e léxico (BM25)."""
		if not self.embeddings_data:
			return []
		
		# Tokeniza query para BM25
		query_words = self._tokenize(query_text)
		
		# Calcula scores para cada chunk
		scores = []
		for idx, entry in enumerate(self.embeddings_data):
			if 'embedding' not in entry:
				continue
			if not self._matches_filters(entry, filters):
				continue
			
			# Score semântico (similaridade de cosseno)
			semantic_score = self._cosine_similarity(query_embedding, entry['embedding'])
			
			# Score léxico (BM25)
			bm25_score_raw = self._bm25_score(query_words, idx)
			lexical_score = min(1.0, bm25_score_raw / 50) if bm25_score_raw > 0 else 0.0
			
			# Score combinado (weighted sum)
			combined_score = (semantic_score * semantic_weight) + (lexical_score * lexical_weight)
			
			# Filtra por threshold
			if combined_score >= self.similarity_threshold:
				scores.append((combined_score, entry, semantic_score, lexical_score))
		
		# Ordena por score combinado (maior primeiro)
		scores.sort(reverse=True, key=lambda x: x[0])
		
		# Retorna top_k resultados
		return scores[:top_k]

	def _search_similar_faiss(
		self,
		query_embedding: List[float],
		top_k: int = 3,
		filters: Optional[Dict[str, Any]] = None,
	) -> List[tuple]:
		"""Busca vetorial com índice FAISS persistente."""
		if self.faiss_index is None or not self.faiss_metadata:
			return []
		try:
			import faiss
			import numpy as np

			query_vec = np.array([query_embedding], dtype="float32")
			faiss.normalize_L2(query_vec)
			candidate_k = max(top_k * 10, 30)
			scores, ids = self.faiss_index.search(query_vec, candidate_k)

			results = []
			for score, idx in zip(scores[0], ids[0]):
				if idx < 0:
					continue
				if idx >= len(self.faiss_metadata):
					continue
				entry = self.faiss_metadata[idx]
				if not self._matches_filters(entry, filters):
					continue
				results.append((float(score), entry, float(score), 0.0))
				if len(results) >= top_k:
					break
			return results
		except Exception as e:
			logger.warning("Falha na busca FAISS, fallback para linear: %s", e)
			return []
		
	async def exec_task(self, query: Any) -> dict:
		"""
		Executa uma consulta RAG na base de conhecimento interna.
		"""
		obs = getattr(self, "obs", get_observability_manager())
		start_time = time.perf_counter()
		logger.info("RAGWorker %s starting RAG query for: %s", self.id, query)
		obs.log_event(
			logger,
			"rag_task_started",
			component="rag_worker",
			worker_id=self.id,
			worker_type="rag",
			source="rag",
		)
		
		query_text, filters = self._parse_query_input(query)
		cache_key = None
		if self.cache_enabled:
			try:
				cache_key = f"{query_text}|{json.dumps(filters or {}, sort_keys=True, ensure_ascii=True)}"
			except Exception:
				cache_key = str(query_text)
			cached = self._cache.get(cache_key)
			if cached and (time.time() - cached.get("ts", 0)) < self.cache_ttl:
				payload = dict(cached.get("value", {}))
				payload["cache_hit"] = True
				return payload
		with obs.span(
			"rag_worker.exec_task",
			{"worker.id": self.id, "worker.type": "rag"},
			span_kind="RETRIEVER",
		):
			if not self.openai_api_key:
				logger.warning("OPENAI_API_KEY não configurada. Usando resultados simulados.")
				await asyncio.sleep(0.3)
				duration_ms = obs.elapsed_ms(start_time)
				obs.log_event(
					logger,
					"rag_task_finished",
					component="rag_worker",
					worker_id=self.id,
					worker_type="rag",
					source="simulated",
					duration_ms=duration_ms,
				)
				return {
					"worker_id": self.id,
					"worker_type": "rag",
					"task": query,
					"result": f"[SIMULADO] Resposta RAG para '{query_text}': Baseado nos documentos internos, a Copa do Mundo tem formato de 32 seleções.",
					"source": "simulated",
					"duration_ms": duration_ms,
				}
			
			try:
				rag_payload = await self._query_rag(query_text, filters=filters)
				pages = []
				if isinstance(rag_payload, dict):
					rag_result = rag_payload.get("text", "")
					pages = rag_payload.get("pages") or []
				else:
					rag_result = rag_payload
				duration_ms = obs.elapsed_ms(start_time)
				obs.log_event(
					logger,
					"rag_task_finished",
					component="rag_worker",
					worker_id=self.id,
					worker_type="rag",
					source="rag",
					duration_ms=duration_ms,
				)
				payload = {
					"worker_id": self.id,
					"worker_type": "rag",
					"task": query,
					"result": rag_result,
					"pages": pages,
					"source": "rag",
					"duration_ms": duration_ms,
				}
				if cache_key:
					self._cache[cache_key] = {"ts": time.time(), "value": payload}
				return payload
			except Exception as e:
				logger.exception("Erro na consulta RAG: %s", e)
				duration_ms = obs.elapsed_ms(start_time)
				obs.log_event(
					logger,
					"rag_task_failed",
					level=logging.ERROR,
					component="rag_worker",
					worker_id=self.id,
					worker_type="rag",
					source="rag",
					duration_ms=duration_ms,
					error=str(e),
				)
				return {
					"worker_id": self.id,
					"worker_type": "rag",
					"task": query,
					"error": str(e),
					"duration_ms": duration_ms,
				}
	
	async def _query_rag(self, query: str, filters: Optional[Dict[str, Any]] = None) -> dict | str:
		"""
		Consulta a base RAG: gera embedding da query e busca documentos similares.
		"""
		obs = getattr(self, "obs", get_observability_manager())
		if not self.embeddings_data:
			return "[RAG] Base de conhecimento não disponível. Execute: python scripts/ingest_rag.py"
		
		if not self.openai_api_key:
			return "[RAG] OPENAI_API_KEY não configurada no .env"
		
		try:
			# Gera embedding da query usando requests + OpenAI API diretamente
			import requests
			import json
			
			api_url = "https://api.openai.com/v1/embeddings"
			headers = {
				"Authorization": f"Bearer {self.openai_api_key}",
				"Content-Type": "application/json"
			}
			payload = {
				"model": "text-embedding-3-small",
				"input": [query]
			}
			
			with obs.span(
				"rag_worker.openai_embedding_request",
				{"worker.id": self.id, "query.length": len(query)},
				span_kind="EMBEDDING",
			):
				loop = asyncio.get_event_loop()
				resp = await loop.run_in_executor(
					None,
					lambda: requests.post(api_url, json=payload, headers=headers, timeout=30)
				)
			
			if resp.status_code != 200:
				return f"[RAG] Erro na API OpenAI: {resp.status_code} {resp.text[:100]}"
			
			resp_data = resp.json()
			query_embedding = resp_data['data'][0]['embedding']
			
			# Busca vetorial FAISS (se disponível) com fallback para híbrida linear.
			try:
				top_k = int(os.getenv("RAG_TOP_K", "3"))
			except Exception:
				top_k = 3
			similar_chunks = self._search_similar_faiss(query_embedding, top_k=top_k, filters=filters)
			search_mode = "faiss"
			if not similar_chunks:
				similar_chunks = self._search_similar(query_embedding, query, top_k=top_k, filters=filters)
				search_mode = "hybrid_linear"
			
			if not similar_chunks:
				return "[RAG] Nenhuma informação relevante encontrada na base de conhecimento."
			
			# Monta resposta com os chunks mais relevantes
			pages = []
			response_parts = [f"[RAG] Informações encontradas na base de conhecimento local (modo: {search_mode}):\n"]
			for i, result in enumerate(similar_chunks, 1):
				if len(result) == 4:
					combined_score, entry, semantic_score, lexical_score = result
				else:
					combined_score, entry = result[0], result[1]
					semantic_score, lexical_score = combined_score, 0.0
				page_num = entry.get("page")
				if isinstance(page_num, int):
					pages.append(page_num)
				
				text_preview = entry['text'][:300].replace('\n', ' ')
				if len(entry['text']) > 300:
					text_preview += "..."
				
				# Exibe scores detalhados
				if len(result) == 4:
					response_parts.append(f"\n📄 Trecho {i} - {entry['path']}:")
					response_parts.append(f"   Score Semântico: {semantic_score:.1%} | Léxico: {lexical_score:.1%} | Combinado: {combined_score:.1%}")
				else:
					response_parts.append(f"\n📄 Trecho {i} (similaridade: {combined_score:.2f}) - {entry['path']}:")
				
				response_parts.append(f"{text_preview}")
			
			unique_pages = sorted({p for p in pages if isinstance(p, int)})
			return {"text": "\n".join(response_parts), "pages": unique_pages}
			
		except Exception as e:
			logger.exception(f"Erro ao consultar RAG: {e}")
			return f"[RAG] Erro ao processar consulta: {str(e)}"
