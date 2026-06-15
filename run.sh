#!/bin/bash
set -e

docker stop godmode-video-bot || true
docker rm godmode-video-bot || true

docker build -t godmode-video-bot .

docker run -d \
  --name godmode-video-bot \
  --restart unless-stopped \
  --env-file .env \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  -v $(pwd)/downloads:/app/downloads \
  godmode-video-bot

echo "Bot started. Logs: docker logs -f godmode-video-bot"
