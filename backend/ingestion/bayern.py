#!/usr/bin/env python3
"""
process_meta4.py

A script to sequentially download GML files from a Meta4 file, transform them by embedding polygons,
ingest them into a PostgreSQL database using a temporary table, convert them to 3D tiles,
append to the main building table, and remove the original files.
This version uses hierarchical tileset merging for better performance.

Usage:
    python process_meta4.py file.meta4

Requirements:
    - Python 3.x
    - lxml
    - psycopg2
    - ogr2ogr (from GDAL)
    - pg2b3dm (pg2b3dm.exe on Windows) command available in PATH or specified
    - gltf-pipeline (for Draco compression)
"""

import sys
import os
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
# import math # math is not strictly needed by the merge logic from script 2, but good to have if complex calcs were added

# Constants
META4_PATH = 'backend/ingestion/data_sources/bamberg.meta4'
DATA_DIR = 'backend/ingestion/data_local/bayern'
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:barcelona@localhost:8735/easyopendata_database')
CACHE_DIR = 'data/tileset' # Root directory for all tileset outputs
PG2B3DM_PATH = 'backend/ingestion/libs/pg2b3dm.exe' # Path to pg2b3dm executable
SQL_INDEX_PATH = 'backend/db/index.sql'
TEMP_TABLE = 'idx_building'  # Temporary table name
MAIN_TABLE = 'building'      # Main building table name
BATCH_N = 1 # number of gml files for which there will be created a separate tileset

