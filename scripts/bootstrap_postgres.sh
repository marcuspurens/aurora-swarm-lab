#!/usr/bin/env bash
set -euo pipefail

DSN=${POSTGRES_DSN:-"postgresql://localhost:5432/aurora"}
psql "$DSN" -f app/queue/schema.sql
