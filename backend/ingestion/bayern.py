#!/usr/bin/env python3
"""
process_meta4.py

Script for processing 3D building data for Bavaria (Bayern), Germany.

Workflow:
1.  **Data Ingestion (Optional):**
    *   Parses a Meta4 file to get links to GML data files.
    *   Downloads GML files.
    *   Transforms GMLs by embedding polygon geometries directly (resolving xlink:href).
    *   Ingests transformed GML data into a temporary PostgreSQL table (`TEMP_TABLE`).
    *   Processes geometries in the temporary table (e.g., converts to MultiPolygonZ, adjusts Z-levels).
    *   Appends data from the temporary table to the main data table (`MAIN_TABLE`).
    *   This phase can be skipped using the `--no-ingest` flag.

2.  **Grid Calculation & Tiling:**
    *   Calculates the overall bounding box (EPSG:4326) of the data in `MAIN_TABLE`.
    *   Divides this bounding box into a grid of approximately 50x50 km cells using a projected CRS (EPSG:25832) for accuracy.
    *   For each grid cell that contains data:
        *   Creates a temporary table (`temp_grid_cell_X_Y`) for that cell's data, selecting from `MAIN_TABLE`.
        *   Generates a 3D tileset (sub-tileset) for this cell's data using `pg2b3dm`.
        *   Applies Draco compression to the generated GLB/GLTF files using `gltf-pipeline`.
        *   The newly created sub-tileset's `tileset.json` is then progressively merged into a main hierarchical `tileset.json` located in `CACHE_DIR`.
    *   Removes downloaded/transformed GMLs and temporary cell tables.

Usage:
    python backend/ingestion/bayern.py <path_to_meta4_file> [--no-ingest]

Example:
    python backend/ingestion/bayern.py backend/ingestion/data_sources/bayern.meta4
    python backend/ingestion/bayern.py backend/ingestion/data_sources/bayern.meta4 --no-ingest

Output:
    - Main 3D tileset: `data/tileset/tileset.json`
    - Sub-tilesets for each grid cell: `data/tileset/sub/cell_X_Y/`
    - Downloaded and intermediate GML files are stored temporarily in `DATA_DIR` and then removed.

Requirements:
    - Python 3.x
    - Python Libraries: psycopg2-binary, lxml, pyproj (see backend/requirements.txt)
    - External Tools:
        - ogr2ogr (from GDAL toolkit)
        - pg2b3dm (pg2b3dm.exe for Windows, or build from source)
        - gltf-pipeline (Node.js package: npm install -g gltf-pipeline)
"""

import sys
import os
import argparse # Added for command line argument parsing
import subprocess
import hashlib
import logging
import shutil
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from lxml import etree
import psycopg2
import json
import math
import pyproj # For coordinate transformations

# Constants
META4_PATH = 'backend/ingestion/data_sources/bayern.meta4'
DATA_DIR = 'backend/ingestion/data_local/bayern'
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:barcelona@localhost:8735/easyopendata_database')
CACHE_DIR = 'data/tileset' # Root directory for all tileset outputs
PG2B3DM_PATH = 'backend/ingestion/libs/pg2b3dm.exe' # Path to pg2b3dm executable
SQL_INDEX_PATH = 'backend/db/index.sql'
TEMP_TABLE = 'idx_building'  # Temporary table name
MAIN_TABLE = 'building'      # Main building table name
# BATCH_N = 15 # Removed: No longer processing in batches for tileset creation during ingestion

# Tileset merging parameters (will be used later, keep for now if relevant for overall tiling strategy)
MAX_CHILDREN_PER_NODE = 8
MIN_GEOMETRIC_ERROR_FOR_LEAF = 500

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def parse_meta4(meta4_file):
    """
    Parses the Meta4 XML file and extracts file information.

    Args:
        meta4_file (str): Path to the Meta4 XML file.

    Returns:
        list of dict: List containing information about each file.
    """
    logging.info(f"Parsing Meta4 file: {meta4_file}")
    tree = etree.parse(meta4_file)
    root = tree.getroot()
    ns = {'metalink': 'urn:ietf:params:xml:ns:metalink'}

    files = []
    for file_elem in root.findall('metalink:file', namespaces=ns):
        name = file_elem.get('name')
        size = int(file_elem.find('metalink:size', namespaces=ns).text)
        hash_elem = file_elem.find('metalink:hash', namespaces=ns)
        hash_type = hash_elem.get('type')
        hash_value = hash_elem.text
        urls = [url_elem.text for url_elem in file_elem.findall('metalink:url', namespaces=ns)]
        files.append({
            'name': name,
            'size': size,
            'hash_type': hash_type,
            'hash_value': hash_value,
            'urls': urls
        })
    logging.info(f"Found {len(files)} files in Meta4.")
    return files

