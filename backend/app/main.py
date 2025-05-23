# ./backend/main.py

import asyncio
import sys  # For logging configuration
import tempfile
from typing import List
from urllib import request
import uuid
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    BackgroundTasks,
)  # Added BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import stripe
from app.database import async_session, init_db
from app.models import Building, RegionRequest
from app.retrieve_geom import retrieve_obj_file
from sqlalchemy.future import select
from geoalchemy2.functions import (
    ST_AsGeoJSON,
    ST_Intersects,
    ST_GeomFromText,
    ST_SimplifyPreserveTopology,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import json
import math

# import redis # Not used
# import subprocess # Not used
import os
import logging
from fastapi.staticfiles import StaticFiles

# import shutil # os.unlink is sufficient

# Configure Logging
log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()  # Default to INFO
logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, log_level_name, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="EasyOpenData Backend API")

# Stripe API Key Initialization (done in on_startup)
# stripe.api_key = os.getenv('STRIPE_SECRET_KEY') # Moved to on_startup


# CORS Configuration
environment = os.getenv("ENVIRONMENT", "production")  # Default to production
frontend_url = os.getenv(
    "FRONTEND_URL", "http://localhost:5173"
)  # Default for dev if not set
vite_base_url_from_env = os.getenv(
    "VITE_BASE_URL"
)  # This is likely the backend's own URL for frontend, or frontend's deployed URL

# Define allowed origins based on environment
if environment == "development":
    # For dev, allow localhost with the typical dev frontend port, and potentially the configured FRONTEND_URL
    # The VITE_BASE_URL in .env is the *backend's* deployed URL, which the frontend uses to call the backend.
    # The FRONTEND_URL in .env is the *frontend's* deployed URL.
    # For CORS on the backend, we need to allow origins from where the frontend is served.
    dev_frontend_port = os.getenv(
        "DEV_FRONTEND_PORT", "5173"
    )  # Get from dev compose or default
    allowed_origins = [
        f"http://localhost:{dev_frontend_port}",
        f"http://127.0.0.1:{dev_frontend_port}",
        # If FRONTEND_URL is set and points to a dev instance, add it
    ]
    if frontend_url and "localhost" not in frontend_url:  # Avoid duplicate localhost
        allowed_origins.append(frontend_url)
    logger.info(f"CORS allowed origins for DEVELOPMENT: {allowed_origins}")
else:  # Production
    allowed_origins = []
    if frontend_url:  # This should be the production frontend URL
        allowed_origins.append(frontend_url)
    # If VITE_BASE_URL is meant to be a frontend origin (unlikely, usually backend's own base), add it.
    # It's more common that FRONTEND_URL is the one we need for CORS.
    # Example: ["https://easyopen.i-am-hellguz.uk"]
    if not allowed_origins:  # Fallback if FRONTEND_URL was not set for prod
        logger.warning(
            "Production FRONTEND_URL not set for CORS, this might cause issues."
        )
        # Add a placeholder or raise an error if critical
    logger.info(f"CORS allowed origins for PRODUCTION: {allowed_origins}")


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(set(allowed_origins)),  # Use set to remove duplicates
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    logger.info("Application starting up...")
    await init_db()
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        logger.warning(
            "STRIPE_SECRET_KEY environment variable is not set. Payment functionality will be disabled."
        )
    else:
        logger.info("Stripe API key configured.")

    # Ensure tempfiles directory exists (using the path from docker-compose volume)
    temp_dir = "/data/tempfiles"
    try:
        os.makedirs(temp_dir, exist_ok=True)
        logger.info(f"Temporary files directory '{temp_dir}' is ready.")
    except OSError as e:
        logger.error(f"Could not create or access temp directory '{temp_dir}': {e}")


async def get_db():  # Keep simple name as it's common FastAPI pattern
    async with async_session() as session:
        yield session


@app.get("/")
async def read_root():
    return {"message": "Easy Open Data Backend v1.0"}


async def _background_remove_temp_file(file_path: str):  # Helper for background task
    """Safely removes a file in the background."""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.info(f"Background task: Successfully removed temp file: {file_path}")
        # else:
        # logger.debug(f"Background task: Temp file not found for removal (already deleted?): {file_path}")
    except Exception as e:
        logger.error(
            f"Background task: Error removing temp file {file_path}: {str(e)}",
            exc_info=True,
        )


