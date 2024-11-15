#!/usr/bin/env python3
"""
transform_gml.py

A script to transform a CityGML file by embedding polygon geometries directly within
lod2Solid's surfaceMember elements, removing external xlink references.

Usage:
    python transform_gml.py input.gml output.gml
"""

### python .\transform_gml.py .\..\data_local\bayern\raw\650_5478.gml .\..\data_local\bayern\650_5478_trs.gml


import sys
import os
from lxml import etree

def get_all_namespaces(gml_tree):
    """
    Extracts all namespaces from the GML tree and assigns a unique prefix to the default namespace.

    Args:
        gml_tree (etree.ElementTree): Parsed GML tree.

    Returns:
        dict: Namespace prefix to URI mapping.
    """
    nsmap = gml_tree.getroot().nsmap.copy()
    # Handle default namespace (None key)
    if None in nsmap:
        nsmap['default'] = nsmap.pop(None)
    # Ensure 'xlink' is included
    if 'xlink' not in nsmap:
        # Attempt to find the xlink namespace
        for prefix, uri in nsmap.items():
            if uri == 'http://www.w3.org/1999/xlink':
                nsmap['xlink'] = uri
                break
        else:
            # If not found, add it manually
            nsmap['xlink'] = 'http://www.w3.org/1999/xlink'
    return nsmap

def transform_gml(input_file, output_file):
    """
    Transforms the input GML file by embedding polygons into surfaceMember elements.

    Args:
        input_file (str): Path to the input GML file.
        output_file (str): Path to the output transformed GML file.
    """
    # Parse the GML file
    print(f"Parsing input GML file: {input_file}")
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(input_file, parser)
    root = tree.getroot()

    # Extract all namespaces
    namespaces = get_all_namespaces(tree)
    print("Namespaces detected:")
    for prefix, uri in namespaces.items():
        print(f"  Prefix: '{prefix}' => URI: '{uri}'")

    # Build a dictionary of gml:id to Polygon elements for quick lookup
    print("Indexing all <gml:Polygon> elements by gml:id...")
    polygon_dict = {}
    for polygon in root.xpath('.//gml:Polygon', namespaces=namespaces):
        polygon_id = polygon.get('{http://www.opengis.net/gml}id')
        if polygon_id:
            polygon_dict[polygon_id] = polygon
    print(f"Indexed {len(polygon_dict)} polygons.")

    # Find all <gml:surfaceMember> elements with xlink:href
    print("Finding all <gml:surfaceMember> elements with xlink:href...")
    surface_members = root.xpath('.//gml:surfaceMember[@xlink:href]', namespaces=namespaces)
    print(f"Found {len(surface_members)} <gml:surfaceMember> elements with xlink:href.")

    for sm in surface_members:
        href = sm.get('{http://www.w3.org/1999/xlink}href')
        if not href:
            continue
        # Extract the referenced polygon ID (remove the '#' prefix)
        polygon_id = href.lstrip('#')
        print(f"Processing surfaceMember referencing Polygon ID: {polygon_id}")
        polygon = polygon_dict.get(polygon_id)
        if not polygon:
            print(f"Warning: Polygon with gml:id='{polygon_id}' not found. Skipping.")
            continue
        # Deep copy the polygon element
        polygon_copy = etree.fromstring(etree.tostring(polygon))
        # Remove any existing 'gml:id' to avoid duplicate IDs
        polygon_copy.attrib.pop('{http://www.opengis.net/gml}id', None)
        # Replace the surfaceMember's xlink:href attribute with the actual Polygon
        sm.clear()  # Remove existing children and attributes
        sm.append(polygon_copy)
        print(f"Embedded Polygon ID: {polygon_id} into surfaceMember.")

    # Optionally, remove standalone <gml:Polygon> elements that were referenced
    print("Removing standalone <gml:Polygon> elements that were referenced...")
    removed_count = 0
    # for polygon_id in polygon_dict.keys():
    #     # Find and remove the standalone polygon
    #     polygons_to_remove = root.xpath(f'.//gml:Polygon[@gml:id="{polygon_id}"]', namespaces=namespaces)
    #     for polygon in polygons_to_remove:
    #         parent = polygon.getparent()
    #         if parent is not None:
    #             parent.remove(polygon)
    #             removed_count += 1
    #             print(f"Removed standalone Polygon ID: {polygon_id}.")
    # print(f"Removed {removed_count} standalone polygons.")

    # Write the transformed GML to the output file
    print(f"Writing transformed GML to: {output_file}")
    tree.write(output_file, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    print("Transformation complete.")

def main():
    if len(sys.argv) != 3:
        print("Usage: python transform_gml.py input.gml output.gml")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]

    if not os.path.isfile(input_file):
        print(f"Error: Input file '{input_file}' does not exist.")
        sys.exit(1)

    try:
        transform_gml(input_file, output_file)
    except etree.XMLSyntaxError as e:
        print(f"XML Syntax Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred during transformation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
