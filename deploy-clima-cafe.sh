#!/bin/bash

set -euo pipefail

# Cambia esta URL si tu repo es privado o usas SSH.
REPO_URL="${REPO_URL:-https://github.com/spulidov91/clima_cafe_v1.git}"
APP_DIR="${APP_DIR:-/home/ec2-user/clima_cafe_v1}"
CONTAINER_NAME="${CONTAINER_NAME:-clima-cafe-api}"
IMAGE_NAME="${IMAGE_NAME:-clima-cafe-api:latest}"
PORT="${PORT:-802}"

echo "== 1. Preparando repositorio =="
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  cd "$APP_DIR"
  git pull origin main
fi

cd "$APP_DIR"

echo "== 2. Eliminando contenedor anterior =="
docker rm -f "$CONTAINER_NAME" || true

echo "== 3. Construyendo imagen Docker =="
docker build -t "$IMAGE_NAME" .

echo "== 4. Levantando contenedor =="
docker run -d \
  --name "$CONTAINER_NAME" \
  -p "$PORT:802" \
  --restart unless-stopped \
  -e TRM_COP_USD="${TRM_COP_USD:-3650}" \
  -e PRECIO_INTERNACIONAL_USD_LB="${PRECIO_INTERNACIONAL_USD_LB:-3.30}" \
  -e PRECIO_LOCAL_COP_KG="${PRECIO_LOCAL_COP_KG:-12500}" \
  -e PORCENTAJE_COBERTURA="${PORCENTAJE_COBERTURA:-0.15}" \
  "$IMAGE_NAME"

echo "== 5. Estado =="
docker ps --filter "name=$CONTAINER_NAME"

echo "== 6. Healthcheck =="
sleep 3
curl -f "http://localhost:$PORT/health"

echo
echo "API desplegada en puerto $PORT"
