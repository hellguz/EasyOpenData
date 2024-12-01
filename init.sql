CREATE DATABASE easyopendata_database;

\c easyopendata_database;

CREATE EXTENSION IF NOT EXISTS postgis;

-- Create the building table
CREATE TABLE building (
    ogc_fid SERIAL PRIMARY KEY,
    geom geometry(Polygon, 4326) NOT NULL,  -- Specify geometry type and SRID
    other_columns TEXT  -- Replace or expand with additional columns as needed
);

-- Create the GIST index for the geom column
CREATE INDEX buildings_geom_idx ON building USING GIST(geom);
