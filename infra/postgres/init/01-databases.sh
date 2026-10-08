#!/usr/bin/env bash
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" \
  --set=app_password="$APP_DB_PASSWORD" \
  --set=airflow_password="$AIRFLOW_DB_PASSWORD" <<'SQL'
CREATE USER app WITH PASSWORD :'app_password';
CREATE DATABASE abroad_to_korea OWNER app;
CREATE USER airflow WITH PASSWORD :'airflow_password';
CREATE DATABASE airflow OWNER airflow;
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname abroad_to_korea <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
SQL
