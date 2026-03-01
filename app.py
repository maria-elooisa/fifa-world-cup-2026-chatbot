import streamlit as st
import streamlit.components.v1 as components
import asyncio
import logging
import base64
import os
import re
import json
import ast
from crew.supervisor import Supervisor
from datetime import datetime
from crew.observability import init_observability
from crew.voice_utils import (
    transcribe_audio, 
    text_to_speech, 
    get_speech_lang_code,
    get_gtts_lang_code
)

init_observability()
DEFAULT_CONTEXT_TTL = int(os.getenv("CONTEXT_TTL", "3"))

# ========================================
# 🌍 SISTEMA DE INTERNACIONALIZAÇÃO (i18n)
# ========================================

LANGUAGE_OPTIONS = [
    "🇧🇷 Português",
    "🇺🇸 English",
    "🇪🇸 Español",
    "🇫🇷 Français",
    "🇩🇪 Deutsch",
    "🇮🇹 Italiano",
    "🇯🇵 日本語",
    "🇨🇳 中文",
    "🇸🇦 العربية",
    "Outro...",
]

LANGUAGE_MAP = {
    "🇧🇷 Português": "português brasileiro",
    "🇺🇸 English": "English",
    "🇪🇸 Español": "Español",
    "🇫🇷 Français": "Français",
    "🇩🇪 Deutsch": "Deutsch",
    "🇮🇹 Italiano": "Italiano",
    "🇯🇵 日本語": "日本語",
    "🇨🇳 中文": "中文",
    "🇸🇦 العربية": "العربية",
}

# 📚 Dicionário de todas as traduções da interface
TRANSLATIONS = {
    "🇧🇷 Português": {
        # Configuração da página
        "page_title": "Copa 2026 Chat",
        "page_icon": "⚽",
        
        # Cabeçalho/Hero
        "app_title": "Assistente da COPA 2026",
        "app_subtitle": "Pergunte sobre seleções, jogos, história e curiosidades.",
        "ball_alt": "Bola",
        
        # Seletor de idioma
        "language_label": "Idioma da resposta",
        "language_help": "Se o usuário não especificar o idioma, o assistente responderá neste idioma.",
        "other_language": "Outro idioma",
        "other_language_placeholder": "Ex.: coreano, polonês, hindi",
        
        # Chat
        "chat_input_placeholder": "Digite sua mensagem...",
        "thinking_message": "Pensando…",
        "welcome_message": "👋 Bem-vindo! Faça uma pergunta sobre a Copa do Mundo 2026 — posso ajudar com seleções, jogos, história e curiosidades.",
        "speak_button": "🎤 Falar",
        "listen_button": "Ouvir resposta",
        "listening": "🎤 Ouvindo...",
        "voice_not_supported": "Seu navegador não suporta reconhecimento de voz.",
        
        # Metadados das mensagens
        "main_facts": "📌 Principais fatos",
        "source": "Fonte:",
        "related_topics": "Tópicos relacionados:",
        "pages": "Páginas:",
        "links": "Links:",
        "source_rag": "📄 RAG (Documento oficial)",
        "source_web": "🌐 Web (Serper)",
        "source_system": "Sistema",
        
        # Debug
        "debug_title": "🔍 Debug: Resposta completa do backend",
    },
    
    "🇺🇸 English": {
        # Page configuration
        "page_title": "World Cup 2026 Chat",
        "page_icon": "⚽",
        
        # Header/Hero
        "app_title": "WORLD CUP 2026 Assistant",
        "app_subtitle": "Ask about teams, matches, history and curiosities.",
        "ball_alt": "Ball",
        
        # Language selector
        "language_label": "Response language",
        "language_help": "If the user doesn't specify the language, the assistant will respond in this language.",
        "other_language": "Other language",
        "other_language_placeholder": "e.g.: Korean, Polish, Hindi",
        
        # Chat
        "chat_input_placeholder": "Type your message...",
        "thinking_message": "Thinking…",
        "welcome_message": "👋 Welcome! Ask a question about the 2026 World Cup — I can help with teams, matches, history and curiosities.",
        "speak_button": "🎤 Speak",
        "listen_button": "Listen to answer",
        "listening": "🎤 Listening...",
        "voice_not_supported": "Your browser doesn't support voice recognition.",
        
        # Message metadata
        "main_facts": "📌 Main facts",
        "source": "Source:",
        "related_topics": "Related topics:",
        "pages": "Pages:",
        "links": "Links:",
        "source_rag": "📄 RAG (Official document)",
        "source_web": "🌐 Web (Serper)",
        "source_system": "System",
        
        # Debug
        "debug_title": "🔍 Debug: Complete backend response",
    },

    "🇪🇸 Español": {
        # Configuración de página
        "page_title": "Copa Mundial 2026 Chat",
        "page_icon": "⚽",
        
        # Encabezado/Hero
        "app_title": "Asistente de la COPA MUNDIAL 2026",
        "app_subtitle": "Pregúntame sobre selecciones, partidos, historia y curiosidades.",
        "ball_alt": "Balón",
        
        # Selector de idioma
        "language_label": "Idioma de respuesta",
        "language_help": "Si el usuario no especifica el idioma, el asistente responderá en este idioma.",
        "other_language": "Otro idioma",
        "other_language_placeholder": "ej.: coreano, polaco, hindi",
        
        # Chat
        "chat_input_placeholder": "Escribe tu mensaje...",
        "thinking_message": "Pensando…",
        "welcome_message": "👋 ¡Bienvenido! Haz una pregunta sobre la Copa Mundial 2026 — puedo ayudarte con selecciones, partidos, historia y curiosidades.",
        "speak_button": "🎤 Hablar",
        "listen_button": "Escuchar respuesta",
        "listening": "🎤 Escuchando...",
        "voice_not_supported": "Tu navegador no admite reconocimiento de voz.",
        
        # Metadatos de mensajes
        "main_facts": "📌 Datos principales",
        "source": "Fuente:",
        "related_topics": "Temas relacionados:",
        "pages": "Páginas:",
        "links": "Enlaces:",
        "source_rag": "📄 RAG (Documento oficial)",
        "source_web": "🌐 Web (Serper)",
        "source_system": "Sistema",
        
        # Debug
        "debug_title": "🔍 Debug: Respuesta completa del backend",
    },

    "🇫🇷 Français": {
        # Configuration de page
        "page_title": "Coupe du Monde 2026 Chat",
        "page_icon": "⚽",
        
        # En-tête/Hero
        "app_title": "Assistant COUPE DU MONDE 2026",
        "app_subtitle": "Posez des questions sur les équipes, les matchs, l'histoire et les curiosités.",
        "ball_alt": "Ballon",
        
        # Sélecteur de langue
        "language_label": "Langue de réponse",
        "language_help": "Si l'utilisateur ne spécifie pas la langue, l'assistant répondra dans cette langue.",
        "other_language": "Autre langue",
        "other_language_placeholder": "ex.: coréen, polonais, hindi",
        
        # Chat
        "chat_input_placeholder": "Tapez votre message...",
        "thinking_message": "En réflexion…",
        "welcome_message": "👋 Bienvenue! Posez une question sur la Coupe du Monde 2026 — je peux vous aider avec les équipes, les matchs, l'histoire et les curiosités.",
        "speak_button": "🎤 Parler",
        "listen_button": "Écouter la réponse",
        "listening": "🎤 Écoute...",
        "voice_not_supported": "Votre navigateur ne prend pas en charge la reconnaissance vocale.",
        
        # Métadonnées des messages
        "main_facts": "📌 Faits principaux",
        "source": "Source:",
        "related_topics": "Sujets connexes:",
        "pages": "Pages:",
        "links": "Liens:",
        "source_rag": "📄 RAG (Document officiel)",
        "source_web": "🌐 Web (Serper)",
        "source_system": "Système",
        
        # Debug
        "debug_title": "🔍 Debug: Réponse complète du backend",
    },

    "🇩🇪 Deutsch": {
        # Seitenkonfiguration
        "page_title": "WM 2026 Chat",
        "page_icon": "⚽",
        
        # Header/Hero
        "app_title": "WM 2026 Assistent",
        "app_subtitle": "Fragen Sie nach Mannschaften, Spielen, Geschichte und Kuriositäten.",
        "ball_alt": "Ball",
        
        # Sprachauswahl
        "language_label": "Antwortsprache",
        "language_help": "Wenn der Benutzer keine Sprache angibt, antwortet der Assistent in dieser Sprache.",
        "other_language": "Andere Sprache",
        "other_language_placeholder": "z.B.: Koreanisch, Polnisch, Hindi",
        
        # Chat
        "chat_input_placeholder": "Schreiben Sie Ihre Nachricht...",
        "thinking_message": "Denke nach…",
        "welcome_message": "👋 Willkommen! Stellen Sie eine Frage zur WM 2026 — ich kann bei Mannschaften, Spielen, Geschichte und Kuriositäten helfen.",
        "speak_button": "🎤 Sprechen",
        "listen_button": "Antwort anhören",
        "listening": "🎤 Hören...",
        "voice_not_supported": "Ihr Browser unterstützt keine Spracherkennung.",
        
        # Nachrichten-Metadaten
        "main_facts": "📌 Hauptfakten",
        "source": "Quelle:",
        "related_topics": "Verwandte Themen:",
        "pages": "Seiten:",
        "links": "Links:",
        "source_rag": "📄 RAG (Offizielles Dokument)",
        "source_web": "🌐 Web (Serper)",
        "source_system": "System",
        
        # Debug
        "debug_title": "🔍 Debug: Vollständige Backend-Antwort",
    },

    "🇮🇹 Italiano": {
        # Configurazione pagina
        "page_title": "Chat Mondiali 2026",
        "page_icon": "⚽",
        
        # Intestazione/Hero
        "app_title": "Assistente MONDIALI 2026",
        "app_subtitle": "Chiedi informazioni su squadre, partite, storia e curiosità.",
        "ball_alt": "Pallone",
        
        # Selettore lingua
        "language_label": "Lingua di risposta",
        "language_help": "Se l'utente non specifica la lingua, l'assistente risponderà in questa lingua.",
        "other_language": "Altra lingua",
        "other_language_placeholder": "es.: coreano, polacco, hindi",
        
        # Chat
        "chat_input_placeholder": "Scrivi il tuo messaggio...",
        "thinking_message": "Sto pensando…",
        "welcome_message": "👋 Benvenuto! Fai una domanda sui Mondiali 2026 — posso aiutarti con squadre, partite, storia e curiosità.",
        "speak_button": "🎤 Parla",
        "listen_button": "Ascolta risposta",
        "listening": "🎤 Ascolto...",
        "voice_not_supported": "Il tuo browser non supporta il riconoscimento vocale.",
        
        # Metadati messaggi
        "main_facts": "📌 Fatti principali",
        "source": "Fonte:",
        "related_topics": "Argomenti correlati:",
        "pages": "Pagine:",
        "links": "Collegamenti:",
        "source_rag": "📄 RAG (Documento ufficiale)",
        "source_web": "🌐 Web (Serper)",
        "source_system": "Sistema",
        
        # Debug
        "debug_title": "🔍 Debug: Risposta completa del backend",
    },

    "🇯🇵 日本語": {
        # ページ設定
        "page_title": "ワールドカップ2026チャット",
        "page_icon": "⚽",
        
        # ヘッダー/Hero
        "app_title": "ワールドカップ2026アシスタント",
        "app_subtitle": "チーム、試合、歴史、豆知識について質問してください。",
        "ball_alt": "ボール",
        
        # 言語選択
        "language_label": "応答言語",
        "language_help": "ユーザーが言語を指定しない場合、アシスタントはこの言語で応答します。",
        "other_language": "その他の言語",
        "other_language_placeholder": "例：韓国語、ポーランド語、ヒンディー語",
        
        # チャット
        "chat_input_placeholder": "メッセージを入力してください...",
        "thinking_message": "考えています…",
        "welcome_message": "👋 ようこそ！2026年ワールドカップについて質問してください。チーム、試合、歴史、豆知識についてお手伝いできます。",
        "speak_button": "🎤 話す",
        "listen_button": "回答を聞く",
        "listening": "🎤 聞いています...",
        "voice_not_supported": "お使いのブラウザは音声認識をサポートしていません。",
        
        # メッセージメタデータ
        "main_facts": "📌 主な事実",
        "source": "ソース:",
        "related_topics": "関連トピック:",
        "pages": "ページ:",
        "links": "リンク:",
        "source_rag": "📄 RAG（公式文書）",
        "source_web": "🌐 Web（Serper）",
        "source_system": "システム",
        
        # デバッグ
        "debug_title": "🔍 デバッグ：バックエンドの完全な応答",
    },

    "🇨🇳 中文": {
        # 页面配置
        "page_title": "2026世界杯聊天",
        "page_icon": "⚽",
        
        # 标题/Hero
        "app_title": "2026世界杯助手",
        "app_subtitle": "询问球队、比赛、历史和趣闻。",
        "ball_alt": "足球",
        
        # 语言选择
        "language_label": "回复语言",
        "language_help": "如果用户未指定语言，助手将使用此语言回复。",
        "other_language": "其他语言",
        "other_language_placeholder": "例如：韩语、波兰语、印地语",
        
        # 聊天
        "chat_input_placeholder": "输入您的消息...",
        "thinking_message": "思考中…",
        "welcome_message": "👋 欢迎！询问关于2026年世界杯的问题——我可以帮助您了解球队、比赛、历史和趣闻。",
        "speak_button": "🎤 说话",
        "listen_button": "收听回答",
        "listening": "🎤 正在听...",
        "voice_not_supported": "您的浏览器不支持语音识别。",
        
        # 消息元数据
        "main_facts": "📌 主要事实",
        "source": "来源:",
        "related_topics": "相关主题:",
        "pages": "页面:",
        "links": "链接:",
        "source_rag": "📄 RAG（官方文档）",
        "source_web": "🌐 网络（Serper）",
        "source_system": "系统",
        
        # 调试
        "debug_title": "🔍 调试：后端完整响应",
    },

    "🇸🇦 العربية": {
        # إعداد الصفحة
        "page_title": "دردشة كأس العالم 2026",
        "page_icon": "⚽",
        
        # الرأس/Hero
        "app_title": "مساعد كأس العالم 2026",
        "app_subtitle": "اسأل عن الفرق والمباريات والتاريخ والحقائق الشيقة.",
        "ball_alt": "كرة",
        
        # اختيار اللغة
        "language_label": "لغة الإجابة",
        "language_help": "إذا لم يحدد المستخدم اللغة، سيجيب المساعد بهذه اللغة.",
        "other_language": "لغة أخرى",
        "other_language_placeholder": "مثال: كورية، بولندية، هندية",
        
        # المحادثة
        "chat_input_placeholder": "اكتب رسالتك...",
        "thinking_message": "أفكر…",
        "welcome_message": "👋 مرحباً! اسأل سؤالاً عن كأس العالم 2026 — يمكنني المساعدة في الفرق والمباريات والتاريخ والحقائق الشيقة.",
        "speak_button": "🎤 تحدث",
        "listen_button": "الاستماع إلى الإجابة",
        "listening": "🎤 الاستماع...",
        "voice_not_supported": "متصفحك لا يدعم التعرف على الصوت.",
        
        # بيانات الرسائل الوصفية
        "main_facts": "📌 الحقائق الرئيسية",
        "source": "المصدر:",
        "related_topics": "المواضيع ذات الصلة:",
        "pages": "الصفحات:",
        "links": "الروابط:",
        "source_rag": "📄 RAG (وثيقة رسمية)",
        "source_web": "🌐 الويب (Serper)",
        "source_system": "النظام",
        
        # التصحيح
        "debug_title": "🔍 التصحيح: الاستجابة الكاملة للخلفية",
    }
}

