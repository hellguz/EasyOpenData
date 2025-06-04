#!/usr/bin/env python3
"""
ingest_state.py

Generic script for processing 3D building data for any German Bundesland,
including support for:
  • Meta4 / ZIP / CityGML sources
  • GeoJSON tile-index (features → properties["xml"])
  • NRW index.json (datasets → files[].name)
  • Mecklenburg-Vorpommern Atom feed (entries → <link rel="section" href="...zip">)
  • Saxony via a plain-text list of ZIP URLs (sachsen.txt)

Usage:
    python backend/ingestion/ingest_state.py --state <state_key> [--no-ingest]

Arguments:
    --state      The key/name of the Bundesland to ingest (e.g., bayern, berlin, nrw, mv, sachsen, etc.).
                 Sources for each state are defined in STATE_SOURCES below.
    --no-ingest  Skip the ingestion phase (download, transform, load to DB). Default: True.

Example:
    python backend/ingestion/ingest_state.py --state bayern
    python backend/ingestion/ingest_state.py --state mv --no-ingest
    python backend/ingestion/ingest_state.py --state sachsen
"""

import sys
import os
import argparse
import subprocess
import logging
import shutil
import zipfile
import json as _json
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from lxml import etree
import psycopg2
import math
import pyproj

# --------- Configuration ---------

# Dictionary of download sources for each Bundesland.
#   • If the value is a list, each element is treated as a direct URL.
#   • If the value is a string ending in .txt, that file is opened and each non-empty line is a URL.
STATE_SOURCES = {
    "bayern": [
        "https://geodaten.bayernatlas.de/xyz/3dgeodata/3D_Gebaeudemodell_LoD2.meta4"
    ],
    "berlin": [
        "https://fbinter.stadt-berlin.de/fb/3d-citygml/LoD2_Berlin.gml"
    ],
    "nrw": [
        # Example: either a ZIP or an index.json
        "https://opendata.nrw.de/3d_model_lod2/nrw_lod2_buildings.zip",
        "https://www.opengeodata.nrw.de/produkte/geobasis/3dg/lod2_gml/lod2_gml/index.json"
    ],
    "niedersachsen": [
        # GeoJSON tile‐index
        "https://lod2.s3.eu-de.cloud-object-storage.appdomain.cloud/lgln-opengeodata-lod2.geojson"
    ],
    "mv": [
        # Mecklenburg-Vorpommern Atom feed
        "https://www.geodaten-mv.de/dienste/gebaeude_atom?type=dataset&id=8397b554-5cb9-4274-8be8-c20490d9a6e8"
    ],
    "sachsen": "backend/ingestion/data_sources/sachsen.txt",
    # … you can add the remaining states similarly …
}

BASE_DATA_LOCAL_DIR = 'backend/ingestion/data_local'
CACHE_DIR = 'data/tileset'
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://postgres:barcelona@localhost:8735/easyopendata_database'
)
PG2B3DM_PATH = 'backend/ingestion/libs/pg2b3dm.exe'
SQL_INDEX_PATH = 'backend/db/index.sql'
CELL_SIZE_KM = 30.0

NO_INGEST_DEFAULT = True
TEMP_TABLE_BASE = 'idx_building'
MAX_CHILDREN_PER_NODE = 8
MIN_GEOMETRIC_ERROR_FOR_LEAF = 100

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# --------- Utility Functions ---------

def download_file(url, dest_path):
    """
    Download a file from 'url' → 'dest_path'. Return True on success, False otherwise.
    """
    try:
        logging.info(f"Downloading {url} → {dest_path}")
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = Request(url, headers=headers)
        with urlopen(req) as resp, open(dest_path, 'wb') as out_f:
            shutil.copyfileobj(resp, out_f)
        logging.info(f"Downloaded to: {dest_path}")
        return True
    except HTTPError as e:
        logging.warning(f"HTTPError {e.code} downloading {url}")
    except URLError as e:
        logging.warning(f"URLError {e.reason} downloading {url}")
    except Exception as e:
        logging.warning(f"Error downloading {url}: {e}", exc_info=True)
    return False

def remove_file(path):
    """
    Remove a file if it exists.
    """
    try:
        if os.path.exists(path):
            os.remove(path)
            logging.info(f"Removed file: {path}")
    except Exception as e:
        logging.warning(f"Failed to remove file {path}: {e}")

def verify_file(file_path, expected_size=None, expected_hash=None, hash_type='sha-256'):
    """
    Stub: Always return True (verification disabled).
    """
    logging.info(f"Skipping verification for {file_path}")
    return True

def get_all_namespaces(gml_tree):
    """
    Extract all namespaces from a parsed GML tree, ensuring 'xlink' is present.
    """
    nsmap = gml_tree.getroot().nsmap.copy()
    if None in nsmap:
        nsmap['default'] = nsmap.pop(None)
    if 'xlink' not in nsmap:
        for pfx, uri in nsmap.items():
            if uri == 'http://www.w3.org/1999/xlink':
                nsmap['xlink'] = uri
                break
        else:
            nsmap['xlink'] = 'http://www.w3.org/1999/xlink'
    return nsmap

