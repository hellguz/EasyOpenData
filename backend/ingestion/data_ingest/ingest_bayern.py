import os
import glob
import subprocess
import psycopg2
from urllib.parse import urlparse

DATA_DIR = 'backend/ingestion/data_local/bayern'
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:barcelona@localhost:5432/easyopendata_database')

def ingest_gml_files():
    gml_files = glob.glob(os.path.join(DATA_DIR, '*.gml'))
    for gml_file in gml_files:
        cmd = [
            'ogr2ogr',
            '-f', 'PostgreSQL',
            '-overwrite',
            '-progress',
            '-lco', 'GEOMETRY_NAME=geom',
            '-skipfailures',
            '-nlt', 'MULTIPOLYGON',
            '-dim', 'XYZ',
            '-s_srs', 'EPSG:25832',
            '-t_srs', 'EPSG:4326',
            DATABASE_URL,
            gml_file
        ]
        subprocess.run(cmd)

    

def put_buildings_on_ground():
    # Parse the DATABASE_URL to get connection parameters
    url = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    
    with conn.cursor() as cur:
        # Update the geometries to put them on ground level
        cur.execute("""
            UPDATE building
            SET geom = ST_Translate(geom, 0, 0, -ST_ZMin(geom))
            WHERE ST_ZMin(geom) != 0;
        """)
        
        conn.commit()
    
    conn.close()

if __name__ == '__main__':
    ingest_gml_files()
    put_buildings_on_ground()

