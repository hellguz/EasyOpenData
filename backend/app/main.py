# ./backend/main.py

import asyncio
import tempfile
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session, init_db
from app.models import Building, RegionRequest
from app.retrieve_geom import retrieve_obj_file
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
    allow_origins=["http://localhost:5173"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    await init_db()

async def get_db():
    async with async_session() as session:
        yield session

@app.get("/")
async def read_root():
    return {"message": "Easy Open Data v1.0"}

@app.post("/retrieve_obj")
async def retrieve_obj(request: RegionRequest):
    print(f"Received region: {request.region}")

    try:
        temp_path = os.path.join("/temp", "34.obj")
        await retrieve_obj_file(request.region, temp_path)
        return FileResponse(
            temp_path,
            media_type="application/octet-stream",
            filename=f"object.txt")
    except Exception as e:
        logger.error(f"Error in retrieve_obj: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def remove_temp_file(file_path: str):
    await asyncio.sleep(0)  # Ensure this runs after the response is sent
    if os.path.exists(file_path):
        os.unlink(file_path)

        
app.mount("/cache", StaticFiles(directory="cache"), name="cache")
