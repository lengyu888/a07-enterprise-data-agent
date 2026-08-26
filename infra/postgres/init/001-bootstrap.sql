CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS demo;

CREATE TABLE IF NOT EXISTS app.app_config (
    config_key TEXT PRIMARY KEY,
    config_value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO app.app_config (config_key, config_value)
VALUES
    ('project_stage', '"phase-0"'::jsonb),
    ('dataset_max_business_date', 'null'::jsonb)
ON CONFLICT (config_key) DO NOTHING;
