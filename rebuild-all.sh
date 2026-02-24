#!/usr/bin/env bash
set -euo pipefail

rm -rf workspaces/*
docker compose down -v
docker compose build --no-cache
docker compose up -d
