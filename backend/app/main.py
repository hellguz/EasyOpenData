# ./backend/main.py

import asyncio
import tempfile
from typing import List
from urllib import request
import uuid
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import stripe
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


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://easyopen.i-am-hellguz.uk", "https://easyopen-server.i-am-hellguz.uk"], 
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
        # Generate a unique filename using UUID
        random_filename = f"{uuid.uuid4()}.obj"
        temp_path = os.path.join("/data/tempfiles", random_filename)
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

        
stripe.api_key = 'REMOVED_STRIPE_KEY'


def calculate_order_amount(amount: float):
    # Replace this constant with a calculation of the order's amount
    # Calculate the order total on the server to prevent
    # people from directly manipulating the amount on the client
    return int(amount*100)

class PaymentIntentRequest(BaseModel): 
    amount: float

@app.post("/create-payment-intent")
async def create_payment_intent(data: PaymentIntentRequest):
    try:
        intent = stripe.PaymentIntent.create(
            amount=calculate_order_amount(data.amount),  # Amount in cents
            currency="eur",
            automatic_payment_methods={"enabled": True},
        )
        return {"clientSecret": intent.client_secret}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
app.mount("/tileset", StaticFiles(directory="../data/tileset"), name="tileset")
