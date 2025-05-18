# EasyOpenData Data Ingestion

## Overview

The `ingestion` directory contains scripts and resources for downloading, transforming, and ingesting 3D building data into a PostGIS database. It also includes tools for generating and optimizing 3D tilesets from the database.

---

## Setup Instructions

### Prerequisites

- **Conda** (optional, for managing Python environments)
- **GDAL** and **OGR** libraries
- **Python 3.x**
- **Node.js** and **npm** (for `gltf-pipeline` and other utilities)
- **PostgreSQL with PostGIS extension**

---

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
pip install -r backend/requirements.txt
```

#### 4. Install gltf-pipeline

```bash
npm install -g gltf-pipeline
```

#### 5. Set Up PostgreSQL Database

Ensure you have a PostgreSQL instance running with the PostGIS extension installed. Update the `DATABASE_URL` in the script to point to your database.

#### 6. Prepare Required Executables

- Place the `pg2b3dm` executable in the `libs/` directory.
- Ensure `ogr2ogr` is available in your system's `PATH`.

---

## Data Ingestion Script

### `process_meta4.py`

This script sequentially downloads GML files from a `.meta4` file, transforms them by embedding polygons into `surfaceMember` elements, ingests them into a PostgreSQL database using a temporary table, converts the data into 3D tiles, and merges them into a single tileset.

#### Workflow

1. **Parse Meta4**: Extract file metadata (URLs, hashes, etc.).
2. **Download**: Fetch files and verify size and hash integrity.
3. **Transform GML**: Embed referenced polygons into the GML structure.
4. **Ingest**: Load transformed data into a temporary PostgreSQL table.
5. **Update Geometries**: Align geometries to the ground level.
6. **Generate 3D Tiles**: Use `pg2b3dm` to create tilesets.
7. **Optimize with Draco Compression**: Compress `.glb` files to reduce size.
8. **Merge Tilesets**: Combine batch tilesets into a single `tileset.json`.
9. **Append Data**: Append data from the temporary table to the main table.
10. **Clean Up**: Remove processed files and drop temporary tables.

---

### Usage

```bash
python process_meta4.py file.meta4
```

#### Configuration Variables

- **`META4_PATH`**: Path to the `.meta4` file.
- **`DATABASE_URL`**: PostgreSQL connection string.
- **`CACHE_DIR`**: Directory for storing tileset outputs.
- **`DATA_DIR`**: Directory for storing temporary data files.
- **`TEMP_TABLE`**: Temporary table name.
- **`MAIN_TABLE`**: Main table name.

---

## Directory Structure

- **`data_sources/`**: Contains `.meta4` files listing URLs for GML data.
- **`data_local/`**: Directory for downloaded GML files.
- **`libs/`**: Contains utilities like `pg2b3dm`.
- **`tileset/`**: Directory for generated tilesets.

---

## Tools and Dependencies

- **GDAL/OGR**: Used for transforming and ingesting GML files.
- **PostGIS**: PostgreSQL extension for spatial data management.
- **pg2b3dm**: Converts PostGIS data to 3D tiles compatible with CesiumJS.
- **gltf-pipeline**: Optimizes and compresses 3D tiles with Draco compression.

---

## Performance Tips

- **Batch Size**: The `BATCH_N` parameter controls the number of GML files processed per batch. Adjust it based on available memory and performance needs.
- **Indexes**: Ensure database indexes are optimized for spatial operations by executing the provided `index.sql`.

---

## Troubleshooting
 
- **Failed Downloads**: Ensure URLs in the `.meta4` file are valid and reachable.
- **Database Errors**: Check that the database URL and permissions are correctly configured.
- **Script Errors**: Refer to the detailed logs for troubleshooting.