def get_text(key: str) -> str:
    """Obtém texto traduzido baseado no idioma selecionado"""
    current_lang = st.session_state.get("preferred_language", "🇧🇷 Português")
    
    # Se for "Outro...", usa português como fallback
    if current_lang == "Outro...":
        current_lang = "🇧🇷 Português"
    
    # Retorna o texto na língua selecionada, ou português como fallback
    return TRANSLATIONS.get(current_lang, TRANSLATIONS["🇧🇷 Português"]).get(
        key, TRANSLATIONS["🇧🇷 Português"].get(key, key)
    )


def auto_translate_system_message(content: str) -> str:
    """Traduz automaticamente mensagens do sistema usando Google Translate API ou fallback"""
    if not content or not content.strip():
        return content
    
    current_lang = st.session_state.get("preferred_language", "🇧🇷 Português")
    
    # Se for português, não precisa traduzir
    if current_lang == "🇧🇷 Português" or current_lang == "Outro...":
        return content
    
    try:
        # Primeiro, tenta usar Google Translate (se disponível)
        return _translate_with_google(content, current_lang)
    except:
        # Fallback: tradução por substituição
        return _translate_with_fallback(content, current_lang)


def _translate_with_google(content: str, target_lang: str) -> str:
    """Tenta traduzir usando Google Translate (requer googletrans)"""
    try:
        from googletrans import Translator
        translator = Translator()
        
        # Mapear idiomas para códigos ISO
        lang_codes = {
            "🇺🇸 English (US)": "en",
            "🇪🇸 Español": "es", 
            "🇫🇷 Français": "fr",
            "🇩🇪 Deutsch": "de",
            "🇮🇹 Italiano": "it",
            "🇯🇵 日本語": "ja",
            "🇨🇳 中文": "zh",
            "🇸🇦 العربية": "ar"
        }
        
        if target_lang in lang_codes:
            result = translator.translate(content, src='pt', dest=lang_codes[target_lang])
            return result.text
    except ImportError:
        # googletrans não está instalado, usa fallback
        pass
    except Exception:
        # Qualquer erro na tradução, usa fallback
        pass
    
    raise Exception("Google Translate não disponível")


