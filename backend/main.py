# ./backend/main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from database import async_session, init_db
from models import Building
from sqlalchemy.future import select
from geoalchemy2.functions import ST_AsGeoJSON, ST_Intersects, ST_GeomFromEWKT
from fastapi.middleware.cors import CORSMiddleware
import json

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

@app.get("/buildings/nuremberg")
async def get_buildings_nuremberg(db: AsyncSession = Depends(get_db)):
    """
    Get buildings within the predefined boundary of Nürnberg.
    """
    try:
        # Define the bounding box for Nürnberg (approximate coordinates)
        nuremberg_bbox = 'POLYGON((11.0 49.4, 11.2 49.4, 11.2 49.6, 11.0 49.6, 11.0 49.4))'

        # Convert WKT polygon to geometry
        geometry = ST_GeomFromEWKT(f'SRID=4326;{nuremberg_bbox}')

        # Build the query
        query = select(
            Building.ogc_fid,
            Building.name,
            ST_AsGeoJSON(Building.geometry).label('geometry')
        ).where(
            Building.ogc_fid < 10000
        )
         #   ST_Intersects(Building.geometry, geometry)
        #)

        # Execute the query
        result = await db.execute(query)
        buildings = result.fetchall()
        #return json.dumps(len(buildings), indent=4)

        # Construct GeoJSON response
        features = []
        for building in buildings:
            feature = {
                "type": "Feature",
                "geometry": json.loads(building.geometry),
                "properties": {
                    "id": building.ogc_fid,
                    "name": building.name
                }
            }
            features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        return geojson

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
