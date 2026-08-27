ALTER TABLE app.analysis_run
    DROP CONSTRAINT IF EXISTS analysis_run_status_check;

ALTER TABLE app.analysis_run
    ADD CONSTRAINT analysis_run_status_check
    CHECK (status IN ('running', 'completed', 'failed', 'cancelled'));

ALTER TABLE app.analysis_run
    ADD COLUMN IF NOT EXISTS original_question TEXT,
    ADD COLUMN IF NOT EXISTS parent_run_id TEXT REFERENCES app.analysis_run(run_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS retry_of_run_id TEXT REFERENCES app.analysis_run(run_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS cancel_requested_at TIMESTAMPTZ;

UPDATE app.analysis_run
SET original_question = question
WHERE original_question IS NULL;

ALTER TABLE app.analysis_run
    ALTER COLUMN original_question SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_analysis_run_parent
    ON app.analysis_run(parent_run_id, started_at);

CREATE TABLE IF NOT EXISTS app.data_import_batch (
    batch_id UUID PRIMARY KEY,
    template_code TEXT NOT NULL CHECK (template_code IN ('quality_inspection', 'equipment_event', 'production_output')),
    source_filename TEXT NOT NULL,
    target_tables JSONB NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count > 0 AND row_count <= 500),
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_import_batch_created
    ON app.data_import_batch(created_at DESC);

INSERT INTO app.app_config (config_key, config_value, updated_at)
VALUES ('phase7_optimization_features', '["multi_turn_follow_up", "fixed_csv_import", "cooperative_cancel_retry"]'::jsonb, NOW())
ON CONFLICT (config_key) DO UPDATE
SET config_value=EXCLUDED.config_value, updated_at=NOW();
