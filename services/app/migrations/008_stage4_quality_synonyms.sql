INSERT INTO app.synonym (topic_code, canonical_term, synonym_term) VALUES
    ('quality', '缺陷数量', 'Pareto'),
    ('quality', '缺陷数量', '缺陷类型')
ON CONFLICT DO NOTHING;
