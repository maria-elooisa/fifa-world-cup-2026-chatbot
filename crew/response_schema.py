"""
Schemas estruturados para respostas do sistema.
Define o formato JSON esperado para diferentes tipos de resposta.
"""

from typing import Dict, List, Optional, Literal
from dataclasses import dataclass, asdict
import json


@dataclass
class ResponseMetadata:
    """Metadados da resposta."""
    model: str
    tokens_used: int
    source: str  # "llm", "rag", "web", "simulated"
    context_source: Optional[str] = None  # "rag", "web", None
    confidence: float = 0.0  # 0.0-1.0


@dataclass
class StructuredResponse:
    """
    Schema estruturado para respostas sobre Copa do Mundo.
    
    Exemplo:
    {
        "type": "historical_facts",
        "query": "Quantas Copas o Brasil ganhou?",
        "answer": "Brasil ganhou 5 Copas do Mundo...",
        "main_facts": ["Brasil: 5 títulos", "Único pentacampeão", ...],
        "related_topics": ["Pelé", "Ronaldo", ...],
        "sources": ["RAG", "Knowledgebase"],
        "metadata": {...}
    }
    """
    
    type: Literal[
        "historical_facts",
        "tournament_info", 
        "player_stats",
        "rule_explanation",
        "2026_info",
        "general_info"
    ]
    query: str
    answer: str
    main_facts: List[str]
    related_topics: Optional[List[str]] = None
    sources: List[str] = None
    metadata: Optional[Dict] = None
    
    def __post_init__(self):
        if self.sources is None:
            self.sources = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        """Converte para dicionário."""
        return {
            "type": self.type,
            "query": self.query,
            "answer": self.answer,
            "main_facts": self.main_facts,
            "related_topics": self.related_topics or [],
            "sources": self.sources,
            "metadata": self.metadata
        }
    
    def to_json(self) -> str:
        """Converte para JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @staticmethod
    def from_dict(data: Dict) -> "StructuredResponse":
        """Cria objeto a partir de dicionário."""
        return StructuredResponse(
            type=data.get("type", "general_info"),
            query=data.get("query", ""),
            answer=data.get("answer", ""),
            main_facts=data.get("main_facts", []),
            related_topics=data.get("related_topics"),
            sources=data.get("sources", []),
            metadata=data.get("metadata")
        )


class ResponseStructurer:
    """
    Estrutura respostas de forma consistente.
    Converte respostas de texto livre em formato estruturado.
    """
    
    @staticmethod
    def build_historical_facts_prompt() -> str:
        """Prompt para fatos históricos da Copa."""
        return """Você é um especialista em história da Copa do Mundo FIFA.

TAREFA: Estruture sua resposta EXATAMENTE no formato JSON abaixo.

FORMATO JSON (OBRIGATÓRIO):
{
  "type": "historical_facts",
  "query": "[pergunta original]",
  "answer": "[resposta principal, 100-200 palavras]",
  "main_facts": [
    "[fato 1]",
    "[fato 2]",
    "[fato 3]"
  ],
  "related_topics": ["tópico1", "tópico2"]
}

REGRAS:
1. A resposta deve ser um JSON válido
2. "answer" deve ser uma explicação clara e concisa
3. "main_facts" deve listar 3-5 fatos principais
4. Sempre inclua ano e contexto temporal
5. Se não tiver certeza, indique com "(?)"

EXEMPLO:
Q: "Quantas Copas o Brasil ganhou?"
{
  "type": "historical_facts",
  "query": "Quantas Copas o Brasil ganhou?",
  "answer": "Brasil ganhou 5 Copas do Mundo, sendo o único país pentacampeão. Os títulos foram conquistados em 1958, 1962, 1970, 1994 e 2002.",
  "main_facts": [
    "Brasil: 5 títulos (pentacampeão)",
    "1958: Primeira Copa, disputada na Suécia",
    "2002: Última Copa conquistada pelo Brasil",
    "Pelé e Ronaldo são os principais artilheiros brasileiros"
  ],
  "related_topics": ["Pelé", "Ronaldo", "Marta"]
}

IMPORTANTE: Responda APENAS com JSON válido, sem texto adicional."""
    
    @staticmethod
    def build_tournament_info_prompt() -> str:
        """Prompt para informações sobre torneios/Copas."""
        return """Você é um especialista em Copa do Mundo FIFA.

TAREFA: Estruture sua resposta EXATAMENTE no formato JSON abaixo.

FORMATO JSON (OBRIGATÓRIO):
{
  "type": "tournament_info",
  "query": "[pergunta original]",
  "answer": "[resposta principal, 100-150 palavras]",
  "main_facts": [
    "[fato 1]",
    "[fato 2]",
    "[fato 3]"
  ],
  "related_topics": ["tópico1", "tópico2"]
}

INFORMAÇÕES CHAVE POR COPA:
- Ano, local, datas
- Número de times, grupos, formato
- Campeão, vice, terceiro lugar
- Estatísticas importantes (gols, público)
- Momentos marcantes

REGRAS:
1. Responda APENAS com JSON válido
2. "answer" explicação clara (máximo 150 palavras)
3. "main_facts": 3-5 fatos principais
4. Cite sempre as datas/anos
5. Seja preciso sobre detalhes

