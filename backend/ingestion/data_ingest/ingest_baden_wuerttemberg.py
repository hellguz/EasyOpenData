import os
import glob
import subprocess

DATA_DIR = 'data_local/baden_wuerttemberg'
DATABASE_URL = os.getenv('DATABASE_URL', 'PG:dbname=your_db user=your_user password=your_pass')

def ingest_gml_files():
    gml_files = glob.glob(os.path.join(DATA_DIR, '*.gml'))
    for gml_file in gml_files:
        cmd = [
            'ogr2ogr',
            '-f', 'PostgreSQL',
            '-overwrite',
            '-progress',
            DATABASE_URL,
            gml_file
        ]
        subprocess.run(cmd)

if __name__ == '__main__':
    ingest_gml_files()

