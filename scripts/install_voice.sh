#!/bin/bash

echo "🎤 Instalando recursos de acessibilidade de voz..."
echo ""

# Ativar ambiente virtual se existir
if [ -d ".venv" ]; then
    echo "Ativando ambiente virtual..."
    source .venv/bin/activate
fi

# Instalar dependências Python
echo "Instalando dependências Python..."
pip install SpeechRecognition>=3.10.0 gTTS>=2.5.0 pydub>=0.25.1 audio-recorder-streamlit>=0.0.8

# Verificar se está no macOS e instalar ffmpeg
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo ""
    echo "Verificando FFmpeg..."
    if ! command -v ffmpeg &> /dev/null; then
        echo "FFmpeg não encontrado. Tentando instalar via Homebrew..."
        if command -v brew &> /dev/null; then
            brew install ffmpeg
        else
            echo "⚠️  Homebrew não encontrado. Por favor, instale o FFmpeg manualmente:"
            echo "   brew install ffmpeg"
        fi
    else
        echo "✅ FFmpeg já está instalado"
    fi
fi

echo ""
echo "✅ Instalação concluída!"
echo ""
echo "Para usar os recursos de voz:"
echo "1. Reinicie o servidor Streamlit"
echo "2. Clique no ícone 🎤 para falar sua pergunta"
echo "3. Clique em 🔊 Msg X para ouvir as respostas"
echo ""
echo "Para mais informações, consulte INSTALL_VOICE.md"
