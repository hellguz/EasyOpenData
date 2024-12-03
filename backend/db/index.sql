-- Create the index if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM pg_indexes 
        WHERE schemaname = 'public' 
        AND tablename = 'building' 
        AND indexname = 'buildings_geom_idx'
    ) THEN
        CREATE INDEX buildings_geom_idx ON building USING GIST(geom);
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

-- Cluster the table using the index
CLUSTER building USING buildings_geom_idx;

-- Analyze to update statistics
ANALYZE building;
