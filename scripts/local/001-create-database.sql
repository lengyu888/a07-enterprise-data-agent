\set ON_ERROR_STOP on

SELECT 'CREATE ROLE a07_app LOGIN PASSWORD ''a07_local_dev_change_me'''
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a07_app')
\gexec

ALTER ROLE a07_app WITH LOGIN PASSWORD 'a07_local_dev_change_me';

SELECT 'CREATE ROLE demo_reader NOLOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'demo_reader')
\gexec

SELECT 'CREATE DATABASE a07_agent OWNER a07_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'a07_agent')
\gexec

ALTER DATABASE a07_agent OWNER TO a07_app;
