# ./backend/retrieve_obj.py

import asyncio
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from geoalchemy2 import functions as func
from app.database import async_session
from app.models import Building
import os
from pyproj import Transformer

async def retrieve_obj_file(region_geojson, output_path):
    """
    Generates an OBJ file with buildings within the given polygon region.

    Args:
        region_geojson (dict): The GeoJSON representing the input region.
        output_path (str): The file path where the OBJ file will be saved.
    """
    # Parse the input GeoJSON to get the polygon geometry
    features = region_geojson.get('features', [])
    if not features:
        raise ValueError("No features found in the input GeoJSON.")
    
    polygon_feature = features[0]
    polygon_geometry = polygon_feature.get('geometry', {})
    if polygon_geometry.get('type') != 'Polygon':
        raise ValueError("The geometry must be of type 'Polygon'.")

    # Convert GeoJSON geometry to GeoJSON string
    polygon_geojson_str = json.dumps(polygon_geometry)

    # Choose the appropriate projection (e.g., UTM zone 32N for Germany)
    # You may need to adjust the EPSG code based on your location
    source_crs = 'EPSG:4326'  # WGS84 Latitude/Longitude
    target_crs = 'EPSG:25832'  # ETRS89 / UTM zone 32N (adjust as needed)

    # Create a Transformer object for coordinate transformation
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)

    # Clean and validate the user polygon once
    polygon = func.ST_SetSRID(func.ST_GeomFromGeoJSON(polygon_geojson_str), 4326)
    polygon = func.ST_MakeValid(polygon)
    polygon = func.ST_Force3D(polygon)
    polygon = func.ST_Buffer(polygon, 0)
    
    # Start an asynchronous database session
    async with async_session() as session:
        # Query the database for buildings within the polygon
        stmt = select(
            Building.gml_id,
            func.ST_AsGeoJSON(Building.geom).label('geom_geojson')
        ).where(
            func.ST_Intersects(
                func.ST_MakeValid(Building.geom),
                polygon
            )
        )
        
        result = await session.execute(stmt)
        buildings = result.fetchall()
        
        if not buildings:
            print("No buildings found within the given region.")
            return

        # Initialize lists to store OBJ data
        obj_vertices = []
        obj_faces = []
        vertex_offset = 0  # Offset for indexing vertices in faces

        # Process each building geometry
        for building in buildings:
            gml_id = building.gml_id
            geom_geojson_str = building.geom_geojson
            if not geom_geojson_str:
                continue  # Skip if geometry is null

            # Load geometry from GeoJSON
            geom_geojson = json.loads(geom_geojson_str)

            # Handle Polygon and MultiPolygon geometries
            geom_type = geom_geojson.get('type')
            coordinates = geom_geojson.get('coordinates')

            if geom_type == 'Polygon':
                polygons = [coordinates]
            elif geom_type == 'MultiPolygon':
                polygons = coordinates
            else:
                print(f"Skipping unsupported geometry type (ID: {gml_id}, Type: {geom_type})")
                continue

            for polygon in polygons:
                ring_vertex_indices = []

                # Process exterior ring
                exterior_coords = polygon[0]
                exterior_indices = []
                for coord in exterior_coords:
                    lon, lat = coord[:2]
                    z = coord[2] if len(coord) > 2 else 0
                    # Transform coordinates
                    x, y = transformer.transform(lon, lat)
                    obj_vertices.append(f"v {x} {z} {y}")
                    vertex_offset += 1
                    exterior_indices.append(vertex_offset)
                # Add face for exterior ring
                obj_faces.append(f"f {' '.join(map(str, exterior_indices))}")

                # Process interior rings (holes)
                for interior_coords in polygon[1:]:
                    interior_indices = []
                    for coord in interior_coords:
                        lon, lat = coord[:2]
                        z = coord[2] if len(coord) > 2 else 0
                        # Transform coordinates
                        x, y = transformer.transform(lon, lat)
                        obj_vertices.append(f"v {x} {z} {y}")
                        vertex_offset += 1
                        interior_indices.append(vertex_offset)
                    # Add face for interior ring (negative indices to denote holes are not standard in OBJ)
                    # Some software may not support holes directly
                    # So, we can skip adding faces for holes or handle them as separate objects
                    # For now, we'll skip adding faces for holes
                    print(f"Skipping interior ring (hole) in building ID: {gml_id}")

        # Write to OBJ file
        with open(output_path, 'w') as obj_file:
            obj_file.write("# OBJ file generated from buildings\n")
            obj_file.write("\n".join(obj_vertices))
            obj_file.write("\n")
            obj_file.write("\n".join(obj_faces))

        print(f"OBJ file successfully written to {output_path}")
        return
