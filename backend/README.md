# EasyOpenData Backend

## Overview

The backend of EasyOpenData is a FastAPI application that serves as the core of the platform, handling data retrieval, processing, and API endpoints for the frontend application. It interacts with a PostGIS database to store and query spatial data.

---

## Key Components

- **FastAPI Application**: Provides RESTful APIs for data retrieval and processing.
- **PostGIS Database**: Stores spatial data and provides efficient spatial queries.
- **Data Ingestion Scripts**: Scripts to download, transform, and ingest data into the database.
- **Payment Processing**: Integration with Stripe API for handling payments.

---

## Setup Instructions

### Prerequisites

- **Docker** and **Docker Compose**
- **Python 3.10+**
- **GDAL** and **OGR** libraries
- **Conda** (optional, for managing environments)
- **Node.js** and **npm** (for gltf-pipeline)

### Running with Docker

The easiest way to run the backend is using Docker Compose.

#### Build and Run

```bash
docker-compose up --build
```

This will start the PostGIS database and the FastAPI backend.

#### Accessing the Backend API

- The backend API will be available at: [http://localhost:5400](http://localhost:5400)

### Manual Setup

If you prefer to run the backend without Docker, follow these steps.

#### 1. Create a Virtual Environment

Using Conda:

```bash
conda create -n easyopendata_env python=3.10
conda activate easyopendata_env
```

#### 2. Install Dependencies

Install GDAL and its libraries:

```bash
conda install -c conda-forge gdal libgdal
```

Install other dependencies:

```bash
pip install -r backend/requirements.txt
```

#### 3. Install gltf-pipeline

```bash
npm install -g gltf-pipeline
```

#### 4. Setup the Database

Ensure PostgreSQL and PostGIS are installed.

```bash
sudo apt install postgresql postgis
```

Create the database and extensions:

```sql
CREATE DATABASE easyopendata_database;
\c easyopendata_database;
CREATE EXTENSION postgis;
```

#### 5. Run Database Initialization Scripts

```bash
psql -U postgres -d easyopendata_database -f backend/db/init.sql
```

#### 6. Run the FastAPI Application

```bash
cd backend
uvicorn app.main:app --reload
```

---

## Data Ingestion

The `backend/ingestion` directory contains scripts to download and process data.

### Ingesting Data

1. **Navigate to the ingestion directory**

```bash
cd backend/ingestion
```

2. **Run the Ingestion Script**

The `bayern.py` script processes Meta4 files to download and ingest data.

```bash
python bayern.py
```

**Note**: Ensure you have the necessary Meta4 files in `data_sources/` and that you have adjusted the `META4_PATH` in the script.

### Requirements

- **lxml**
- **psycopg2**
- **GDAL/OGR** command-line tools (`ogr2ogr`)
- **pg2b3dm** executable (must be in `libs/`)

---

## Directory Structure

- **app/**: FastAPI application code.
  - `main.py`: Main application file.
  - `database.py`: Database connection setup.
  - `models.py`: Database models and Pydantic schemas.
  - `retrieve_geom.py`: Functions to retrieve and process geometries.

- **db/**: Database scripts.
  - `init.sql`: Database initialization script.
  - `index.sql`: Indexing script for the database.

- **ingestion/**: Data ingestion scripts.
  - `bayern.py`: Script to process and ingest data.
  - `data_sources/`: Directory containing Meta4 files.
  - `data_local/`: Directory where downloaded data will be stored.
  - `libs/`: Contains necessary executables like `pg2b3dm.exe`.

---

## API Endpoints

- **GET /**: Root endpoint to check if the backend is running.
- **POST /retrieve_obj**: Accepts a GeoJSON region and returns an OBJ file with the buildings within that region.
- **POST /create-payment-intent**: Creates a Stripe payment intent for processing payments.

---

## Environment Variables

- **DATABASE_URL**: The connection string for the PostGIS database.
- **STRIPE_API_KEY**: Your Stripe secret API key for payment processing.

---

## Payment Processing

The backend integrates with Stripe to handle payments. Ensure you have set your Stripe API keys in the environment variables.

---

## Contributing

Contributions are welcome! Please ensure any changes to the backend code are thoroughly tested.

---

## License

This project is licensed under the MIT License.