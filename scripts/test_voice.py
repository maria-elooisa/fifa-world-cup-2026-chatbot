#!/usr/bin/env python3
"""
Script de teste para verificar se os recursos de voz estão funcionando
"""
import sys
import os

print("🔍 Testando recursos de voz...")
print("=" * 60)

# Teste 1: Verificar importações
print("\n1️⃣ Verificando bibliotecas instaladas...")
try:
    import speech_recognition as sr
    print("   ✅ SpeechRecognition instalado")
except ImportError as e:
    print(f"   ❌ SpeechRecognition NÃO instalado: {e}")
    sys.exit(1)

try:
    from gtts import gTTS
    print("   ✅ gTTS instalado")
except ImportError as e:
    print(f"   ❌ gTTS NÃO instalado: {e}")
    sys.exit(1)

try:
    import pydub
    print("   ✅ pydub instalado")
except ImportError as e:
    print(f"   ⚠️  pydub NÃO instalado (opcional): {e}")

try:
    from audio_recorder_streamlit import audio_recorder
    print("   ✅ audio-recorder-streamlit instalado")
except ImportError as e:
    print(f"   ❌ audio-recorder-streamlit NÃO instalado: {e}")
    sys.exit(1)

# Teste 2: Testar Text-to-Speech
print("\n2️⃣ Testando Text-to-Speech (gTTS)...")
try:
    import io
    tts = gTTS(text="Teste de áudio", lang="pt", slow=False)
    audio_buffer = io.BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    audio_bytes = audio_buffer.read()
    print(f"   ✅ TTS funcionando! Gerados {len(audio_bytes)} bytes de áudio")
except Exception as e:
    print(f"   ❌ Erro ao testar TTS: {e}")
    import traceback
    traceback.print_exc()

# Teste 3: Verificar voice_utils
print("\n3️⃣ Testando módulo voice_utils...")
try:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from crew.voice_utils import text_to_speech, get_gtts_lang_code, get_speech_lang_code
    
    print("   ✅ voice_utils importado com sucesso")
    
    # Testar função
    test_text = "Olá, este é um teste."
    audio = text_to_speech(test_text, "pt")
    if audio:
        print(f"   ✅ text_to_speech funcionando! Gerados {len(audio)} bytes")
    else:
        print("   ❌ text_to_speech retornou None")
        
except Exception as e:
    print(f"   ❌ Erro ao testar voice_utils: {e}")
    import traceback
    traceback.print_exc()

# Teste 4: Verificar conectividade
print("\n4️⃣ Verificando conectividade com internet...")
try:
    import urllib.request
    urllib.request.urlopen('https://www.google.com', timeout=3)
    print("   ✅ Conexão com internet OK")
except Exception as e:
    print(f"   ❌ Sem conexão com internet: {e}")
    print("   ⚠️  Os serviços de voz precisam de internet para funcionar!")

print("\n" + "=" * 60)
print("✅ Testes concluídos!")
print("\nSe todos os testes passaram, os recursos de voz devem funcionar.")
print("Se houver erros, instale as dependências faltantes:")
print("  pip install SpeechRecognition gTTS audio-recorder-streamlit")
