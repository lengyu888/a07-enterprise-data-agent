-- Historical runs already persisted every repair_sql node before the dedicated
-- repair_count column existed. Reconstruct the value so the evaluation panel
-- does not misclassify repaired SQL as a first-pass success.
UPDATE app.sql_artifact AS artifact
SET repair_count = LEAST(2, repair_steps.repair_count)
FROM (
    SELECT run_id, COUNT(*)::INTEGER AS repair_count
    FROM app.run_step
    WHERE node_name = 'repair_sql'
    GROUP BY run_id
) AS repair_steps
WHERE artifact.run_id = repair_steps.run_id;