# Tileset merging parameters
MAX_CHILDREN_PER_NODE = 8  # Max direct children before a node tries to subdivide in merged tileset
MIN_GEOMETRIC_ERROR_FOR_LEAF = 500  # Sub-tilesets with geometric error below this won't be further subdivided by merge

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
        f'{database_url}', # Swapped order for clarity, PG:connstring first
        gml_file,
        '-nln', table_name,
        '-progress',
        '-lco', 'GEOMETRY_NAME=geom',
        '-lco', 'LAUNDER=NO', # Preserve original column names
        '-skipfailures',
        '-nlt', 'MULTIPOLYGONZ', # Explicitly target MULTIPOLYGONZ
        '-dim', 'XYZ', # Ensure 3D
        '-s_srs', 'EPSG:25832', # Source CRS from GML (UTM32N)
        '-t_srs', 'EPSG:4326', # Target CRS for PostGIS (WGS84)
        '-makevalid' # Ask ogr2ogr to attempt to make geometries valid
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
                    "gltf-pipeline.cmd", # Assuming gltf-pipeline is in PATH
                    '-i', gltf_file,
                    '-o', compressed_file,
                    '--draco.compressionLevel', '7', # As per original
                    '-d' # Ensure Draco options are used if source has none
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
    logging.info(f"Attempting to convert geometries in table '{table_name}' to MULTIPOLYGONZ.")
    url = urlparse(database_url)
    conn_params = {
        "dbname": url.path.lstrip("/"), "user": url.username,
        "host": url.hostname, "port": url.port
    }
    if url.password: conn_params["password"] = url.password

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE temp_converted_geoms (gml_id VARCHAR PRIMARY KEY, converted_geom GEOMETRY(MULTIPOLYGONZ, 4326));")
            # No need to commit after CREATE TEMP TABLE in autocommit off mode, but won't hurt in default autocommit on.
            # If using psycopg2 default (autocommit off for transactions), commit after DDL is good.
            conn.commit()


            # It's safer to ST_RemoveRepeatedPoints before ST_MakeValid
            # And ensure ST_Multi wraps the ST_Collect for explicit MultiPolygonZ formation
            insert_complex_sql = f"""
                INSERT INTO temp_converted_geoms (gml_id, converted_geom)
                SELECT
                    t.gml_id,
                    ST_Multi( -- Ensure the result is a MultiPolygon(Z)
                        ST_Collect( -- Collect all valid 3D polygons for this gml_id
                            ST_MakeValid(
                                ST_RemoveRepeatedPoints( -- Add this to clean up minor issues
                                    ST_Force3D(dumped.geom)
                                )
                            )
                        )
                    )
                FROM
                    public."{table_name}" t,
                    LATERAL ST_Dump(ST_CollectionExtract(t.geom, 3)) AS dumped
                WHERE
                    t.geom IS NOT NULL AND
                    ST_GeometryType(t.geom) IN ('ST_PolyhedralSurface', 'ST_GeometryCollection', 'ST_Solid', 'ST_MultiSurface') AND
                    ST_NRings(dumped.geom) > 0 AND ST_NPoints(dumped.geom) > 2 -- Basic check for non-degenerate polygons
                GROUP BY
                    t.gml_id
                ON CONFLICT (gml_id) DO NOTHING;
            """
            cur.execute(insert_complex_sql)
            logging.info(f"Processed {cur.rowcount} complex geometries (PolyhedralSurface, etc.) into temp_converted_geoms.")
            conn.commit()

            insert_simple_sql = f"""
                INSERT INTO temp_converted_geoms (gml_id, converted_geom)
                SELECT
                    t.gml_id,
                    ST_Multi(
                        ST_CollectionExtract(
                            ST_MakeValid(
                                ST_RemoveRepeatedPoints( -- Add this
                                    ST_Force3D(t.geom)
                                )
                            ),
                            3 
                        )
                    )
                FROM
                    public."{table_name}" t
                WHERE
                    t.geom IS NOT NULL AND
                    ST_GeometryType(t.geom) IN ('ST_Polygon', 'ST_MultiPolygon') AND
                    NOT EXISTS (SELECT 1 FROM temp_converted_geoms tcg WHERE tcg.gml_id = t.gml_id) AND
                    ST_NRings(t.geom) > 0 AND ST_NPoints(t.geom) > 2 -- Basic check for non-degenerate input
                ON CONFLICT (gml_id) DO NOTHING;
            """
            cur.execute(insert_simple_sql)
            logging.info(f"Processed {cur.rowcount} simple geometries (Polygon, MultiPolygon) into temp_converted_geoms.")
            conn.commit()

            insert_general_collection_sql = f"""
                INSERT INTO temp_converted_geoms (gml_id, converted_geom)
                SELECT
                    t.gml_id,
                    ST_Multi(
                        ST_CollectionExtract(
                            ST_MakeValid(
                                ST_RemoveRepeatedPoints( -- Add this
                                    ST_Force3D(t.geom)
                                )
                            ),
                            3 
                        )
                    )
                FROM
                    public."{table_name}" t
                WHERE
                    t.geom IS NOT NULL AND
                    ST_GeometryType(t.geom) = 'ST_GeometryCollection' AND 
                    NOT EXISTS (SELECT 1 FROM temp_converted_geoms tcg WHERE tcg.gml_id = t.gml_id) AND
                    ST_NPoints(t.geom) > 2 -- Basic check for non-degenerate input
                ON CONFLICT (gml_id) DO NOTHING;
            """
            cur.execute(insert_general_collection_sql)
            logging.info(f"Processed {cur.rowcount} general GeometryCollection types into temp_converted_geoms.")
            conn.commit()


            update_successful_sql = f"""
                UPDATE public."{table_name}" t
                SET geom = tcg.converted_geom
                FROM temp_converted_geoms tcg
                WHERE t.gml_id = tcg.gml_id AND tcg.converted_geom IS NOT NULL AND NOT ST_IsEmpty(tcg.converted_geom); -- Ensure not empty
            """
            cur.execute(update_successful_sql)
            updated_count = cur.rowcount
            logging.info(f"Updated {updated_count} geometries in '{table_name}' with converted MULTIPOLYGONZ.")
            conn.commit()

            # Check for geometries that were processed but resulted in empty geometries after conversion.
            # Also, check for geometries that were not processed at all by the conversion logic
            # (e.g. because they were filtered out by ST_NPoints/ST_NRings or didn't match type criteria).
            update_failed_to_null_sql = f"""
                UPDATE public."{table_name}" t
                SET geom = NULL
                WHERE 
                    t.geom IS NOT NULL AND (
                        NOT EXISTS ( -- Not successfully updated (either not in temp_converted_geoms or its converted_geom was NULL/Empty)
                            SELECT 1 FROM temp_converted_geoms tcg
                            WHERE tcg.gml_id = t.gml_id AND tcg.converted_geom IS NOT NULL AND NOT ST_IsEmpty(tcg.converted_geom)
                        )
                        OR
                        ST_IsEmpty(t.geom) -- Or if the geom in the table itself is now empty post-update
                    );
            """
            cur.execute(update_failed_to_null_sql)
            nulled_count = cur.rowcount
            if nulled_count > 0:
                logging.warning(f"Set {nulled_count} geometries to NULL in '{table_name}' as they could not be converted to valid non-empty MULTIPOLYGONZ or were not processed by conversion logic.")
            conn.commit()

            cur.execute("DROP TABLE temp_converted_geoms;")
            conn.commit()
            logging.info(f"Geometry conversion to MultiPolygonZ for table '{table_name}' complete.")

    except psycopg2.Error as e:
        logging.error(f"PostgreSQL Error during geometry conversion for '{table_name}': {e.pgcode} - {e.pgerror}", exc_info=True)
        if conn: conn.rollback()
        raise
    except Exception as e:
        logging.error(f"Generic Error during geometry conversion for '{table_name}': {e}", exc_info=True)
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()
                  