IMPORTANTE: Responda APENAS com JSON válido, sem texto adicional."""
    
    @staticmethod
    def build_player_stats_prompt() -> str:
        """Prompt para estatísticas de jogadores."""
        return """Você é um especialista em história e estatísticas da Copa do Mundo.

TAREFA: Estruture sua resposta EXATAMENTE no formato JSON abaixo.

FORMATO JSON (OBRIGATÓRIO):
{
  "type": "player_stats",
  "query": "[pergunta original]",
  "answer": "[resposta principal, 100-150 palavras]",
  "main_facts": [
    "[fato estatístico 1]",
    "[fato estatístico 2]",
    "[fato estatístico 3]"
  ],
  "related_topics": ["jogador1", "jogador2"]
}

INFORMAÇÕES IMPORTANTES:
- Gols marcados
- Partidas jogadas
- Títulos conquistados
- Recordes quebrados
- Anos de participação

REGRAS:
1. Responda APENAS com JSON válido
2. "answer" deve incluir estatísticas principais
3. "main_facts" lista números e conquistas
4. Sempre cite o período/anos
5. Se houver dúvida, marque com "(?)"

IMPORTANTE: Responda APENAS com JSON válido, sem texto adicional."""
    
    @staticmethod
    def build_rule_explanation_prompt() -> str:
        """Prompt para explicação de regras."""
        return """Você é um especialista em regras de Copa do Mundo FIFA.

TAREFA: Estruture sua resposta EXATAMENTE no formato JSON abaixo.

FORMATO JSON (OBRIGATÓRIO):
{
  "type": "rule_explanation",
  "query": "[pergunta original]",
  "answer": "[explicação clara, 100-150 palavras]",
  "main_facts": [
    "[aspecto 1 da regra]",
    "[aspecto 2 da regra]",
    "[aspecto 3 da regra]"
  ],
  "related_topics": ["tópico relacionado"]
}

REGRAS A COBRIR:
- Formato do torneio (grupos, fases)
- Critérios de classificação
- Desempates
- Cartões e suspensões
- Regulamentos especiais para 2026

REGRAS:
1. Responda APENAS com JSON válido
2. "answer" explicação didática e clara
3. "main_facts" lista aspectos principais
4. Use linguagem acessível
5. Cite regras oficiais quando possível

IMPORTANTE: Responda APENAS com JSON válido, sem texto adicional."""
    
    @staticmethod
    def build_copa_2026_prompt() -> str:
        """Prompt para informações sobre Copa 2026."""
        return """Você é especialista em Copa do Mundo 2026 FIFA.

TAREFA: Estruture sua resposta EXATAMENTE no formato JSON abaixo.

FORMATO JSON (OBRIGATÓRIO):
{
  "type": "2026_info",
  "query": "[pergunta original]",
  "answer": "[resposta prática, 100-150 palavras]",
  "main_facts": [
    "[informação prática 1]",
    "[informação prática 2]",
    "[informação prática 3]"
  ],
  "related_topics": ["localização", "transporte", "hospedagem"]
}

INFORMAÇÕES PRINCIPAIS 2026:
- Datas: Junho-Julho 2026
- Sedes: EUA, Canadá, México
- 48 times (em vez de 32)
- Novo formato de grupos
- Cidades anfitriãs
- Estádios
- Hospedagem, transporte, turismo

REGRAS:
1. Responda APENAS com JSON válido
2. "answer" informações práticas e úteis
3. "main_facts" dados verificáveis
4. Sempre cite datas e locais
5. Seja preciso sobre números

IMPORTANTE: Responda APENAS com JSON válido, sem texto adicional."""
    
    @staticmethod
    def detect_response_type(query: str) -> str:
        """
        Detecta o tipo de resposta necessária baseado na query.
        
        Returns:
            "historical_facts", "tournament_info", "player_stats", 
            "rule_explanation", "2026_info", ou "general_info"
        """
        query_lower = query.lower()
        
        # Detecta 2026
        if "2026" in query:
            return "2026_info"
        
        # Detecta estatísticas de jogadores
        if any(word in query_lower for word in ["gols", "artilheiro", "jogador", "camisa", "estrela", "craque"]):
            return "player_stats"
        
        # Detecta regras
        if any(word in query_lower for word in ["regra", "como", "permitido", "proibido", "formato", "critério"]):
            return "rule_explanation"
        
        # Detecta informações de torneio
        if any(word in query_lower for word in ["copa", "mundial", "torneio", "final", "grupo", "sede", "host"]):
            return "tournament_info"
        
        # Detecta fatos históricos
        if any(word in query_lower for word in ["história", "historico", "quando", "qual", "quantas", "primeiro", "recordes"]):
            return "historical_facts"
        
        return "general_info"
    
    @staticmethod
    def get_prompt_for_type(response_type: str) -> str:
        """Retorna o prompt apropriado para o tipo de resposta."""
        prompts = {
            "historical_facts": ResponseStructurer.build_historical_facts_prompt(),
            "tournament_info": ResponseStructurer.build_tournament_info_prompt(),
            "player_stats": ResponseStructurer.build_player_stats_prompt(),
            "rule_explanation": ResponseStructurer.build_rule_explanation_prompt(),
            "2026_info": ResponseStructurer.build_copa_2026_prompt(),
            "general_info": ResponseStructurer.build_historical_facts_prompt()  # fallback
        }
        return prompts.get(response_type, prompts["general_info"])
