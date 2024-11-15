import json

# Path to the large GeoJSON file
input_file = r"output_dir\650_5478_repr.geojson"

# Path for the output smaller GeoJSON file
output_file = "650_5478_repr_small.geojson"

# Desired size of the output file in bytes (50 MB)
desired_size = 1 * 1024 * 1024

def extract_small_geojson(input_file, output_file, max_size):
    try:
        with open(input_file, 'r', encoding='utf-8') as infile:
            # Initialize variables to construct the new GeoJSON
            small_data = {
                "type": "FeatureCollection",
                "features": []
            }
            
            # Read the opening part of the GeoJSON file
            line = infile.readline()
            while line.strip() != '"features": [':
                line = infile.readline()

            # Read features one by one
            current_size = 0
            for line in infile:
                if line.strip() == ']':
                    break  # End of features list

                # Remove trailing comma if present
                feature_str = line.rstrip(',\n')
                
                # Parse feature JSON
                feature = json.loads(feature_str)
                
                # Add feature to the new collection
                small_data["features"].append(feature)
                
                # Update current size
                current_size += len(feature_str.encode('utf-8'))
                
                # Stop if the current size exceeds or reaches the desired size
                if current_size >= max_size:
                    break

            # Write closing brackets for the JSON structure
            with open(output_file, 'w', encoding='utf-8') as outfile:
                json.dump(small_data, outfile, ensure_ascii=False, indent=2)
            
            print(f"Extracted {len(small_data['features'])} features into {output_file}")

    except Exception as e:
        print(f"An error occurred: {e}")

# Run the function to extract a smaller GeoJSON file
extract_small_geojson(input_file, output_file, desired_size)