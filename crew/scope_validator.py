"""
Validador de Escopo: Garante que respostas estejam dentro do contexto documentado.

Este módulo implementa validação de escopo para:
1. RAG: Rejeitar perguntas sobre tópicos não cobertos no PDF
2. Web Search: Limitar buscas apenas a Copa 2026 / FIFA
3. Hallucination Prevention: Evitar que o modelo crie informações falsas
"""

import logging
import os
import re
from typing import Tuple, List
from enum import Enum

logger = logging.getLogger(__name__)


class QueryScope(Enum):
	"""Escopo válido de perguntas do sistema."""
	RAG_ONLY = "rag_only"  # Apenas no documento PDF
	WEB_ONLY = "web_only"   # Apenas informações atualizadas
	BOTH = "both"           # Pode usar RAG e Web
	CLARIFY = "clarify"     # Necessita de clarificação do usuário
	OUT_OF_SCOPE = "out_of_scope"  # Deve ser rejeitado


class ScopeValidator:
	"""
	Valida se uma pergunta está dentro do escopo do sistema.
	
	Escopo permitido:
	- Copa do Mundo (histórico, regulamentos, formatos, estatísticas)
	- Copa 2026 (cidades, estádios, viagens, hospedagem, ingressos)
	- FIFA (regras, formatos de competição)
	
	Escopo NÃO permitido:
	- Política, religião, assuntos não-esportivos
	- Consultoria financeira/legal (fora do escopo Copa)
	- Informações pessoais de terceiros
	"""
	
	def __init__(self):
		"""Inicializa validador com keywords permitidas."""
		self.last_entities: dict = {}
		
		# Tópicos permitidos no RAG (documento PDF)
		self.rag_keywords = {
			# Copa do Mundo histórica
			'copa', 'mundial', 'world cup', 'fifa', 'torneio',
			'seleção', 'selecao', 'brasil', 'argentina', 'alemanha',
			'itália', 'italia', 'holanda', 'franca', 'frança', 'españa', 'espanha',
			
			# Estrutura da competição
			'grupo', 'gruposcopa', 'classificação', 'classificacao', 'semifinal',
			'final', 'jogo', 'partida', 'rodada', 'fase', 'campeonato',
			'format', 'formato', 'regras', 'regulamento', 'eliminatória', 'eliminatoria',
			'oitava', 'oitavas', 'quarta', 'quartas', 'semi', 'final',
			
			# Locais e infraestrutura
			'estádio', 'estadio', 'arena', 'campo', 'sede', 'host',
			'país', 'pais', 'cidade', 'metlife', 'arena', 'estádios',
			
			# Estatísticas e resultados
			'gol', 'gols', 'artilheiro', 'melhor atacante',
			'resultado', 'placar', 'score', 'vitória', 'vitoria',
			'derrota', 'empate', 'perdeu', 'ganhou', 'campeão', 'campeao',
			'vencedor', 'tricampeão', 'bicampeão', 'recordes', 'recorde',
			'estatística', 'estatistica', 'dado', 'número', 'numero',
			
			# Jogadores e histórico
			'jogador', 'jogadora', 'craques', 'lendas',
			'pelé', 'pele', 'maradona', 'ronaldo', 'ronaldinho',
			'messi', 'neymar', 'história', 'historia', 'histórico', 'historico',
			
			# Tecnologia e regulamentos
			'var', 'tecnologia', 'video', 'árbitro', 'arbitro',
			'cartão', 'cartao', 'amarelo', 'vermelho', 'falta', 'penalti',
			
			# Tempo e períodos
			'1930', '1934', '1938', '1950', '1958', '1962', '1970',
			'1978', '1982', '1986', '1990', '1994', '1998', '2002',
			'2006', '2010', '2014', '2018', '2022',
		}
		
		# Tópicos permitidos na Web Search
		self.web_keywords = {
			# Praticamente tudo sobre Copa 2026
			'2026', 'copa 2026', 'world cup 2026', 'mundial 2026',
			
			# Informações práticas
			'hotel', 'hotéis', 'hospedagem', 'acomodação', 'acomodacao',
			'passagem', 'voo', 'transporte', 'uber', 'taxi', 'metrô',
			'restaurante', 'comida', 'refeição', 'comidas tipicas', 'culinária',
			'turismo', 'turista', 'atração', 'atracao', 'pontos turísticos',
			'clima', 'tempo', 'previsão', 'previsao', 'temperatura', 'chuva',
			'preço', 'preco', 'custo', 'orçamento', 'orcamento',
			'ingresso', 'bilhete', 'passaporte', 'visto', 'documento',
			'seguro', 'vacinação', 'vacinacao', 'saúde', 'saude', 'requisito',
			
			# Cidades e estádios 2026
			'new york', 'los angeles', 'miami', 'cidade do méxico', 'cancun',
			'vancouver', 'toronto', 'kansas', 'seattle', 'denver',
			'metlife', 'estádio', 'arena', 'capacidade', 'localização', 'localizacao',
			'new jersey', 'east rutherford',
			
			# Calendário e cronograma
			'calendário', 'calendario', 'datas', 'horários', 'horarios',
			'agenda', 'cronograma', 'programação', 'programacao',
			
			# Vendas, compra e reservas
			'venda', 'comprar', 'reservar', 'booking', 'ingresso', 'ingressos',
			'quanto custa', 'onde comprar', 'disponibilidade', 'como comprar',
			'canal', 'oficial', 'fifa',
			
			# Copa 2026 específico
			'copa 2026', '2026', '48 times', 'novo formato', 'grupos',
			
			# Informações sobre Copa (genéricas)
			'copa', 'mundial', 'seleção', 'brasil', 'história', 'fase',
			'eliminatória', 'oitavas', 'quartas', 'semifinal', 'final',
			'var', 'regra', 'regulamento',
		}
		
		# Tópicos EXPLICITAMENTE NÃO PERMITIDOS
		self.out_of_scope_keywords = {
			# Assuntos políticos/religiosos
			'política', 'politica', 'eleição', 'eleicao', 'voto', 'partido',
			'presidente', 'governo', 'ministério', 'congresso',
			'religião', 'religiao', 'deus', 'igreja', 'ateu',
			
			# Consultoria não-autorizada
			'empréstimo', 'credito', 'crédito', 'investimento', 'bolsa',
			'ações', 'criptomoeda', 'bitcoin', 'trader',
			'imposto', 'dedução fiscal', 'contabilidade', 'auditoria',
			'advogado', 'processo legal', 'lei', 'contrato juridico',
			
			# Assuntos médicos/sensíveis
			'medicamento', 'droga', 'receita', 'diagnóstico', 'doença',
			'cirurgia', 'terapia', 'psicológico', 'psicologia',
			
			# Conteúdo inadequado
			'hack', 'crack', 'pirataria', 'roubo', 'crime',
			'arma', 'violência', 'violencia', 'porno', 'sexo',
		}

		# Catálogo simples de entidades para extração (heurística)
		self._entity_catalog = {
			"countries": {
				"brasil": "Brasil",
				"uruguai": "Uruguai",
				"argentina": "Argentina",
				"alemanha": "Alemanha",
				"franca": "França",
				"frança": "França",
				"inglaterra": "Inglaterra",
				"espanha": "Espanha",
				"españa": "Espanha",
				"italia": "Itália",
				"itália": "Itália",
				"mexico": "México",
				"méxico": "México",
				"canada": "Canadá",
				"canadá": "Canadá",
				"eua": "Estados Unidos",
				"estados unidos": "Estados Unidos",
				"usa": "Estados Unidos",
			},
			"cities": {
				"new york": "New York",
				"nova york": "New York",
				"miami": "Miami",
				"los angeles": "Los Angeles",
				"dallas": "Dallas",
				"atlanta": "Atlanta",
				"boston": "Boston",
				"seattle": "Seattle",
				"toronto": "Toronto",
				"vancouver": "Vancouver",
				"guadalajara": "Guadalajara",
				"monterrey": "Monterrey",
				"cidade do méxico": "Cidade do México",
				"cidade do mexico": "Cidade do México",
			},
			"players": {
				"pelé": "Pelé",
				"pele": "Pelé",
				"messi": "Messi",
				"maradona": "Maradona",
				"neymar": "Neymar",
				"ronaldo": "Ronaldo",
				"ronaldinho": "Ronaldinho",
				"mbappe": "Mbappé",
				"müller": "Müller",
				"klose": "Klose",
			},
			"tournament_terms": {
				"copa": "Copa do Mundo",
				"mundial": "Copa do Mundo",
				"world cup": "Copa do Mundo",
				"fifa": "FIFA",
				"2026": "Copa 2026",
			},
			"stages": {
				"fase de grupos": "Fase de grupos",
				"oitavas": "Oitavas",
				"quartas": "Quartas",
				"semifinal": "Semifinal",
				"final": "Final",
			},
		}

	def extract_entities(self, query: str) -> dict:
		"""Extrai entidades básicas da pergunta (heurística)."""
		if not query:
			return {}
		text = query.lower()
		entities = {
			"years": [],
			"countries": [],
			"cities": [],
			"players": [],
			"tournament_terms": [],
			"stages": [],
		}
		# Anos
		for year in re.findall(r"\b(19[3-9]\d|20[0-2]\d|2026)\b", text):
			entities["years"].append(int(year))
		# Catálogo
		for category, mapping in self._entity_catalog.items():
			for term, label in mapping.items():
				if term in text:
					entities[category].append(label)
		# Dedup
		for key, values in entities.items():
			seen = []
			for v in values:
				if v not in seen:
					seen.append(v)
			entities[key] = seen
		# Remove vazios
		cleaned = {k: v for k, v in entities.items() if v}
		return cleaned
	
	def validate_query(self, query: str) -> Tuple[QueryScope, str]:
		"""
		Valida se uma query está dentro do escopo permitido.
		
		Returns:
			Tuple[QueryScope, str]: (escopo, razão)
		"""
		query_lower = query.lower().strip()
		self.last_entities = self.extract_entities(query)
		if self.last_entities:
			logger.info(
				"scope_entities_extracted",
				extra={"event": "scope_entities_extracted", "entities": self.last_entities},
			)
		
		# Rejeita queries muito curtas
		if len(query_lower) < 3:
			return QueryScope.CLARIFY, "Sua pergunta ficou muito curta. Pode detalhar um pouco mais?"
		
		# Verifica se está explicitamente fora de escopo
		for keyword in self.out_of_scope_keywords:
			if keyword in query_lower:
				return QueryScope.OUT_OF_SCOPE, (
					f"Sobre '{keyword}' eu não consigo ajudar. Meu foco é a Copa do Mundo FIFA. "
					"Se quiser, pergunte sobre a Copa 2026 ou edições anteriores."
				)
		
		# VALIDAÇÃO RESTRITA: Se pergunta é sobre viagem/documentos mas NÃO menciona Copa, pedir clarificação
		copa_terms = ['copa', 'mundial', 'fifa', 'world cup']
		travel_keywords = [
			'ingresso', 'bilhete', 'entrada', 'como comprar',
			'hotel', 'hospedagem', 'transporte', 'voo', 'viajar', 'viagem',
			'visto', 'passaporte', 'documento', 'documentação', 'documentacao',
			'seguro', 'vacinação', 'vacinacao', 'saúde', 'saude',
			'imigração', 'imigracao', 'consulado', 'embaixada',
			'ds-160', 'b2', 'eua', 'estados unidos'
		]
		if any(word in query_lower for word in travel_keywords):
			if not any(word in query_lower for word in copa_terms):
				# Identifica o tipo de pergunta
				topic = "ingressos"
				if any(w in query_lower for w in ['hotel', 'hospedagem']):
					topic = "hospedagem"
				elif any(w in query_lower for w in ['transporte', 'voo', 'viajar', 'viagem']):
					topic = "transporte/viagem"
				elif any(w in query_lower for w in [
					'visto', 'passaporte', 'documento', 'documentação', 'documentacao',
					'seguro', 'vacinação', 'vacinacao', 'imigração', 'imigracao',
					'consulado', 'embaixada', 'ds-160', 'b2', 'eua', 'estados unidos'
				]):
					topic = "documentos/entrada"
				
				return QueryScope.CLARIFY, (
					f"Posso ajudar, mas preciso confirmar o evento. Você está falando da Copa do Mundo 2026?\n"
					"Se sim, me diga e eu explico como funciona o tema que você mencionou.\n\n"
					"Exemplo de pergunta:\n"
					f"  \"Como funciona {topic} para a Copa 2026?\""
				)

		# se há ano histórico + termos do futebol, assumir Copa histórica (RAG)
		historical_year = re.search(r"\b(19[3-9]\d|20[0-1]\d|202[0-2])\b", query_lower)
		if historical_year and "2026" not in query_lower:
			historical_terms = [
				'copa', 'mundial', 'fifa', 'seleção', 'selecao',
				'campeão', 'campeao', 'campeã', 'campea',
				'título', 'titulo', 'final', 'artilheiro', 'gols',
				'jogo', 'partida'
			]
			if any(term in query_lower for term in historical_terms):
				return QueryScope.RAG_ONLY, (
					f"Pergunta histórica ({historical_year.group(0)}) - usando base de conhecimento"
				)
		
		# Detecta perguntas sobre Copa mesmo sem mencionar "Copa" explicitamente
		copa_related_patterns = [
			# Menções explícitas de Copa
			('copa', 'Copa'),
			('mundial', 'Copa'),
			('world cup', 'Copa'),
			('fifa', 'Copa'),
			('2026', 'Copa 2026'),
			
			# Fases da competição
			('fase', 'Fases da Copa'),
			('eliminatória', 'Fases da Copa'),
			('eliminatoria', 'Fases da Copa'),
			('oitava', 'Fases da Copa'),
			('quartas', 'Fases da Copa'),
			('semifinal', 'Fases da Copa'),
			('final', 'Fases da Copa'),
			
			# Estádios e locais
			('estádio', 'Estádios'),
			('estadio', 'Estádios'),
			('arena', 'Estádios'),
			('metlife', 'Estádios Copa 2026'),
			
			# Tecnologia e regulamentos
			('var', 'Regulamentos da Copa'),
			('árbitro', 'Regulamentos da Copa'),
			('arbitro', 'Regulamentos da Copa'),
			('cartão', 'Regulamentos da Copa'),
			('regra', 'Regulamentos da Copa'),

			# Resultados e conquistas
			('campeão', 'História da Copa'),
			('campeao', 'História da Copa'),
			('campeã', 'História da Copa'),
			('campea', 'História da Copa'),
			('título', 'História da Copa'),
			('titulo', 'História da Copa'),
			('artilheiro', 'História da Copa'),
			('seleção', 'História da Copa'),
			('selecao', 'História da Copa'),
			
			# Informações práticas entram apenas se também mencionar Copa
		]
		
		copa_context = None
		for pattern, context in copa_related_patterns:
			if pattern in query_lower:
				copa_context = context
				break
		
		# Se detectou padrão Copa, classifica como válido
		if copa_context:
			is_practical = any(kw in query_lower for kw in [
				'2026', 'como', 'onde', 'quando', 'quanto custa', 'preço',
				'hotel', 'voo', 'transporte', 'ingresso', 'necessário',
				'devo', 'preciso', 'melhor', 'recomenda', 'comprar',
				'localiz', 'fica', 'endereço', 'endereco'
			])
			
			is_historical = any(kw in query_lower for kw in [
				'história', 'historia', 'histórico', 'historico', 'passado',
				'quando foi', 'qual', 'quantas', 'quanto', 'recorde',
				'campeão', 'campeao', 'primeiro', 'artilheiro',
			])
			
			if '2026' in query_lower or is_practical:
				return QueryScope.WEB_ONLY, f"Pergunta sobre {copa_context} - buscando informações atualizadas"
			elif is_historical:
				return QueryScope.RAG_ONLY, f"Pergunta sobre {copa_context} - usando base de conhecimento"
			else:
				return QueryScope.BOTH, f"Pergunta sobre {copa_context} - verificando múltiplas fontes"
		
		# FALLBACK: Se não detectou padrão Copa claro, oferece sugestão de clarificação
		suggestion = self._suggest_clarification(query_lower)
		if suggestion:
			return QueryScope.CLARIFY, suggestion
		
		# Última chance: se menciona Copa mas é ambíguo, tenta mesmo assim
		if any(kw in query_lower for kw in ['copa', 'mundial', 'fifa']):
			return QueryScope.BOTH, "Pergunta sobre Copa - verificando múltiplas fontes"
		
		return QueryScope.OUT_OF_SCOPE, (
			"Esta pergunta não está relacionada à Copa do Mundo ou à Copa 2026. "
			"Eu sou especializado em informações sobre a Copa do Mundo.\n\n"
			"Você pode perguntar sobre:\n"
			"  • História da Copa (campeonatos, jogadores, recordes)\n"
			"  • Copa 2026 (datas, cidades, estádios, ingressos)\n"
			"  • Regras, fases e formato da competição\n"
			"  • Informações práticas para viajar (passaporte, visto, hospedagem)"
		)

	def rewrite_query(self, query: str, scope: QueryScope | str | None = None) -> str:
		"""
		Reescreve a query para melhorar recall de RAG/Web.
		Ex.: adiciona contexto "Copa do Mundo" quando faltante.
		"""
		if not query:
			return query

		enabled = os.getenv("QUERY_REWRITE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
		if not enabled:
			return query

		normalized = ""
		if isinstance(scope, QueryScope):
			normalized = scope.value
		elif scope:
			normalized = str(scope).strip().lower()

		# Não reescreve quando precisa de clarificação ou está fora de escopo
		if normalized in {"clarify", "out_of_scope"}:
			return query

		trimmed = " ".join(query.strip().split())
		query_lower = trimmed.lower()
		if self._contains_copa_terms(query_lower):
			return trimmed

		target = None
		years = []
		if isinstance(getattr(self, "last_entities", None), dict):
			years = self.last_entities.get("years", []) or []

		if normalized in {"web_only", "web", "search"}:
			target = "Copa do Mundo 2026"
		elif normalized in {"rag_only", "rag"}:
			target = "Copa do Mundo"
		elif normalized in {"both"}:
			if 2026 in years or "2026" in query_lower:
				target = "Copa do Mundo 2026"
			else:
				target = "Copa do Mundo"

		if not target:
			return trimmed

		if target.lower() in query_lower:
			return trimmed

		return f"{trimmed} ({target})"

	@staticmethod
	def _contains_copa_terms(text: str) -> bool:
		if not text:
			return False
		return any(term in text for term in ["copa", "mundial", "fifa", "world cup"])
	
	def _suggest_clarification(self, query_lower: str) -> str:
		"""
		Sugere uma clarificação para perguntas ambíguas ou genéricas.
		
		Exemplos:
		- "Como comprar?" → "Você quer comprar ingressos para a Copa 2026?"
		- "O que é?" → "Você quer saber sobre a Copa 2026?"
		- "Como comprar ingressos?" (sem Copa) → "Você quer saber como comprar ingressos para a Copa 2026?"
		"""
		
		# Detecta perguntas ambíguas sobre ingressos (sem menção de Copa)
		if any(word in query_lower for word in ['ingresso', 'bilhete', 'entrada']):
			if not any(word in query_lower for word in ['copa', 'mundial', '2026', 'fifa']):
				return (
					"Posso ajudar, mas preciso confirmar o evento. Você quer saber sobre ingressos da Copa do Mundo 2026?\n"
					"Se sim, pergunte: \"Como comprar ingressos para a Copa 2026?\""
				)

		if "onde assistir" in query_lower or (
			"assistir" in query_lower and not any(kw in query_lower for kw in ['copa', 'mundial', '2026', 'fifa'])
		):
			return (
				"Você quer saber onde assistir à Copa do Mundo 2026?\n"
				"A transmissão varia por país e emissora. Se me disser o seu país, eu detalho as opções."
			)

		if query_lower in {"quando começa?", "quando comeca?", "quando começa", "quando comeca"}:
			return (
				"Você está perguntando sobre a Copa do Mundo 2026 ou outra edição?\n"
				"Se for a Copa 2026, posso informar as datas oficiais. Se for outra, me diga o ano."
			)

		if any(term in query_lower for term in ["melhor time", "melhor seleção", "melhor selecao"]):
			return (
				"\"Melhor time\" pode significar várias coisas: mais títulos, melhor campanha ou melhor elenco.\n"
				"Você quer o melhor time da história das Copas, da Copa 2026 ou de uma edição específica?"
			)

		if "maior goleada" in query_lower:
			return (
				"Você quer a maior goleada da história das Copas no geral, em finais, ou de uma edição específica?\n"
				"Se puder indicar o contexto, eu respondo com precisão."
			)
		
		# Detecta perguntas muito genéricas
		if query_lower == "como comprar?":
			return (
				"Sua pergunta ficou ambígua. Você quer saber:\n"
				"  • Como comprar ingressos para a Copa 2026?\n"
				"  • Como comprar passagens ou hospedagem para a Copa 2026?\n\n"
				"Se puder especificar, eu consigo ajudar melhor."
			)
		
		if query_lower == "o que é?":
			return (
				"Sua pergunta ficou muito genérica. Você quer saber sobre:\n"
				"  • O que é a Copa do Mundo?\n"
				"  • O que é o VAR?\n"
				"  • O que é a fase eliminatória?\n\n"
				"Por favor, especifique melhor."
			)
		
		if "o que é" in query_lower and len(query_lower) < 20:
			if not any(kw in query_lower for kw in ['var', 'vai', 'fase', 'grupo', 'copa', 'mundial']):
				return None  # Deixa a validação normal fazer seu trabalho
		
		return None
	
	def validate_response(self, question: str, response: str, source: str) -> Tuple[bool, str]:
		"""
		Valida se a resposta é relevante à pergunta e não foi 'alucinou'.
		
		Args:
			question: Pergunta original
			response: Resposta gerada
			source: Fonte ('rag' ou 'serper')
		
		Returns:
			Tuple[bool, str]: (é_válida, razão)
		"""
		response_lower = response.lower()
		
		# Rejeita respostas muito curtas/vazias
		if len(response.strip()) < 20:
			return False, "Resposta inadequada - muito curta ou vazia"
		
		# Verifica respostas genéricas/fora de escopo
		red_flags = [
			'não tenho informação',
			'nao tenho informacao',
			'fora do escopo',
			'não posso responder',
			'nao posso responder',
			'isso é confidencial',
			'isso é privado',
		]
		
		if any(flag in response_lower for flag in red_flags):
			return False, "Sistema devolveu resposta de fora do escopo"
		
		# Valida coerência entre pergunta e resposta
		question_lower = question.lower()
		
		# Se pergunta menciona Copa, resposta deve mencionar Copa
		if any(kw in question_lower for kw in ['copa', 'mundial', 'fifa']):
			if not any(kw in response_lower for kw in ['copa', 'mundial', 'fifa']):
				logger.warning(f"Resposta pode estar fora de contexto: {response[:100]}")
				# Ainda permite, mas loga aviso
		
		return True, "Resposta válida"


# Singleton instance
_validator = None


def get_scope_validator() -> ScopeValidator:
	"""Retorna instância única do validador."""
	global _validator
	if _validator is None:
		_validator = ScopeValidator()
	return _validator
