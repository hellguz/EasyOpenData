-- Create the index if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM pg_indexes 
        WHERE schemaname = 'public' 
        AND tablename = 'building' 
        AND indexname = 'idx_makevalid_geom'
    ) THEN
        CREATE INDEX IF NOT EXISTS buildings_geom_idx ON building USING GIST (ST_MakeValid(geom));
    END IF;
END $$;

-- Add the unique constraint if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM pg_constraint 
        WHERE conname = 'gml_id_unique' 
        AND conrelid = 'public.building'::regclass
    ) THEN
        ALTER TABLE public.building ADD CONSTRAINT gml_id_unique UNIQUE (gml_id);
    END IF;
END $$;

-- ALTER TABLE building
-- ADD CONSTRAINT enforce_geotype_geom CHECK (GeometryType(geom) = 'GEOMETRYCOLLECTION' OR geom IS NULL);


-- Make all geometry entries valid or empty
-- If they aren't all MultiPolygonZ, convert them now
-- Turn off NOTICE output first and restore it after this operation

-- SET client_min_messages = WARNING;

-- UPDATE building
-- SET geom = ST_Force3D(ST_CollectionExtract(ST_MakeValid(geom), 3))
-- WHERE NOT ST_IsValid(geom) OR GeometryType(geom) != 'MULTIPOLYGONZ';

-- RESET client_min_messages;


-- Cluster the table using the index
-- CLUSTER building USING buildings_geom_idx;

-- Analyze to update statistics
ANALYZE building;
