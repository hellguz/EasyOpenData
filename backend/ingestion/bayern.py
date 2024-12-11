#!/usr/bin/env python3
"""
process_meta4.py

A script to sequentially download GML files from a Meta4 file, transform them by embedding polygons,
ingest them into a PostgreSQL database using a temporary table, convert them to 3D tiles,
append to the main building table, and remove the original files.

Usage:
    python process_meta4.py file.meta4

Requirements:
    - Python 3.x
    - lxml
    - psycopg2
    - ogr2ogr (from GDAL)
    - pg2b3dm_new command available in PATH
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

# Constants
META4_PATH = 'backend/ingestion/data_sources/bayern.meta4'
DATA_DIR = 'backend/ingestion/data_local/bayern'
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:barcelona@localhost:8735/easyopendata_database')
CACHE_DIR = 'data/tileset'
PG2B3DM_PATH = 'backend/ingestion/libs/pg2b3dm.exe'
SQL_INDEX_PATH = 'backend/db/index.sql'
TEMP_TABLE = 'idx_building'  # Temporary table name
MAIN_TABLE = 'building'      # Main building table name
BATCH_N = 20 # number of gml files for which there will be created a separate tileset

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
        headers = {'User-Agent': 'Mozilla/5.0'}
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
        logging.warning(f"Unexpected error when downloading {url}: {e}")
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
    logging.info(f"Verifying file: {file_path}")
    # Check size
    actual_size = os.path.getsize(file_path)
    if actual_size != expected_size:
        logging.error(f"Size mismatch for {file_path}: expected {expected_size}, got {actual_size}")
        return False
    # Check hash
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
    # Handle default namespace (None key)
    if None in nsmap:
        nsmap['default'] = nsmap.pop(None)
    # Ensure 'xlink' is included
    if 'xlink' not in nsmap:
        # Attempt to find the xlink namespace
        for prefix, uri in nsmap.items():
            if uri == 'http://www.w3.org/1999/xlink':
                nsmap['xlink'] = uri
                break
        else:
            # If not found, add it manually
            nsmap['xlink'] = 'http://www.w3.org/1999/xlink'
    return nsmap

def transform_gml(input_file, output_file):
    """
    Transforms the input GML file by embedding polygons into surfaceMember elements.

    Args:
        input_file (str): Path to the input GML file.
        output_file (str): Path to the output transformed GML file.
    """
    # Parse the GML file
    logging.info(f"Parsing input GML file: {input_file}")
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(input_file, parser)
    root = tree.getroot()

    # Extract all namespaces
    namespaces = get_all_namespaces(tree)
    # logging.debug("Namespaces detected:")
    # for prefix, uri in namespaces.items():
    #     logging.debug(f"  Prefix: '{prefix}' => URI: '{uri}'")

    # Build a dictionary of gml:id to Polygon elements for quick lookup
    logging.info("Indexing all <gml:Polygon> elements by gml:id...")
    polygon_dict = {}
    for polygon in root.xpath('.//gml:Polygon', namespaces=namespaces):
        polygon_id = polygon.get('{http://www.opengis.net/gml}id')
        if polygon_id:
            polygon_dict[polygon_id] = polygon
    logging.info(f"Indexed {len(polygon_dict)} polygons.")

    # Find all <gml:surfaceMember> elements with xlink:href
    logging.info("Finding all <gml:surfaceMember> elements with xlink:href...")
    surface_members = root.xpath('.//gml:surfaceMember[@xlink:href]', namespaces=namespaces)
    logging.info(f"Found {len(surface_members)} <gml:surfaceMember> elements with xlink:href.")

    for sm in surface_members:
        href = sm.get('{http://www.w3.org/1999/xlink}href')
        if not href:
            continue
        # Extract the referenced polygon ID (remove the '#' prefix)
        polygon_id = href.lstrip('#')
        # logging.debug(f"Processing surfaceMember referencing Polygon ID: {polygon_id}")
        polygon = polygon_dict.get(polygon_id)
        if not polygon:
            logging.warning(f"Polygon with gml:id='{polygon_id}' not found. Skipping.")
            continue
        # Deep copy the polygon element
        polygon_copy = etree.fromstring(etree.tostring(polygon))
        # Remove any existing 'gml:id' to avoid duplicate IDs
        polygon_copy.attrib.pop('{http://www.opengis.net/gml}id', None)
        # Replace the surfaceMember's xlink:href attribute with the actual Polygon
        sm.clear()  # Remove existing children and attributes
        sm.append(polygon_copy)
        # logging.debug(f"Embedded Polygon ID: {polygon_id} into surfaceMember.")

    # Optionally, remove standalone <gml:Polygon> elements that were referenced
    # logging.info("Removing standalone <gml:Polygon> elements that were referenced...")
    # removed_count = 0
    # for polygon_id in polygon_dict.keys():
    #     # Find and remove the standalone polygon
    #     polygons_to_remove = root.xpath(f'.//gml:Polygon[@gml:id="{polygon_id}"]', namespaces=namespaces)
    #     for polygon in polygons_to_remove:
    #         parent = polygon.getparent()
    #         if parent is not None:
    #             parent.remove(polygon)
    #             removed_count += 1
    #             logging.debug(f"Removed standalone Polygon ID: {polygon_id}.")
    # logging.info(f"Removed {removed_count} standalone polygons.")

    # Write the transformed GML to the output file
    logging.info(f"Writing transformed GML to: {output_file}")
    tree.write(output_file, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    logging.info("Transformation complete.")

def ingest_gml_file(gml_file, database_url, table_name):
    """
    Ingests a GML file into a PostgreSQL database using ogr2ogr into a specified table.

    Args:
        gml_file (str): Path to the GML file.
        database_url (str): PostgreSQL connection URL.
        table_name (str): Target table name for ingestion.
    """
    logging.info(f"Ingesting GML file into database table '{table_name}': {gml_file}")
    cmd = [
        'ogr2ogr',
        '-f', 'PostgreSQL',
        '-nln', table_name,              # Specify the target table name
        '-progress',
        '-lco', 'GEOMETRY_NAME=geom',
        '-skipfailures',
        '-nlt', 'MULTIPOLYGONZ',
        '-dim', 'XYZ',
        '-s_srs', 'EPSG:25832',
        '-t_srs', 'EPSG:4326',
        database_url,
        gml_file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logging.error(f"ogr2ogr failed for {gml_file}: {result.stderr}")
        raise RuntimeError(f"ogr2ogr failed: {result.stderr}")
    logging.info(f"Ingested {gml_file} into table '{table_name}' successfully.")

def execute_sql_file(sql_file_path, database_url):
    """Executes a SQL file in the database."""
    logging.info(f"Executing SQL file: {sql_file_path}")
    url = urlparse(database_url)
    conn = psycopg2.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    try:
        with conn.cursor() as cur:
            with open(sql_file_path, 'r') as f:
                cur.execute(f.read())
            conn.commit()
        logging.info("SQL file executed successfully")
    except Exception as e:
        logging.error(f"Failed to execute SQL file: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def update_geometries(database_url, table_name):
    """
    Updates the geometries in the specified table to put them on ground level.

    Args:
        database_url (str): PostgreSQL connection URL.
        table_name (str): Table to update.
    """
    logging.info(f"Updating geometries to ground level in table '{table_name}'.")
    url = urlparse(database_url)
    conn = psycopg2.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE {table_name}
                SET geom = ST_Translate(geom, 0, 0, -ST_ZMin(geom))
                WHERE ST_ZMin(geom) != 0;
            """)
            conn.commit()
        logging.info(f"Geometries in table '{table_name}' updated successfully.")
    except Exception as e:
        logging.error(f"Failed to update geometries in table '{table_name}': {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def convert_to_3d_tiles(cache_dir, database_url, table_name):
    """
    Converts buildings from the specified table in the database to 3D tiles using pg2b3dm.

    Args:
        cache_dir (str): Output directory for 3D tiles.
        database_url (str): PostgreSQL connection URL.
        table_name (str): Table to convert to 3D tiles.
    """
    logging.info(f"Converting table '{table_name}' to 3D tiles with pg2b3dm.")
    # Parse the database URL for parameters
    url = urlparse(database_url)
    dbname = url.path[1:]
    user = url.username
    host = url.hostname or 'localhost'
    port = url.port
    # Assume password is handled via environment or .pgpass
    cmd = [
        PG2B3DM_PATH,
        '-h', f"{host}:{port}",
        '-U', user,
        '-c', 'geom',
        '-t', table_name,
        '-d', dbname,
        '-o', cache_dir, 
         '--use_implicit_tiling', 'false'  # Uncomment if needed
    ]
    # To handle password, set PGPASSWORD environment variable if available
    env = os.environ.copy()
    if url.password:
        env['PGPASSWORD'] = url.password
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    if result.returncode != 0:
        logging.error(f"pg2b3dm failed: {result.stderr}")
        raise RuntimeError(f"pg2b3dm failed: {result.stderr}")
    logging.info("3D tiles generated successfully.")

def apply_draco_compression(cache_dir):
    """
    Applies Draco compression to all .glb files in the specified directory.

    Args:
        cache_dir (str): Directory containing .glb files.
    """
    logging.info("Applying Draco compression to glTF files.")
    for root, dirs, files in os.walk(cache_dir):
        for file in files:
            if file.endswith('.glb'):
                gltf_file = os.path.join(root, file)

                # Check if the first line of the file contains "draco"
                try:
                    with open(gltf_file, 'rb') as f:
                        first_line = f.readline().decode('utf-8', errors='ignore')
                        if "draco" in first_line.lower():
                            logging.info(f"File {gltf_file} already contains Draco; skipping compression.")
                            continue
                except Exception as e:
                    logging.error(f"Error reading file {gltf_file}: {e}")
                    continue

                # Proceed with Draco compression
                compressed_file = os.path.join(root, f"{os.path.splitext(file)[0]}_draco.glb")
                cmd = [
                    "gltf-pipeline",
                    '-i', gltf_file,
                    '-o', compressed_file,
                    '--draco.compressionLevel', '7'
                ]
                print(" ".join(cmd))
                result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if result.returncode != 0:
                    logging.error(f"Draco compression failed for {gltf_file}: {result.stderr}")
                else:
                    os.replace(compressed_file, gltf_file)
                    logging.info(f"Applied Draco compression to {gltf_file}")
                    
def append_temp_to_main(database_url, temp_table, main_table):
    """
    Appends data from the temporary table to the main table by copying all columns.
    If the main table does not have certain columns, they will be created.
    Handles duplicates by ignoring records that violate primary key constraints.

    Args:
        database_url (str): PostgreSQL connection URL.
        temp_table (str): Temporary table name.
        main_table (str): Main table name.
    """
    logging.info(f"Appending data from '{temp_table}' to '{main_table}'.")
    url = urlparse(database_url)
    conn = psycopg2.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )

    try:
        with conn.cursor() as cur:
            # Fetch main table columns
            cur.execute(f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = '{main_table}'
                ORDER BY ordinal_position;
            """)
            main_columns = [row[0] for row in cur.fetchall()]

            # Fetch temp table columns and their data types
            cur.execute(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = '{temp_table}'
                ORDER BY ordinal_position;
            """)
            temp_columns_info = cur.fetchall()
            temp_columns = [row[0] for row in temp_columns_info]

            # Add missing columns to main_table
            for col_name, data_type in temp_columns_info:
                if col_name not in main_columns:
                    logging.info(f"Column '{col_name}' does not exist in '{main_table}'. Adding it.")
                    # Add the column with the same data_type as in temp_table
                    # Note: For complex types or special columns, you may need a more robust mapping.
                    alter_sql = f'ALTER TABLE "{main_table}" ADD COLUMN "{col_name}" {data_type};'
                    cur.execute(alter_sql)
                    main_columns.append(col_name)
                    logging.info(f"Column '{col_name}' added to '{main_table}'.")

            # Now all temp_columns should exist in main_table
            # We will insert all columns from temp_table to main_table
            columns_str = ', '.join([f'"{col}"' for col in temp_columns])

            # Fetch primary key columns from the main table
            cur.execute(f"""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid
                                     AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = '{main_table}'::regclass
                  AND i.indisprimary;
            """)
            pk_columns = [row[0] for row in cur.fetchall()]
            if not pk_columns:
                raise ValueError(f"No primary key defined for table '{main_table}'.")

            # Construct the ON CONFLICT clause
            conflict_target = ', '.join([f'"{col}"' for col in pk_columns])
            on_conflict_clause = f"ON CONFLICT ({conflict_target}) DO NOTHING"

            logging.info(f"Using ON CONFLICT clause on columns: {conflict_target}")

            # Execute the INSERT statement with ON CONFLICT
            insert_sql = f"""
                INSERT INTO "{main_table}" ({columns_str})
                SELECT {columns_str} FROM "{temp_table}"
                {on_conflict_clause};
            """
            cur.execute(insert_sql)

            inserted_count = cur.rowcount
            conn.commit()
            logging.info(f"Data appended from '{temp_table}' to '{main_table}' successfully. Inserted {inserted_count} records.")

    except Exception as e:
        logging.error(f"Failed to append data from '{temp_table}' to '{main_table}': {e}")
        conn.rollback()
        raise
    finally:
        conn.close()



