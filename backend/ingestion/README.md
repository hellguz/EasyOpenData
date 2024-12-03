# EasyOpenData Data Ingestion

## Overview

The `ingestion` directory contains scripts and resources for downloading, transforming, and ingesting 3D building data into the PostGIS database. It also includes tools for generating 3D tilesets from the database.

---

## Setup Instructions

### Prerequisites

- **Conda** (optional, for managing Python environments)
- **GDAL** and **OGR** libraries
- **Python 3.x**
- **Node.js** and **npm** (for `gltf-pipeline`)

### Steps

#### 1. Create a Conda Environment (Optional)

```bash
conda create -n easyopendata_env python=3.10
conda activate easyopendata_env
```

#### 2. Install GDAL and Libraries

```bash
conda install -c conda-forge gdal libgdal
```

#### 3. Install Python Dependencies

```bash
pip install -r ../../requirements.txt
```

#### 4. Install gltf-pipeline

```bash
npm install -g gltf-pipeline
```

---

## Data Ingestion Scripts

### `bayern.py`

This script sequentially downloads GML files from a Meta4 file, transforms them by embedding polygons, ingests them into a PostgreSQL database, converts them to 3D tiles, and removes the original files.

#### Usage

```bash
python bayern.py
```

#### Notes

- Ensure that the `META4_PATH` variable in the script points to a valid `.meta4` file in the `data_sources/` directory.
- The script requires the `pg2b3dm.exe` executable to be present in the `libs/` directory.

### Directory Structure

- **data_sources/**: Contains `.meta4` files that list the URLs of GML data to download.
- **data_local/**: Directory where downloaded GML files are stored temporarily.
- **libs/**: Contains necessary executables like `pg2b3dm.exe`.

---

## Additional Information

- **GDAL/OGR**: Used for converting and ingesting GML files into PostGIS.
- **pg2b3dm**: Tool for converting PostGIS data into 3D tiles compatible with CesiumJS.
- **gltf-pipeline**: Used for optimizing and compressing glTF files.

---

## Tips

- **Error Handling**: The scripts include logging to help diagnose issues during the ingestion process.
- **Performance**: Adjust database settings in `init.sql` and `index.sql` for better performance during bulk data ingestion.

---

## Contributing

Contributions to improve data ingestion scripts are welcome. Please ensure that any new scripts or changes are well-documented and tested.

---

## License

This project is licensed under the MIT License.