@app.post("/retrieve_obj")
async def retrieve_obj(
    request: RegionRequest, background_tasks: BackgroundTasks
):  # Added BackgroundTasks
    logger.info(
        f"Received /retrieve_obj request."
    )  # Avoid logging request body for PII/size
    temp_file_path = None
    try:
        random_filename = f"{uuid.uuid4()}.obj"
        # Path corresponds to the volume mount in docker-compose.yml for easyopen_backend
        temp_dir_path = "/data/tempfiles"

        if not os.path.isdir(temp_dir_path):  # Make sure it exists
            logger.error(
                f"Temp directory '{temp_dir_path}' does not exist. Check volume mounts."
            )
            raise HTTPException(
                status_code=500,
                detail="Server-side temporary storage misconfiguration.",
            )

        temp_file_path = os.path.join(temp_dir_path, random_filename)

        await retrieve_obj_file(
            request.region, temp_file_path
        )  # Assumes retrieve_obj_file handles its own DB session
        logger.info(f"OBJ file generated at: {temp_file_path}")

        # Schedule the temp file for deletion AFTER the response is sent
        # background_tasks.add_task(_background_remove_temp_file, temp_file_path)

        return FileResponse(
            temp_file_path,
            media_type="application/octet-stream",
            filename=f"easyopendata_export_{uuid.uuid4().hex[:6]}.obj",  # Shorter unique part
        )
    except ValueError as ve:  # Specific error from retrieve_obj_file
        logger.warning(f"Value error during OBJ retrieval: {str(ve)}")
        if temp_file_path and os.path.exists(temp_file_path):
            background_tasks.add_task(
                _background_remove_temp_file, temp_file_path
            )  # Cleanup if created
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"General error in /retrieve_obj: {str(e)}", exc_info=True)
        if temp_file_path and os.path.exists(temp_file_path):
            background_tasks.add_task(
                _background_remove_temp_file, temp_file_path
            )  # Cleanup if created
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing your request.",
        )


# Removed original `async def remove_temp_file(file_path: str):` as it's replaced by the background task


def _calculate_order_amount_cents(amount_euros: float) -> int:  # Internal helper
    """Converts amount from euros to cents, ensuring integer."""
    return int(round(amount_euros * 100))


class PaymentIntentRequest(BaseModel):
    amount: float  # Amount in Euros, e.g., 10.50 for €10.50


@app.post("/create-payment-intent")
async def create_payment_intent(data: PaymentIntentRequest):
    if not stripe.api_key:
        logger.error("Stripe API key not set. Cannot create payment intent.")
        raise HTTPException(
            status_code=503, detail="Payment processing is currently unavailable."
        )

    if data.amount <= 0:
        logger.warning(f"Invalid payment amount received: {data.amount}")
        raise HTTPException(
            status_code=400, detail="Payment amount must be a positive value."
        )

    amount_in_cents = _calculate_order_amount_cents(data.amount)
    logger.info(
        f"Creating payment intent for {data.amount:.2f} EUR ({amount_in_cents} cents)."
    )
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_in_cents,
            currency="eur",
            automatic_payment_methods={"enabled": True},
        )
        return {"clientSecret": intent.client_secret}
    except stripe.error.StripeError as se:
        logger.error(f"Stripe API error: {str(se)}", exc_info=True)
        # Provide a user-friendly message if available from Stripe, otherwise a generic one.
        user_msg = getattr(
            se, "user_message", "A problem occurred with the payment processor."
        )
        raise HTTPException(
            status_code=getattr(se, "http_status", 500), detail=user_msg
        )
    except Exception as e:
        logger.error(
            f"Unexpected error creating payment intent: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Could not create payment intent due to an internal server error.",
        )


# The static files for tilesets are now served by a dedicated Nginx container (easyopen_tileset)
# So, the backend no longer needs to mount/serve them directly.
# If you had specific backend logic that interacted with files in `../data/tileset`
# that logic would now use the path `/data/tileset` (as mounted in backend's docker-compose).
# app.mount("/tileset", StaticFiles(directory="../data/tileset"), name="tileset") # This is removed
