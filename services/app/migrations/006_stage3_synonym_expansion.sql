INSERT INTO app.synonym (topic_code, canonical_term, synonym_term) VALUES
    ('equipment', '停机时长', '停机时间'),
    ('equipment', '停机时长', '停机分钟数'),
    ('production', '完工产量', '生产量')
ON CONFLICT DO NOTHING;