def _translate_with_fallback(content: str, target_lang: str) -> str:
    """Tradução simplificada por substituição direta"""
    # Dicionário mestre de traduções básicas
    base_translations = {
        "🇺🇸 English (US)": {
            "Desculpe": "Sorry",
            "não consegui": "I couldn't",
            "gerar uma resposta": "generate a response", 
            "agora": "right now",
            "Tente novamente": "Please try again",
            "fora do escopo": "outside the scope",
            "Copa do Mundo": "World Cup",
            "Por favor": "Please",
            "Ocorreu um erro": "An error occurred",
            "ao processar": "while processing",
            "sua solicitação": "your request",
            "mais específico": "more specific",
            "pergunta": "question",
            "Processando": "Processing",
            
            # Mensagens específicas do validator - ordenadas por tamanho
            "Esta pergunta não está relacionada à Copa do Mundo ou à Copa 2026. Eu sou especializado em informações sobre a Copa do Mundo": "This question is not related to the World Cup or the 2026 World Cup. I specialize in information about the World Cup",
            "Esta pergunta não está relacionada à Copa do Mundo ou à Copa 2026": "This question is not related to the World Cup or the 2026 World Cup",
            "Esta pergunta não está relacionada à Copa do Mundo": "This question is not related to the World Cup",
            "Eu sou especializado em informações sobre a Copa do Mundo": "I specialize in information about the World Cup",
            "ou à Copa 2026": "or the 2026 World Cup",
            "Eu sou especializado em informações": "I specialize in information",
            "sobre a Copa do Mundo": "about the World Cup",
            "Você pode perguntar sobre": "You can ask about",
            "História da Copa": "World Cup History",
            "campeonatos, jogadores, recordes": "championships, players, records",
            "datas, cidades, estádios, ingressos": "dates, cities, stadiums, tickets",
            "Regras, fases e formato da competição": "Rules, phases and competition format",
            "Informações práticas para viajar": "Practical travel information",
            "passaporte, visto, hospedagem": "passport, visa, accommodation"
        },
        "🇪🇸 Español": {
            "Desculpe": "Lo siento",
            "não consegui": "no pude",
            "gerar uma resposta": "generar una respuesta",
            "agora": "ahora", 
            "Tente novamente": "Inténtalo de nuevo",
            "fora do escopo": "fuera del alcance",
            "Copa do Mundo": "Copa Mundial",
            "Por favor": "Por favor",
            "Ocorreu um erro": "Ocurrió un error",
            "ao processar": "al procesar",
            "sua solicitação": "tu solicitud",
            "mais específico": "más específico",
            "pergunta": "pregunta",
            "Processando": "Procesando",
            
            # Mensagens específicas do validator - ordenadas por tamanho
            "Esta pergunta não está relacionada à Copa do Mundo ou à Copa 2026. Eu sou especializado em informações sobre a Copa do Mundo": "Esta pregunta no está relacionada con la Copa Mundial o la Copa 2026. Soy especialista en información sobre la Copa Mundial",
            "Esta pergunta não está relacionada à Copa do Mundo ou à Copa 2026": "Esta pregunta no está relacionada con la Copa Mundial o la Copa 2026",
            "Esta pergunta não está relacionada à Copa do Mundo": "Esta pregunta no está relacionada con la Copa Mundial",
            "Eu sou especializado em informações sobre a Copa do Mundo": "Soy especialista en información sobre la Copa Mundial",
            "ou à Copa 2026": "o la Copa 2026",
            "Eu sou especializado em informações": "Soy especialista en información",
            "sobre a Copa do Mundo": "sobre la Copa Mundial",
            "Você pode perguntar sobre": "Puedes preguntar sobre",
            "História da Copa": "Historia de la Copa",
            "campeonatos, jogadores, recordes": "campeonatos, jugadores, récords",
            "datas, cidades, estádios, ingressos": "fechas, ciudades, estadios, entradas",
            "Regras, fases e formato da competição": "Reglas, fases y formato de la competición",
            "Informações práticas para viajar": "Información práctica para viajar",
            "passaporte, visto, hospedagem": "pasaporte, visa, alojamiento"
        },
        "🇫🇷 Français": {
            "Desculpe": "Désolé",
            "não consegui": "je n'ai pas pu", 
            "gerar uma resposta": "générer une réponse",
            "agora": "maintenant",
            "Tente novamente": "Veuillez réessayer",
            "fora do escopo": "hors de portée",
            "Copa do Mundo": "Coupe du Monde",
            "Por favor": "S'il vous plaît",
            "Ocorreu um erro": "Une erreur s'est produite",
            "ao processar": "lors du traitement",
            "sua solicitação": "votre demande", 
            "mais específico": "plus précis",
            "pergunta": "question",
            "Processando": "Traitement",
            
            # Mensagens específicas do validator - ordenadas por tamanho
            "Esta pergunta não está relacionada à Copa do Mundo ou à Copa 2026. Eu sou especializado em informações sobre a Copa do Mundo": "Cette question n'est pas liée à la Coupe du Monde ou à la Coupe 2026. Je suis spécialisé dans les informations sur la Coupe du Monde",
            "Esta pergunta não está relacionada à Copa do Mundo ou à Copa 2026": "Cette question n'est pas liée à la Coupe du Monde ou à la Coupe 2026",
            "Esta pergunta não está relacionada à Copa do Mundo": "Cette question n'est pas liée à la Coupe du Monde",
            "Eu sou especializado em informações sobre a Copa do Mundo": "Je suis spécialisé dans les informations sur la Coupe du Monde",
            "ou à Copa 2026": "ou à la Coupe 2026",
            "Eu sou especializado em informações": "Je suis spécialisé dans les informations",
            "sobre a Copa do Mundo": "sur la Coupe du Monde",
            "Você pode perguntar sobre": "Vous pouvez demander des informations sur",
            "História da Copa": "Histoire de la Coupe",
            "campeonatos, jogadores, recordes": "championnats, joueurs, records",
            "datas, cidades, estádios, ingressos": "dates, villes, stades, billets",
            "Regras, fases e formato da competição": "Règles, phases et format de la compétition",
            "Informações práticas para viajar": "Informations pratiques pour voyager",
            "passaporte, visto, hospedagem": "passeport, visa, hébergement"
        }
        # Adicione mais idiomas se necessário
    }
    
    if target_lang in base_translations:
        result = content
        # PROBLEMA IDENTIFICADO: ordena por tamanho decrescente (frases maiores primeiro)
        # para evitar substituições parciais
        sorted_translations = sorted(base_translations[target_lang].items(), key=lambda x: len(x[0]), reverse=True)
        for pt_phrase, translated_phrase in sorted_translations:
            result = result.replace(pt_phrase, translated_phrase)
        return result
    
    return content  # Se idioma não suportado, retorna original

# ========================================
# 🎨 CORES E ESTILOS
# ========================================

COLORS = {
    "base_bg": "#FFFFFF",
    "card_bg": "#FFFFFF", 
    "text_primary": "#0F172A",
    "text_secondary": "#334155",
    "border": "#E2E8F0",
    "muted": "#64748B",
    # Copa 2026 palette
    "wc_red": "#17552E",
    "wc_green": "#228B22", 
    "wc_blue": "#1E3C72",
    "wc_gold": "#D4AF37",
    "soft_blue": "#E5F2FF",
    "soft_gold": "#FFF6D6",
    "soft_neutral": "#F8FAFC",
}

# ========================================
# 🎨 CSS CUSTOMIZADO
# ========================================

