-- Drop index if it exists, then create it
DROP INDEX IF EXISTS buildings_geom_idx;
CREATE INDEX buildings_geom_idx ON building USING GIST(geom);

-- Cluster the table using the index
CLUSTER building USING buildings_geom_idx;

-- Analyze to update statistics
ANALYZE building;