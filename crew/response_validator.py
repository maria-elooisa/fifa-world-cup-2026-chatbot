"""
Validador de estrutura de respostas.
Garante que as respostas seguem o formato JSON estruturado.
"""

import json
import logging
from typing import Tuple, Dict, Optional
import re

logger = logging.getLogger(__name__)


class ResponseValidator:
    """Valida e ajusta respostas estruturadas."""
    
    @staticmethod
    def is_valid_json(text: str) -> Tuple[bool, Optional[Dict]]:
        """
        Verifica se texto é JSON válido.
        
        Returns:
            (is_valid, parsed_json)
        """
        try:
            # Remove markdown code blocks se houver
            text = text.strip()
            if text.startswith("```"):
                # Remove ``` e ```json, etc
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
                text = text.strip()
            
            data = json.loads(text)
            return True, data
        except json.JSONDecodeError as e:
            logger.warning(f"JSON inválido: {e}")
            return False, None
    
    @staticmethod
    def validate_structured_response(response_dict: Dict) -> Tuple[bool, str]:
        """
        Valida se resposta segue o schema estruturado.
        
        Returns:
            (is_valid, error_message)
        """
        required_fields = ["type", "query", "answer", "main_facts"]
        
        for field in required_fields:
            if field not in response_dict:
                return False, f"Campo obrigatório ausente: '{field}'"
        
        # Valida tipos
        if not isinstance(response_dict["type"], str):
            return False, "'type' deve ser string"
        
        if not isinstance(response_dict["query"], str):
            return False, "'query' deve ser string"
        
        if not isinstance(response_dict["answer"], str):
            return False, "'answer' deve ser string"
        
        if not isinstance(response_dict["main_facts"], list):
            return False, "'main_facts' deve ser lista"
        
        if len(response_dict["main_facts"]) == 0:
            return False, "'main_facts' não pode estar vazio"
        
        # Valida tipo
        valid_types = [
            "historical_facts",
            "tournament_info",
            "player_stats",
            "rule_explanation",
            "2026_info",
            "general_info"
        ]
        
        if response_dict["type"] not in valid_types:
            return False, f"'type' inválido. Esperado um de: {', '.join(valid_types)}"
        
        # Valida comprimento mínimo
        if len(response_dict["answer"]) < 20:
            return False, "'answer' muito curto (mínimo 20 caracteres)"
        
        return True, "Válido"
    
    @staticmethod
    def extract_json_from_text(text: str) -> Optional[Dict]:
        """
        Tenta extrair JSON de texto que pode conter conteúdo adicional.
        
        Strategies:
        1. Verifica se é JSON puro
        2. Procura por bloco JSON entre { }
        3. Tenta remover prefixo/sufixo de texto
        """
        text = text.strip()
        
        # Tenta JSON direto
        is_valid, data = ResponseValidator.is_valid_json(text)
        if is_valid:
            return data
        
        # Procura por padrão { ... }
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            json_str = match.group(0)
            is_valid, data = ResponseValidator.is_valid_json(json_str)
            if is_valid:
                return data
        
        # Tenta remover prefixo comum ("Aqui está a resposta: ", etc)
        prefixes = [
            "Aqui está a resposta:",
            "Aqui está o resultado:",
            "Resposta estruturada:",
            "Resultado:",
            "JSON:",
            "```json",
            "```"
        ]
        
        for prefix in prefixes:
            if text.startswith(prefix):
                remaining = text[len(prefix):].strip()
                is_valid, data = ResponseValidator.is_valid_json(remaining)
                if is_valid:
                    return data
        
        logger.warning(f"Não consegui extrair JSON válido do texto")
        return None
    
    @staticmethod
    def fix_incomplete_json(text: str) -> str:
        """
        Tenta corrigir JSON incompleto ou mal formatado.
        
        Técnicas:
        - Adiciona chaves de fechamento faltantes
        - Corrige aspas não fechadas
        - Remove trailing commas
        """
        text = text.strip()
        
        # Conta chaves abertas vs fechadas
        open_braces = text.count('{')
        close_braces = text.count('}')
        
        if open_braces > close_braces:
            text += '}' * (open_braces - close_braces)
        
        # Remove trailing comma antes de }
        text = re.sub(r',(\s*})', r'\1', text)
        
        # Remove trailing comma antes de ]
        text = re.sub(r',(\s*\])', r'\1', text)
        
        return text
    
    @staticmethod
    def validate_and_fix_response(text: str) -> Tuple[bool, Optional[Dict], str]:
        """
        Valida resposta e tenta corrigir se possível.
        
        Returns:
            (is_valid, parsed_json, message)
        """
        if not text or not isinstance(text, str):
            return False, None, "Texto vazio ou inválido"
        
        # Tenta extrair JSON
        json_data = ResponseValidator.extract_json_from_text(text)
        
        if json_data:
            # Valida estrutura
            is_valid, msg = ResponseValidator.validate_structured_response(json_data)
            if is_valid:
                return True, json_data, "JSON válido e estruturado corretamente"
            else:
                return False, json_data, f"Estrutura inválida: {msg}"
        
        # Tenta corrigir JSON mal formatado
        fixed_text = ResponseValidator.fix_incomplete_json(text)
        is_valid, fixed_json = ResponseValidator.is_valid_json(fixed_text)
        
        if is_valid:
            is_valid_struct, msg = ResponseValidator.validate_structured_response(fixed_json)
            if is_valid_struct:
                return True, fixed_json, "JSON corrigido e validado"
            else:
                return False, fixed_json, f"JSON corrigido mas estrutura inválida: {msg}"
        
        return False, None, "Não consegui extrair/validar JSON"
    
    @staticmethod
    def extract_main_answer(json_data: Dict) -> str:
        """
        Extrai a resposta principal (answer) do JSON estruturado.
        """
        return json_data.get("answer", "Sem resposta disponível")
    
    @staticmethod
    def format_structured_response(json_data: Dict) -> str:
        """
        Formata resposta estruturada em texto legível.
        
        Exemplo output:
        ```
        RESPOSTA ESTRUTURADA
        
        Pergunta: Quantas Copas o Brasil ganhou?
        
        Resposta:
        Brasil ganhou 5 Copas do Mundo, sendo o único país pentacampeão...
        
        Fatos Principais:
        • Brasil: 5 títulos (pentacampeão)
        • 1958: Primeira Copa, disputada na Suécia
        • 2002: Última Copa conquistada pelo Brasil
        
        Tópicos Relacionados: Pelé, Ronaldo, Marta
        Tipo: historical_facts
        ```
        """
        output = []
        output.append("RESPOSTA ESTRUTURADA\n")
        
        # Pergunta
        query = json_data.get("query", "N/A")
        output.append(f"Pergunta: {query}\n")
        
        # Resposta
        answer = json_data.get("answer", "N/A")
        output.append(f"Resposta:\n{answer}\n")
        
        # Fatos principais
        main_facts = json_data.get("main_facts", [])
        if main_facts:
            output.append("Fatos Principais:")
            for fact in main_facts:
                output.append(f"  • {fact}")
            output.append("")
        
        # Tópicos relacionados
        related = json_data.get("related_topics", [])
        if related:
            output.append(f"Tópicos Relacionados: {', '.join(related)}")
        
        # Tipo e fontes
        response_type = json_data.get("type", "general_info")
        sources = json_data.get("sources", [])
        
        output.append(f"\nTipo: {response_type}")
        if sources:
            output.append(f"Fontes: {', '.join(sources)}")
        
        return "\n".join(output)