def download_file(url, dest_path):
    """
    Downloads a file from a URL to a destination path.

    Args:
        url (str): URL to download from.
        dest_path (str): Destination file path.

    Returns:
        bool: True if download was successful, False otherwise.
    """
    try:
        logging.info(f"Downloading from URL: {url}")
        headers = {'User-Agent': 'Mozilla/5.0'} # Kept from original
        req = Request(url, headers=headers)
        with urlopen(req) as response, open(dest_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        logging.info(f"Downloaded file to: {dest_path}")
        return True
    except HTTPError as e:
        logging.warning(f"HTTP Error: {e.code} when downloading {url}")
    except URLError as e:
        logging.warning(f"URL Error: {e.reason} when downloading {url}")
    except Exception as e:
        logging.warning(f"Unexpected error when downloading {url}: {e}", exc_info=True)
    return False

def verify_file(file_path, expected_size, expected_hash, hash_type='sha-256'):
    """
    Verifies the size and hash of a downloaded file.

    Args:
        file_path (str): Path to the file.
        expected_size (int): Expected file size in bytes.
        expected_hash (str): Expected hash value.
        hash_type (str): Hash algorithm, default 'sha-256'.

    Returns:
        bool: True if verification succeeds, False otherwise.
    """
    logging.info(f"❕Verification disabled for {file_path}.")
    return True
    logging.info(f"Verifying file: {file_path}")
    if not os.path.exists(file_path): # Added robust check
        logging.error(f"File not found for verification: {file_path}")
        return False
    actual_size = os.path.getsize(file_path)
    if actual_size != expected_size:
        logging.error(f"Size mismatch for {file_path}: expected {expected_size}, got {actual_size}")
        return False
    hash_func = hashlib.new(hash_type)
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_func.update(chunk)
    actual_hash = hash_func.hexdigest()
    if actual_hash.lower() != expected_hash.lower():
        logging.error(f"Hash mismatch for {file_path}: expected {expected_hash}, got {actual_hash}")
        return False
    logging.info(f"Verification passed for {file_path}")
    return True

def get_all_namespaces(gml_tree):
    """
    Extracts all namespaces from the GML tree and assigns a unique prefix to the default namespace.

    Args:
        gml_tree (etree.ElementTree): Parsed GML tree.

    Returns:
        dict: Namespace prefix to URI mapping.
    """
    nsmap = gml_tree.getroot().nsmap.copy()
    if None in nsmap:
        nsmap['default'] = nsmap.pop(None)
    if 'xlink' not in nsmap:
        for prefix, uri in nsmap.items():
            if uri == 'http://www.w3.org/1999/xlink':
                nsmap['xlink'] = uri
                break
        else:
            nsmap['xlink'] = 'http://www.w3.org/1999/xlink'
    return nsmap

def transform_gml(input_file, output_file):
    """
    Transforms the input GML file by embedding polygons into surfaceMember elements.

    Args:
        input_file (str): Path to the input GML file.
        output_file (str): Path to the output transformed GML file.
    """
    logging.info(f"Parsing input GML file: {input_file}")
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(input_file, parser)
    root = tree.getroot()
    namespaces = get_all_namespaces(tree)
    
    polygon_dict = {}
    for polygon in root.xpath('.//gml:Polygon', namespaces=namespaces):
        polygon_id = polygon.get('{http://www.opengis.net/gml}id')
        if polygon_id:
            polygon_dict[polygon_id] = polygon
    logging.info(f"Indexed {len(polygon_dict)} polygons.")

    surface_members = root.xpath('.//gml:surfaceMember[@xlink:href]', namespaces=namespaces)
    logging.info(f"Found {len(surface_members)} <gml:surfaceMember> elements with xlink:href.")

    for sm in surface_members:
        href = sm.get('{http://www.w3.org/1999/xlink}href')
        if not href:
            continue
        polygon_id = href.lstrip('#')
        polygon = polygon_dict.get(polygon_id)
        if polygon is None: # Changed from `if not polygon:` for clarity
            logging.warning(f"Polygon with gml:id='{polygon_id}' not found. Skipping.")
            continue
        polygon_copy = etree.fromstring(etree.tostring(polygon))
        polygon_copy.attrib.pop('{http://www.opengis.net/gml}id', None)
        sm.clear()
        sm.append(polygon_copy)

    logging.info(f"Writing transformed GML to: {output_file}")
    tree.write(output_file, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    logging.info("Transformation complete.")

def ingest_gml_file(gml_file, database_url, table_name):
    """
    Ingests a GML file into a PostgreSQL database using ogr2ogr into a specified table.
    (Kept exactly as in the user's original script)
    """
    logging.info(f"Ingesting GML file into database table '{table_name}': {gml_file}")
    cmd = [
        'ogr2ogr',
        '-f', 'PostgreSQL',
        f'{database_url}',
        gml_file,
        '-nln', table_name,
        '-progress',
        '-lco', 'GEOMETRY_NAME=geom',
        # '-lco', 'LAUNDER=NO', # Preserve original column names
        '-skipfailures',
        '-nlt', 'GEOMETRYZ', # Explicitly target MULTIPOLYGONZ
        # '-dim', 'XYZ', # Ensure 3D
        '-s_srs', 'EPSG:25832', # Source CRS from GML (UTM32N)
        '-t_srs', 'EPSG:4326', # Target CRS for PostGIS (WGS84)
        # '-makevalid', # Ask ogr2ogr to attempt to make geometries valid
        # '-oo', 'GML_MULTI_SURFACE_AS_MULTI_POLYGON=YES',
    ]
    # If the table exists, ogr2ogr will try to append.
    # If it's the first time for this table_name, it will create it.
    # We rely on dropping TEMP_TABLE before first use in a batch.
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logging.error(f"ogr2ogr failed for {gml_file}: {result.stderr}")
        # Log stdout as well for more details if needed
        logging.debug(f"ogr2ogr STDOUT for {gml_file}: {result.stdout}")
        raise RuntimeError(f"ogr2ogr failed: {result.stderr}")
    logging.info(f"Ingested {gml_file} into table '{table_name}' successfully.")

def execute_sql_file(sql_file_path, database_url):
    """Executes a SQL file in the database."""
    logging.info(f"Executing SQL file: {sql_file_path}")
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
            with open(sql_file_path, 'r') as f:
                cur.execute(f.read())
            conn.commit()
        logging.info(f"SQL file '{sql_file_path}' executed successfully.")
    except Exception as e:
        logging.error(f"Failed to execute SQL file '{sql_file_path}': {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def update_geometries(database_url, table_name):
    """
    Updates the geometries in the specified table to put them on ground level.
    (Kept exactly as in the user's original script)
    """
    logging.info(f"Updating geometries to ground level in table '{table_name}'.")
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
            # This simple query assumes geometries are already valid MULTIPOLYGONZ or similar
            # and just need Z translation.
            cur.execute(f"""
                UPDATE "{table_name}"
                SET geom = ST_Translate(geom, 0, 0, -ST_ZMin(geom))
                WHERE ST_ZMin(geom) != 0 AND geom IS NOT NULL;
            """)
            conn.commit()
        logging.info(f"Geometries in table '{table_name}' updated successfully.")
    except Exception as e:
        logging.error(f"Failed to update geometries in table '{table_name}': {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def convert_to_3d_tiles(cache_dir, database_url, table_name):
    """
    Converts buildings from the specified table in the database to 3D tiles using pg2b3dm.
    (Kept as in the user's original script, with minor adjustments for clarity if any)
    """
    logging.info(f"Converting table '{table_name}' to 3D tiles with pg2b3dm into '{cache_dir}'.")
    url = urlparse(database_url)
    dbname = url.path.lstrip("/")
    user = url.username
    host = url.hostname or 'localhost'
    port = url.port or 5432 

    cmd = [
        PG2B3DM_PATH,
        '-h', f"{host}:{port}",
        '-U', user,
        '-c', 'geom', # geometry column
        '-a', 'gml_id', # attributes column (for feature ID in b3dm)
        '-t', table_name,
        '-d', dbname,
        '-o', cache_dir,
        '--use_implicit_tiling', 'false', # Explicitly false as in original
        # Consider adding other pg2b3dm optimizations if needed later, but start with original
        # '--geometric_error_strategy', 'halfdiagonal',
        # '--max_features_per_tile', '10000',
    ]
    logging.debug(f"pg2b3dm command: {' '.join(cmd)}")
    env = os.environ.copy()
    if url.password:
        env['PGPASSWORD'] = url.password
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    if result.returncode != 0:
        logging.error(f"pg2b3dm failed for {table_name}:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
        raise RuntimeError(f"pg2b3dm failed: {result.stderr}")
    logging.info(f"3D tiles generated successfully for {table_name} in '{cache_dir}'.")

def apply_draco_compression(cache_dir):
    """
    Applies Draco compression to all .glb files in the specified directory.
    (Kept mostly as in the user's original script, removed the unreliable 'already compressed' check)
    """
    logging.info(f"Applying Draco compression to glTF files in {cache_dir}.")
    glb_files_found = False
    for root_dir, _, files in os.walk(cache_dir):
        for file in files:
            if file.endswith('.glb'):
                glb_files_found = True
                gltf_file = os.path.join(root_dir, file)
                # Output to a temporary file first, then replace
                compressed_file = os.path.join(root_dir, f"{os.path.splitext(file)[0]}_draco_temp.glb")
                
                cmd = [
                    "gltf-pipeline.cmd",
                    '-i', gltf_file,
                    '-o', compressed_file,
                    '--draco.compressionLevel', '7',
                    '--draco.quantizePositionBits', '16',   # Increased from 14 to 16 (higher precision)
                    '--draco.quantizeNormalBits', '14',     # Increased from 10 to 14 (higher precision)
                    '--draco.quantizeTexcoordBits', '14',   # Increased from 12 to 14 (higher precision)
                    '--draco.uncompressedFallback',         # Keep fallback for compatibility
                    '--draco.unifiedQuantization'           # Use unified quantization for better quality
                ]
                logging.debug(f"Draco command: {' '.join(cmd)}")
                try:
                    # Using shell=False is safer, ensure gltf-pipeline is directly executable or use shell=True carefully
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, timeout=300)
                    os.replace(compressed_file, gltf_file)
                    logging.info(f"Applied Draco compression to {gltf_file}")
                except subprocess.CalledProcessError as e:
                    logging.error(f"Draco compression failed for {gltf_file}: {e.stderr}")
                    if os.path.exists(compressed_file): os.remove(compressed_file)
                except subprocess.TimeoutExpired:
                    logging.error(f"Draco compression timed out for {gltf_file}")
                    if os.path.exists(compressed_file): os.remove(compressed_file)
                except Exception as e:
                    logging.error(f"Draco compression general error for {gltf_file}: {e}")
                    if os.path.exists(compressed_file): os.remove(compressed_file)

    if not glb_files_found:
        logging.info(f"No .glb files found in {cache_dir} for Draco compression.")
                    
def append_temp_to_main(database_url, temp_table, main_table):
    """
    Appends data from the temporary table to the main table by copying all columns.
    (Kept exactly as in the user's original script)
    """
    logging.info(f"Appending data from '{temp_table}' to '{main_table}'.")
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
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = '{main_table}' AND table_schema = 'public'
                ORDER BY ordinal_position;
            """)
            main_columns = [row[0] for row in cur.fetchall()]

            cur.execute(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = '{temp_table}' AND table_schema = 'public'
                ORDER BY ordinal_position;
            """)
            temp_columns_info = cur.fetchall()
            temp_column_names = [row[0] for row in temp_columns_info]

            for col_name, data_type in temp_columns_info:
                if col_name not in main_columns:
                    logging.info(f"Column '{col_name}' (type: {data_type}) does not exist in '{main_table}'. Adding it.")
                    # Ensure data_type is safe for ALTER TABLE. For complex types, this might need adjustment.
                    # For ogr2ogr created tables, types are usually standard.
                    alter_sql = f'ALTER TABLE public."{main_table}" ADD COLUMN "{col_name}" {data_type};'
                    cur.execute(alter_sql)
                    main_columns.append(col_name) # Add to list for current transaction context
                    logging.info(f"Column '{col_name}' added to '{main_table}'.")
            
            conn.commit() # Commit ALTER TABLE statements

            # Re-fetch main_columns after potential ALTER TABLE operations
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{main_table}' AND table_schema = 'public' ORDER BY ordinal_position;")
            main_columns_after_alter = [row[0] for row in cur.fetchall()]

            # Determine common columns that can be inserted
            insertable_columns = [col for col in temp_column_names if col in main_columns_after_alter]
            if not insertable_columns:
                logging.error(f"No common columns found between '{temp_table}' and '{main_table}' for insertion. Skipping append.")
                return # Or raise error

            columns_str = ', '.join([f'"{col}"' for col in insertable_columns])
            select_columns_str = ', '.join([f'"{col}"' for col in insertable_columns]) # Ensure we select only these

            cur.execute(f"""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = 'public."{main_table}"'::regclass AND i.indisprimary;
            """)
            pk_columns = [row[0] for row in cur.fetchall()]
            
            on_conflict_clause = ""
            if pk_columns:
                conflict_target = ', '.join([f'"{col}"' for col in pk_columns if col in insertable_columns])
                if conflict_target: # Ensure PK columns are actually part of insertable columns
                    on_conflict_clause = f"ON CONFLICT ({conflict_target}) DO NOTHING"
                    logging.info(f"Using ON CONFLICT clause on PK columns: {conflict_target}")
                else:
                    logging.warning(f"Primary key columns {pk_columns} not in insertable columns {insertable_columns}. No ON CONFLICT uniqueness.")
            else:
                logging.warning(f"No primary key defined for table '{main_table}'. Duplicate records may be inserted if not handled by data.")

            insert_sql = f"""
                INSERT INTO public."{main_table}" ({columns_str})
                SELECT {select_columns_str} FROM public."{temp_table}"
                {on_conflict_clause};
            """
            logging.debug(f"Insert SQL: {insert_sql}")
            cur.execute(insert_sql)
            inserted_count = cur.rowcount
            conn.commit()
            logging.info(f"Data appended from '{temp_table}' to '{main_table}'. Inserted/ignored {inserted_count} records.")

    except Exception as e:
        logging.error(f"Failed to append data from '{temp_table}' to '{main_table}': {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def drop_temp_table(database_url, temp_table):
    """
    Drops the temporary table from the database.
    (Kept exactly as in the user's original script)
    """
    logging.info(f"Dropping temporary table '{temp_table}'.")
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
            cur.execute(f'DROP TABLE IF EXISTS public."{temp_table}";') # Added schema
            conn.commit()
        logging.info(f"Temporary table '{temp_table}' dropped successfully.")
    except Exception as e:
        logging.error(f"Failed to drop temporary table '{temp_table}': {e}", exc_info=True)
        if conn:
            conn.rollback()
        # raise # Do not raise, as this might be called at start and table might not exist
    finally:
        if conn:
            conn.close()

def remove_file(file_path):
    """
    Removes a file from the filesystem.
    """
    try:
        if os.path.exists(file_path): # Check existence before removal
            os.remove(file_path)
            logging.info(f"Removed file: {file_path}")
    except OSError as e:
        logging.warning(f"Failed to remove file {file_path}: {e}")

# --- Hierarchical Tileset Merging Functions (adapted from script 2) ---
def _calculate_node_bounding_volume(nodes_data):
    if not nodes_data: return [0, 0, 0, 0, 0, 0]
    regions = [n["boundingVolume"]["region"] for n in nodes_data if n.get("boundingVolume") and n["boundingVolume"].get("region")]
    if not regions: return [0, 0, 0, 0, 0, 0]
    
    min_lon = min(r[0] for r in regions)
    min_lat = min(r[1] for r in regions)
    max_lon = max(r[2] for r in regions)
    max_lat = max(r[3] for r in regions)
    min_h = min(r[4] for r in regions)
    max_h = max(r[5] for r in regions)
    return [min_lon, min_lat, max_lon, max_lat, min_h, max_h]

def _get_tileset_data(ts_path, root_output_dir):
    if not os.path.isfile(ts_path):
        logging.warning(f"Child tileset file not found, skipping: {ts_path}")
        return None
    try:
        with open(ts_path, 'r', encoding='utf-8') as f:
            ts = json.load(f)
        root = ts.get("root")
        if not root: return None
        bounding_volume = root.get("boundingVolume")
        if not bounding_volume or "region" not in bounding_volume: return None # Ensure region exists
        geometric_error = root.get("geometricError")
        if geometric_error is None: return None # Must have geometric error

        rel_path = os.path.relpath(os.path.abspath(ts_path), root_output_dir).replace(os.sep, "/")
        
        region_coords = bounding_volume["region"]
        return {
            "uri": rel_path,
            "boundingVolume": bounding_volume, # Keep the whole boundingVolume dict
            "geometricError": geometric_error,
            "refine": root.get("refine", "ADD").upper(),
            "centerX": (region_coords[0] + region_coords[2]) / 2,
            "centerY": (region_coords[1] + region_coords[3]) / 2,
        }
    except Exception as e:
        logging.error(f"Error processing child tileset {ts_path}: {e}", exc_info=True)
        return None

def _build_tileset_tree_recursive(tileset_items_data, current_bounding_region, current_geometric_error, level=0):
    node = {
        "boundingVolume": {"region": current_bounding_region},
        "geometricError": current_geometric_error,
        "refine": "ADD", # Default to ADD for intermediate nodes
        "children": []
    }

    is_leaf_node_in_merge_tree = False
    if not tileset_items_data: # Should not happen if called correctly
        return node 
        
    if (len(tileset_items_data) <= MAX_CHILDREN_PER_NODE or
        all(item["geometricError"] < MIN_GEOMETRIC_ERROR_FOR_LEAF for item in tileset_items_data) or
        level > 10): # Max recursion depth guard
        is_leaf_node_in_merge_tree = True

    if is_leaf_node_in_merge_tree:
        for item_data in tileset_items_data:
            node["children"].append({
                "boundingVolume": item_data["boundingVolume"],
                "geometricError": item_data["geometricError"],
                "refine": item_data["refine"], # Use refine from child's root
                "content": {"uri": item_data["uri"]}
            })
        # Refine mode for this node itself is ADD, as it's just grouping external tilesets
    else: # Subdivide
        node["refine"] = "REPLACE" # Internal subdividing nodes use REPLACE
        center_lon = (current_bounding_region[0] + current_bounding_region[2]) / 2
        center_lat = (current_bounding_region[1] + current_bounding_region[3]) / 2
        
        quadrants_items = {"sw": [], "se": [], "nw": [], "ne": []}
        for item in tileset_items_data:
            if item["centerX"] < center_lon: # West
                quadrants_items["nw" if item["centerY"] >= center_lat else "sw"].append(item)
            else: # East
                quadrants_items["ne" if item["centerY"] >= center_lat else "se"].append(item)

        child_geometric_error = current_geometric_error / 2.0 

        for quad_key, items_in_quad in quadrants_items.items():
            if items_in_quad:
                # Calculate tight bounding box for this quadrant's items
                quad_actual_region = _calculate_node_bounding_volume(items_in_quad)
                if quad_actual_region == [0,0,0,0,0,0] and len(items_in_quad) > 0 : # if all items had bad BV
                    logging.warning(f"Quadrant {quad_key} has items but computed an empty bounding region. Items: {items_in_quad}")
                    # Fallback to a broader region or skip? For now, it might create a [0,0,0,0,0,0] node.
                    # This indicates an issue with _get_tileset_data or child tilesets.
                    # Let's ensure quad_actual_region is not degenerate if items_in_quad.
                    # This part might need more robust handling if child tilesets have invalid BVs.
                    pass


                child_node = _build_tileset_tree_recursive(items_in_quad, quad_actual_region, child_geometric_error, level + 1)
                node["children"].append(child_node)
    return node

def merge_tilesets_hierarchically(output_path, input_tileset_paths): # Renamed for clarity
    logging.info(f"Starting hierarchical merge for {len(input_tileset_paths)} tilesets into {output_path}")
    
    root_output_dir = os.path.dirname(os.path.abspath(output_path))
    
    all_child_tileset_data = []
    for ts_path in input_tileset_paths:
        data = _get_tileset_data(ts_path, root_output_dir)
        if data:
            all_child_tileset_data.append(data)

    if not all_child_tileset_data:
        logging.warning("No valid child tilesets to merge. Creating an empty root tileset.")
        # Mimic structure of pg2b3dm empty tileset
        merged_tileset = {
            "asset": {"version": "1.1", "gltfUpAxis": "Z"}, # Common for pg2b3dm
            "geometricError": 0, # Or a large default like 500000
            "root": {
                "boundingVolume": {"region": [0,0,0,0,0,0]},
                "geometricError": 0,
                "refine": "ADD",
                "children": []
            }
        }
    else:
        root_region = _calculate_node_bounding_volume(all_child_tileset_data)
        
        # Estimate root geometric error
        # Based on max child geometric error or diagonal of root region
        max_child_ge = max(item["geometricError"] for item in all_child_tileset_data if item["geometricError"] is not None) if all_child_tileset_data else 0
        
        # Heuristic: a factor of the largest dimension of the bounding box in degrees, converted roughly to meters.
        # Or simply a large fixed value, or multiple of max child error.
        lon_span = root_region[2] - root_region[0]
        lat_span = root_region[3] - root_region[1]
        # A very rough approximation for geometric error (meters) based on degrees
        # Using 1 degree ~ 111km. Error should be related to tile size on screen.
        # For root, make it large enough so it's always refined from afar.
        root_geometric_error_heuristic = max(lon_span, lat_span) * 111000 * 0.5 # Half diagonal approx
        
        # Ensure it's significantly larger than children, and has a minimum sensible value for large area
        root_geometric_error = max(root_geometric_error_heuristic, max_child_ge * 4, 200000) 
        
        logging.info(f"Root region for merge: {root_region}, initial geometricError: {root_geometric_error}")

        root_node = _build_tileset_tree_recursive(all_child_tileset_data, root_region, root_geometric_error)

        merged_tileset = {
            "asset": {"version": "1.1", "gltfUpAxis": "Y"},
            "geometricError": root_geometric_error, # Root geometric error of the tileset
            "root": root_node
        }

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(merged_tileset, f, indent=2)
        logging.info(f"Hierarchical merged tileset successfully written to {output_path}")
    except IOError as e:
        logging.error(f"Failed to write merged tileset to {output_path}: {e}", exc_info=True)
        raise
# --- End Hierarchical Tileset Merging Functions ---

def ensure_main_table_exists(database_url, table_name):
    """
    Ensures that the main table exists in the database. Creates it if it does not exist.
    (Kept as in the user's original script)
    """
    logging.info(f"Ensuring main table '{table_name}' exists.")
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
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table_name}' AND table_schema = 'public'
                );
            """)
            exists = cur.fetchone()[0]

            if not exists:
                logging.info(f"Table 'public.{table_name}' does not exist. Creating it.")
                # Original script had attributes JSONB, keeping it. gml_id as PK.
                # GEOMETRY(GEOMETRYZ, 4326) is flexible, MULTIPOLYGONZ is stricter.
                # ogr2ogr with -nlt MULTIPOLYGONZ attempts to conform.
                # Let's use GEOMETRYZ for main table to be more robust if some non-multipolygons sneak in,
                # but pg2b3dm might prefer MULTIPOLYGONZ. The original script had GEOMETRYZ.
                cur.execute(f"""
                    CREATE TABLE public."{table_name}" (
                        gml_id VARCHAR PRIMARY KEY,
                        geom GEOMETRY(GEOMETRYZ, 4326), 
                        attributes JSONB 
                    );
                """)
                conn.commit()
                logging.info(f"Table 'public.{table_name}' created successfully.")
            else:
                logging.info(f"Table 'public.{table_name}' already exists.")
    except Exception as e:
        logging.error(f"Failed to ensure table '{table_name}' exists: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def convert_geometries_to_multipolygonz(database_url, table_name):
    logging.info(f"Attempting to convert geometries in table '{table_name}' (column 'geom') to MULTIPOLYGONZ.")
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
    updated_count = 0
    sql_update_query = "" # Initialize for logging in case of early error

    try:
        conn = psycopg2.connect(**conn_params)
        conn.autocommit = False # Start a transaction
        cursor = conn.cursor()

        cursor.execute("SELECT PostGIS_Version();")
        pg_version = cursor.fetchone()[0]
        logging.info(f"Connected to PostgreSQL with PostGIS version: {pg_version}")

        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        total_rows = cursor.fetchone()[0]
        logging.info(f"Total rows in table '{table_name}': {total_rows}")

        if total_rows == 0:
            logging.info(f"Table '{table_name}' is empty. No geometries to convert.")
            return

        # --- Diagnostic: Log current geometry types before conversion ---
        logging.info(f"Querying current geometry types in '{table_name}' before conversion...")
        # It's good to qualify geom with table_name if there's any ambiguity, though not strictly needed here.
        # Also checking coordinate dimension and Z presence.
        diagnostic_query = f"""
            SELECT
                ST_GeometryType(geom) as geom_type,
                COUNT(*) as count,
                ST_SRID(geom) as srid,
                CASE WHEN ST_CoordDim(geom) IS NOT NULL THEN ST_CoordDim(geom)::text ELSE 'NULL' END as coord_dim,
                CASE WHEN ST_HasZ(geom) IS NOT NULL THEN ST_HasZ(geom)::text ELSE 'NULL' END as has_z
            FROM {table_name}
            WHERE geom IS NOT NULL
            GROUP BY geom_type, srid, coord_dim, has_z
            ORDER BY count DESC;
        """
        cursor.execute(diagnostic_query)
        initial_types = cursor.fetchall()
        if not initial_types:
            logging.info(f"No non-NULL geometries found in '{table_name}' to analyze.")
        else:
            logging.info(f"Initial geometry types, SRIDs, dimensions, and Z presence in '{table_name}':")
            for geom_type, count, srid_val, dim, has_z_flag in initial_types:
                logging.info(f"  - Type: {geom_type}, Count: {count}, SRID: {srid_val}, Dimensions: {dim}, Has Z: {has_z_flag}")
        # --- End Diagnostic ---

        # ST_GeometryType returns the base type (e.g., 'ST_MultiSurface' not 'ST_MultiSurfaceZ')
        # ST_SRID(geom) is used to preserve SRID for empty geometries
        # The CTE (WITH collection_parts) is to avoid multiple calls to ST_CollectionExtract(geom, 3)
        # and to handle its result (which could be NULL, an empty geometry, a Polygon, or a MultiPolygon)
        sql_update_query = f"""
        UPDATE {table_name}
        SET geom = CASE
            -- Handle NULL inputs first
            WHEN geom IS NULL THEN NULL

            -- Handle EMPTY geometries: convert to an empty MULTIPOLYGONZ with original SRID
            WHEN ST_IsEmpty(geom) THEN
                ST_Force3DZ(ST_Multi(ST_SetSRID(ST_GeomFromText('POLYGON EMPTY'), ST_SRID(geom))))

            -- If already ST_MultiPolygon, ensure Z coordinate (idempotent if already Z)
            WHEN ST_GeometryType(geom) = 'ST_MultiPolygon' THEN
                ST_Force3DZ(geom)

            -- If ST_Polygon, convert to ST_MultiPolygon and ensure Z coordinate
            WHEN ST_GeometryType(geom) = 'ST_Polygon' THEN
                ST_Force3DZ(ST_Multi(geom))

            -- Handle collections: ST_GeometryCollection, ST_MultiSurface, ST_PolyhedralSurface
            -- These types can contain polygons that need to be extracted.
            -- ST_GeometryType returns the base name, e.g., 'ST_PolyhedralSurface' for 'ST_PolyhedralSurfaceZ'.
            WHEN ST_GeometryType(geom) IN ('ST_GeometryCollection', 'ST_MultiSurface', 'ST_PolyhedralSurface') THEN
                (
                    WITH collection_parts AS (
                        -- Extract only POLYGON components (type 3) from the current row's geometry
                        SELECT ST_CollectionExtract({table_name}.geom, 3) AS extracted_geom
                    )
                    SELECT
                        CASE
                            -- If no polygons were extracted, or the result of extraction is an empty geometry
                            WHEN cp.extracted_geom IS NULL OR ST_IsEmpty(cp.extracted_geom) THEN
                                NULL -- Cannot convert to MultiPolygonZ if no polygons are present or extracted
                            -- If polygons were extracted, ensure they are MULTIPOLYGONZ
                            -- ST_Multi will handle if extracted_geom is Polygon or MultiPolygon
                            ELSE
                                ST_Force3DZ(ST_Multi(cp.extracted_geom))
                        END
                    FROM collection_parts cp
                )
            -- For any other geometry type (Points, LineStrings, etc.), set to NULL
            ELSE NULL
        END;
        """

        logging.info(f"Executing update on '{table_name}'. This might take a while for large tables...")
        cursor.execute(sql_update_query)
        updated_count = cursor.rowcount
        
        conn.commit()
        logging.info(f"Successfully converted geometries in '{table_name}'. {updated_count} rows' 'geom' column potentially modified.")

        logging.info(f"Querying geometry types in '{table_name}' after conversion...")
        cursor.execute(f"""
            SELECT ST_GeometryType(geom) as geom_type, COUNT(*) as count, ST_SRID(geom) as srid
            FROM {table_name}
            GROUP BY geom_type, srid
            ORDER BY count DESC;
        """)
        type_counts_after = cursor.fetchall()
        logging.info(f"Geometry types in '{table_name}' after conversion:")
        if not type_counts_after:
            logging.info("  - No geometries found (or all are NULL).")
        for geom_type, count, srid_val in type_counts_after:
            logging.info(f"  - Type: {geom_type if geom_type else 'NULL_GEOM_VALUE'}, Count: {count}, SRID: {srid_val}")

    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logging.error(f"Database error occurred: {e}")
        logging.error(f"SQLSTATE: {e.pgcode}")
        logging.error(f"Problematic SQL query might have been:\n{sql_update_query}")
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f"An unexpected error occurred: {e}")
        logging.error(f"Problematic SQL query might have been:\n{sql_update_query}")
        raise
    finally:
        if conn:
            conn.close()
            logging.info("Database connection closed.")
                                      
def main(args): # Modified to accept parsed arguments
    meta4_file_path_arg = args.meta4_file_path_arg

    # Ensure DATA_DIR (for temporary GML downloads) and CACHE_DIR (for tileset outputs) exist
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    # sub_tilesets_base_dir = os.path.join(CACHE_DIR, 'sub') # Removed: No longer creating sub-tilesets during ingestion
    # os.makedirs(sub_tilesets_base_dir, exist_ok=True) # Removed
    
    ensure_main_table_exists(DATABASE_URL, MAIN_TABLE)
    # Original script runs index.sql once at the start if ix == 0.
    # Let's run it once before the loop.
    if os.path.exists(SQL_INDEX_PATH):
         execute_sql_file(SQL_INDEX_PATH, DATABASE_URL)
    else:
        logging.warning(f"SQL index file not found at {SQL_INDEX_PATH}, skipping execution.")

    if args.no_ingest:
        logging.info("Skipping ingestion process due to --no-ingest flag.")
        # The main loop for processing and ingesting files will be skipped.
        # If there's a need to generate tilesets from already existing data in MAIN_TABLE
        # even when --no-ingest is true, that logic would need to be added here.
        # For now, per the subtask, we are just skipping the ingestion part.
    else:
        files = parse_meta4(meta4_file_path_arg)
        total_files = len(files)
        processed_files_count_overall = 0
        # generated_sub_tileset_paths = [] # Removed: No longer creating sub-tilesets during ingestion

        logging.info(f"Starting ingestion of {total_files} GML files into '{MAIN_TABLE}'.")

        for ix, file_info in enumerate(files):
            processed_files_count_overall += 1
            file_name = file_info['name']
            logging.info(f"--- Processing file {processed_files_count_overall}/{total_files}: {file_name} ---")

            # Ensure TEMP_TABLE is clean for this GML file
            drop_temp_table(DATABASE_URL, TEMP_TABLE)

            download_path = os.path.join(DATA_DIR, file_name)
            transformed_file_name = os.path.splitext(file_name)[0] + '_trs.gml'
            transformed_path = os.path.join(DATA_DIR, transformed_file_name)

            downloaded = False
            for url in file_info['urls']:
                if download_file(url, download_path):
                    if verify_file(download_path, file_info['size'], file_info['hash_value'], file_info['hash_type']):
                        downloaded = True
                        break
                    else:
                        logging.warning(f"Verification failed for {download_path} from {url}. Trying next.")
                        remove_file(download_path)
            if not downloaded:
                logging.error(f"Failed to download and verify {file_name} from all URLs. Skipping this file.")
                continue

            gml_processed_successfully = False
            try:
                transform_gml(download_path, transformed_path)
                ingest_gml_file(transformed_path, DATABASE_URL, TEMP_TABLE)

                # Process data in TEMP_TABLE and append to MAIN_TABLE
                convert_geometries_to_multipolygonz(DATABASE_URL, TEMP_TABLE)
                update_geometries(DATABASE_URL, TEMP_TABLE)
                append_temp_to_main(DATABASE_URL, TEMP_TABLE, MAIN_TABLE)

                gml_processed_successfully = True
                logging.info(f"Successfully processed and ingested {file_name} into {MAIN_TABLE}.")

            except Exception as e:
                logging.error(f"Error during processing or ingesting of {file_name}: {e}", exc_info=True)
            finally:
                # Clean up individual GML files after processing
                remove_file(transformed_path)
                transformed_gfs_path = transformed_path.replace(".gml", ".gfs")
                remove_file(transformed_gfs_path)
                remove_file(download_path)

            if not gml_processed_successfully:
                 logging.warning(f"File {file_name} was not successfully ingested into {MAIN_TABLE}.")

        logging.info(f"--- All {total_files} GML files processed for ingestion. ---")

        # Tileset generation and merging will be handled separately after all data is in MAIN_TABLE.
        # The merge_tilesets_hierarchically call and related logic are removed from here.
        # If apply_draco_compression and convert_to_3d_tiles are to be run on the entire MAIN_TABLE
        # at once, those calls would happen outside this ingestion loop, likely in a new section of main()
        # or as separate functions called after this loop.

    # --- Grid Calculation and Tiling Phase ---
    # This phase calculates the dataset's total bounds, divides it into a grid (e.g., 50x50km cells),
    # then processes each cell to generate a 3D tileset. These cell-specific tilesets (sub-tilesets)
    # are progressively merged into a main hierarchical tileset.
    # This phase runs regardless of --no-ingest, operating on data present in MAIN_TABLE.

    logging.info("--- Starting Grid Calculation and Tiling Phase ---")

    # Ensure the base directory for sub-tilesets exists within CACHE_DIR
    sub_tilesets_root_dir = os.path.join(CACHE_DIR, 'sub')
    os.makedirs(sub_tilesets_root_dir, exist_ok=True)

    dataset_bounds = get_dataset_bounds(DATABASE_URL, MAIN_TABLE)
    grid_cells = [] # Initialize in case bounds calculation fails or table is empty

    if dataset_bounds:
        CELL_SIZE_KM = 50.0 # Define cell size in kilometers
        logging.info(f"Attempting to calculate grid cells of size {CELL_SIZE_KM}x{CELL_SIZE_KM} km.")
        grid_cells = calculate_grid_cells(dataset_bounds, CELL_SIZE_KM)
    else:
        logging.error(f"Could not calculate dataset bounds for '{MAIN_TABLE}'. Skipping grid-based tiling.")

    if grid_cells:
        logging.info(f"Successfully calculated {len(grid_cells)} grid cells. Proceeding with tiling for each cell.")
        generated_sub_tileset_paths = [] # List to keep track of successfully generated sub-tileset.json paths
        main_hierarchical_tileset_path = os.path.join(CACHE_DIR, 'tileset.json') # Path for the main merged tileset

        for i, cell_info in enumerate(grid_cells):
            grid_x_idx = cell_info['grid_x_idx']
            grid_y_idx = cell_info['grid_y_idx']
            logging.info(f"--- Processing Grid Cell {i+1}/{len(grid_cells)} (Index X:{grid_x_idx}, Y:{grid_y_idx}) ---")

            # Define a unique name for the temporary table for this cell's data
            temp_cell_table_name = f"temp_grid_cell_{grid_x_idx}_{grid_y_idx}"

            try:
                # Create a temporary table containing only data for the current grid cell
                has_data = create_temp_table_for_grid_cell(DATABASE_URL, MAIN_TABLE, temp_cell_table_name, cell_info)

                if not has_data:
                    logging.info(f"No data found in '{MAIN_TABLE}' for cell (X:{grid_x_idx}, Y:{grid_y_idx}). Skipping tiling for this cell.")
                    continue # Move to the next cell

                # Define output directory for this cell's tileset
                cell_tileset_output_dir = os.path.join(sub_tilesets_root_dir, f"cell_{grid_x_idx}_{grid_y_idx}")
                os.makedirs(cell_tileset_output_dir, exist_ok=True)

                logging.info(f"Generating 3D tiles for cell (X:{grid_x_idx}, Y:{grid_y_idx}). Output to: {cell_tileset_output_dir}")
                convert_to_3d_tiles(cell_tileset_output_dir, DATABASE_URL, temp_cell_table_name)
                
                logging.info(f"Applying Draco compression for cell (X:{grid_x_idx}, Y:{grid_y_idx}) tiles.")
                apply_draco_compression(cell_tileset_output_dir)

                # Path to the sub-tileset's main JSON file
                sub_tileset_json_path = os.path.join(cell_tileset_output_dir, 'tileset.json')
                if os.path.exists(sub_tileset_json_path):
                    generated_sub_tileset_paths.append(sub_tileset_json_path)
                    logging.info(f"Sub-tileset generated: {sub_tileset_json_path}. Merging into main hierarchical tileset.")

                    # Progressively merge after each successful sub-tileset generation
                    merge_tilesets_hierarchically(main_hierarchical_tileset_path, generated_sub_tileset_paths)
                    logging.info(f"Progressively merged {len(generated_sub_tileset_paths)} sub-tilesets into {main_hierarchical_tileset_path}")
                else:
                    logging.warning(f"Tileset.json not found for cell (X:{grid_x_idx}, Y:{grid_y_idx}) at {sub_tileset_json_path}. This cell will not be included in the main tileset.")

            except Exception as e:
                logging.error(f"An error occurred while processing cell (X:{grid_x_idx}, Y:{grid_y_idx}): {e}", exc_info=True)
                # Decide if to continue with other cells or stop. For robustness, continue.
            finally:
                # Always attempt to drop the temporary cell table to keep the database clean
                drop_temp_table(DATABASE_URL, temp_cell_table_name)
        
        if generated_sub_tileset_paths:
            logging.info(f"Finished processing all grid cells. The final main hierarchical tileset is located at: {main_hierarchical_tileset_path}")
        else:
            logging.warning("No sub-tilesets were generated in this run. The main tileset may be empty or unchanged from a previous run.")
            # If no sub-tilesets were made and the main tileset doesn't exist, create an empty one.
            if not os.path.exists(main_hierarchical_tileset_path):
                 merge_tilesets_hierarchically(main_hierarchical_tileset_path, []) # Creates an empty tileset structure

    else: # This 'else' corresponds to 'if grid_cells:' after attempting to calculate them
        logging.warning("No grid cells were generated (e.g., dataset was empty or bounds could not be determined). Tiling process cannot proceed.")

    logging.info("🏁 Main script execution finished.")


# --- Grid Cell Data Handling and Tiling Functions ---
def create_temp_table_for_grid_cell(database_url, main_table_name, temp_table_name, cell_bounds):
    """
    Creates a temporary table for a grid cell by selecting data from the main table
    that intersects with the cell's bounds.

    Args:
        database_url (str): Connection string for the database.
        main_table_name (str): Name of the main table containing all geometries.
        temp_table_name (str): Name for the temporary table to be created.
        cell_bounds (dict): {'min_lon', 'min_lat', 'max_lon', 'max_lat'} for the cell.

    Returns:
        bool: True if the temporary table was created and contains data, False otherwise.
    """
    logging.info(f"Creating temporary table '{temp_table_name}' for cell: {cell_bounds}")
    url = urlparse(database_url)
    conn_params = {
        "dbname": url.path.lstrip("/"),
        "user": url.username,
        "host": url.hostname,
        "port": url.port,
    }
    if url.password:
        conn_params["password"] = url.password

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        with conn.cursor() as cur:
            # Drop the temporary table if it already exists
            cur.execute(f'DROP TABLE IF EXISTS public."{temp_table_name}";')

            # Create the temporary table with data intersecting the cell bounds
            # Using ST_MakeEnvelope with SRID 4326, assuming 'geom' in main_table_name is also 4326
            # The && operator is a BBOX-only intersection check, potentially faster as a first pass
            # ST_Intersects is a more precise geometry intersection check.
            # For simplicity and correctness with pg2b3dm, often a full intersection is better if performance allows.
            # Let's use ST_Intersects as it's generally safer for ensuring data truly falls within the cell for tiling.
            create_sql = f"""
                CREATE TABLE public."{temp_table_name}" AS
                SELECT * FROM public."{main_table_name}"
                WHERE ST_Intersects(geom, ST_MakeEnvelope(
                    {cell_bounds['min_lon']}, {cell_bounds['min_lat']},
                    {cell_bounds['max_lon']}, {cell_bounds['max_lat']},
                    4326
                ));
            """
            logging.debug(f"Executing SQL for temp table: {create_sql}")
            cur.execute(create_sql)

            # Check if any rows were inserted
            cur.execute(f"SELECT COUNT(*) FROM public.\"{temp_table_name}\";")
            count = cur.fetchone()[0]

            if count > 0:
                logging.info(f"Temporary table '{temp_table_name}' created with {count} records.")
                # Add a spatial index to the temporary table's geometry column
                # This can significantly speed up pg2b3dm processing.
                # Ensure the geometry column name 'geom' is correct.
                index_sql = f'CREATE INDEX "idx_{temp_table_name}_geom" ON public."{temp_table_name}" USING GIST (geom);'
                logging.debug(f"Executing SQL for index: {index_sql}")
                cur.execute(index_sql)
                conn.commit()
                logging.info(f"Spatial index created on '{temp_table_name}.geom'.")
                return True
            else:
                logging.info(f"No data found for cell. Temporary table '{temp_table_name}' is empty or not created if CREATE AS SELECT found no rows and didn't error.")
                # Explicitly drop if it was created but is empty, to keep DB clean
                cur.execute(f'DROP TABLE IF EXISTS public."{temp_table_name}";')
                conn.commit()
                return False

    except Exception as e:
        logging.error(f"Error creating temp table '{temp_table_name}' for cell: {e}", exc_info=True)
        if conn:
            conn.rollback() # Rollback any partial transaction
        # Attempt to drop the table again in case of failure during creation after it was formed
        try:
            if conn: # Re-establish simple connection if original one is bad
                 with conn.cursor() as cur_cleanup:
                    cur_cleanup.execute(f'DROP TABLE IF EXISTS public."{temp_table_name}";')
                    conn.commit()
        except Exception as e_cleanup:
            logging.error(f"Failed to cleanup temp table '{temp_table_name}' after error: {e_cleanup}")
        return False
    finally:
        if conn:
            conn.close()

# --- Grid Calculation Functions ---
def get_dataset_bounds(database_url, table_name):
    """
    Calculates the overall bounding box of geometries in the specified table.

    Args:
        database_url (str): Connection string for the database.
        table_name (str): Name of the table containing geometries.

    Returns:
        dict: A dictionary with {'min_lon': ..., 'min_lat': ..., 'max_lon': ..., 'max_lat': ...}
              or None if the table is empty or an error occurs.
    """
    logging.info(f"Calculating dataset bounds for table '{table_name}'.")
    url = urlparse(database_url)
    conn_params = {
        "dbname": url.path.lstrip("/"),
        "user": url.username,
        "host": url.hostname,
        "port": url.port,
    }
    if url.password:
        conn_params["password"] = url.password

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        with conn.cursor() as cur:
            # Ensure SRID is 4326 for bounds
            # ST_Extent aggregates geometries and returns a box2d, ST_Transform ensures it's in 4326
            # ST_Envelope creates a geometry from the box2d for ST_AsText or further processing
            # Using ST_XMin etc. directly on ST_Extent might be more direct if SRID is guaranteed.
            # Let's assume geom is in 4326 as per prior ingestion steps.
            query = f"""
                SELECT
                    ST_XMin(ST_Extent(geom)),
                    ST_YMin(ST_Extent(geom)),
                    ST_XMax(ST_Extent(geom)),
                    ST_YMax(ST_Extent(geom))
                FROM public."{table_name}"
                WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom);
            """
            cur.execute(query)
            result = cur.fetchone()

            if result and all(val is not None for val in result):
                bounds = {
                    'min_lon': result[0],
                    'min_lat': result[1],
                    'max_lon': result[2],
                    'max_lat': result[3]
                }
                logging.info(f"Calculated bounds for '{table_name}': {bounds}")
                return bounds
            else:
                logging.warning(f"No valid geometries found in table '{table_name}' to calculate bounds.")
                return None
    except Exception as e:
        logging.error(f"Error calculating bounds for table '{table_name}': {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def calculate_grid_cells(bounds, cell_size_km):
    """
    Calculates grid cells based on dataset bounds and a cell size.

    Args:
        bounds (dict): Dictionary with {'min_lon', 'min_lat', 'max_lon', 'max_lat'}.
        cell_size_km (float): Desired cell size in kilometers.

    Returns:
        list: A list of dictionaries, where each dictionary represents a grid cell
              with its lon/lat bounds and grid indices.
    """
    if not bounds:
        logging.error("Invalid bounds provided for grid calculation.")
        return []

    logging.info(f"Calculating grid cells with cell size {cell_size_km} km.")

    # Define transformers
    # EPSG:25832 is ETRS89 / UTM zone 32N, suitable for Germany/Bayern
    # EPSG:4326 is WGS84 (lon/lat)
    try:
        transformer_to_proj = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)
        transformer_to_wgs84 = pyproj.Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)
    except pyproj.exceptions.CRSError as e:
        logging.error(f"Failed to initialize coordinate transformers: {e}. Ensure pyproj CRS data is available.")
        return []


    # Transform overall dataset bounds from WGS84 to the projected CRS
    try:
        min_x_proj, min_y_proj = transformer_to_proj.transform(bounds['min_lon'], bounds['min_lat'])
        max_x_proj, max_y_proj = transformer_to_proj.transform(bounds['max_lon'], bounds['max_lat'])
    except pyproj.exceptions.ProjError as e:
        logging.error(f"Error transforming bounds to projected CRS: {e}")
        return []

    logging.info(f"Projected bounds (EPSG:25832): min_x={min_x_proj}, min_y={min_y_proj}, max_x={max_x_proj}, max_y={max_y_proj}")

    cell_size_m = cell_size_km * 1000.0

    # Calculate number of cells
    # Ensure we cover the entire extent, hence math.ceil
    if (max_x_proj - min_x_proj) <= 0 or (max_y_proj - min_y_proj) <= 0 :
        logging.warning("Projected bounds have zero or negative extent. Cannot create grid.")
        return []

    num_cells_x = math.ceil((max_x_proj - min_x_proj) / cell_size_m)
    num_cells_y = math.ceil((max_y_proj - min_y_proj) / cell_size_m)

    if num_cells_x == 0 or num_cells_y == 0:
        logging.warning(f"Calculated zero cells in one or both dimensions ({num_cells_x}x{num_cells_y}). Check bounds and cell size.")
        return []

    logging.info(f"Grid dimensions: {num_cells_x} cells in X, {num_cells_y} cells in Y.")

    grid_cells = []
    for i in range(num_cells_x):
        for j in range(num_cells_y):
            # Calculate cell's projected bounds
            cell_min_x = min_x_proj + i * cell_size_m
            cell_max_x = min_x_proj + (i + 1) * cell_size_m
            cell_min_y = min_y_proj + j * cell_size_m
            cell_max_y = min_y_proj + (j + 1) * cell_size_m

            # Transform cell bounds back to WGS84 (lon/lat)
            try:
                cell_min_lon, cell_min_lat = transformer_to_wgs84.transform(cell_min_x, cell_min_y)
                cell_max_lon, cell_max_lat = transformer_to_wgs84.transform(cell_max_x, cell_max_y)
            except pyproj.exceptions.ProjError as e:
                logging.error(f"Error transforming cell {i},{j} bounds back to WGS84: {e}")
                continue # Skip this cell or handle error as appropriate

            grid_cells.append({
                'min_lon': cell_min_lon,
                'min_lat': cell_min_lat,
                'max_lon': cell_max_lon,
                'max_lat': cell_max_lat,
                'grid_x_idx': i,
                'grid_y_idx': j
            })

    logging.info(f"Calculated {len(grid_cells)} grid cells.")
    return grid_cells
# --- End Grid Calculation Functions ---


if __name__ == '__main__':
    # Check for pg2b3dm and gltf-pipeline (optional, but good practice)
    if not os.path.exists(PG2B3DM_PATH) or not os.access(PG2B3DM_PATH, os.X_OK):
        logging.warning(
            f"pg2b3dm not found or not executable at {PG2B3DM_PATH}. "
            f"Ensure it's correctly placed and executable, or update PG2B3DM_PATH."
        )
        # sys.exit(1) # Decide if this is critical enough to exit

    try:
        # Check gltf-pipeline (assuming it's in PATH)
        subprocess.run(["gltf-pipeline.cmd", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.warning(
            "gltf-pipeline command not found or failed. Please install it (e.g., npm install -g gltf-pipeline) "
            "if Draco compression is desired."
        )

    meta4_file_to_use = META4_PATH
    # Setup command-line argument parsing
    parser = argparse.ArgumentParser(description="Process Meta4 GML files for 3D building tiling for Bayern.")
    parser.add_argument('meta4_file_path_arg', help="Path to the Meta4 file (e.g., backend/ingestion/data_sources/bayern.meta4).")
    parser.add_argument('--no-ingest', action='store_true',
                        help="Skip the data ingestion phase (download, transform, load to DB). "
                             "Useful if data is already in the main table and only tiling is needed.")
    
    args = parser.parse_args()

    if not os.path.isfile(args.meta4_file_path_arg):
        logging.error(f"Meta4 file '{args.meta4_file_path_arg}' does not exist.")
        sys.exit(1)
        
    main(args)
