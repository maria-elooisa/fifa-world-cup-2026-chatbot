"""
LLM Generator - Módulo responsável por gerar respostas usando GPT-4.1 nano.
"""

import asyncio
import logging
import os
import json
import re
import time
from typing import Optional
import requests
from .response_schema import ResponseStructurer
from .response_validator import ResponseValidator
from .observability import get_observability_manager

logger = logging.getLogger(__name__)

class LLMGenerator:
    """
    Gerador de respostas usando OpenAI API.
    
    REQUISITO: GPT-4.1 nano
    FALLBACK: gpt-4o-mini
    """
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.obs = get_observability_manager()
        
        # Modelo requerido (GPT-4.1 nano quando disponível)
        self.required_model = "gpt-4.1-nano"
        
        # Modelo configurado (com fallback automático)
        self.configured_model = os.getenv("LLM_MODEL", "gpt-4.1-nano")
        
        # Modelos alternativos (em ordem de preferência)
        self.fallback_models = [
            "gpt-4.1-nano",      # Modelo requerido (primeira opção)
            "gpt-4o-mini",       # Equivalente disponível agora
            "gpt-4-turbo",       # Alternativa mais poderosa
            "gpt-4"              # Última alternativa
        ]
        
        self.model = self.configured_model
        self.base_url = "https://api.openai.com/v1"
        self.max_tokens = 500
        self.default_temperature = self._load_temperature()
        
        if not self.api_key:
            logger.warning("OPENAI_API_KEY não configurada!")
            
        logger.info(f"LLMGenerator iniciado")
        logger.info(f"  Modelo requerido: {self.required_model}")
        logger.info(f"  Modelo configurado: {self.configured_model}")
        logger.info(f"  Modelos alternativos: {', '.join(self.fallback_models[1:])}")
    
    def _build_system_prompt(
        self,
        response_type: Optional[str] = None,
        language_request: Optional[str] = None,
    ) -> str:
        """Constrói o prompt do sistema estruturado para Copa do Mundo."""
        if response_type:
            # Usa prompt específico para o tipo de resposta
            base_prompt = ResponseStructurer.get_prompt_for_type(response_type)
        else:
            # Fallback para prompt genérico estruturado
            base_prompt = """Você é um assistente especializado em Copa do Mundo FIFA.

INSTRUÇÕES GERAIS:
1. Responda APENAS sobre Copa do Mundo (histórico, 2026, regras, etc)
2. Estruture sua resposta em JSON com os campos: type, query, answer, main_facts, related_topics
3. Respostas devem ter 100-200 palavras no máximo
4. Sempre cite anos/datas quando relevante
5. Se não souber, indique com "(?)"

ESCOPO PERMITIDO:
- História da Copa (1930-2026)
- Informações Copa 2026
- Regras, formato, estatísticas
- Jogadores e recordes

ESCOPO NÃO PERMITIDO:
- Política, ideologia, religião
- Finanças, criptomoedas, investimentos
- Hacking, segurança
- Tópicos não relacionados a Copa

RESPONDA SEMPRE EM JSON ESTRUTURADO."""
        lang_instruction = self._build_language_instruction(language_request)
        base_prompt += f"\n\n{lang_instruction}"
        return base_prompt

    @staticmethod
    def _build_language_instruction(language_request: Optional[str]) -> str:
        """Constrói instrução de idioma com dicas para casos raros."""
        default_instruction = (
            "IDIOMA: Responda em português brasileiro (pt-BR). "
            "Mantenha o JSON e as chaves exatamente como especificado."
        )
        if not language_request:
            return default_instruction

        lang = language_request.strip()
        if not lang:
            return default_instruction

        return (
            "IDIOMA OBRIGATÓRIO: Responda exclusivamente no idioma solicitado pelo usuário: "
            f"{lang}. Não use português.\n"
            "LANGUAGE OVERRIDE (MUST FOLLOW): All textual fields must be in the requested language. "
            "Do NOT use Portuguese. Keep JSON keys unchanged."
        )

    @staticmethod
    def _detect_language_request(query: str) -> Optional[str]:
        """Detecta pedido de idioma do usuário e retorna o texto do idioma."""
        if not query:
            return None
        patterns = [
            r"(?:responda|responder|resposta)\s+em\s+([^\\.;,\\n\\?]+)",
            r"(?:answer|respond)\s+in\s+([^\\.;,\\n\\?]+)",
            r"(?:em|no)\s+idioma\s+([^\\.;,\\n\\?]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, query, flags=re.IGNORECASE)
            if match:
                lang = match.group(1).strip()
                # Remove complementos comuns no final
                lang = re.sub(r"\\b(por favor|please|pls|plz)\\b.*$", "", lang, flags=re.IGNORECASE).strip()
                return lang if lang else None
        return None

    @staticmethod
    def _truncate(text: Optional[str], limit: int) -> str:
        if not text:
            return ""
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text
        return text[:limit] + " ..."
    
    async def generate(
        self, 
        query: str, 
        context: Optional[str] = None,
        temperature: Optional[float] = None,
        structured: bool = True,
        language_request: Optional[str] = None
    ) -> dict:
        """
        Gera uma resposta usando LLM com suporte a resposta estruturada.
        
        Args:
            query: Pergunta do usuário
            context: Contexto adicional (resultado RAG/Web)
            temperature: Criatividade (0.0-1.0)
            structured: Se True, retorna resposta em JSON estruturado
        
        Returns:
            {
                "response": str (texto ou JSON),
                "model": str,
                "tokens_used": int,
                "source": "llm",
                "structured": bool,
                "data": dict (se structured=True)
            }
        """
        obs = getattr(self, "obs", get_observability_manager())
        start_time = time.perf_counter()
        temperature = self._normalize_temperature(temperature)
        if not self.api_key:
            logger.warning("OPENAI_API_KEY não configurada, usando resposta simulada")
            simulated = await self._simulate_response(query, context)
            simulated["duration_ms"] = obs.elapsed_ms(start_time)
            obs.log_event(
                logger,
                "llm_generation_finished",
                component="llm_generator",
                source="simulated",
                duration_ms=simulated["duration_ms"],
            )
            return simulated
        
        try:
            obs.log_event(
                logger,
                "llm_generation_started",
                component="llm_generator",
                source="llm",
            )
            # Detecta idioma solicitado (ou mantém pt-BR como padrão)
            if not language_request:
                language_request = self._detect_language_request(query)
            # Detecta tipo de resposta para usar prompt apropriado
            response_type = None
            if structured:
                response_type = ResponseStructurer.detect_response_type(query)
                logger.info(f"Tipo de resposta detectado: {response_type}")
            
            # Constrói a mensagem do usuário
            user_message = self._build_user_message(query, context, language_request)
            
            # Faz a requisição à OpenAI API
            response = await self._call_openai(
                user_message,
                temperature,
                response_type if structured else None,
                language_request,
            )
            
            # Se structured, tenta validar e parsear JSON
            if structured:
                is_valid, json_data, msg = ResponseValidator.validate_and_fix_response(
                    response["response"]
                )
                response["structured"] = is_valid
                if is_valid:
                    response["data"] = json_data
                    logger.info(f"Resposta estruturada validada: {response_type}")
                else:
                    logger.warning(f"Resposta não estruturada corretamente: {msg}")
            else:
                response["structured"] = False

            # Força idioma quando solicitado e a resposta ainda parece pt-BR
            if language_request and not self._is_portuguese_request(language_request):
                try:
                    if response.get("structured") and response.get("data"):
                        if self._looks_portuguese(json.dumps(response["data"], ensure_ascii=False)):
                            translated = await self._translate_json_payload(
                                response["data"], language_request
                            )
                            if translated:
                                response["response"] = translated
                                is_valid, json_data, _ = ResponseValidator.validate_and_fix_response(translated)
                                if is_valid:
                                    response["structured"] = True
                                    response["data"] = json_data
                    else:
                        if self._looks_portuguese(str(response.get("response", ""))):
                            translated_text = await self._translate_text(
                                str(response.get("response", "")), language_request
                            )
                            if translated_text:
                                response["response"] = translated_text
                except Exception:
                    pass
            
            response["duration_ms"] = obs.elapsed_ms(start_time)
            obs.log_event(
                logger,
                "llm_generation_finished",
                component="llm_generator",
                source=response.get("source", "llm"),
                duration_ms=response["duration_ms"],
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Erro ao gerar resposta com LLM: {e}")
            duration_ms = obs.elapsed_ms(start_time)
            obs.log_event(
                logger,
                "llm_generation_failed",
                level=logging.ERROR,
                component="llm_generator",
                source="llm",
                duration_ms=duration_ms,
                error=str(e),
            )
            return {
                "response": f"Desculpe, erro ao processar sua pergunta: {str(e)}",
                "model": self.model,
                "tokens_used": 0,
                "source": "error",
                "error": str(e),
                "structured": False,
                "duration_ms": duration_ms,
            }

    def _load_temperature(self) -> float:
        """Carrega temperatura padrão a partir do .env."""
        raw = os.getenv("LLM_TEMPERATURE", "0.3")
        try:
            value = float(raw)
        except Exception:
            value = 0.3
        return max(0.0, min(1.0, value))

    def _normalize_temperature(self, temperature: Optional[float]) -> float:
        """Normaliza a temperatura dentro do intervalo [0,1]."""
        if temperature is None:
            return self.default_temperature
        try:
            value = float(temperature)
        except Exception:
            return self.default_temperature
        return max(0.0, min(1.0, value))
    
    def _build_user_message(
        self, query: str, context: Optional[str], language_request: Optional[str] = None
    ) -> str:
        """Constrói a mensagem para enviar ao LLM."""
        lang_prefix = ""
        if language_request:
            lang_prefix = f"[Idioma solicitado: {language_request}]\n"
        if context:
            return f"""{lang_prefix}Pergunta do usuário: {query}

Contexto fornecido (RAG/Web):
{context}

Com base no contexto acima, responda de forma concisa e relevante."""
        else:
            return f"{lang_prefix}Pergunta: {query}\n\nResponda baseado em seu conhecimento sobre Copa do Mundo."

    @staticmethod
    def _is_portuguese_request(lang: str) -> bool:
        if not lang:
            return True
        t = lang.lower()
        return "portugu" in t or "pt" in t

    @staticmethod
    def _looks_portuguese(text: str) -> bool:
        if not text:
            return False
        t = text.lower()
        markers = [
            "não", "você", "selecao", "seleção", "história", "campeão",
            "campeao", "pergunta", "resposta", "fase", "jogos", "mundial",
            "copa", "torneio", "paises", "países",
        ]
        hits = sum(1 for m in markers if m in t)
        return hits >= 3

    async def _translate_json_payload(self, data: dict, target_lang: str) -> str | None:
        system_prompt = (
            "You are a translation engine. Translate all VALUES in the JSON to the target language. "
            "Keep JSON keys unchanged. Return ONLY valid JSON."
        )
        user_message = (
            f"Target language: {target_lang}\n\nJSON:\n"
            f"{json.dumps(data, ensure_ascii=False)}"
        )
        result = await self._call_openai_custom(system_prompt, user_message)
        return result.get("response") if result else None

    async def _translate_text(self, text: str, target_lang: str) -> str | None:
        system_prompt = (
            "You are a translation engine. Translate the text to the target language. "
            "Return only the translated text."
        )
        user_message = f"Target language: {target_lang}\n\nText:\n{text}"
        result = await self._call_openai_custom(system_prompt, user_message)
        return result.get("response") if result else None

    async def _call_openai_custom(self, system_prompt: str, user_message: str) -> dict | None:
        """Chamada simples para tradução/ajustes sem prompt estruturado."""
        if not self.api_key:
            return None
        for model_to_try in self.fallback_models:
            try:
                url = f"{self.base_url}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model_to_try,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.0,
                }
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: requests.post(url, json=payload, headers=headers, timeout=30),
                )
                if response.status_code != 200:
                    continue
                data = response.json()
                if "choices" not in data or not data["choices"]:
                    continue
                return {
                    "response": data["choices"][0]["message"]["content"],
                    "model": model_to_try,
                    "tokens_used": (data.get("usage", {}) or {}).get("total_tokens", 0),
                }
            except Exception:
                continue
        return None
    
    async def _call_openai(
        self,
        user_message: str,
        temperature: float,
        response_type: Optional[str] = None,
        language_request: Optional[str] = None,
    ) -> dict:
        """
        Chama a OpenAI API de forma assíncrona com fallback automático.
        
        Se o modelo requerido (gpt-4.1-nano) não estiver disponível,
        tenta usar o próximo modelo na lista de fallback.
        """
        obs = getattr(self, "obs", get_observability_manager())
        for attempt, model_to_try in enumerate(self.fallback_models):
            try:
                url = f"{self.base_url}/chat/completions"
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                # Usa prompt específico se tipo de resposta fornecido
                system_prompt = self._build_system_prompt(response_type, language_request)
                
                payload = {
                    "model": model_to_try,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": user_message
                        }
                    ],
                    "max_tokens": self.max_tokens,
                    "temperature": temperature,
                    "top_p": 0.9
                }

                # Executa requisição em thread separada
                response = None
                status_code = None
                response_text = None
                result_payload = None
                with obs.span(
                    "llm_generator.openai_chat_request",
                    {"llm.model": model_to_try},
                    span_kind="LLM",
                ) as span:
                    # Anexa input ao span (truncado)
                    if span is not None:
                        try:
                            max_in = int(os.getenv("TRACE_INPUT_MAX_CHARS", "2000"))
                        except Exception:
                            max_in = 2000
                        input_value = self._truncate(user_message, max_in)
                        try:
                            span.set_attribute("input.value", input_value)
                            span.set_attribute("llm.input", input_value)
                            span.set_attribute("llm.input_messages", input_value)
                            span.set_attribute("input.mime_type", "text/plain")
                            span.set_attribute("openinference.input.value", input_value)
                            span.set_attribute("openinference.input.mime_type", "text/plain")
                        except Exception:
                            pass
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: requests.post(url, json=payload, headers=headers, timeout=30)
                    )
                    status_code = response.status_code
                    if span is not None:
                        try:
                            span.set_attribute("http.status_code", status_code)
                        except Exception:
                            pass

                    if status_code == 200:
                        data = response.json()
                        if "choices" not in data or len(data["choices"]) == 0:
                            raise Exception("Resposta vazia da OpenAI")

                        generated_text = data["choices"][0]["message"]["content"]
                        usage = data.get("usage", {}) or {}
                        tokens_used = usage.get("total_tokens", 0)
                        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
                        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
                        total_tokens = int(tokens_used or 0)
                        if total_tokens == 0:
                            total_tokens = prompt_tokens + completion_tokens
                            tokens_used = total_tokens

                        if span is not None:
                            try:
                                span.set_attribute("llm.model_name", model_to_try)
                                # OpenInference recommended attributes
                                span.set_attribute("llm.token_count.prompt", prompt_tokens)
                                span.set_attribute("llm.token_count.completion", completion_tokens)
                                span.set_attribute("llm.token_count.total", total_tokens)
                                # Alternate attribute names used by some UIs
                                span.set_attribute("llm.usage.prompt_tokens", prompt_tokens)
                                span.set_attribute("llm.usage.completion_tokens", completion_tokens)
                                span.set_attribute("llm.usage.total_tokens", total_tokens)
                                span.set_attribute("llm.prompt_tokens", prompt_tokens)
                                span.set_attribute("llm.completion_tokens", completion_tokens)
                                span.set_attribute("llm.total_tokens", total_tokens)
                                span.set_attribute("total_tokens", total_tokens)
                                # Backward compatibility for some OpenInference variants
                                span.set_attribute("openinference.llm.usage.prompt_tokens", prompt_tokens)
                                span.set_attribute("openinference.llm.usage.completion_tokens", completion_tokens)
                                span.set_attribute("openinference.llm.usage.total_tokens", total_tokens)
                                # Output (truncado)
                                try:
                                    max_out = int(os.getenv("TRACE_OUTPUT_MAX_CHARS", "2000"))
                                except Exception:
                                    max_out = 2000
                                output_value = self._truncate(generated_text, max_out)
                                span.set_attribute("output.value", output_value)
                                span.set_attribute("llm.output", output_value)
                                span.set_attribute("llm.output_messages", output_value)
                                span.set_attribute("output.mime_type", "text/plain")
                                span.set_attribute("openinference.output.value", output_value)
                                span.set_attribute("openinference.output.mime_type", "text/plain")
                            except Exception:
                                pass

                        # Cálculo opcional de custo via env (por 1K tokens)
                        total_cost = None
                        try:
                            prompt_rate = float(os.getenv("LLM_COST_PROMPT_PER_1K", "0") or 0)
                            completion_rate = float(os.getenv("LLM_COST_COMPLETION_PER_1K", "0") or 0)
                            if prompt_rate or completion_rate:
                                total_cost = (
                                    (prompt_tokens * prompt_rate) + (completion_tokens * completion_rate)
                                ) / 1000.0
                                if span is not None:
                                    try:
                                        span.set_attribute("llm.total_cost", total_cost)
                                        span.set_attribute("llm.cost.total", total_cost)
                                        span.set_attribute("total_cost", total_cost)
                                        span.set_attribute("llm.cost.prompt", (prompt_tokens * prompt_rate) / 1000.0)
                                        span.set_attribute("llm.cost.completion", (completion_tokens * completion_rate) / 1000.0)
                                    except Exception:
                                        pass
                        except Exception:
                            total_cost = None

                        result_payload = {
                            "response": generated_text,
                            "model": model_to_try,
                            "tokens_used": tokens_used,
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                            "total_cost": total_cost,
                            "source": "llm",
                            "finish_reason": data["choices"][0].get("finish_reason", "stop"),
                            "is_fallback": model_to_try != self.configured_model
                        }
                    else:
                        response_text = response.text

                if status_code == 200 and result_payload is not None:
                    # Log se usou fallback
                    if model_to_try != self.configured_model:
                        logger.info(f"Fallback: {self.configured_model} → {model_to_try} (sucesso)")
                    return result_payload

                if status_code == 404:
                    # Modelo não existe, tenta o próximo
                    logger.warning(f"Modelo {model_to_try} não disponível (404)")
                    if attempt == len(self.fallback_models) - 1:
                        # Último modelo, retorna erro
                        raise Exception(f"Nenhum modelo disponível. Último tentado: {model_to_try}")
                    continue  # Tenta próximo modelo
                
                else:
                    # Outro erro
                    logger.error(f"OpenAI API error: {status_code} - {response_text}")
                    if attempt == len(self.fallback_models) - 1:
                        raise Exception(f"OpenAI API error: {status_code}")
                    continue
                    
            except Exception as e:
                if attempt == len(self.fallback_models) - 1:
                    # Último modelo, lança erro
                    raise e
                logger.debug(f"Modelo {model_to_try} falhou, tentando próximo: {str(e)}")
                continue
    
    async def _simulate_response(self, query: str, context: Optional[str]) -> dict:
        """Simula uma resposta quando OpenAI API não está disponível."""
        await asyncio.sleep(0.2)  # Simula latência
        
        simulated_responses = {
            "história": "A Copa do Mundo começou em 1930 no Uruguai. Desde então, 22 edições foram realizadas (até 2026). Brasil é o país com mais títulos (5 campeões). A Copa 2026 será sediada nos EUA, Canadá e México.",
            "2026": "A Copa do Mundo 2026 será realizada nos EUA, Canadá e México de junho a julho. Será a primeira Copa com 48 seleções (em vez de 32). O formato muda para 3 grupos de 16 times.",
            "brasil": "Brasil é tricampeão mundial (1958, 1962, 1970) e pentacampeão (1994, 2002). Pelé foi o maior artilheiro nas primeiras Copas. Brasil sempre é uma das favoritas.",
            "regras": "A Copa do Mundo segue as regras oficiais de futebol FIFA. Cada jogo tem 90 minutos, prorrogação de 30 minutos se necessário, e pênaltis em caso de empate na decisão.",
            "default": f"Baseado em seu conhecimento sobre Copa do Mundo: {query[:100]}..."
        }
        
        # Tenta encontrar resposta simulada relevante
        query_lower = query.lower()
        for key, response in simulated_responses.items():
            if key in query_lower:
                return {
                    "response": response,
                    "model": self.model,
                    "tokens_used": len(response.split()),
                    "source": "simulated",
                    "warning": "OPENAI_API_KEY não configurada - resposta simulada"
                }
        
        return {
            "response": simulated_responses["default"],
            "model": self.model,
            "tokens_used": 50,
            "source": "simulated",
            "warning": "OPENAI_API_KEY não configurada - resposta simulada"
        }


# Singleton
_generator_instance: Optional[LLMGenerator] = None

def get_llm_generator() -> LLMGenerator:
    """Retorna instância singleton do gerador LLM."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = LLMGenerator()
    return _generator_instance
