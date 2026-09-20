\set ON_ERROR_STOP on

-- Host prerequisite: install a pgvector package compatible with the running
-- PostgreSQL major version.  This script is intentionally idempotent and does
-- not create application tables; the vector projection remains rebuildable.
CREATE EXTENSION IF NOT EXISTS vector;

SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';
