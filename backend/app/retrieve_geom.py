# ./backend/retrieve_obj.py

import asyncio
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from geoalchemy2 import functions as func
from app.database import async_session
from app.models import Building
import os
from pyproj import Transformer  # For coordinate transformation

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

    # Start an asynchronous database session
    async with async_session() as session:
        # Query the database for buildings within the polygon
        stmt = select(
            Building.ogc_fid,
            func.ST_AsGeoJSON(
                func.ST_Transform(
                    func.ST_Simplify(Building.geom, 0.1),
                    25832  # Transform the result to 25832 after filtering
                )
            ).label('geom_geojson')
        ).where(
            func.ST_Intersects(
                func.ST_MakeValid(Building.geom),  # Building geometries are kept in their original SRID (4326)
                func.ST_MakeValid(func.ST_GeomFromGeoJSON(polygon_geojson_str))  # Transform the input polygon to 4326
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
            ogc_fid = building.ogc_fid
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
                print(f"Skipping unsupported geometry type (ID: {ogc_fid}, Type: {geom_type})")
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
                    print(f"Skipping interior ring (hole) in building ID: {ogc_fid}")

        # Write to OBJ file
        with open(output_path, 'w') as obj_file:
            obj_file.write("# OBJ file generated from buildings\n")
            obj_file.write("\n".join(obj_vertices))
            obj_file.write("\n")
            obj_file.write("\n".join(obj_faces))

        print(f"OBJ file successfully written to {output_path}")
        return

# Example usage
if __name__ == '__main__':
    # Load the input region GeoJSON
    region_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "bef0b7ecb5e2a869ea655de233909ed2",
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [11.078828018081367, 49.452387361598454],
                            [11.075765898190326, 49.452622450748436],
                            [11.07450436712378, 49.45031424385303],
                            [11.076197865379754, 49.449993191955855],
                            [11.08040312808447, 49.44850087839157],
                            [11.085839287965683, 49.452705969665345],
                            [11.078828018081367, 49.452387361598454]
                        ]
                    ]
                }
            }
        ]
    }
    output_path = 'output.obj'
    asyncio.run(retrieve_obj(region_geojson, output_path))
