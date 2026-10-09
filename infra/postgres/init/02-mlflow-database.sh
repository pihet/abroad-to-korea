#!/usr/bin/env bash
set -euo pipefail

# This also runs as a one-off Compose service so existing PostgreSQL volumes are supported.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" \
  --set=mlflow_password="$MLFLOW_DB_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE mlflow LOGIN PASSWORD ' || quote_literal(:'mlflow_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mlflow') \gexec
ALTER ROLE mlflow WITH LOGIN PASSWORD :'mlflow_password';
SELECT 'CREATE DATABASE mlflow OWNER mlflow'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'mlflow') \gexec
SQL
