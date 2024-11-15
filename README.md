# EasyOpenData
## Open Data Extractor for German Spatial Datasets

## Overview
This project aims to provide an easy-to-use platform for accessing and downloading spatial data from German open data sources, covering all Bundesländer. The system standardizes the diverse formats in which these datasets are available and presents them to users via an intuitive web interface.

Users can interact with a map, select areas of interest (via polygons or rectangles), and choose the data layers they wish to download. Available data types include:
- Parcels
- Terrain
- 3D Buildings (LOD1/LOD2)

The platform processes the selected data and provides it in the user's desired format after payment, either as a direct download or via email.

---

## Key Features
- **Map-Based User Interface**: Allows users to interact with spatial data visually by selecting areas on a map.
- **Multi-Format Support**: Data is standardized into a unified format, enabling seamless querying and export in multiple formats (e.g., GeoJSON, glTF).
- **Dynamic Data Processing**: Only fetches and processes data for the area selected by the user, ensuring efficiency.
- **Real-Time Visualization**: Users can preview data layers on the map as they select their areas of interest.
- **Scalable Backend**: Built for performance, capable of handling large datasets from multiple regions.

---

## Technologies Used

### **Backend**

- **PostGIS**: Spatial database for storing and querying geographic data efficiently.
- **Python FastAPI**: Backend framework for building APIs to handle user requests and interact with PostGIS.
- **GDAL**: Used for data conversion between formats like CityGML, GeoJSON, and glTF.
- **Py3Dtiles/Trimesh**: For converting 3D data to glTF format dynamically.
- **Docker**: Containerized deployment for portability and scalability.

### **Frontend**

- **React + Leaflet**: Interactive map interface for 2D visualization and area selection.
- **CesiumJS**: 3D visualization for previewing datasets like LOD1/LOD2 buildings.

### **Infrastructure**

- **PostgreSQL + PostGIS**: Backend database for spatial data storage and indexing.
- **NGINX**: For serving static files and proxying API requests.
- **Cloud Storage**: For storing processed datasets ready for download (e.g., AWS S3, Google Cloud Storage).

---

## Workflow

1. **Data Ingestion**:
   - Import spatial data from various Bundesländer open data portals.
   - Convert datasets into a unified format (e.g., CityGML or PostGIS-compatible geometry).

2. **Data Storage**:
   - Store standardized data in a PostGIS database with spatial indexing for efficient querying.

3. **User Interaction**:
   - Users draw polygons/rectangles on the map to define areas of interest.
   - Backend processes the request, fetching relevant data using spatial queries.

4. **Data Processing**:
   - Convert queried data to web-friendly formats:
     - GeoJSON for 2D previews.
     - glTF for 3D previews.
   - Generate downloadable files in formats requested by the user.

5. **Data Delivery**:
   - Users download processed data directly from the browser or receive it via email after payment.

---

## Project Goals

1. **Standardization**: Harmonize data formats across all Bundesländer for consistent access and processing.
2. **Ease of Use**: Create a user-friendly interface for both novice and advanced users.
3. **Scalability**: Design a backend architecture capable of handling large datasets and high user demand.
4. **Flexibility**: Enable the export of data in various formats (e.g., GeoJSON, glTF, Shapefile).

---

## Example Usage

### **Frontend**

1. User opens the webpage and views a map interface.
2. Selects an area of interest by drawing a polygon or rectangle.
3. Chooses the desired data layers (e.g., 3D buildings).
4. Proceeds to payment and downloads the processed data.

### **Backend**

1. Receives the user’s area and data type requests via API.
2. Queries PostGIS for intersecting objects within the selected area.
3. Dynamically converts data into the requested format (e.g., glTF).
4. Returns the processed data for download.

---

## Setup

### **Backend**

1. Install PostgreSQL and PostGIS:

   ```bash
   sudo apt install postgresql postgis
   ```

2. Clone the repository and install dependencies:

   ```bash
   git clone https://github.com/your-repo/open-data-extractor.git
   cd open-data-extractor/backend
   pip install -r requirements.txt
   ```

3. Import sample data into PostGIS:

   ```bash
   ogr2ogr -f "PostgreSQL" PG:"dbname=your_db user=your_user password=your_pass" sample_data.gml
   ```

4. Run the FastAPI server:

   ```bash
   uvicorn main:app --reload
   ```

### **Frontend**

1. Install Node.js and dependencies:

   ```bash
   cd open-data-extractor/frontend
   npm install
   ```

2. Run the React development server:

   ```bash
   npm start
   ```

---

## Future Roadmap

- Add support for additional data layers (e.g., terrain, parcels).
- Implement caching for frequently requested data.
- Introduce user accounts for managing downloads and licenses.
- Explore additional formats for exporting data (e.g., OBJ, IFC).
- Expand coverage beyond Germany to other European countries.

---

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your changes. Ensure all code adheres to the style guide and includes proper documentation.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

---

## Contact

For questions, feedback, or support, contact us at:

- **Email**: support@opendataextractor.com