def drop_temp_table(database_url, temp_table):
    """
    Drops the temporary table from the database.

    Args:
        database_url (str): PostgreSQL connection URL.
        temp_table (str): Temporary table name.
    """
    logging.info(f"Dropping temporary table '{temp_table}'.")
    url = urlparse(database_url)
    conn = psycopg2.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {temp_table};")
            conn.commit()
        logging.info(f"Temporary table '{temp_table}' dropped successfully.")
    except Exception as e:
        logging.error(f"Failed to drop temporary table '{temp_table}': {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def remove_file(file_path):
    """
    Removes a file from the filesystem.

    Args:
        file_path (str): Path to the file.
    """
    try:
        os.remove(file_path)
        logging.info(f"Removed file: {file_path}")
    except OSError as e:
        logging.warning(f"Failed to remove file {file_path}: {e}")

import os
import json
import math

def merge_tilesets_into_one(output_path, input_tilesets):
    """
    Merges multiple region-based tilesets into a single tileset.json that references all of them as external.
    If some tilesets do not exist or do not have a region boundingVolume, they are skipped.
    If no valid tilesets remain, creates a minimal tileset with no children.
    
    Args:
        output_path (str): Path to the final merged tileset.json output file.
        input_tilesets (list[str]): Paths to the input tileset.json files to merge.

    Returns:
        None. Writes the merged tileset.json to output_path.
    """
    
    # Load all valid tilesets
    loaded_tilesets = []
    for ts_path in input_tilesets:
        if not os.path.isfile(ts_path):
            # Skip if the file doesn't exist
            continue
        try:
            with open(ts_path, 'r', encoding='utf-8') as f:
                ts = json.load(f)
                loaded_tilesets.append((ts_path, ts))
        except (IOError, json.JSONDecodeError):
            # Skip if the file cannot be read or is not valid JSON
            continue
    
    # Filter down to only those with a region boundingVolume
    all_regions = []
    valid_tilesets = []
    for ts_path, ts in loaded_tilesets:
        root = ts.get("root", {})
        bv = root.get("boundingVolume", {})
        region = bv.get("region")
        
        if region and isinstance(region, list) and len(region) == 6:
            all_regions.append(region)
            valid_tilesets.append((ts_path, ts))
        # If there's no valid region, skip this tileset
    
    if not valid_tilesets:
        # No valid tilesets found, create an empty tileset
        # with a minimal boundingVolume and no children.
        # We'll use a generic region that covers no area.
        # For example, we can pick a degenerate region:
        degenerate_region = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        empty_tileset = {
            "asset": {
                "version": "1.1"
            },
            "geometricError": 0,
            "root": {
                "boundingVolume": {
                    "region": degenerate_region
                },
                "refine": "ADD",
                "geometricError": 0,
                "children": []
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(empty_tileset, f, indent=2)
        print(f"No valid tilesets found. Created an empty merged tileset at {output_path}")
        return
    
    # Compute the encompassing region for all valid tilesets
    west = min(r[0] for r in all_regions)
    south = min(r[1] for r in all_regions)
    east = max(r[2] for r in all_regions)
    north = max(r[3] for r in all_regions)
    minH = min(r[4] for r in all_regions)
    maxH = max(r[5] for r in all_regions)
    merged_region = [west, south, east, north, minH, maxH]

    # Construct children for the merged tileset
    children = []
    output_dir = os.path.dirname(os.path.abspath(output_path))
    for ts_path, ts in valid_tilesets:
        ts_abs = os.path.abspath(ts_path)
        rel_path = os.path.relpath(ts_abs, output_dir)
        
        child = {
            "boundingVolume": ts["root"]["boundingVolume"],
            "geometricError": ts["root"]["geometricError"],
            "refine": ts["root"].get("refine", "ADD").upper(),
            "content": {
                "uri": rel_path
            }
        }
        children.append(child)

    # Determine the maximum geometricError for the parent tileset
    parent_geometric_error = max(ts["root"]["geometricError"] for _, ts in valid_tilesets)
    
    # Create the merged tileset JSON structure
    merged_tileset = { 
        "asset": {
            "version": "1.1"
        },
        "geometricError": parent_geometric_error,
        "root": {
            "boundingVolume": {
                "region": merged_region
            },
            "refine": "ADD",
            "geometricError": parent_geometric_error,
            "children": children
        }
    }

    # Write the merged tileset to disk
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged_tileset, f, indent=2)
    print(f"Merged tileset written to {output_path}")

def ensure_main_table_exists(database_url, table_name):
    """
    Ensures that the main table exists in the database. Creates it if it does not exist.

    Args:
        database_url (str): PostgreSQL connection URL.
        table_name (str): Name of the main table.
    """
    logging.info(f"Ensuring main table '{table_name}' exists.")
    url = urlparse(database_url)
    conn = psycopg2.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    try:
        with conn.cursor() as cur:
            # Check if the table exists
            cur.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table_name}'
                );
            """)
            exists = cur.fetchone()[0]

            if not exists:
                logging.info(f"Table '{table_name}' does not exist. Creating it.")
                cur.execute(f"""
                    CREATE TABLE {table_name} (
                        gml_id VARCHAR PRIMARY KEY,
                        geom GEOMETRY(GEOMETRYZ, 4326),
                        attributes JSONB
                    );
                """)
                conn.commit()
                logging.info(f"Table '{table_name}' created successfully.")
            else:
                logging.info(f"Table '{table_name}' already exists.")
    except Exception as e:
        logging.error(f"Failed to ensure table '{table_name}' exists: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def main(meta4_file):
    # Ensure DATA_DIR and CACHE_DIR exist
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    # Ensure the main table exists
    ensure_main_table_exists(DATABASE_URL, MAIN_TABLE)
    # execute_sql_file(SQL_INDEX_PATH, DATABASE_URL)

    
    # Parse the Meta4 file
    files = parse_meta4(meta4_file)

    # Drop the temporary table
    drop_temp_table(DATABASE_URL, TEMP_TABLE)

    for ix, file_info in enumerate(files):
        
        # if ix < 130 * BATCH_N:
        #     continue
        
        file_name = file_info['name']
        size = file_info['size']
        hash_type = file_info['hash_type']
        hash_value = file_info['hash_value']
        urls = file_info['urls']

        logging.info(f"▶️   FILE {ix+1}/{len(files)}")
        logging.info(f"Processing file: {file_name}")


        temp_tileset_dir = os.path.join(CACHE_DIR, 'sub', str(ix // BATCH_N))  
        main_tileset_dir = CACHE_DIR
           
        os.makedirs(main_tileset_dir, exist_ok=True)   
        os.makedirs(temp_tileset_dir, exist_ok=True)

        # Determine download paths
        download_path = os.path.join(DATA_DIR, file_name)
        transformed_file_name = os.path.splitext(file_name)[0] + '_trs.gml'
        transformed_path = os.path.join(DATA_DIR, transformed_file_name)

        # Download the file from available URLs
        downloaded = False
        for url in urls:
            if download_file(url, download_path):
                # Verify the file
                if verify_file(download_path, size, hash_value, hash_type):
                    downloaded = True
                    break
                else:
                    logging.warning(f"Verification failed for {download_path}. Trying next URL.")
                    remove_file(download_path)
        if not downloaded:
            logging.error(f"Failed to download and verify {file_name} from all URLs. Skipping.")
            continue

        try:
            # Transform the GML file
            transform_gml(download_path, transformed_path)

            # Ingest the transformed GML into the temporary table
            ingest_gml_file(transformed_path, DATABASE_URL, TEMP_TABLE)

            # Update geometries in the temporary table
            update_geometries(DATABASE_URL, TEMP_TABLE)



            if ix % BATCH_N == 0 or ix == len(files) - 1:            
                # Convert the temporary table to 3D tiles
                convert_to_3d_tiles(temp_tileset_dir, DATABASE_URL, TEMP_TABLE)

                # Apply Draco compression to the newly generated tiles
                apply_draco_compression(temp_tileset_dir)

                # Append data from temporary table to main table
                append_temp_to_main(DATABASE_URL, TEMP_TABLE, MAIN_TABLE)

                # Drop the temporary table
                drop_temp_table(DATABASE_URL, TEMP_TABLE)

                batch_count = ix // BATCH_N + 1

                # Collect all input tileset.json paths
                input_tileset_paths = [
                    os.path.join(CACHE_DIR, 'sub', str(b), 'tileset.json')
                    for b in range(batch_count)
                ]

                merged_tileset_path = os.path.join(CACHE_DIR, 'tileset.json')

                logging.info(f"Merging {len(input_tileset_paths)} tilesets into {merged_tileset_path}...")

                try:
                    # Call our custom merging function
                    merge_tilesets_into_one(merged_tileset_path, input_tileset_paths)
                    logging.info("Merged tileset into main tileset successfully.")
                except Exception as e:
                    logging.error(f"Failed to combine merged tilesets: {e}")
                    raise RuntimeError(f"Failed to combine merged tilesets: {e}")

            # npx 3d-tiles-tools combine -i backend/tileset\ -o backend/tileset_combined -f

            if ix == 0:
                # Execute SQL indexing file once before processing
                execute_sql_file(SQL_INDEX_PATH, DATABASE_URL)
                
            # Remove the transformed GML file
            remove_file(transformed_path)
            # Remove the transformed GFS file if it exists
            transformed_gfs_path = os.path.splitext(transformed_path)[0] + ".gfs"
            if os.path.isfile(transformed_gfs_path):
                remove_file(transformed_gfs_path)

            # Optionally, remove the original downloaded GML file
            remove_file(download_path)

            logging.info(f"✅  Completed processing for {file_name}")

        except Exception as e:
            logging.error(f"An error occurred while processing {file_name}: {e}")
            # Optionally, clean up files or continue
            continue

    logging.info("🏁 All files processed.")

if __name__ == '__main__':
    meta4_file = META4_PATH
    if not os.path.isfile(meta4_file):
        logging.error(f"Meta4 file '{meta4_file}' does not exist.")
        sys.exit(1)
    main(meta4_file)