def transform_gml(input_file, output_file):
    """
    Embed polygons referenced by xlink:href directly inside <gml:surfaceMember>.
    """
    logging.info(f"Transforming GML: {input_file} → {output_file}")
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(input_file, parser)
    root = tree.getroot()
    ns = get_all_namespaces(tree)

    poly_index = {}
    for poly in root.xpath('.//gml:Polygon', namespaces=ns):
        pid = poly.get('{http://www.opengis.net/gml}id')
        if pid:
            poly_index[pid] = poly

    surface_elems = root.xpath('.//gml:surfaceMember[@xlink:href]', namespaces=ns)
    for sm in surface_elems:
        href = sm.get('{http://www.w3.org/1999/xlink}href')
        if not href:
            continue
        pid = href.lstrip('#')
        poly = poly_index.get(pid)
        if poly is None:
            logging.warning(f"No polygon found for gml:id='{pid}'. Skipping.")
            continue
        poly_copy = etree.fromstring(etree.tostring(poly))
        poly_copy.attrib.pop('{http://www.opengis.net/gml}id', None)
        sm.clear()
        sm.append(poly_copy)

    tree.write(output_file, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    logging.info(f"Wrote transformed: {output_file}")

def ingest_gml_file(gml_file, database_url, table_name):
    """
    Use ogr2ogr to ingest a GML into PostGIS.
    """
    logging.info(f"Ingesting GML {gml_file} → {table_name}")
    cmd = [
        'ogr2ogr',
        '-f', 'PostgreSQL',
        database_url,
        gml_file,
        '-nln', table_name,
        '-progress',
        '-lco', 'GEOMETRY_NAME=geom',
        '-skipfailures',
        '-nlt', 'GEOMETRYZ',
        '-s_srs', 'EPSG:25832',
        '-t_srs', 'EPSG:4326'
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logging.error(f"ogr2ogr failed: {result.stderr}")
        raise RuntimeError(f"ogr2ogr error: {result.stderr}")
    logging.info(f"Ingested {gml_file} into {table_name}")

def extract_zip(zip_path, extract_to):
    """
    Extract a ZIP archive to a directory.
    """
    try:
        logging.info(f"Extracting {zip_path} → {extract_to}")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_to)
        logging.info(f"Extracted {zip_path}")
    except Exception as e:
        logging.error(f"Failed to extract {zip_path}: {e}", exc_info=True)
        raise

def execute_sql_file(sql_file, database_url):
    """
    Run SQL file against the database.
    """
    logging.info(f"Executing SQL file: {sql_file}")
    url = urlparse(database_url)
    conn_params = {
        "dbname": url.path.lstrip("/"),
        "user": url.username,
        "host": url.hostname,
        "port": url.port
    }
    if url.password:
        conn_params["password"] = url.password

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        with conn.cursor() as cur, open(sql_file, 'r') as f:
            cur.execute(f.read())
        conn.commit()
        logging.info(f"Executed {sql_file}")
    except Exception as e:
        logging.error(f"Error executing {sql_file}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def ensure_main_table_exists(database_url, table_name):
    """
    Create main table "table_name" if not exists.
    Schema: gml_id VARCHAR PK, geom GEOMETRY(GEOMETRYZ,4326), attributes JSONB
    """
    logging.info(f"Ensuring table {table_name} exists")
    url = urlparse(database_url)
    conn_params = {
        "dbname": url.path.lstrip("/"),
        "user": url.username,
        "host": url.hostname,
        "port": url.port
    }
    if url.password:
        conn_params["password"] = url.password

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema='public' AND table_name = '{table_name}'
                );
            """)
            exists = cur.fetchone()[0]
            if not exists:
                logging.info(f"Creating table public.{table_name}")
                cur.execute(f"""
                    CREATE TABLE public."{table_name}" (
                        gml_id VARCHAR PRIMARY KEY,
                        geom GEOMETRY(GEOMETRYZ, 4326),
                        attributes JSONB
                    );
                """)
                conn.commit()
                logging.info(f"Created public.{table_name}")
            else:
                logging.info(f"public.{table_name} already exists")
    except Exception as e:
        logging.error(f"Error ensuring {table_name}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def drop_temp_table(database_url, temp_table_name):
    """
    Drop a temporary table if it exists.
    """
    logging.info(f"Dropping temp table {temp_table_name} (if exists)")
    url = urlparse(database_url)
    conn_params = {
        "dbname": url.path.lstrip("/"),
        "user": url.username,
        "host": url.hostname,
        "port": url.port
    }
    if url.password:
        conn_params["password"] = url.password

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS public."{temp_table_name}";')
        conn.commit()
        logging.info(f"Dropped {temp_table_name}")
    except Exception as e:
        logging.error(f"Error dropping {temp_table_name}: {e}", exc_info=True)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def update_geometries(database_url, table_name):
    """
    Translate Z so that min(Z)=0 for all geometries in table_name.
    """
    logging.info(f"Updating geometries (ground level) in {table_name}")
    url = urlparse(database_url)
    conn_params = {
        "dbname": url.path.lstrip("/"),
        "user": url.username,
        "host": url.hostname,
        "port": url.port
    }
    if url.password:
        conn_params["password"] = url.password

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE public."{table_name}"
                SET geom = ST_Translate(geom, 0, 0, -ST_ZMin(geom))
                WHERE geom IS NOT NULL AND ST_ZMin(geom) <> 0;
            """)
        conn.commit()
        logging.info(f"Updated geometries in {table_name}")
    except Exception as e:
        logging.error(f"Error updating geometries in {table_name}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def convert_geometries_to_multipolygonz(database_url, table_name):
    """
    Convert all geometries in table_name to MULTIPOLYGONZ. Others (Points, LineStrings, etc.)
    become NULL. Empty → empty MultiPolygonZ. Collection→ extract Polygons.
    """
    logging.info(f"Converting geometries to MULTIPOLYGONZ in {table_name}")
    url = urlparse(database_url)
    conn_params = {
        "dbname": url.path.lstrip("/"),
        "user": url.username,
        "host": url.hostname,
        "port": url.port
    }
    if url.password:
        conn_params["password"] = url.password

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        conn.autocommit = False
        cur = conn.cursor()

        # (Optional) log pre‐conversion stats
        cur.execute(f"""
            SELECT
                ST_GeometryType(geom) AS geom_type,
                COUNT(*) AS cnt,
                ST_SRID(geom) AS srid,
                ST_CoordDim(geom) AS coord_dim,
                ST_HasZ(geom) AS has_z
            FROM public."{table_name}"
            WHERE geom IS NOT NULL
            GROUP BY geom_type, srid, coord_dim, has_z
            ORDER BY cnt DESC;
        """)
        pre_stats = cur.fetchall()
        logging.info(f"[Before] geometry stats for {table_name}: {pre_stats}")

        update_sql = f"""
            UPDATE public."{table_name}"
            SET geom = CASE
                WHEN geom IS NULL THEN NULL
                WHEN ST_IsEmpty(geom) THEN
                    ST_Force3DZ(
                        ST_Multi(
                            ST_SetSRID(
                                ST_GeomFromText('POLYGON EMPTY'),
                                ST_SRID(geom)
                            )
                        )
                    )
                WHEN ST_GeometryType(geom) = 'ST_MultiPolygon' THEN
                    ST_Force3DZ(geom)
                WHEN ST_GeometryType(geom) = 'ST_Polygon' THEN
                    ST_Force3DZ(ST_Multi(geom))
                WHEN ST_GeometryType(geom) IN ('ST_GeometryCollection', 'ST_MultiSurface', 'ST_PolyhedralSurface') THEN
                    (
                        WITH coll AS (
                            SELECT ST_CollectionExtract(geom, 3) AS extracted
                            FROM public."{table_name}"
                            WHERE gml_id = public."{table_name}".gml_id
                        )
                        SELECT
                            CASE
                                WHEN cp.extracted IS NULL OR ST_IsEmpty(cp.extracted) THEN NULL
                                ELSE ST_Force3DZ(ST_Multi(cp.extracted))
                            END
                        FROM coll AS cp
                    )
                ELSE
                    NULL
            END;
        """
        cur.execute(update_sql)
        logging.info(f"Applied MULTIPOLYGONZ conversion; rows affected: {cur.rowcount}")
        conn.commit()

        # (Optional) log post‐conversion stats
        cur.execute(f"""
            SELECT ST_GeometryType(geom) AS geom_type, COUNT(*) AS cnt, ST_SRID(geom) AS srid
            FROM public."{table_name}"
            GROUP BY geom_type, srid
            ORDER BY cnt DESC;
        """)
        post_stats = cur.fetchall()
        logging.info(f"[After] geometry stats for {table_name}: {post_stats}")

    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f"Error converting geometries in {table_name}: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

def append_temp_to_main(database_url, temp_table, main_table):
    """
    Append rows from temp_table → main_table. Create missing columns in main_table, then
    INSERT … ON CONFLICT(PK) DO NOTHING.
    """
    logging.info(f"Appending {temp_table} → {main_table}")
    url = urlparse(database_url)
    conn_params = {
        "dbname": url.path.lstrip("/"),
        "user": url.username,
        "host": url.hostname,
        "port": url.port
    }
    if url.password:
        conn_params["password"] = url.password

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        with conn.cursor() as cur:
            # main_table columns
            cur.execute(f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name = '{main_table}'
                ORDER BY ordinal_position;
            """)
            main_cols = [row[0] for row in cur.fetchall()]

            # temp_table columns
            cur.execute(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name = '{temp_table}'
                ORDER BY ordinal_position;
            """)
            temp_info = cur.fetchall()
            temp_cols = [c for c,_ in temp_info]

            # Add missing columns to main_table
            for col, dtype in temp_info:
                if col not in main_cols:
                    logging.info(f"Adding column {col} ({dtype}) to {main_table}")
                    cur.execute(f'ALTER TABLE public."{main_table}" ADD COLUMN "{col}" {dtype};')
                    main_cols.append(col)
            conn.commit()

            # Refresh main_cols
            cur.execute(f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name = '{main_table}'
                ORDER BY ordinal_position;
            """)
            main_cols = [row[0] for row in cur.fetchall()]

            # Determine overlapping columns
            insert_cols = [c for c in temp_cols if c in main_cols]
            if not insert_cols:
                logging.error(f"No overlapping columns between {temp_table} & {main_table}. Skipping append.")
                return

            cols_str = ', '.join(f'"{c}"' for c in insert_cols)
            select_str = ', '.join(f'"{c}"' for c in insert_cols)

            # PK columns for ON CONFLICT
            cur.execute(f"""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a 
                  ON a.attrelid = i.indrelid 
                 AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = 'public."{main_table}"'::regclass 
                  AND i.indisprimary;
            """)
            pk_cols = [row[0] for row in cur.fetchall()]
            conflict_clause = ""
            if pk_cols:
                conflict_on = ', '.join(f'"{c}"' for c in pk_cols if c in insert_cols)
                if conflict_on:
                    conflict_clause = f"ON CONFLICT ({conflict_on}) DO NOTHING"

            insert_sql = f"""
                INSERT INTO public."{main_table}" ({cols_str})
                SELECT {select_str} FROM public."{temp_table}" {conflict_clause};
            """
            cur.execute(insert_sql)
            logging.info(f"Inserted/ignored {cur.rowcount} rows into {main_table}")
            conn.commit()

    except Exception as e:
        logging.error(f"Error appending {temp_table} → {main_table}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def get_dataset_bounds(database_url, table_name):
    """
    Return bounding box of all non-empty geometries in table_name as:
      { 'min_lon', 'min_lat', 'max_lon', 'max_lat' }
    or None if no geometries.
    """
    logging.info(f"Calculating bounds for {table_name}")
    url = urlparse(database_url)
    conn_params = {
        "dbname": url.path.lstrip("/"),
        "user": url.username,
        "host": url.hostname,
        "port": url.port
    }
    if url.password:
        conn_params["password"] = url.password

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    ST_XMin( ST_Extent(geom) ),
                    ST_YMin( ST_Extent(geom) ),
                    ST_XMax( ST_Extent(geom) ),
                    ST_YMax( ST_Extent(geom) )
                FROM public."{table_name}"
                WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom);
            """)
            row = cur.fetchone()
            if row and all(v is not None for v in row):
                bounds = {
                    'min_lon': row[0],
                    'min_lat': row[1],
                    'max_lon': row[2],
                    'max_lat': row[3]
                }
                logging.info(f"Bounds for {table_name}: {bounds}")
                return bounds
            else:
                logging.warning(f"No valid geometries in {table_name} → cannot compute bounds")
                return None
    except Exception as e:
        logging.error(f"Error getting bounds for {table_name}: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def calculate_grid_cells(bounds, cell_size_km):
    """
    Split WGS84 bounding box into ~cell_size_km × cell_size_km grid cells
    (via EPSG:25832 projection). Return list of dicts:
      { 'min_lon', 'min_lat', 'max_lon', 'max_lat', 'grid_x_idx', 'grid_y_idx' }
    """
    if not bounds:
        return []

    logging.info(f"Calculating grid cells (size {cell_size_km} km)")
    try:
        proj_to = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)
        proj_back = pyproj.Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)
    except pyproj.exceptions.CRSError as e:
        logging.error(f"CRS transformer error: {e}", exc_info=True)
        return []

    min_x, min_y = proj_to.transform(bounds['min_lon'], bounds['min_lat'])
    max_x, max_y = proj_to.transform(bounds['max_lon'], bounds['max_lat'])
    cell_m = cell_size_km * 1000.0

    if max_x <= min_x or max_y <= min_y:
        logging.warning("Degenerate projected bounds; cannot create grid")
        return []

    nx = math.ceil((max_x - min_x) / cell_m)
    ny = math.ceil((max_y - min_y) / cell_m)
    cells = []

    for i in range(nx):
        for j in range(ny):
            cmin_x = min_x + i * cell_m
            cmax_x = min_x + (i + 1) * cell_m
            cmin_y = min_y + j * cell_m
            cmax_y = min_y + (j + 1) * cell_m

            try:
                cmin_lon, cmin_lat = proj_back.transform(cmin_x, cmin_y)
                cmax_lon, cmax_lat = proj_back.transform(cmax_x, cmax_y)
            except pyproj.exceptions.ProjError as e:
                logging.error(f"Error reprojecting cell {i},{j}: {e}", exc_info=True)
                continue

            cells.append({
                'min_lon': cmin_lon,
                'min_lat': cmin_lat,
                'max_lon': cmax_lon,
                'max_lat': cmax_lat,
                'grid_x_idx': i,
                'grid_y_idx': j
            })
    logging.info(f"Created {len(cells)} grid cells")
    return cells

