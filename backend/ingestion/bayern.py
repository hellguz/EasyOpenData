#!/usr/bin/env python3
"""
process_meta4.py

A script to sequentially download GML files from a Meta4 file, transform them by embedding polygons,
ingest them into a PostgreSQL database, convert them to 3D tiles, and remove the original files.

Usage:
    python process_meta4.py file.meta4

Requirements:
    - Python 3.x
    - lxml
    - psycopg2
    - ogr2ogr (from GDAL)
    - pg2b3dm_new command available in PATH
"""

import sys
import os
import glob
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
META4_PATH = 'backend/ingestion/data_sources/bamberg.meta4'
DATA_DIR = 'backend/ingestion/data_local/bayern'
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:barcelona@localhost:5432/easyopendata_database')
CACHE_DIR = 'backend/tileset'

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
    print(f"Parsing input GML file: {input_file}")
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(input_file, parser)
    root = tree.getroot()

    # Extract all namespaces
    namespaces = get_all_namespaces(tree)
    # print("Namespaces detected:")
    # for prefix, uri in namespaces.items():
    #     print(f"  Prefix: '{prefix}' => URI: '{uri}'")

    # Build a dictionary of gml:id to Polygon elements for quick lookup
    print("Indexing all <gml:Polygon> elements by gml:id...")
    polygon_dict = {}
    for polygon in root.xpath('.//gml:Polygon', namespaces=namespaces):
        polygon_id = polygon.get('{http://www.opengis.net/gml}id')
        if polygon_id:
            polygon_dict[polygon_id] = polygon
    print(f"Indexed {len(polygon_dict)} polygons.")

    # Find all <gml:surfaceMember> elements with xlink:href
    print("Finding all <gml:surfaceMember> elements with xlink:href...")
    surface_members = root.xpath('.//gml:surfaceMember[@xlink:href]', namespaces=namespaces)
    print(f"Found {len(surface_members)} <gml:surfaceMember> elements with xlink:href.")

    for sm in surface_members:
        href = sm.get('{http://www.w3.org/1999/xlink}href')
        if not href:
            continue
        # Extract the referenced polygon ID (remove the '#' prefix)
        polygon_id = href.lstrip('#')
        # print(f"Processing surfaceMember referencing Polygon ID: {polygon_id}")
        polygon = polygon_dict.get(polygon_id)
        if not polygon:
            print(f"Warning: Polygon with gml:id='{polygon_id}' not found. Skipping.")
            continue
        # Deep copy the polygon element
        polygon_copy = etree.fromstring(etree.tostring(polygon))
        # Remove any existing 'gml:id' to avoid duplicate IDs
        polygon_copy.attrib.pop('{http://www.opengis.net/gml}id', None)
        # Replace the surfaceMember's xlink:href attribute with the actual Polygon
        sm.clear()  # Remove existing children and attributes
        sm.append(polygon_copy)
        # print(f"Embedded Polygon ID: {polygon_id} into surfaceMember.")

    # Optionally, remove standalone <gml:Polygon> elements that were referenced
    # print("Removing standalone <gml:Polygon> elements that were referenced...")
    # removed_count = 0
    # for polygon_id in polygon_dict.keys():
    #     # Find and remove the standalone polygon
    #     polygons_to_remove = root.xpath(f'.//gml:Polygon[@gml:id="{polygon_id}"]', namespaces=namespaces)
    #     for polygon in polygons_to_remove:
    #         parent = polygon.getparent()
    #         if parent is not None:
    #             parent.remove(polygon)
    #             removed_count += 1
    #             print(f"Removed standalone Polygon ID: {polygon_id}.")
    # print(f"Removed {removed_count} standalone polygons.")

    # Write the transformed GML to the output file
    print(f"Writing transformed GML to: {output_file}")
    tree.write(output_file, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    print("Transformation complete.")
def ingest_gml_file(gml_file, database_url):
    """
    Ingests a GML file into a PostgreSQL database using ogr2ogr.

    Args:
        gml_file (str): Path to the GML file.
        database_url (str): PostgreSQL connection URL.
    """
    logging.info(f"Ingesting GML file into database: {gml_file}")
    cmd = [
        'ogr2ogr',
        '-f', 'PostgreSQL',
        # '-overwrite',
        '-progress',
        '-lco', 'GEOMETRY_NAME=geom',
        '-skipfailures',
        '-nlt', 'MULTIPOLYGON',
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
    logging.info(f"Ingested {gml_file} into database successfully.")

def put_buildings_on_ground(database_url):
    """
    Updates the geometries in the 'building' table to put them on ground level.

    Args:
        database_url (str): PostgreSQL connection URL.
    """
    logging.info("Updating building geometries to ground level.")
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
            cur.execute("""
                UPDATE building
                SET geom = ST_Translate(geom, 0, 0, -ST_ZMin(geom))
                WHERE ST_ZMin(geom) != 0;
            """)
            conn.commit()
            logging.info("Building geometries updated successfully.")
    except Exception as e:
        logging.error(f"Failed to update building geometries: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def convert_to_3d_tiles(cache_dir, database_url):
    """
    Converts buildings from the database to 3D tiles using pg2b3dm_new.

    Args:
        cache_dir (str): Output directory for 3D tiles.
        database_url (str): PostgreSQL connection URL.
    """
    logging.info("Converting buildings to 3D tiles with pg2b3dm_new.")
    # Parse the database URL for parameters
    url = urlparse(database_url)
    dbname = url.path[1:]
    user = url.username
    host = url.hostname or 'localhost'
    # Assume password is handled via environment or .pgpass
    cmd = [
        'pg2b3dm',
        '-h', host,
        '-U', user,
        '-c', 'geom',
        '-t', 'building',
        '-d', dbname,
        '-o', cache_dir, 
        '--use_implicit_tiling', 'false'
    ]
    # To handle password, set PGPASSWORD environment variable if available
    env = os.environ.copy()
    if url.password:
        env['PGPASSWORD'] = url.password
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    if result.returncode != 0:
        logging.error(f"pg2b3dm_new failed: {result.stderr}")
        raise RuntimeError(f"pg2b3dm_new failed: {result.stderr}")
    logging.info("3D tiles generated successfully.")

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

def main(meta4_file):
    # Ensure DATA_DIR exists
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Parse the Meta4 file
    files = parse_meta4(meta4_file)

    for file_info in files:
        file_name = file_info['name']
        size = file_info['size']
        hash_type = file_info['hash_type']
        hash_value = file_info['hash_value']
        urls = file_info['urls']

        logging.info(f"Processing file: {file_name}")

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

            # Ingest the transformed GML into the database
            ingest_gml_file(transformed_path, DATABASE_URL)

            # Update building geometries
            put_buildings_on_ground(DATABASE_URL)

            # Convert to 3D tiles
            convert_to_3d_tiles(CACHE_DIR, DATABASE_URL)

            # Remove the transformed GML file
            remove_file(transformed_path)
            # Remove the transformed GFS file
            remove_file(transformed_path.split(".")[0] + ".gfs")

            # Optionally, remove the original downloaded GML file
            remove_file(download_path)

            logging.info(f"Completed processing for {file_name}")

        except Exception as e:
            logging.error(f"An error occurred while processing {file_name}: {e}")
            # Optionally, clean up files or continue
            continue

    logging.info("All files processed.")

if __name__ == '__main__':
    meta4_file = META4_PATH
    if not os.path.isfile(meta4_file):
        logging.error(f"Meta4 file '{meta4_file}' does not exist.")
        sys.exit(1)
    main(meta4_file)
