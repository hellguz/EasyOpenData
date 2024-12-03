-- Part 1: Database and extension creation (in transaction)
CREATE DATABASE easyopendata_database;
\c easyopendata_database;
CREATE EXTENSION IF NOT EXISTS postgis;

-- Part 2: System settings (must be outside transaction)
\connect easyopendata_database
\echo 'Setting system parameters...'

\set ON_ERROR_STOP off
ALTER SYSTEM SET maintenance_work_mem TO '1GB';
ALTER SYSTEM SET work_mem TO '256MB';
ALTER SYSTEM SET max_parallel_workers_per_gather TO 4;
\set ON_ERROR_STOP on