def create_temp_table_for_grid_cell(database_url, main_table, temp_table, cell_bounds):
    """
    Create temp_table selecting rows from main_table whose geom intersects the cell envelope.
    Return True if >0 rows; else drop temp_table and return False.
    """
    logging.info(f"Creating temp table {temp_table} for bounds {cell_bounds}")
    url = urlparse(database_url)
    conn_params = {
        "dbname": url.path.lstrip("/"),
        "user": url.username,
        "host": url.hostname,
        "port": url.port
    }
    if url.password:
        conn_params["password"] = url.password

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS public."{temp_table}";')
            create_sql = f"""
                CREATE TABLE public."{temp_table}" AS
                SELECT * FROM public."{main_table}"
                WHERE ST_Intersects(
                    geom,
                    ST_MakeEnvelope(
                        {cell_bounds['min_lon']}, {cell_bounds['min_lat']},
                        {cell_bounds['max_lon']}, {cell_bounds['max_lat']},
                        4326
                    )
                );
            """
            cur.execute(create_sql)
            cur.execute(f'SELECT COUNT(*) FROM public."{temp_table}";')
            cnt = cur.fetchone()[0]
            if cnt > 0:
                logging.info(f"Temp table {temp_table} has {cnt} rows")
                idx_sql = f'CREATE INDEX "idx_{temp_table}_geom" ON public."{temp_table}" USING GIST(geom);'
                cur.execute(idx_sql)
                conn.commit()
                return True
            else:
                logging.info(f"No rows in {temp_table}. Dropping it.")
                cur.execute(f'DROP TABLE IF EXISTS public."{temp_table}";')
                conn.commit()
                return False
    except Exception as e:
        logging.error(f"Error creating {temp_table}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        try:
            if conn:
                with conn.cursor() as cur2:
                    cur2.execute(f'DROP TABLE IF EXISTS public."{temp_table}";')
                    conn.commit()
        except:
            pass
        return False
    finally:
        if conn:
            conn.close()

def convert_to_3d_tiles(cache_dir, database_url, table_name):
    """
    Run pg2b3dm to convert table_name → 3D tiles under cache_dir.
    """
    logging.info(f"Converting {table_name} → 3D tiles in {cache_dir}")
    url = urlparse(database_url)
    dbname = url.path.lstrip("/")
    user = url.username
    host = url.hostname or 'localhost'
    port = url.port or 5432

    cmd = [
        PG2B3DM_PATH,
        '-h', f"{host}:{port}",
        '-U', user,
        '-c', 'geom',
        '-a', 'gml_id',
        '-t', table_name,
        '-d', dbname,
        '-o', cache_dir,
        '--use_implicit_tiling', 'false'
    ]
    env = os.environ.copy()
    if url.password:
        env['PGPASSWORD'] = url.password

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    if result.returncode != 0:
        logging.error(f"pg2b3dm error: {result.stderr}")
        raise RuntimeError(f"pg2b3dm failed: {result.stderr}")
    logging.info(f"3D tiles for {table_name} written to {cache_dir}")

def apply_draco_compression(cache_dir):
    """
    Apply Draco compression to all .glb files under cache_dir.
    """
    logging.info(f"Applying Draco compression in {cache_dir}")
    found = False
    for root_dir, _, files in os.walk(cache_dir):
        for fname in files:
            if fname.lower().endswith('.glb'):
                found = True
                glb_path = os.path.join(root_dir, fname)
                tmp_path = os.path.join(root_dir, f"{os.path.splitext(fname)[0]}_draco_tmp.glb")
                cmd = [
                    "gltf-pipeline.cmd",
                    "-i", glb_path,
                    "-o", tmp_path,
                    "--draco.compressionLevel", "7",
                    "--draco.quantizePositionBits", "16",
                    "--draco.quantizeNormalBits", "14",
                    "--draco.quantizeTexcoordBits", "14",
                    "--draco.uncompressedFallback",
                    "--draco.unifiedQuantization"
                ]
                logging.debug(f"Running Draco: {' '.join(cmd)}")
                try:
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
                    os.replace(tmp_path, glb_path)
                    logging.info(f"Compressed {glb_path}")
                except Exception as e:
                    logging.error(f"Draco compression failed for {glb_path}: {e}", exc_info=True)
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
    if not found:
        logging.info(f"No .glb files found in {cache_dir}")

def merge_tilesets_hierarchically(output_path, input_tileset_paths):
    """
    Merge multiple tileset.json files into one hierarchical tileset at output_path.
    """
    logging.info(f"Merging {len(input_tileset_paths)} tilesets → {output_path}")
    root_dir = os.path.dirname(os.path.abspath(output_path))
    child_data = []

    for ts in input_tileset_paths:
        if not os.path.isfile(ts):
            logging.warning(f"Tileset not found: {ts}")
            continue
        try:
            with open(ts, 'r', encoding='utf-8') as f:
                data = _json.load(f)
        except Exception as e:
            logging.error(f"Error reading {ts}: {e}", exc_info=True)
            continue

        root_node = data.get("root")
        if not root_node or "boundingVolume" not in root_node or "region" not in root_node["boundingVolume"]:
            continue
        ge = data.get("geometricError")
        region = root_node["boundingVolume"]["region"]
        rel = os.path.relpath(os.path.abspath(ts), root_dir).replace(os.sep, "/")
        child_data.append({
            "uri": rel,
            "boundingVolume": root_node["boundingVolume"],
            "geometricError": ge,
            "refine": root_node.get("refine", "ADD").upper(),
            "centerX": (region[0] + region[2]) / 2,
            "centerY": (region[1] + region[3]) / 2
        })

    if not child_data:
        logging.warning("No valid child tilesets; writing empty root tileset.")
        merged = {
            "asset": {"version": "1.1", "gltfUpAxis": "Z"},
            "geometricError": 0,
            "root": {
                "boundingVolume": {"region": [0,0,0,0,0,0]},
                "geometricError": 0,
                "refine": "ADD",
                "children": []
            }
        }
    else:
        regions = [item["boundingVolume"]["region"] for item in child_data]
        min_lon = min(r[0] for r in regions)
        min_lat = min(r[1] for r in regions)
        max_lon = max(r[2] for r in regions)
        max_lat = max(r[3] for r in regions)
        min_h = min(r[4] for r in regions)
        max_h = max(r[5] for r in regions)
        root_region = [min_lon, min_lat, max_lon, max_lat, min_h, max_h]

        max_child_ge = max(item["geometricError"] for item in child_data if item["geometricError"] is not None)
        lon_span = root_region[2] - root_region[0]
        lat_span = root_region[3] - root_region[1]
        geo_heuristic = max(lon_span, lat_span) * 111000 * 0.5
        root_ge = max(geo_heuristic, max_child_ge * 4, 200000)

        def build_node(items, region, ge_val, level=0):
            node = {
                "boundingVolume": {"region": region},
                "geometricError": ge_val,
                "refine": "ADD",
                "children": []
            }
            is_leaf = (
                len(items) <= MAX_CHILDREN_PER_NODE or
                all(it["geometricError"] < MIN_GEOMETRIC_ERROR_FOR_LEAF for it in items) or
                level > 10
            )
            if is_leaf:
                for it in items:
                    node["children"].append({
                        "boundingVolume": it["boundingVolume"],
                        "geometricError": it["geometricError"],
                        "refine": it["refine"],
                        "content": {"uri": it["uri"]}
                    })
            else:
                node["refine"] = "REPLACE"
                cx = (region[0] + region[2]) / 2
                cy = (region[1] + region[3]) / 2
                quads = {"sw": [], "se": [], "nw": [], "ne": []}
                for it in items:
                    if it["centerX"] < cx:
                        key = "nw" if it["centerY"] >= cy else "sw"
                    else:
                        key = "ne" if it["centerY"] >= cy else "se"
                    quads[key].append(it)
                child_ge = ge_val / 2.0
                for quad_items in quads.values():
                    if not quad_items:
                        continue
                    rs = [i["boundingVolume"]["region"] for i in quad_items]
                    r = [
                        min(r0 for r0,_,_,_,_,_ in rs),
                        min(r1 for _,r1,_,_,_,_ in rs),
                        max(r2 for _,_,r2,_,_,_ in rs),
                        max(r3 for _,_,_,r3,_,_ in rs),
                        min(r4 for _,_,_,_,r4,_ in rs),
                        max(r5 for _,_,_,_,_,r5 in rs)
                    ]
                    child_node = build_node(quad_items, r, child_ge, level+1)
                    node["children"].append(child_node)
            return node

        root_node = build_node(child_data, root_region, root_ge)
        merged = {
            "asset": {"version": "1.1", "gltfUpAxis": "Y"},
            "geometricError": root_ge,
            "root": root_node
        }

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            _json.dump(merged, f, indent=2)
        logging.info(f"Wrote merged tileset: {output_path}")
    except Exception as e:
        logging.error(f"Error writing merged tileset: {e}", exc_info=True)
        raise

# --------- Main Workflow ---------

def main():
    parser = argparse.ArgumentParser(
        description="Ingest LOD2 building data for a chosen Bundesland"
    )
    parser.add_argument(
        '--state',
        required=True,
        help="Key of the Bundesland to ingest (e.g., bayern, berlin, nrw, mv, sachsen, …)"
    )
    parser.add_argument(
        '--no-ingest',
        action='store_true',
        default=NO_INGEST_DEFAULT,
        help="Skip download & ingestion. Default: True"
    )

    args = parser.parse_args()
    state = args.state.lower()
    no_ingest = args.no_ingest

    if state not in STATE_SOURCES:
        logging.error(f"Unknown state key '{state}'. Available keys: {list(STATE_SOURCES.keys())}")
        sys.exit(1)

    src_config = STATE_SOURCES[state]
    urls = []

    # If config is a string ending with .txt, read it as a plain-text list of URLs.
    if isinstance(src_config, str) and src_config.lower().endswith('.txt'):
        txt_path = src_config
        if not os.path.isfile(txt_path):
            logging.error(f"Expected URL list file not found: {txt_path}")
            sys.exit(1)
        with open(txt_path, 'r', encoding='utf-8') as txtf:
            for line in txtf:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
    # Otherwise, assume it's already a list of URLs.
    elif isinstance(src_config, list):
        urls = list(src_config)
    else:
        logging.error(f"Invalid STATE_SOURCES entry for '{state}'")
        sys.exit(1)

    if not urls:
        logging.error(f"No download URLs found for '{state}'. Aborting.")
        sys.exit(1)

    data_dir = os.path.join(BASE_DATA_LOCAL_DIR, state)
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    main_table = f"building_{state}"
    temp_table = f"{TEMP_TABLE_BASE}_{state}"

    # 1) Ensure main table exists
    ensure_main_table_exists(DATABASE_URL, main_table)

    # 2) Execute SQL index if present
    if os.path.exists(SQL_INDEX_PATH):
        execute_sql_file(SQL_INDEX_PATH, DATABASE_URL)
    else:
        logging.warning(f"{SQL_INDEX_PATH} not found; skipping index SQL")

    # 3) Ingestion if not skipped
    if no_ingest:
        logging.info(f"--no-ingest set; skipping ingestion for '{state}'")
    else:
        all_gml_paths = []

        for src_url in urls:
            parsed = urlparse(src_url)
            fname = os.path.basename(parsed.path).split('?')[0]
            dest_path = os.path.join(data_dir, fname)

            if not download_file(src_url, dest_path):
                logging.error(f"Failed to download {src_url}; skipping this source")
                continue

            lower = fname.lower()

            # 3.a) .meta4
            if lower.endswith('.meta4'):
                try:
                    meta_tree = etree.parse(dest_path)
                except Exception as e:
                    logging.error(f"Failed to parse {dest_path} as Meta4: {e}", exc_info=True)
                    remove_file(dest_path)
                    continue

                ns = {'metalink': 'urn:ietf:params:xml:ns:metalink'}
                entries = []
                for fe in meta_tree.getroot().findall('metalink:file', namespaces=ns):
                    name = fe.get('name')
                    size = int(fe.find('metalink:size', namespaces=ns).text)
                    h = fe.find('metalink:hash', namespaces=ns)
                    hash_type = h.get('type') if h is not None else None
                    hash_val = h.text if h is not None else None
                    urls_inner = [ue.text for ue in fe.findall('metalink:url', namespaces=ns)]
                    entries.append({
                        'name': name,
                        'size': size,
                        'hash_type': hash_type,
                        'hash_value': hash_val,
                        'urls': urls_inner
                    })
                if not entries:
                    logging.warning(f"No <file> entries in {dest_path}")
                else:
                    for entry in entries:
                        gml_name = entry['name']
                        gml_path = os.path.join(data_dir, gml_name)
                        downloaded = False
                        for u in entry['urls']:
                            if download_file(u, gml_path):
                                downloaded = True
                                break
                        if not downloaded:
                            logging.error(f"Failed to download referenced GML {gml_name}")
                            continue
                        all_gml_paths.append(gml_path)

                remove_file(dest_path)

            # 3.b) .zip
            elif lower.endswith('.zip'):
                try:
                    extract_zip(dest_path, data_dir)
                except Exception:
                    remove_file(dest_path)
                    continue

                for root_dir, _, files in os.walk(data_dir):
                    for f in files:
                        if f.lower().endswith(('.gml', '.xml')):
                            full = os.path.join(root_dir, f)
                            if full not in all_gml_paths:
                                all_gml_paths.append(full)
                remove_file(dest_path)

            # 3.c) .geojson or .json
            elif lower.endswith(('.geojson', '.json')):
                try:
                    with open(dest_path, 'r', encoding='utf-8') as jf:
                        data = _json.load(jf)
                except Exception as e:
                    logging.error(f"Failed to parse JSON {dest_path}: {e}", exc_info=True)
                    remove_file(dest_path)
                    continue

                # ▪ NRW index.json format
                if isinstance(data, dict) and 'datasets' in data:
                    base_url = src_url.rsplit('/', 1)[0]
                    for ds in data.get('datasets', []):
                        for f_entry in ds.get('files', []):
                            name = f_entry.get('name')
                            if not name:
                                continue
                            gml_url = f"{base_url}/{name}"
                            gml_path = os.path.join(data_dir, name)
                            if download_file(gml_url, gml_path):
                                all_gml_paths.append(gml_path)
                            else:
                                logging.error(f"Failed to download GML {gml_url}")
                    remove_file(dest_path)

                # ▪ GeoJSON tile‐index format
                elif isinstance(data, dict) and 'features' in data:
                    for feat in data.get('features', []):
                        props = feat.get('properties', {})
                        gml_url = props.get('xml')
                        if not gml_url:
                            continue
                        gml_fname = os.path.basename(urlparse(gml_url).path)
                        gml_path = os.path.join(data_dir, gml_fname)
                        if download_file(gml_url, gml_path):
                            all_gml_paths.append(gml_path)
                        else:
                            logging.error(f"Failed to download GML from GeoJSON xml: {gml_url}")
                    remove_file(dest_path)

                else:
                    logging.warning(f"Unrecognized JSON structure in {dest_path}. Skipping.")
                    remove_file(dest_path)

            # 3.c-2) Atom feed (MV format)
            elif lower.endswith('.xml') or lower.endswith('.atom') or 'gebaeude_atom' in lower:
                # Attempt to parse as Atom feed
                try:
                    tree = ET.parse(dest_path)
                    root = tree.getroot()
                except Exception as e:
                    logging.warning(f"Failed to parse as XML: {dest_path}; treating as GML/XML.")
                    root = None

                is_atom = False
                if root is not None:
                    if root.tag.endswith('feed') and 'http://www.w3.org/2005/Atom' in root.tag:
                        is_atom = True

                if is_atom:
                    logging.info(f"Detected Atom feed: {dest_path}")
                    atom_ns = {'atom': 'http://www.w3.org/2005/Atom'}
                    for entry in root.findall('atom:entry', atom_ns):
                        for link in entry.findall('atom:link', atom_ns):
                            rel = link.get('rel')
                            href = link.get('href')
                            if rel == 'section' and href and href.lower().endswith('.zip'):
                                zfname = os.path.basename(urlparse(href).path)
                                zpath = os.path.join(data_dir, zfname)
                                if download_file(href, zpath):
                                    try:
                                        extract_zip(zpath, data_dir)
                                    except Exception:
                                        continue
                                    for rd, _, fls in os.walk(data_dir):
                                        for f in fls:
                                            if f.lower().endswith(('.gml', '.xml')):
                                                full = os.path.join(rd, f)
                                                if full not in all_gml_paths:
                                                    all_gml_paths.append(full)
                                    remove_file(zpath)
                    remove_file(dest_path)
                else:
                    # Not an Atom feed → assume it’s a direct GML/XML source
                    all_gml_paths.append(dest_path)

            # 3.d) Direct .gml/.xml
            elif lower.endswith(('.gml', '.xml')):
                all_gml_paths.append(dest_path)

            else:
                logging.warning(f"Unrecognized file type: {dest_path}")

        if not all_gml_paths:
            logging.error(f"No GML files found for '{state}'. Aborting ingestion.")
        else:
            logging.info(f"Found {len(all_gml_paths)} GML(s) to ingest for '{state}'")
            for gml_path in all_gml_paths:
                drop_temp_table(DATABASE_URL, temp_table)

                base = os.path.splitext(os.path.basename(gml_path))[0]
                transformed = os.path.join(data_dir, f"{base}_trs.gml")
                try:
                    transform_gml(gml_path, transformed)
                except Exception as e:
                    logging.error(f"Failed to transform {gml_path}: {e}", exc_info=True)
                    continue

                try:
                    ingest_gml_file(transformed, DATABASE_URL, temp_table)
                except Exception as e:
                    logging.error(f"Failed to ingest {transformed} → {temp_table}: {e}", exc_info=True)
                    remove_file(transformed)
                    continue

                try:
                    convert_geometries_to_multipolygonz(DATABASE_URL, temp_table)
                    update_geometries(DATABASE_URL, temp_table)
                except Exception as e:
                    logging.error(f"Geometry processing error for {temp_table}: {e}", exc_info=True)

                try:
                    append_temp_to_main(DATABASE_URL, temp_table, main_table)
                except Exception as e:
                    logging.error(f"Error appending {temp_table} → {main_table}: {e}", exc_info=True)

                remove_file(transformed)
                # Optionally remove the original gml_path to save space:
                # remove_file(gml_path)

            logging.info(f"Completed ingestion for '{state}'")

    # 4) Grid calculation & tiling (always runs)
    logging.info("Starting grid calculation & tiling phase")
    sub_root = os.path.join(CACHE_DIR, 'sub', state)
    os.makedirs(sub_root, exist_ok=True)

    bounds = get_dataset_bounds(DATABASE_URL, main_table)
    grid_cells = calculate_grid_cells(bounds, CELL_SIZE_KM) if bounds else []

    if grid_cells:
        logging.info(f"Processing {len(grid_cells)} grid cells for '{state}'")
        generated_tiles = []
        main_tileset = os.path.join(CACHE_DIR, f"tileset_{state}.json")

        for idx, cell in enumerate(grid_cells):
            gx = cell['grid_x_idx']
            gy = cell['grid_y_idx']
            logging.info(f"--- Cell {idx+1}/{len(grid_cells)} (X={gx}, Y={gy}) ---")

            cell_temp = f"{temp_table}_{gx}_{gy}"
            has_data = create_temp_table_for_grid_cell(
                DATABASE_URL, main_table, cell_temp, cell
            )
            if not has_data:
                continue

            cell_dir = os.path.join(sub_root, f"cell_{gx}_{gy}")
            os.makedirs(cell_dir, exist_ok=True)

            try:
                convert_to_3d_tiles(cell_dir, DATABASE_URL, cell_temp)
                apply_draco_compression(cell_dir)
            except Exception as e:
                logging.error(f"Error generating/compressing tiles for cell_{gx}_{gy}: {e}", exc_info=True)

            tileset_json = os.path.join(cell_dir, 'tileset.json')
            if os.path.exists(tileset_json):
                generated_tiles.append(tileset_json)
                try:
                    merge_tilesets_hierarchically(main_tileset, generated_tiles)
                except Exception as e:
                    logging.error(f"Error merging into {main_tileset}: {e}", exc_info=True)
            else:
                logging.warning(f"No tileset.json in {cell_dir}")

            drop_temp_table(DATABASE_URL, cell_temp)

        if generated_tiles:
            logging.info(f"Final tileset for '{state}': {main_tileset}")
        else:
            logging.warning(f"No sub-tilesets for '{state}'. Writing empty tileset.")
            merge_tilesets_hierarchically(main_tileset, [])
    else:
        logging.warning(f"No grid cells to process for '{state}' (empty or invalid bounds)")

    logging.info(f"Finished script for state '{state}'")

if __name__ == '__main__':
    main()
