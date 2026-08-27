INSERT INTO app.app_config (config_key, config_value, updated_at)
VALUES ('project_stage', '"phase-7"'::jsonb, NOW())
ON CONFLICT (config_key) DO UPDATE
SET config_value=EXCLUDED.config_value, updated_at=NOW();
