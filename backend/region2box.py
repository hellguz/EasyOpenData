import json
import math
import os

# WGS84 Ellipsoid constants
a = 6378137.0        # Equatorial radius
e2 = 6.69437999014e-3  # Square of eccentricity

def geodetic_to_ecef(lon, lat, h):
    """Convert geodetic coordinates to ECEF."""
    cos_lat = math.cos(lat)
    sin_lat = math.sin(lat)
    cos_lon = math.cos(lon)
    sin_lon = math.sin(lon)

    N = a / math.sqrt(1 - e2 * sin_lat * sin_lat)

    X = (N + h) * cos_lat * cos_lon
    Y = (N + h) * cos_lat * sin_lon
    Z = (N * (1 - e2) + h) * sin_lat

    return X, Y, Z

def region_to_box(region):
    """Convert region bounding volume to box bounding volume."""
    west, south, east, north, minHeight, maxHeight = region

    # Calculate center point
    lon_center = (west + east) / 2
    lat_center = (south + north) / 2
    height_center = (minHeight + maxHeight) / 2

    # Convert center point to ECEF
    centerX, centerY, centerZ = geodetic_to_ecef(lon_center, lat_center, height_center)

    # Calculate box dimensions
    delta_lon = (east - west)
    delta_lat = (north - south)
    delta_height = (maxHeight - minHeight)

    # Approximate distances over the Earth's surface
    # Calculate average radius at latitude
    R_lat = a * math.cos(lat_center) / math.sqrt(1 - e2 * math.sin(lat_center)**2)

    # Width and depth in meters
    width = delta_lon * R_lat
    depth = delta_lat * a * (1 - e2) / (1 - e2 * math.sin(lat_center)**2)**1.5

    # Half-axes lengths
    halfWidth = width / 2
    halfDepth = depth / 2
    halfHeight = delta_height / 2

    # Create half-axes vectors (assuming axis-aligned box in ECEF coordinates)
    halfAxes = [
        halfWidth, 0, 0,    # Half-axis X vector
        0, halfDepth, 0,    # Half-axis Y vector
        0, 0, halfHeight    # Half-axis Z vector
    ]

    # Build the box array
    box = [centerX, centerY, centerZ] + halfAxes
    return box

def process_tile(tile):
    """Recursively process tiles to replace region with box bounding volumes."""
    if 'boundingVolume' in tile and 'region' in tile['boundingVolume']:
        region = tile['boundingVolume']['region']
        box = region_to_box(region)
        tile['boundingVolume'] = {'box': box}

    if 'children' in tile:
        for child in tile['children']:
            process_tile(child)

def main():
    # Load tileset.json
    with open('backend/cache/tileset.json', 'r') as f:
        tileset = json.load(f)

    # Process the root tile
    process_tile(tileset['root'])

    # Save the updated tileset.json
    with open('backend/cache/tileset_box.json', 'w') as f:
        json.dump(tileset, f, indent=2)

    print("Updated tileset.json saved as tileset_box.json")

if __name__ == '__main__':
    main()
