from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from database import async_session, init_db
from models import Building
from typing import List
from sqlalchemy.future import select
from geoalchemy2.functions import ST_AsGeoJSON, ST_Intersects, ST_GeomFromGeoJSON
import json

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await init_db()

async def get_db():
    async with async_session() as session:
        yield session

@app.get("/")
async def read_root():
    return {"message": "Hello World"}

@app.post("/buildings")
async def get_buildings(geometry: dict, db: AsyncSession = Depends(get_db)):
    """
    Get buildings within the given boundary.

    :param geometry: GeoJSON geometry defining the boundary.
    """
    try:
        # Convert input geometry (GeoJSON) to a string
        geometry_geojson = json.dumps(geometry)

        # Create a geometry object from the GeoJSON
        geom = ST_GeomFromGeoJSON(geometry_geojson)

        # Build the query
        query = select(
            Building.id,
            ST_AsGeoJSON(Building.geom).label('geometry')
        ).where(
            ST_Intersects(Building.geom, geom)
        )

        # Execute the query
        result = await db.execute(query)
        buildings = result.fetchall()

        # Construct GeoJSON response
        features = []
        for building in buildings:
            feature = {
                "type": "Feature",
                "geometry": json.loads(building.geometry),
                "properties": {
                    "id": building.id
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

