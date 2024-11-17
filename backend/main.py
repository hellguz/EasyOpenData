# ./backend/main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from database import async_session, init_db
from models import Building
from sqlalchemy.future import select
from geoalchemy2.functions import ST_AsGeoJSON, ST_Intersects, ST_GeomFromText, ST_SimplifyPreserveTopology
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
import math
import redis  # Commented out Redis import

redis_client = redis.Redis(host='localhost', port=6379, db=0) 
# to run redis: docker run -d -p 6379:6379 redis  (NOTE FOR gpt: add it in README somewhere!)

app = FastAPI()

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

    return (lon_deg_min, lat_deg_min, lon_deg_max, lat_deg_max)

@app.get("/buildings/tiles/{z}/{x}/{y}")
async def get_buildings_tile(z: int, x: int, y: int, db: AsyncSession = Depends(get_db)):
    """
    Get buildings within the bounding box of a specific tile.
    """
    try:
        tile_key = f"{z}/{x}/{y}"
        cached_data = redis_client.get(tile_key)
        if cached_data and False:
            geojson = json.loads(cached_data)
            headers = {
                "Cache-Control": "public, max-age=86400"
            }
            return JSONResponse(content=geojson, headers=headers)

        # Calculate bounding box for the tile
        bbox = tile_bbox(x, y, z)
        bbox_wkt = f'POLYGON(({bbox[0]} {bbox[1]}, {bbox[0]} {bbox[3]}, {bbox[2]} {bbox[3]}, {bbox[2]} {bbox[1]}, {bbox[0]} {bbox[1]}))'

        # Determine simplification tolerance based on zoom level
        tolerance = get_simplification_tolerance(z)

        # Query buildings within the bounding box with simplification
        query = select(
            Building.ogc_fid,
            Building.name,
            ST_AsGeoJSON(ST_SimplifyPreserveTopology(Building.geometry, tolerance)).label('geometry')
        ).where(
            ST_Intersects(Building.geometry, ST_GeomFromText(bbox_wkt, 4326))
        )

        result = await db.execute(query)
        buildings = result.fetchall()

        # Construct GeoJSON FeatureCollection
        features = []
        for building in buildings:
            geometry = json.loads(building.geometry)
            feature = {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "id": building.ogc_fid,
                    "name": building.name,
                    "height": calculate_building_height(geometry)  # Function to calculate height
                }
            }
            features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        headers = {
            "Cache-Control": "public, max-age=86400"  # Cache for 1 day
        }

        # # After generating geojson
        redis_client.set(tile_key, json.dumps(geojson), ex=86400)  # Cache for 1 day

        return JSONResponse(content=geojson, headers=headers)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
