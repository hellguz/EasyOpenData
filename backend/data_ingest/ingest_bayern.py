import os
import glob
import subprocess

DATA_DIR = 'backend/data_local/bayern'
DATABASE_URL = os.getenv('DATABASE_URL', 'PG:dbname=easyopendata_database user=postgres password=barcelona')

def ingest_gml_files():
    gml_files = glob.glob(os.path.join(DATA_DIR, '*.gml'))
    for gml_file in gml_files:
        cmd = [
            'ogr2ogr',
            '-f', 'PostgreSQL',
            '-overwrite',
            '-progress',
            '-lco', 'GEOMETRY_NAME=geometry',
            '-skipfailures',
            '-nlt', 'CONVERT_TO_LINEAR',
            '-nlt', 'MULTIPOLYGON',
            '-s_srs', 'EPSG:25832',
            '-t_srs', 'EPSG:4326',
            DATABASE_URL,
            gml_file
        ]
        subprocess.run(cmd)

if __name__ == '__main__':
    ingest_gml_files()


