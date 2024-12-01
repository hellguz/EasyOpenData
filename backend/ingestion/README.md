These scripts can be executed to download 3D Bulidings data from gml files, ingest them in the database, and create a Tileset of 3D Tiles from the database.

Before you run the scripts:

1. Create a conda environment in the root project folder (EasyOpenData):
...
2. activate the new environment:
...
3. Install GDAL with libraries:
conda install -c conda-forge gdal libgdal 
3. Install all other dependencies:
pip install -r .\backend\requirements.txt
4. Install gltf-pipeline:
npm install -g gltf-pipeline