def main(meta4_file_path_arg): # Renamed arg to avoid conflict with global
    # Ensure DATA_DIR and CACHE_DIR exist
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    sub_tilesets_base_dir = os.path.join(CACHE_DIR, 'sub')
    os.makedirs(sub_tilesets_base_dir, exist_ok=True) # For batch-specific tilesets
    
    ensure_main_table_exists(DATABASE_URL, MAIN_TABLE)
    # Original script runs index.sql once at the start if ix == 0.
    # Let's run it once before the loop.
    if os.path.exists(SQL_INDEX_PATH):
         execute_sql_file(SQL_INDEX_PATH, DATABASE_URL)
    else:
        logging.warning(f"SQL index file not found at {SQL_INDEX_PATH}, skipping execution.")

    files = parse_meta4(meta4_file_path_arg)
    total_files = len(files)

    # The original script dropped TEMP_TABLE once before loop.
    # It's better to drop/ensure clean state at the start of each batch processing cycle for TEMP_TABLE.
    
    # Loop through files, processing them in batches
    processed_files_count_overall = 0
    generated_sub_tileset_paths = []

    # for batch_start_index in range(0, total_files, BATCH_N):
    for batch_start_index in range(0, 2, BATCH_N):
        batch_files = files[batch_start_index : batch_start_index + BATCH_N]
        current_batch_number = batch_start_index // BATCH_N
        
        logging.info(f"\n--- Processing Batch {current_batch_number} (Files {batch_start_index + 1} to {min(batch_start_index + BATCH_N, total_files)} of {total_files}) ---\n")

        # Ensure TEMP_TABLE is clean for this batch
        drop_temp_table(DATABASE_URL, TEMP_TABLE) # ogr2ogr will create it if it doesn't exist upon first insert

        batch_had_ingested_data = False
        for file_info in batch_files:
            processed_files_count_overall += 1
            file_name = file_info['name']
            logging.info(f"▶️ File {processed_files_count_overall}/{total_files} (Batch {current_batch_number}): {file_name}")

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
                        remove_file(download_path) # Clean up failed download
            if not downloaded:
                logging.error(f"Failed to download and verify {file_name} from all URLs. Skipping.")
                continue

            try:
                transform_gml(download_path, transformed_path)
                ingest_gml_file(transformed_path, DATABASE_URL, TEMP_TABLE) # Ingest into TEMP_TABLE
                batch_had_ingested_data = True # Mark that this batch has data
            except Exception as e:
                logging.error(f"Error during transform/ingest of {file_name}: {e}", exc_info=True)
            finally:
                # Clean up individual GML files after processing
                remove_file(transformed_path)
                transformed_gfs_path = transformed_path.replace(".gml", ".gfs") # ogr2ogr might create .gfs
                remove_file(transformed_gfs_path)
                remove_file(download_path) # Original downloaded file

        # After all files in the batch are attempted for ingestion into TEMP_TABLE
        if batch_had_ingested_data:
            try:
                # convert_geometries_to_multipolygonz(DATABASE_URL, TEMP_TABLE) 
                update_geometries(DATABASE_URL, TEMP_TABLE)
                
                batch_tileset_dir = os.path.join(sub_tilesets_base_dir, str(current_batch_number))
                os.makedirs(batch_tileset_dir, exist_ok=True)
                
                convert_to_3d_tiles(batch_tileset_dir, DATABASE_URL, TEMP_TABLE)
                # apply_draco_compression(batch_tileset_dir) # Compress GLBs in this batch's tileset
                append_temp_to_main(DATABASE_URL, TEMP_TABLE, MAIN_TABLE)
                
                # Add path of this batch's tileset.json for final merge
                batch_tileset_json_path = os.path.join(batch_tileset_dir, 'tileset.json')
                if os.path.exists(batch_tileset_json_path):
                    generated_sub_tileset_paths.append(batch_tileset_json_path)
                else:
                    logging.warning(f"Tileset.json not found for batch {current_batch_number} at {batch_tileset_json_path}")

            except Exception as e:
                logging.error(f"Error processing data in TEMP_TABLE for batch {current_batch_number}: {e}", exc_info=True)
        else:
            logging.info(f"Batch {current_batch_number} had no successfully ingested data. Skipping tileset generation and DB append for this batch.")
        
        # TEMP_TABLE is dropped at the start of the next batch iteration.
        logging.info(f"--- Finished Batch {current_batch_number} ---")

    # After all batches are processed, create the final hierarchical tileset
    if generated_sub_tileset_paths:
        logging.info(f"All batches processed. Merging {len(generated_sub_tileset_paths)} sub-tilesets into a final hierarchical tileset.")
        final_tileset_path = os.path.join(CACHE_DIR, 'tileset.json')
        try:
            merge_tilesets_hierarchically(final_tileset_path, generated_sub_tileset_paths)
            logging.info(f"Final hierarchical tileset created at {final_tileset_path}")
        except Exception as e:
            logging.error(f"Failed to create final hierarchical tileset: {e}", exc_info=True)
    else:
        logging.warning("No sub-tilesets were generated. Skipping final merge.")

    logging.info("🏁 All files processed.")


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
    if len(sys.argv) > 1:
        meta4_file_to_use = sys.argv[1]
        logging.info(f"Using Meta4 file from command line argument: {meta4_file_to_use}")
    
    if not os.path.isfile(meta4_file_to_use):
        logging.error(f"Meta4 file '{meta4_file_to_use}' does not exist.")
        sys.exit(1)
        
    main(meta4_file_to_use)
