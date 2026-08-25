CREATE TABLE IF NOT EXISTS app.analysis_run (
    run_id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    scene TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    model_id TEXT NOT NULL,
    generation_mode TEXT NOT NULL DEFAULT 'deepseek',
    answer TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS app.run_step (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES app.analysis_run(run_id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    node_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    summary TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (run_id, step_order)
);

CREATE TABLE IF NOT EXISTS app.sql_artifact (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES app.analysis_run(run_id) ON DELETE CASCADE,
    sql_text TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    referenced_tables JSONB NOT NULL,
    executed_at TIMESTAMPTZ,
    row_count INTEGER
);

CREATE TABLE IF NOT EXISTS app.result_snapshot (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES app.analysis_run(run_id) ON DELETE CASCADE,
    columns JSONB NOT NULL,
    rows JSONB NOT NULL,
    chart_spec JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analysis_run_started_at ON app.analysis_run(started_at DESC);

INSERT INTO app.app_config (config_key, config_value, updated_at) VALUES
    ('project_stage', '"phase-2"'::jsonb, NOW())
ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value, updated_at = NOW();