def load_custom_css() -> None:
    # Carregar imagem da bola como base64
    try:
        with open("front/bola-de-futebol.png", "rb") as f:
            img_data = base64.b64encode(f.read()).decode()
        ball_img = f"data:image/png;base64,{img_data}"
    except:
        ball_img = ""  # Fallback se não encontrar a imagem
        
    st.markdown(
        f"""
        <style>
        /* CSS Cache Buster v3.0 - I18N Edition */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {{ font-family: 'Inter', sans-serif; }}

        [data-testid="stToolbar"],
        #MainMenu,
        header,
        footer,
        [data-testid="stSidebar"], 
        [data-testid="stSidebarCollapsedControl"] {{
            display: none !important;
        }}

        html, body, .stApp, .stApp > div, .main, .main > div, [data-testid="stAppViewContainer"], [data-testid="stBottom"] {{
            background: {COLORS['base_bg']} !important;
            color: {COLORS['text_primary']} !important;
        }}

        /* Forçar fundo branco em todos os elementos do rodapé */
        [data-testid="stBottom"], 
        [data-testid="stBottom"] > div,
        footer,
        .stApp footer {{
            background: {COLORS['base_bg']} !important;
        }}

        .main .block-container {{
            max-width: 980px;
            padding-top: 1.6rem;
            padding-bottom: 2rem;
        }}

        .hero {{
            margin: 0 auto 1.5rem;
            text-align: center;
        }}
        .hero-frame {{
            display: block;
            width: 100%;
            max-width: 100%;
            margin: 0;
            border-radius: 18px;
            background: linear-gradient(#FFFFFF, #FFFFFF) padding-box,
                    radial-gradient(ellipse at center, #90EE90, #32CD32, #228B22, #2D5016) border-box;
            padding: 40px 24px;
            border: 4px solid transparent;
            box-shadow: 0 8px 32px rgba(15, 23, 42, 0.15), 0 0 0 1px rgba(45, 80, 22, 0.1);
        }}
        .hero-inner {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            align-items: center;
        }}
        .hero-title {{
            font-size: 48px !important;
            font-weight: 900 !important;
            letter-spacing: -0.03em !important;
            color: {COLORS['text_primary']} !important;
            margin: 0 !important;
            line-height: 1.1 !important;
            text-shadow: 0 2px 4px rgba(15, 23, 42, 0.1) !important;
            display: flex !important;
            align-items: center !important;
            gap: 12px !important;
        }}
        .hero-title img {{
            width: 48px !important;
            height: 48px !important;
            object-fit: contain !important;
        }}
        .hero-subtitle {{
            font-size: 1.1rem;
            color: {COLORS['muted']};
            margin: 0;
        }}

        .chat-surface {{
            background: {COLORS['base_bg']};
            border: none;
            border-radius: 0;
            padding: 0;
            box-shadow: none;
        }}
        .chat-scroll-container {{
            max-height: calc(100vh - 200px);
            overflow-y: auto;
            padding-bottom: 0.5rem;
            scroll-behavior: smooth;
        }}

        .user-row,
        .bot-row {{
            display: flex;
            gap: 10px;
            margin: 12px 0;
        }}
        .user-row {{
            justify-content: flex-end;
        }}
        .bot-row {{
            justify-content: flex-start;
        }}
        .message-container {{
            max-width: 800px;
            display: flex;
            flex-direction: column;
        }}
        .user-bubble,
        .bot-bubble {{
            border: none;
            border-radius: 16px;
            padding: 14px 16px;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
            line-height: 1.6;
            word-break: break-word;
            margin-bottom: 4px;
        }}
        .user-bubble::selection,
        .bot-bubble::selection,
        .user-bubble *::selection,
        .bot-bubble *::selection {{
            background: #A5D6A7;
            color: #1B5E20;
        }}
        .user-bubble {{
            background: linear-gradient(135deg, #E8F5E9 0%, #C8E6C9 100%);
            color: #1B5E20;
            border: 1px solid #A5D6A7;
            font-weight: 500;
        }}
        .bot-bubble {{
            background: #FFFFFF;
            color: {COLORS['text_primary']};
            border: 1px solid #E0E0E0;
        }}
        .msg-meta {{
            font-size: 0.75rem;
            color: {COLORS['muted']};
            margin: 0;
            user-select: none;
        }}
        .msg-meta.right {{ text-align: right; }}
        .msg-meta.left {{ text-align: left; }}

        [data-testid="stChatInput"] {{
            background: {COLORS['base_bg']} !important;
        }}
        [data-testid="stChatInput"] > div {{
            background: linear-gradient(#FFFFFF, #FFFFFF) padding-box,
                    radial-gradient(ellipse at center, #90EE90, #32CD32, #228B22, #2D5016) border-box;
            border: 2px solid transparent !important;
            border-radius: 14px;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08) !important;
        }}
        /* Remover qualquer borda ou box-shadow vermelho */
        [data-testid="stChatInput"] > div:focus-within {{
            border: 2px solid transparent !important;
            box-shadow: 0 2px 12px rgba(34, 139, 34, 0.15) !important;
            outline: none !important;
        }}
        [data-testid="stChatInput"] textarea {{
            background: #FFFFFF !important;
            color: {COLORS['text_primary']} !important;
            font-size: 1rem !important;
            line-height: 1.45 !important;
            border: none !important;
            caret-color: {COLORS['text_primary']} !important;
        }}
        [data-testid="stChatInput"] textarea:focus {{
            outline: none !important;
            box-shadow: none !important;
            border: none !important;
        }}        
        [data-testid="stChatInput"] textarea::placeholder {{
            color: {COLORS['text_secondary']} !important;
            opacity: 0.7 !important;
        }}
        
        /* Alinhamento do microfone com o chat input */
        div[data-testid="column"]:has(iframe[title*="audio_recorder"]) {{
            display: flex !important;
            align-items: center !important;
            padding-bottom: 0 !important;
            padding-top: 0 !important;
            min-height: 60px !important;
        }}
        
        /* Ajustar alinhamento da linha toda */
        div[data-testid="stHorizontalBlock"]:has(iframe[title*="audio_recorder"]) {{
            align-items: center !important;
            gap: 0.5rem !important;
        }}
        [data-testid="stChatInput"] button {{
            background: #228B22 !important;
            border: none !important;
        }}
        [data-testid="stChatInput"] button:hover {{
            background: #2D5016 !important;
        }}
        [data-testid="stChatInput"] button svg {{
            fill: white !important;
        }}

        /* Remover QUALQUER borda/outline/box-shadow vermelho em TODOS os estados */
        [data-testid="stChatInput"],
        [data-testid="stChatInput"] *,
        [data-testid="stChatInput"] > div,
        [data-testid="stChatInput"] textarea,
        [data-testid="stChatInput"] input {{
            border-color: transparent !important;
            outline-color: transparent !important;
        }}
        [data-testid="stChatInput"]:focus-within,
        [data-testid="stChatInput"] *:focus,
        [data-testid="stChatInput"] > div:focus-within,
        [data-testid="stChatInput"] textarea:focus,
        [data-testid="stChatInput"] input:focus {{
            border-color: transparent !important;
            outline-color: transparent !important;
            box-shadow: 0 2px 12px rgba(34, 139, 34, 0.15) !important;
        }}

        .quick-prompts-wrapper {{
            margin: 0 0 8px 0;
        }}
        .quick-prompts-label {{
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: {COLORS['muted']} !important;
            margin-bottom: 4px !important;
            font-weight: 500;
        }}
        .simple-button {{
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 25px;
            border: 2px solid {COLORS['wc_blue']};
            background-color: #FFFFFF;
            color: {COLORS['wc_blue']};
            padding: 10px 16px;
            font-weight: 600;
            font-size: 0.85rem;
            font-family: 'Inter', sans-serif;
            box-shadow: 0 2px 8px rgba(30, 60, 114, 0.15);
            min-height: 36px;
            text-align: center;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        :root {{
            --lang-width: 260px;
        }}
        .language-label {{
            font-size: 0.82rem;
            color: #000000;
            font-weight: 600;
            text-align: right;
            margin: 0 0 4px 0;
        }}
        /* Seletor de idioma alinhado à direita (dentro do fluxo) */
        div[data-testid="stSelectbox"] {{
            max-width: var(--lang-width);
            margin-left: auto;
        }}
        div[data-testid="stSelectbox"] > div {{
            border-radius: 14px !important;
            border: 1px solid {COLORS['border']} !important;
            background: #FFFFFF !important;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12);
        }}
        div[data-testid="stSelectbox"] [data-baseweb="select"] > div {{
            background: #FFFFFF !important;
            border-radius: 14px !important;
            padding-right: 38px !important;
            background-image: url("{ball_img}");
            background-repeat: no-repeat;
            background-size: 18px 18px;
            background-position: right 12px center;
        }}
        div[data-testid="stSelectbox"] svg {{
            display: none !important;
        }}
        div[data-testid="stSelectbox"] * {{
            color: #000000 !important;
        }}
        /* Dropdown do seletor de idioma - fundo branco com borda cinza */
        div[role="listbox"],
        ul[role="listbox"],
        div[data-baseweb="popover"] {{
            background: #FFFFFF !important;
            background-color: #FFFFFF !important;
            color: {COLORS['text_primary']} !important;
            border: 2px solid #9E9E9E !important;
            border-radius: 8px !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
        }}
        div[role="listbox"] *,
        ul[role="listbox"] *,
        div[data-baseweb="popover"] * {{
            background: transparent !important;
        }}
        div[role="option"],
        li[role="option"] {{
            background: #FFFFFF !important;
            background-color: #FFFFFF !important;
            color: {COLORS['text_primary']} !important;
            padding: 8px 12px !important;
        }}
        div[role="option"]:hover,
        li[role="option"]:hover {{
            background: #F5F5F5 !important;
            background-color: #F5F5F5 !important;
            color: #000000 !important;
        }}
        div[role="option"][aria-selected="true"],
        li[role="option"][aria-selected="true"] {{
            background: #E8F5E9 !important;
            background-color: #E8F5E9 !important;
            color: #1B5E20 !important;
            font-weight: 600 !important;
        }}
        /* Forçar todos os elementos do popover/dropdown com fundo branco */
        [data-baseweb="menu"],
        [data-baseweb="popover"] > div,
        [data-baseweb="popover"] ul {{
            background: #FFFFFF !important;
            background-color: #FFFFFF !important;
        }}
        @media (max-width: 720px) {{
            :root {{
                --lang-width: 52vw;
            }}
        }}
        
        /* Botões de "Ouvir resposta" abaixo das mensagens */
        button[kind="primary"],
        button[kind="secondary"] {{
            background: #FFFFFF !important;
            color: #228B22 !important;
            border: 1px solid #228B22 !important;
            border-radius: 8px !important;
            padding: 6px 12px !important;
            font-size: 0.85rem !important;
            margin: 8px 0 !important;
        }}
        button[kind="primary"]:hover,
        button[kind="secondary"]:hover {{
            background: #E8F5E9 !important;
            border-color: #2D5016 !important;
        }}
        
        /* Container das colunas - alinhamento no meio e fundo branco */
        div[data-testid="stHorizontalBlock"]:has(button[class*="audio"]) {{
            display: flex !important;
            align-items: center !important;
            gap: 12px !important;
            background: {COLORS['base_bg']} !important;
        }}
        
        /* Container do microfone com padding para evitar corte */
        div[data-testid="column"]:first-child {{
            background: {COLORS['base_bg']} !important;
            min-height: 62px !important;
            padding: 2px !important;
            box-sizing: border-box !important;
        }}
        
        /* Estilo para áudio player - limitado à largura da mensagem */
        audio {{
            max-width: 100% !important;
            width: 100% !important;
            margin: 8px 0 !important;
            border-radius: 8px !important;
            box-sizing: border-box !important;
        }}
        
        /* Container do áudio deve respeitar o limite */
        [data-testid="stAudio"] {{
            max-width: 100% !important;
            overflow: hidden !important;
        }}
        
        /* Indicação visual quando está gravando */
        [data-testid="stChatInput"].recording {{
            border: 3px solid #D32F2F !important;
            box-shadow: 0 0 20px rgba(211, 47, 47, 0.4) !important;
            animation: recording-pulse 1.5s ease-in-out infinite !important;
        }}
        
        @keyframes recording-pulse {{
            0%, 100% {{
                box-shadow: 0 0 20px rgba(211, 47, 47, 0.4);
            }}
            50% {{
                box-shadow: 0 0 30px rgba(211, 47, 47, 0.6);
            }}
        }}
        
        /* Esconder visualização de áudio gravado do audio_recorder */
        iframe[title*="audio_recorder"] audio,
        iframe[title*="audio_recorder"] [class*="audio"],
        iframe[title*="audio_recorder"] [class*="player"],
        div[data-testid="column"]:has(iframe[title*="audio_recorder"]) audio,
        div[data-testid="column"]:has(iframe[title*="audio_recorder"]) [data-testid="stAudio"] {{
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            width: 0 !important;
            opacity: 0 !important;
        }}
        
        /* Animação de transcrição para o microfone */
        @keyframes transcribe-pulse {{
            0%, 100% {{ 
                transform: scale(1) translateY(0); 
            }}
            50% {{ 
                transform: scale(1.1) translateY(-5px); 
            }}
        }}
        
        .transcribing-mic {{
            animation: transcribe-pulse 0.8s ease-in-out infinite !important;
        }}
        
        </style>
        """,
        unsafe_allow_html=True,
    )


