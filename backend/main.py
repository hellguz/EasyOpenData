# ./backend/main.py

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from database import async_session, init_db
from models import Building
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
import shutil

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Initialize Redis client
redis_client = redis.Redis(host='localhost', port=6379, db=0) 

# Configure CORS
origins = [
    "http://localhost:8080",  # Frontend origin
    # Add other origins if needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allowed origins
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

@app.get("/buildings/tiles/{z}/{x}/{y}")
async def get_buildings_tile(z: int, x: int, y: int, db: AsyncSession = Depends(get_db)):
    """
    Get buildings within the bounding box of a specific tile.
    Serve as 3D tiles (b3dm format).
    """
    tile_key = f"{z}/{x}/{y}"
    cached_data = redis_client.get(tile_key)
    if cached_data and False:
        # Serve cached b3dm tile
        tile_path = f"./cache/tiles/{tile_key}.b3dm"
        if os.path.exists(tile_path):
            logger.info(f"Serving cached tile: {tile_path}")
            return FileResponse(tile_path, media_type="application/octet-stream")
        else:
            logger.warning(f"Tile key found in Redis but file does not exist: {tile_path}. Deleting cache key.")
            redis_client.delete(tile_key)

    # Calculate bounding box for the tile
    bbox = tile_bbox(x, y, z)
    min_lon, min_lat, max_lon, max_lat = bbox

    # Validate bounding box
    if min_lon == max_lon or min_lat == max_lat:
        logger.error(f"Invalid bounding box for tile {tile_key}: {bbox}")
        raise HTTPException(status_code=400, detail="Invalid tile coordinates resulting in zero area bounding box.")

    bbox_wkt = f'POLYGON(({min_lon} {min_lat}, {min_lon} {max_lat}, {max_lon} {max_lat}, {max_lon} {min_lat}, {min_lon} {min_lat}))'
    logger.info(f"Tile {tile_key} WKT: {bbox_wkt}")


    # Query buildings within the bounding box with simplification
    # query = select(
    #     Building.ogc_fid,
    #     Building.name,
    #     ST_AsGeoJSON(ST_SimplifyPreserveTopology(Building.geometry, tolerance)).label('geometry')
    # ).where(
    #     ST_Intersects(Building.geometry, ST_GeomFromText(bbox_wkt, 4326))
    # )

    # result = await db.execute(query)
    # buildings = result.fetchall()
    # logger.info(f"Fetched {len(buildings)} buildings for tile {tile_key}")

    # # Construct GeoJSON FeatureCollection
    # features = []
    # for building in buildings:
    #     geometry = json.loads(building.geometry)
    #     feature = {
    #         "type": "Feature",
    #         "geometry": geometry,
    #         "properties": {
    #             "id": building.ogc_fid,
    #             "name": building.name,
    #             "height": calculate_building_height(geometry)  # Function to calculate height
    #         }
    #     }
    #     features.append(feature)

    # geojson = {
    #     "type": "FeatureCollection",
    #     "features": features
    # }

    # # Save GeoJSON to a temporary file (optional, if needed for pg2b3dm)
    # geojson_path = f"./temp/{tile_key}.geojson"
    # os.makedirs(os.path.dirname(geojson_path), exist_ok=True)
    # with open(geojson_path, 'w') as f:
    #     json.dump(geojson, f)

    # Set up the output directory for tiles
    output_dir = f"./cache/tiles/{tile_key}"
    os.makedirs(output_dir, exist_ok=True)

            # Run pg2b3dm to generate the tile using --query instead of --bbox
    # Remove --bbox and --tileidcolumn, use --query for spatial filtering
    query_str = f"SELECT * FROM building WHERE ST_Intersects(geometry, ST_GeomFromText('{bbox_wkt}', 4326))"

    cmd = [
        "C:\PostgreSQL\pg2b3dm\pg2b3dm.exe",
        "-h", "localhost",
        #"-p", "5432",
        "-U", "postgres",
        "-d", "easyopendata_database",
        "-t", "building",
        "-c", "geometry",
        "-a", "gml_id",
        "-o", output_dir,
        #"-q", query_str,
    ]

    # Set environment variables for pg2b3dm (if needed)
    env = os.environ.copy()
    env['PGPASSWORD'] = 'barcelona'  # Replace with your actual password

    logger.info(f"Running pg2b3dm command for tile {tile_key}: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, env=env)
    except FileNotFoundError:
        logger.error("pg2b3dm executable not found. Please ensure it is installed and in the system PATH.")
        raise HTTPException(status_code=500, detail="pg2b3dm executable not found.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error generating tile {tile_key}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating tile: {str(e)}")

    # Check if the tile was generated
    tile_path = f"{output_dir}/tiles/0/0/0.b3dm"
    if os.path.exists(tile_path):
        # Cache the tile path in Redis
        redis_client.set(tile_key, tile_path, ex=86400)  # Cache for 1 day
        logger.info(f"Tile {tile_key} generated and cached at {tile_path}")
        return FileResponse(tile_path, media_type="application/octet-stream")
    else:
        logger.error(f"Tile not found after generation: {tile_path}")
        raise HTTPException(status_code=404, detail="Tile not found after generation")


    def get_simplification_tolerance(z: int):
        """Determine simplification tolerance based on zoom level."""
        if z < 10:
            return 0.01
        elif z < 14:
            return 0.005
        else:
            return 0.001

    def calculate_building_height(geometry_geojson):
        """
        Calculate the height of a building from its geometry.

        Args:
            geometry_geojson (dict): GeoJSON geometry.

        Returns:
            float: Height in meters.
        """
        # Assuming geometry is a MultiPolygonZ or PolygonZ
        # Extract Z values and calculate height
        z_values = []
        if geometry_geojson['type'] == 'MultiPolygon':
            for polygon in geometry_geojson['coordinates']:
                for ring in polygon:
                    for coord in ring:
                        if len(coord) == 3:
                            z_values.append(coord[2])
        elif geometry_geojson['type'] == 'Polygon':
            for ring in geometry_geojson['coordinates']:
                for coord in ring:
                    if len(coord) == 3:
                        z_values.append(coord[2])

        if z_values:
            return max(z_values) - min(z_values)
        else:
            return 30.0  # Default height if Z is not available
