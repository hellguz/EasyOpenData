# EasyOpenData Frontend

## Overview

This is a simple frontend HTML page that displays 3D buildings of Nürnberg using CesiumJS. It fetches building data from the backend and renders them on a 3D map.

## Setup

1. **Install Dependencies**

   No installation is required. The frontend uses CDN links for CesiumJS.

2. **Run the Backend**

   Ensure the backend server is running:

   ```bash
   uvicorn main:app --reload
