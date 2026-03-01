"""
Utilidades para reconhecimento de voz (Speech-to-Text) e síntese de voz (Text-to-Speech)
"""
import io
import os
import tempfile
import logging
from typing import Optional
import streamlit as st
import ssl

# Configurar SSL para evitar problemas de certificado
try:
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
except ImportError:
    pass

logger = logging.getLogger(__name__)


def get_speech_lang_code(display_lang: str) -> str:
    """Mapeia idioma de exibição para código de idioma"""
    lang_map = {
        "🇧🇷 Português": "pt-BR",
        "🇺🇸 English": "en-US",
        "🇪🇸 Español": "es-ES",
        "🇫🇷 Français": "fr-FR",
        "🇩🇪 Deutsch": "de-DE",
        "🇮🇹 Italiano": "it-IT",
        "🇯🇵 日本語": "ja-JP",
        "🇨🇳 中文": "zh-CN",
        "🇸🇦 العربية": "ar-SA",
    }
    return lang_map.get(display_lang, "pt-BR")


def get_gtts_lang_code(display_lang: str) -> str:
    """Mapeia idioma de exibição para código gTTS"""
    lang_map = {
        "🇧🇷 Português": "pt",
        "🇺🇸 English": "en",
        "🇪🇸 Español": "es",
        "🇫🇷 Français": "fr",
        "🇩🇪 Deutsch": "de",
        "🇮🇹 Italiano": "it",
        "🇯🇵 日本語": "ja",
        "🇨🇳 中文": "zh-CN",
        "🇸🇦 العربية": "ar",
    }
    return lang_map.get(display_lang, "pt")


def transcribe_audio(audio_bytes: bytes, language: str = "pt-BR") -> Optional[str]:
    """
    Transcreve áudio para texto usando Google Speech Recognition
    
    Args:
        audio_bytes: Bytes do arquivo de áudio
        language: Código do idioma (ex: pt-BR, en-US)
        
    Returns:
        Texto transcrito ou None se falhar
    """
    try:
        import speech_recognition as sr
        
        logger.info(f"Iniciando transcrição de áudio ({len(audio_bytes)} bytes) no idioma '{language}'")
        
        recognizer = sr.Recognizer()
        
        # Salvar audio bytes em arquivo temporário
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_path = tmp_file.name
        
        try:
            # Carregar áudio
            with sr.AudioFile(tmp_path) as source:
                # Ajustar para ruído ambiente
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = recognizer.record(source)
            
            logger.info(f"Áudio carregado, enviando para Google Speech Recognition...")
            
            # Transcrever usando Google Speech Recognition (gratuito)
            text = recognizer.recognize_google(audio_data, language=language)
            logger.info(f"✅ Áudio transcrito com sucesso: '{text}'")
            return text
            
        finally:
            # Limpar arquivo temporário
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except ImportError as e:
        logger.error(f"❌ Biblioteca speech_recognition não instalada: {e}")
        return None
    except sr.UnknownValueError:
        logger.warning("❌ Google Speech Recognition não conseguiu entender o áudio")
        return None
    except sr.RequestError as e:
        logger.error(f"❌ Erro ao conectar ao serviço Google Speech Recognition: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Erro ao transcrever áudio: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def text_to_speech(text: str, language: str = "pt") -> Optional[bytes]:
    """
    Converte texto para áudio usando Google Text-to-Speech
    
    Args:
        text: Texto a ser convertido
        language: Código do idioma gTTS (ex: pt, en, es)
        
    Returns:
        Bytes do arquivo de áudio MP3 ou None se falhar
    """
    try:
        from gtts import gTTS
        
        # Remover HTML/formatação do texto
        import re
        clean_text = re.sub(r'<[^>]+>', '', text)
        clean_text = re.sub(r'\*\*', '', clean_text)
        clean_text = re.sub(r'```[\s\S]*?```', '', clean_text)  # Remove code blocks
        clean_text = clean_text.strip()
        
        if not clean_text:
            logger.warning("Texto vazio após limpeza")
            return None
        
        # Limitar tamanho do texto para evitar erros
        if len(clean_text) > 5000:
            clean_text = clean_text[:5000] + "..."
        
        logger.info(f"Gerando TTS para: '{clean_text[:100]}...' no idioma '{language}'")
        
        # Gerar áudio
        tts = gTTS(text=clean_text, lang=language, slow=False)
        
        # Salvar em buffer de memória
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        
        audio_bytes = audio_buffer.read()
        logger.info(f"✅ TTS gerado com sucesso: {len(audio_bytes)} bytes")
        return audio_bytes
        
    except ImportError as e:
        logger.error(f"❌ Biblioteca gTTS não instalada: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Erro ao gerar áudio: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def create_audio_player(audio_bytes: bytes, autoplay: bool = False) -> str:
    """
    Cria um player de áudio HTML5 com os bytes fornecidos
    
    Args:
        audio_bytes: Bytes do arquivo de áudio
        autoplay: Se deve reproduzir automaticamente
        
    Returns:
        HTML do player de áudio
    """
    import base64
    
    audio_base64 = base64.b64encode(audio_bytes).decode()
    autoplay_attr = "autoplay" if autoplay else ""
    
    return f'''
    <audio controls {autoplay_attr} style="width: 100%; margin-top: 8px;">
        <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
        Seu navegador não suporta o elemento de áudio.
    </audio>
    '''
