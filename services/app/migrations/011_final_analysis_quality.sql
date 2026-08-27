ALTER TABLE app.sql_artifact
    ADD COLUMN IF NOT EXISTS repair_count INTEGER NOT NULL DEFAULT 0
    CHECK (repair_count BETWEEN 0 AND 2);

CREATE TABLE IF NOT EXISTS app.clarification_event (
    clarification_id UUID PRIMARY KEY,
    original_question TEXT NOT NULL,
    detected_scene TEXT,
    missing_fields JSONB NOT NULL,
    options JSONB NOT NULL,
    resolved_question TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_clarification_event_created_at
    ON app.clarification_event(created_at DESC);

INSERT INTO app.app_config (config_key, config_value, updated_at)
VALUES ('final_optimization_features', '["evaluation_dashboard", "result_export", "ambiguity_clarification"]'::jsonb, NOW())
ON CONFLICT (config_key) DO UPDATE
SET config_value=EXCLUDED.config_value, updated_at=NOW();
