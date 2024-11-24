# ./backend/main.py

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session, init_db
from app.models import Building
from sqlalchemy.future import select
from geoalchemy2.functions import ST_AsGeoJSON, ST_Intersects, ST_GeomFromText, ST_SimplifyPreserveTopology
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import json
import math
import redis
import subprocess
import os
import logging
from fastapi.staticfiles import StaticFiles

import shutil

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Initialize Redis client
redis_client = redis.Redis(host='localhost', port=6379, db=0) 

# Configure CORS
origins = [
    "http://localhost:5173",  # Frontend origin
    # Add other origins if needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allowed origins
    allow_credentials=True,
    allow_methods=["*"],    # Allow all HTTP methods
    allow_headers=["*"],    # Allow all headers
)

@app.on_event("startup")
async def on_startup():
    await init_db()

async def get_db():
    async with async_session() as session:
        yield session

@app.get("/")
async def read_root():
    return {"message": "Hello World"}

# Utility function to calculate tile bounding box
def tile_bbox(x: int, y: int, z: int):
    """
    Calculate the bounding box for a given tile in EPSG:4326.

    Args:
        x (int): Tile X coordinate.
        y (int): Tile Y coordinate.
        z (int): Zoom level.

    Returns:
        tuple: (min_lon, min_lat, max_lon, max_lat)
    """
    n = 2.0 ** z
    lon_deg_min = x / n * 360.0 - 180.0
    lat_rad_min = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_deg_min = math.degrees(lat_rad_min)

    lon_deg_max = (x + 1) / n * 360.0 - 180.0
    lat_rad_max = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
    lat_deg_max = math.degrees(lat_rad_max)

    logger.debug(f"tile_bbox({z}, {x}, {y}) = ({lon_deg_min}, {lat_deg_min}, {lon_deg_max}, {lat_deg_max})")
    
    return (lon_deg_min, lat_deg_min, lon_deg_max, lat_deg_max)

app.mount("/cache", StaticFiles(directory="cache"), name="cache")

@app.get("/buildings/tiles/{z}/{x}/{y}.b3dm")
async def get_buildings_tile(z: int, x: int, y: int, db: AsyncSession = Depends(get_db)):
    tile_key = f"{z}/{x}/{y}"
    output_dir = f"./cache/tiles/{tile_key}"
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "C:\\PostgreSQL\\pg2b3dm\\pg2b3dm.exe",
        "-h", "localhost",
        "-U", "postgres",
        "-d", "easyopendata_database",
        "-t", "building",
        "-c", "geometry",
        "-a", "gml_id",
        "-o", output_dir,
        # "-q", query_str,  # Uncomment and modify if using spatial filtering
    ]

    env = os.environ.copy()
    env['PGPASSWORD'] = 'barcelona'  # Replace with your actual password

    logger.info(f"Running pg2b3dm command for tile {tile_key}: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, env=env)
    except FileNotFoundError:
        logger.error("pg2b3dm executable not found.")
        raise HTTPException(status_code=500, detail="pg2b3dm executable not found.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error generating tile {tile_key}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating tile: {str(e)}")

    # Adjust the tile path as per pg2b3dm output
    tile_path = f"{output_dir}/tiles/0/0/0.b3dm"
    if os.path.exists(tile_path):
        logger.info(f"Tile {tile_key} generated and cached at {tile_path}")
        return FileResponse(tile_path, media_type="application/octet-stream")
    else:
        logger.error(f"Tile not found after generation: {tile_path}")
        raise HTTPException(status_code=404, detail="Tile not found after generation")
    