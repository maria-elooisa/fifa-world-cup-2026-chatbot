#!/usr/bin/env bash
set -euo pipefail

check_docker_cli() {
  if ! command -v docker >/dev/null 2>&1; then
    cat <<'EOF'
Erro: comando 'docker' nao encontrado.

Para usar Phoenix via Docker Compose, instale e inicie o Docker Desktop:
  1) brew install --cask docker
  2) abra o app "Docker" uma vez e aguarde ficar "Engine running"
  3) reabra o terminal e rode novamente este script
EOF
    exit 127
  fi
}

resolve_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
    return
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
    return
  fi

  cat <<'EOF'
Erro: Docker Compose nao disponivel.

Instale/atualize o Docker Desktop para habilitar "docker compose"
ou instale o binario "docker-compose".
EOF
  exit 127
}

check_docker_engine() {
  if ! docker info >/dev/null 2>&1; then
    cat <<'EOF'
Erro: Docker instalado, mas a engine nao esta ativa.

Abra o app "Docker" e aguarde iniciar.
Depois rode novamente:
  bash scripts/phoenix.sh up
EOF
    exit 1
  fi
}

usage() {
  cat <<'EOF'
Uso:
  bash scripts/phoenix.sh up
  bash scripts/phoenix.sh down
  bash scripts/phoenix.sh logs
  bash scripts/phoenix.sh status

Comandos:
  up      Sobe o Phoenix via docker compose
  down    Derruba o container
  logs    Mostra logs em tempo real
  status  Mostra status dos containers
EOF
}

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

check_docker_cli
resolve_compose_cmd
check_docker_engine

case "$1" in
  up)
    "${COMPOSE_CMD[@]}" up -d phoenix
    echo "Phoenix disponivel em: http://localhost:6006"
    ;;
  down)
    "${COMPOSE_CMD[@]}" down
    ;;
  logs)
    "${COMPOSE_CMD[@]}" logs -f phoenix
    ;;
  status)
    "${COMPOSE_CMD[@]}" ps
    ;;
  *)
    usage
    exit 1
    ;;
esac