# ========================================
# 🔧 FUNÇÕES AUXILIARES
# ========================================

def initialize_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    if "pending_query" not in st.session_state:
        st.session_state.pending_query = None
    if "pending_query_raw" not in st.session_state:
        st.session_state.pending_query_raw = None
    if "supervisor" not in st.session_state:
        st.session_state.supervisor = None
    if "clarify_pending" not in st.session_state:
        st.session_state.clarify_pending = False
    if "clarify_base_question" not in st.session_state:
        st.session_state.clarify_base_question = None
    if "context_hint" not in st.session_state:
        st.session_state.context_hint = None
    if "context_ttl" not in st.session_state:
        st.session_state.context_ttl = 0
    if "preferred_language" not in st.session_state:
        st.session_state.preferred_language = "🇧🇷 Português"
    if "custom_language" not in st.session_state:
        st.session_state.custom_language = ""
    if "is_transcribing" not in st.session_state:
        st.session_state.is_transcribing = False

    # ✨ MENSAGEM INICIAL TRADUZIDA DINAMICAMENTE
    if not st.session_state.messages:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": get_text("welcome_message"),
                "timestamp": datetime.now(),
            }
        ]


def _escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )


def _contains_copa_terms(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(term in t for term in ["copa", "mundial", "fifa", "world cup", "2026"])


def _detect_context_hint(text: str) -> str | None:
    if not text:
        return None
    t = text.lower()
    if "2026" in t or "copa 2026" in t or "world cup 2026" in t:
        return "Copa 2026"
    if any(term in t for term in ["copa", "mundial", "fifa", "world cup"]):
        return "Copa do Mundo"
    return None


def _parse_response_text(text: str) -> dict:
    """Tenta extrair um dicionário com chaves relevantes a partir de `text`.
    Retorna dict com pelo menos a chave 'answer'."""
    import json
    import ast
    import re

    result = {}
    if not text:
        return {"answer": ""}

    # Primeiro, tenta JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Depois, tenta literal_eval (string de dict Python)
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Fallback: usar regex para extrair campos simples
    # answer
    m = re.search(r"answer\s*[:=]\s*(?:\"\"\"|\\'\\'\\'|\"|'|)(.*?)(?:\"\"\"|\\'\\'\\'|\"|'|)(,|$)", text, re.S | re.I)
    if m:
        ans = m.group(1).strip()
        result["answer"] = ans
    else:
        # Se não encontramos, retorna o texto inteiro como answer
        result["answer"] = text

    # related_topics
    m2 = re.search(r"related_topics\s*[:=]\s*(\[.*?\])", text, re.S | re.I)
    if m2:
        try:
            result["related_topics"] = ast.literal_eval(m2.group(1))
        except Exception:
            # limpa colchetes e split
            s = m2.group(1).strip("[] ")
            result["related_topics"] = [t.strip().strip("'\"") for t in s.split(",") if t.strip()]

    # outros campos simples
    for key in ("source", "model", "context_source", "link"):
        m3 = re.search(fr"{key}\s*[:=]\s*(?:\"|'|)(.*?)(?:\"|'|)(,|$)", text, re.S | re.I)
        if m3:
            result[key] = m3.group(1).strip()

    return result


def _has_language_request(text: str) -> bool:
    if not text:
        return False
    patterns = [
        r"(?:responda|responder|resposta)\s+em\s+",
        r"(?:answer|respond)\s+in\s+",
        r"(?:em|no)\s+idioma\s+",
    ]
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def _get_preferred_language_value() -> str | None:
    lang_label = st.session_state.get("preferred_language", "🇧🇷 Português")
    lang = LANGUAGE_MAP.get(lang_label, lang_label)
    if lang == "Outro...":
        lang = st.session_state.get("custom_language", "").strip()
    if not lang or lang in {"🇧🇷 Português", "português brasileiro", "Português"}:
        return None
    return lang


def _format_answer_and_facts(parsed: dict, message: dict = None) -> str:
    """Gera HTML formatado (estilo markdown) para 'answer' e 'main_facts'."""
    answer = parsed.get("answer") if isinstance(parsed, dict) else parsed
    if answer is None:
        answer = ""
    # escapar HTML e preservar quebras de linha em parágrafos
    escaped = _escape_html(str(answer))
    # transforma duplas quebras em parágrafos
    paragraphs = escaped.split("\n\n")
    answer_html = "".join(f"<p style=\"margin:6px 0 8px 0;line-height:1.6;color:#1A1A1A\">{p}</p>" for p in paragraphs)

    # main_facts como lista - verifica tanto em parsed quanto em message
    main_facts = None
    if isinstance(parsed, dict) and parsed.get("main_facts"):
        main_facts = parsed.get("main_facts")
    elif message and isinstance(message, dict) and message.get("main_facts"):
        main_facts = message.get("main_facts")
    
    facts_html = ""
    if main_facts and isinstance(main_facts, (list, tuple)) and len(main_facts) > 0:
        facts_html += '<div style="margin-top:12px;padding:10px 12px;background:#F9FAFB;border-radius:8px;border:1px solid #E5E7EB">'
        # ✨ TRADUZIDO DINAMICAMENTE
        facts_html += f'<div style="font-weight:600;color:#374151;margin-bottom:6px;font-size:0.9rem">{get_text("main_facts")}</div>'
        facts_html += '<ul style="margin:0;padding-left:18px;color:#4B5563">'
        for f in main_facts:
            facts_html += f"<li style=\"margin-bottom:4px;line-height:1.5;\">{_escape_html(str(f))}</li>"
        facts_html += '</ul></div>'

    return answer_html + facts_html


def render_message_html(message: dict) -> str:
    role = message.get("role")
    raw_content = message.get("content", "")
    timestamp = message.get("timestamp")
    try:
        ts = timestamp.strftime("%H:%M") if timestamp else ""
    except Exception:
        ts = ""

    if role == "user":
        content = _escape_html(raw_content)
        meta = f'<div class="msg-meta right">{ts}</div>' if ts else ""
        return (
            '<div class="user-row">'
            f'  <div class="message-container">'
            f'    <div class="user-bubble">{content}</div>'
            f'    {meta}'
            "  </div>"
            "</div>"
        )

    # role == assistant (bot)
    parsed = None
    try:
        if isinstance(raw_content, dict):
            parsed = raw_content
        elif isinstance(raw_content, str) and ("answer" in raw_content and ("{" in raw_content or "\n" in raw_content)):
            parsed = _parse_response_text(raw_content)
    except Exception:
        parsed = None

    if parsed and isinstance(parsed, dict) and parsed.get("answer"):
        content_text = parsed.get("answer")
    else:
        content_text = raw_content

    # ✨ TRADUÇÃO AUTOMÁTICA DE MENSAGENS DO SISTEMA
    # Quando vem do sistema (qualquer tipo), traduz automaticamente
    system_sources = ["sistema", "system", "validator", "supervisor", "clarification", "validation"]
    is_system_message = (
        message.get("source") in system_sources or 
        message.get("context_source") in system_sources or
        (parsed and parsed.get("source") in system_sources) or
        (parsed and parsed.get("worker_type") in ["validation", "clarification", "supervisor"])
    )
    
    if is_system_message:
        original_content = content_text
        current_lang = st.session_state.get("preferred_language", "🇧🇷 Português")
        print(f"[DEBUG] Sistema detectado! Idioma atual: '{current_lang}'")
        print(f"[DEBUG] Vai traduzir? {current_lang != '🇧🇷 Português' and current_lang != 'Outro...'}")
        
        content_text = auto_translate_system_message(content_text)
        
        # Debug para verificar tradução
        if original_content != content_text:
            print(f"[TRADUÇÃO REALIZADA] {current_lang}: '{original_content[:50]}...' → '{content_text[:50]}...'")
        else:
            print(f"[SEM TRADUÇÃO] Idioma: {current_lang} | Conteúdo: '{original_content[:100]}...'")
            
            # Forçar tradução se idioma não for português
            if current_lang != "🇧🇷 Português" and current_lang != "Outro...":
                print(f"[FORÇA TRADUÇÃO] Tentando traduzir para {current_lang}")
                content_text = _translate_with_fallback(content_text, current_lang)
                if original_content != content_text:
                    print(f"[TRADUÇÃO FORÇADA] Sucesso: '{content_text[:50]}...'")
                else:
                    print(f"[TRADUÇÃO FORÇADA] Falhou - usando original")

    # Formatar answer e main_facts como HTML (estilo markdown)
    content_html = _format_answer_and_facts(parsed if parsed else {"answer": content_text}, message)

    # campos de fonte: preferir valores já presentes na mensagem, senão usar parsed
    source = message.get("source") or (parsed.get("source") if parsed else None)
    model = message.get("model") or (parsed.get("model") if parsed else None)
    context_source = message.get("context_source") or (parsed.get("context_source") if parsed else None)
    link = message.get("link") or (parsed.get("link") if parsed else None)
    related = message.get("related_topics") or (parsed.get("related_topics") if parsed else None)
    pages = message.get("pages") or (parsed.get("pages") if parsed else None)
    links = message.get("links") or (parsed.get("links") if parsed else None)

    # 🐛 DEBUG: Log de todas as variáveis importantes
    logging.info(f"🐛 DEBUG Metadados: context_source={context_source}, source={source}, pages={pages}, links={links}")

    # ✨ RENDERIZAÇÃO DA FONTE TRADUZIDA DINAMICAMENTE
    fonte_html = ''
    fonte_html += '<div style="margin-top: 10px; padding: 10px 12px; background: #F5F5F5; border-radius: 8px; font-size: 0.88rem; color: #424242; border: 1px solid #E0E0E0;">'
    fonte_html += '<div style="display:flex;gap:6px;align-items:center;">'
    fonte_html += f'<span style="color:#757575;font-weight:500;">{get_text("source")}</span>'
    
    # Usar context_source ao invés de source/model
    if context_source == "rag":
        source_label = get_text("source_rag")
    elif context_source == "web":
        source_label = get_text("source_web")
    elif context_source:
        source_label = f"{context_source}"
    elif source == "rag":
        source_label = get_text("source_rag")
    elif source == "web":
        source_label = get_text("source_web")
    else:
        source_label = get_text("source_system")

    fonte_html += f"<span style=\"color:#616161;\">{_escape_html(source_label)}</span>"
    fonte_html += '</div>'

    if related:
        try:
            tags = ", ".join([_escape_html(str(t)) for t in related])
            fonte_html += f"<div style=\"margin-top:7px;color:#616161;font-size:0.82rem;line-height:1.4;\"><span style=\"font-weight:500;color:#757575;\">{get_text('related_topics')}</span> {tags}</div>"
        except Exception:
            pass

    if pages and (context_source == "rag" or source == "rag"):
        try:
            page_list = ", ".join([str(p) for p in pages if p is not None])
            if page_list:
                logging.info(f"🎨 Renderizando páginas na UI: {page_list}")
                fonte_html += f"<div style=\"margin-top:6px;color:#616161;font-size:0.82rem;line-height:1.4;\"><span style=\"font-weight:500;color:#757575;\">{get_text('pages')}</span> {page_list}</div>"
            else:
                logging.warning(f"⚠️ Lista de páginas vazia após filtrar: pages={pages}")
        except Exception as e:
            logging.error(f"❌ Erro ao renderizar páginas: {e}, pages={pages}")
            pass

    if links and (context_source == "web" or source == "serper" or source == "web"):
        try:
            link_items = []
            for lnk in links:
                safe = _escape_html(str(lnk))
                link_items.append(f"<a href=\"{safe}\" target=\"_blank\" style=\"color:#1E3C72;text-decoration:underline;\">{safe}</a>")
            if link_items:
                fonte_html += f"<div style=\"margin-top:6px;color:#616161;font-size:0.82rem;line-height:1.4;\"><span style=\"font-weight:500;color:#757575;\">{get_text('links')}</span> "
                fonte_html += " | ".join(link_items)
                fonte_html += "</div>"
        except Exception:
            pass

    fonte_html += '</div>'

    meta = f'<div class="msg-meta left">{ts}</div>' if ts else ""
    
    # Retornar HTML da mensagem sem o botão de áudio (será adicionado separadamente no Streamlit)
    return (
        '<div class="bot-row">'
        f'  <div class="message-container">'
        f'    <div class="bot-bubble">{content_html}</div>'
        f'    {fonte_html}'
        f'    {meta}'
        "  </div>"
        "</div>"
    )


def handle_user_query(query: str) -> None:
    raw_query = query.strip()
    processed_query = raw_query

    # Atualiza contexto com base no input atual
    hint_found = _detect_context_hint(raw_query)
    if hint_found:
        st.session_state.context_hint = hint_found
        st.session_state.context_ttl = DEFAULT_CONTEXT_TTL

    # Se havia pergunta ambígua anterior, completa com o novo input
    if st.session_state.clarify_pending and st.session_state.clarify_base_question:
        processed_query = (
            f"{st.session_state.clarify_base_question}\n"
            f"Complemento do usuário: {raw_query}"
        )
        st.session_state.clarify_pending = False
        st.session_state.clarify_base_question = None

    # Aplica contexto recente se a nova pergunta não mencionar Copa
    if st.session_state.context_hint and st.session_state.context_ttl > 0:
        if not _contains_copa_terms(processed_query):
            processed_query = f"{processed_query} (sobre {st.session_state.context_hint})"

    # Reduz TTL do contexto quando não há nova âncora
    if not hint_found and st.session_state.context_ttl > 0:
        st.session_state.context_ttl -= 1
        if st.session_state.context_ttl <= 0:
            st.session_state.context_hint = None

    # Captura idioma preferido (sem sobrescrever se usuário pediu explicitamente)
    lang_pref = None
    if not _has_language_request(raw_query):
        lang_pref = _get_preferred_language_value()

    st.session_state.messages.append({"role": "user", "content": raw_query, "timestamp": datetime.now()})
    st.session_state.is_processing = True
    if lang_pref:
        st.session_state.pending_query = {
            "query": processed_query,
            "preferred_language": lang_pref,
        }
    else:
        st.session_state.pending_query = processed_query
    st.session_state.pending_query_raw = raw_query
    st.rerun()


def _normalize_backend_response(response: object) -> tuple[dict, dict | None]:
    """Normaliza resposta do backend para um payload único e mantém nested para fallback."""
    if isinstance(response, dict):
        parsed = response
    elif isinstance(response, str):
        parsed = _parse_response_text(response)
    else:
        parsed = {}

    nested = None
    if isinstance(parsed, dict) and parsed.get("result"):
        res_val = parsed.get("result")
        if isinstance(res_val, str):
            nested = _parse_response_text(res_val)
        elif isinstance(res_val, dict):
            nested = res_val

    final = {}
    if nested and isinstance(nested, dict):
        final.update(nested)
    if isinstance(parsed, dict):
        final.update(parsed)
    return final, nested


def _build_bot_message(final: dict, response: object, nested: dict | None) -> dict:
    content_val = final.get("answer") or final.get("response") or final.get("result") or str(response)
    main_facts_val = final.get("main_facts")
    if not main_facts_val and nested:
        main_facts_val = nested.get("main_facts")

    return {
        "role": "assistant",
        "content": content_val,
        "timestamp": datetime.now(),
        "source": final.get("source"),
        "model": final.get("model"),
        "context_source": final.get("context_source"),
        "link": final.get("link"),
        "related_topics": final.get("related_topics"),
        "main_facts": main_facts_val,
        "pages": final.get("pages"),
        "links": final.get("links"),
    }


def _reset_processing_state() -> None:
    st.session_state.is_processing = False
    st.session_state.pending_query = None
    st.session_state.pending_query_raw = None


def get_bot_response(query: str) -> dict:
    if st.session_state.supervisor is None:
        st.session_state.supervisor = Supervisor(num_workers=2)
    results = asyncio.run(st.session_state.supervisor.dispatch([query]))
    if results and len(results) > 0 and results[0] is not None:
        return results[0]  # Retorna o dict completo
    # ✨ MARCA MENSAGEM COMO SISTEMA PARA TRADUÇÃO AUTOMÁTICA
    return {
        "result": "Desculpe, não consegui gerar uma resposta agora.", 
        "source": "sistema",
        "context_source": "system"
    }


def refresh_welcome_message():
    """Atualiza a mensagem de boas-vindas quando o idioma muda"""
    if st.session_state.messages and st.session_state.messages[0].get("role") == "assistant":
        # Atualiza apenas se a primeira mensagem for a de boas-vindas
        current_content = st.session_state.messages[0].get("content", "")
        # Verifica se é uma mensagem de boas-vindas (contém emoji 👋)
        if "👋" in current_content:
            st.session_state.messages[0]["content"] = get_text("welcome_message")


# ========================================
# 🚀 APLICAÇÃO PRINCIPAL
# ========================================

def main() -> None:
    # ✨ CONFIGURAÇÃO DA PÁGINA TRADUZIDA DINAMICAMENTE
    st.set_page_config(
        page_title=get_text("page_title"),
        page_icon=get_text("page_icon"),
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    load_custom_css()
    initialize_session_state()

    # ✨ BLOCO DE DEBUG TRADUZIDO
    with st.expander(get_text("debug_title"), expanded=False):
        if "_last_raw_response" in st.session_state and st.session_state._last_raw_response:
            st.json(st.session_state._last_raw_response if isinstance(st.session_state._last_raw_response, dict) else str(st.session_state._last_raw_response))

    # Carregar imagem da bola
    try:
        with open("front/bola-de-futebol.png", "rb") as f:
            img_data = base64.b64encode(f.read()).decode()
        ball_img = f"data:image/png;base64,{img_data}"
    except:
        ball_img = ""

    # ✨ HERO TRADUZIDO DINAMICAMENTE
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-frame">
                <div class="hero-inner">
                    <p class="hero-title">
                        <img src="{ball_img}" alt="{get_text('ball_alt')}" style="width: 48px; height: 48px; object-fit: contain;">
                        {get_text('app_title')}
                    </p>
                    <p class="hero-subtitle">{get_text('app_subtitle')}</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Renderizar mensagens com botões de áudio integrados
    for idx, m in enumerate(st.session_state.messages):
        # Renderizar HTML da mensagem
        st.markdown(render_message_html(m), unsafe_allow_html=True)
        
        # Se for mensagem do bot, adicionar botão de ouvir logo abaixo
        if m.get("role") == "assistant":
            audio_key = f"audio_{idx}"
            playing_key = f"playing_{idx}"
            
            # Inicializar estados
            if playing_key not in st.session_state:
                st.session_state[playing_key] = False
            
            # Verificar se o áudio atual está tocando
            if st.session_state[playing_key]:
                # Mostrar player de áudio customizado com autoplay
                audio_base64 = base64.b64encode(st.session_state[audio_key]).decode()
                
                # Criar colunas para ícone e botão de parar próximos
                audio_col1, audio_col2 = st.columns([1, 20], gap="small")
                
                with audio_col1:
                    # Ícone animado
                    st.markdown(f'''
                    <div style="display: flex; align-items: center;">
                        <span style="font-size: 20px; animation: pulse 1.5s ease-in-out infinite;">🔊</span>
                    </div>
                    <style>
                        @keyframes pulse {{
                            0%, 100% {{ opacity: 1; transform: scale(1); }}
                            50% {{ opacity: 0.6; transform: scale(1.1); }}
                        }}
                    </style>
                    ''', unsafe_allow_html=True)
                
                with audio_col2:
                    # Botão para parar o áudio
                    if st.button("⏹ Parar", key=f"stop_{idx}", help="Parar áudio"):
                        st.session_state[playing_key] = False
                        st.rerun()
                
                # Player de áudio
                st.markdown(f'''
                <audio id="audio_{idx}" autoplay style="display: none;">
                    <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
                </audio>
                <script>
                    (function() {{
                        const audio = document.getElementById('audio_{idx}');
                        if (audio) {{
                            audio.addEventListener('ended', function() {{
                                console.log('Audio {idx} ended');
                            }});
                        }}
                    }})();
                </script>
                ''', unsafe_allow_html=True)
            else:
                # Mostrar botão para gerar/ouvir áudio
                if st.button(f"🔊 {get_text('listen_button')}", key=f"tts_btn_{idx}", use_container_width=False):
                    if audio_key not in st.session_state:
                        # Gerar áudio pela primeira vez
                        with st.spinner("Gerando áudio..."):
                            try:
                                lang_code = get_gtts_lang_code(st.session_state.get("preferred_language", "🇧🇷 Português"))
                                content = m.get("content", "")
                                
                                # Limpar o conteúdo
                                clean_text = re.sub(r'<[^>]+>', '', content)
                                clean_text = re.sub(r'\*\*', '', clean_text)
                                clean_text = clean_text.strip()
                                
                                if clean_text:
                                    logging.info(f"Gerando TTS para mensagem {idx}")
                                    audio_bytes = text_to_speech(clean_text, lang_code)
                                    
                                    if audio_bytes:
                                        st.session_state[audio_key] = audio_bytes
                                        st.session_state[playing_key] = True
                                        st.rerun()
                                    else:
                                        st.error("❌ Erro ao gerar áudio")
                            except Exception as e:
                                logging.error(f"Erro ao gerar TTS: {e}")
                                st.error(f"❌ Erro: {str(e)}")
                    else:
                        # Áudio já existe, apenas tocar novamente
                        st.session_state[playing_key] = True
                        st.rerun()

    # ✨ MENSAGEM DE "PENSANDO" TRADUZIDA
    if st.session_state.is_processing:
        st.markdown(
            '<div class="bot-row">'
            '  <div class="message-container">'
            f'    <div class="bot-bubble">{get_text("thinking_message")}</div>'
            '  </div>'
            '</div>',
            unsafe_allow_html=True
        )

    
    # Auto-scroll (JavaScript é executado automaticamente no Streamlit)

    # ✨ SELETOR DE IDIOMA TRADUZIDO DINAMICAMENTE
    lang_cols = st.columns([7, 3])
    with lang_cols[1]:
        st.markdown(f'<div class="language-label">{get_text("language_label")}</div>', unsafe_allow_html=True)
        
        # Seletor de idioma com callback para atualizar mensagem de boas-vindas
        st.selectbox(
            get_text("language_label"),
            LANGUAGE_OPTIONS,
            key="preferred_language",
            label_visibility="collapsed",
            help=get_text("language_help"),
            on_change=refresh_welcome_message  # Callback executa quando idioma muda
        )
        
        if st.session_state.preferred_language == "Outro...":
            st.text_input(
                get_text("other_language"),
                key="custom_language",
                label_visibility="collapsed",
                placeholder=get_text("other_language_placeholder"),
            )

    # ✨ INPUT COM MICROFONE ESTILIZADO E FUNCIONAL
    if "last_audio_bytes" not in st.session_state:
        st.session_state.last_audio_bytes = None
    
    # Processar transcrição se estiver no estado de transcrição (ANTES de renderizar)
    if st.session_state.get("is_transcribing", False) and st.session_state.last_audio_bytes:
        try:
            lang_code = get_speech_lang_code(st.session_state.get("preferred_language", "🇧🇷 Português"))
            logging.info(f"Idioma de transcrição: {lang_code}")
            
            transcribed_text = transcribe_audio(st.session_state.last_audio_bytes, lang_code)
            logging.info(f"Texto transcrito: '{transcribed_text}'")
            
            st.session_state.is_transcribing = False
            st.session_state.last_audio_bytes = None
            
            if transcribed_text and transcribed_text.strip():
                handle_user_query(transcribed_text)
                st.rerun()
            else:
                st.toast("Não foi possível transcrever. Tente falar mais alto e claro.", icon="❌")
                logging.warning("Transcrição retornou vazia")
                st.rerun()
                
        except Exception as e:
            st.session_state.is_transcribing = False
            st.session_state.last_audio_bytes = None
            logging.error(f"Erro ao transcrever: {e}", exc_info=True)
            st.toast(f"Erro na transcrição: {str(e)}", icon="❌")
            st.rerun()
    
    # Container para microfone alinhado com o input de chat
    mic_col1, mic_col2 = st.columns([1, 15], gap="small")
    
    with mic_col1:
        try:
            from audio_recorder_streamlit import audio_recorder
            
            # CSS para estilizar o audio_recorder com a aparência desejada
            st.markdown("""
            <style>
            /* Container do audio_recorder */
            div[data-testid="stVerticalBlock"] > div:has(iframe[title*="audio_recorder"]) {
                height: 60px !important;
                min-height: 60px !important;
                display: flex !important;
                align-items: center !important;
                margin-bottom: 0 !important;
                background: transparent !important;
                overflow: visible !important;
            }
            
            /* Iframe do audio_recorder */
            iframe[title*="audio_recorder"] {
                height: 60px !important;
                width: 100% !important;
                border: none !important;
                background: transparent !important;
                outline: none !important;
            }
            
            /* Remover qualquer borda azul de foco */
            iframe[title*="audio_recorder"]:focus,
            iframe[title*="audio_recorder"]:focus-visible {
                outline: none !important;
                border: none !important;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # Usar audio_recorder com estilização
            audio_bytes = audio_recorder(
                text="",
                recording_color="#FF8C00",
                neutral_color="#228B22",
                icon_name="microphone",
                icon_size="2x",
                pause_threshold=2.0,
                sample_rate=16000,
                key="mic_recorder_final"
            )
            
            # CSS adicional para deixar o botão com aparência customizada
            components.html(f"""
            <style>
            /* Injetar estilos no documento pai */
            </style>
            <script>
            (function() {{
                // Verificar se está transcrevendo via data attribute
                const isTranscribing = {str(st.session_state.get('is_transcribing', False)).lower()};
                
                function styleRecorder() {{
                    try {{
                        const parentDoc = window.parent.document;
                        const iframe = parentDoc.querySelector('iframe[title*="audio_recorder"]');
                        
                        if (!iframe) return;
                        
                        // Ajustar altura do iframe
                        iframe.style.height = '60px !important';
                        
                        // Adicionar animação se está transcrevendo
                        if (isTranscribing) {{
                            iframe.classList.add('transcribing-mic');
                        }} else {{
                            iframe.classList.remove('transcribing-mic');
                        }}
                        
                        // Aplicar estilos ao container do iframe
                        const container = iframe.parentElement;
                        if (container) {{
                            container.style.cssText = `
                                width: 100% !important;
                                height: 60px !important;
                                min-height: 60px !important;
                                display: flex !important;
                                align-items: center !important;
                                justify-content: center !important;
                                overflow: visible !important;
                            `;
                        }}
                        
                        // Tentar estilizar o conteúdo do iframe
                        try {{
                            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                            
                            // Estilizar html e body do iframe para fundo branco
                            if (iframeDoc.documentElement) {{
                                iframeDoc.documentElement.style.cssText = `
                                    background: #FFFFFF !important;
                                    margin: 0 !important;
                                    padding: 0 !important;
                                `;
                            }}
                            
                            if (iframeDoc.body) {{
                                iframeDoc.body.style.cssText = `
                                    margin: 0 !important;
                                    padding: 0 !important;
                                    display: flex !important;
                                    align-items: center !important;
                                    justify-content: center !important;
                                    height: 60px !important;
                                    min-height: 60px !important;
                                    overflow: visible !important;
                                    background: #FFFFFF !important;
                                `;
                            }}
                            
                            // Adicionar CSS global para remover outline azul e forçar cores
                            if (!iframeDoc.getElementById('remove-outline-style')) {{
                                const style = iframeDoc.createElement('style');
                                style.id = 'remove-outline-style';
                                style.textContent = `
                                    * {{
                                        outline: none !important;
                                    }}
                                    *:focus {{
                                        outline: none !important;
                                        box-shadow: none !important;
                                    }}
                                    button:focus {{
                                        outline: none !important;
                                        box-shadow: none !important;
                                    }}
                                    svg[fill*="#228B22"] path,
                                    svg[fill*="228B22"] path {{
                                        fill: #228B22 !important;
                                    }}
                                    svg[fill*="#FF8C00"] path,
                                    svg[fill*="FF8C00"] path,
                                    svg[fill*="#D32F2F"] path,
                                    svg[fill*="D32F2F"] path {{
                                        fill: #FF8C00 !important;
                                    }}
                                `;
                                iframeDoc.head.appendChild(style);
                            }}
                            
                            const button = iframeDoc.querySelector('button') || iframeDoc.querySelector('div');
                            
                            if (button) {{
                                button.style.cssText = `
                                    width: 100% !important;
                                    min-width: 100% !important;
                                    height: 56px !important;
                                    min-height: 56px !important;
                                    max-height: 56px !important;
                                    background: #FFFFFF !important;
                                    border: none !important;
                                    border-radius: 12px !important;
                                    cursor: pointer !important;
                                    box-shadow: none !important;
                                    transition: all 0.2s ease !important;
                                    display: flex !important;
                                    align-items: center !important;
                                    justify-content: center !important;
                                    padding: 0 !important;
                                    margin: 0 !important;
                                    outline: none !important;
                                `;
                                
                                // Remover outline ao focar
                                button.addEventListener('focus', function() {{
                                    this.style.outline = 'none';
                                    this.style.boxShadow = 'none';
                                }});
                                
                                // Estilizar o SVG dentro do botão
                                const svg = button.querySelector('svg');
                                if (svg) {{
                                    const fill = svg.getAttribute('fill');
                                    
                                    // Se está transcrevendo, forçar azul
                                    if (isTranscribing) {{
                                        svg.setAttribute('fill', '#1E3C72');
                                        svg.style.fill = '#1E3C72 !important';
                                        svg.style.color = '#1E3C72 !important';
                                        
                                        const paths = svg.querySelectorAll('path');
                                        paths.forEach(path => {{
                                            path.setAttribute('fill', '#1E3C72');
                                            path.style.fill = '#1E3C72';
                                        }});
                                    }}
                                    // Verificar se está gravando (cor laranja)
                                    else if (fill && (fill.includes('D32F2F') || fill.includes('FF8C00') || fill.includes('ff8c00') || fill.toLowerCase().includes('darkorange'))) {{
                                        // Gravando - forçar laranja
                                        svg.setAttribute('fill', '#FF8C00');
                                        svg.style.fill = '#FF8C00 !important';
                                        svg.style.color = '#FF8C00 !important';
                                        
                                        // Aplicar cor em todos os paths dentro do SVG
                                        const paths = svg.querySelectorAll('path');
                                        paths.forEach(path => {{
                                            path.setAttribute('fill', '#FF8C00');
                                            path.style.fill = '#FF8C00';
                                        }});
                                    }} else {{
                                        // Parado - forçar verde
                                        svg.setAttribute('fill', '#228B22');
                                        svg.style.fill = '#228B22 !important';
                                        svg.style.color = '#228B22 !important';
                                        
                                        // Aplicar cor em todos os paths dentro do SVG
                                        const paths = svg.querySelectorAll('path');
                                        paths.forEach(path => {{
                                            path.setAttribute('fill', '#228B22');
                                            path.style.fill = '#228B22';
                                        }});
                                    }}
                                    
                                    svg.style.cssText += `
                                        width: 36px !important;
                                        height: 36px !important;
                                        background: transparent !important;
                                    `;
                                }}
                            }}
                        }} catch (e) {{
                            // Cross-origin, não consegue acessar
                        }}
                    }} catch (e) {{
                        console.error('Erro ao estilizar:', e);
                    }}
                }}
                
                // Executar periodicamente
                setInterval(styleRecorder, 100);
                setTimeout(styleRecorder, 100);
                setTimeout(styleRecorder, 500);
            }})();
            </script>
            """, height=0)
            
            # Processar áudio gravado
            if audio_bytes and audio_bytes != st.session_state.last_audio_bytes:
                st.session_state.last_audio_bytes = audio_bytes
                st.session_state.is_transcribing = True
                logging.info(f"Áudio recebido - tamanho: {len(audio_bytes)} bytes")
                st.rerun()
                
        except ImportError:
            st.markdown("""
            <div style="width: 100%; height: 62px; display: flex; align-items: center; justify-content: center;">
                <div style="
                    width: 100%;
                    height: 58px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: #E0E0E0;
                    border-radius: 12px;
                    color: #757575;
                    font-size: 12px;
                ">
                    🎤 Módulo não instalado
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    with mic_col2:
        # ✨ INPUT DE CHAT TRADUZIDO DINAMICAMENTE
        if st.session_state.is_transcribing:
            query = st.chat_input("Transcrevendo...", disabled=True)
        else:
            query = st.chat_input(get_text("chat_input_placeholder"))


    if query:
        handle_user_query(query)

    if st.session_state.is_processing and st.session_state.pending_query:
        response = get_bot_response(st.session_state.pending_query)

        # Guardar resposta bruta completa para debug
        st.session_state._last_raw_response = response

        final, nested = _normalize_backend_response(response)
        bot_message = _build_bot_message(final, response, nested)

        st.session_state.messages.append(bot_message)
        # Se a resposta pediu clarificação, guarda a última pergunta do usuário
        if final.get("worker_type") == "clarification" or final.get("source") == "clarification":
            st.session_state.clarify_pending = True
            st.session_state.clarify_base_question = st.session_state.pending_query_raw
        _reset_processing_state()
        st.rerun()


if __name__ == "__main__":
    main()
