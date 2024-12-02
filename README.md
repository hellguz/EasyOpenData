# EasyOpenData

## Open Data Extractor for German Spatial Datasets

### Overview

EasyOpenData is a platform that provides an easy-to-use interface for accessing and downloading spatial data from German open data sources, covering all Bundesländer. It standardizes the diverse formats in which these datasets are available and presents them to users via an intuitive web interface.

Users can interact with a map, select areas of interest (via polygons), and choose the data layers they wish to download. Available data types include:

- **3D Buildings (LOD1/LOD2)**

The platform processes the selected data and provides it in the user's desired format after payment, either as a direct download or via email.

---

### Key Features

- **Map-Based User Interface**: Allows users to interact with spatial data visually by selecting areas on a map.
- **Multi-Format Support**: Data is standardized into a unified format, enabling seamless querying and export.
- **Dynamic Data Processing**: Fetches and processes data only for the area selected by the user, ensuring efficiency.
- **Real-Time Visualization**: Users can preview data layers on the map as they select their areas of interest.
- **Payment Integration**: Secure payment processing via Stripe.
- **Scalable Backend**: Built for performance, capable of handling large datasets from multiple regions.

---

### Technologies Used

#### Backend

- **PostGIS**: Spatial database for storing and querying geographic data efficiently.
- **Python FastAPI**: Backend framework for building APIs to handle user requests and interact with PostGIS.
- **GDAL**: Used for data conversion between formats.
- **Docker**: Containerized deployment for portability and scalability.
- **Stripe API**: For handling payment transactions.

#### Frontend

- **React**: JavaScript library for building user interfaces.
- **MapLibre GL JS**: Interactive map interface for visualization and area selection.
- **Deck.gl**: For rendering 3D data on the map.
- **Mapbox Draw**: Allows users to draw shapes on the map.

---

### Getting Started

#### Prerequisites

- **Docker** and **Docker Compose** installed on your system.
- **Node.js** and **npm/yarn** (for frontend development).
- **Python 3.10+** (for backend development).

#### Setup Instructions

##### Clone the Repository

```bash
git clone https://github.com/your-repo/easyopendata.git
cd easyopendata
```

##### Environment Variables

Create a `.env` file in both the `backend` and `frontend` directories if needed to set environment variables.

##### Run with Docker Compose

```bash
docker-compose up --build
```

This command will:

- Start the PostGIS database.
- Build and run the backend FastAPI server.
- Build and run the frontend React application.

##### Access the Application

- **Frontend**: [http://localhost:5173](http://localhost:5173)
- **Backend API**: [http://localhost:5400](http://localhost:5400)

---

### Usage

1. **Open the Web Application**: Navigate to [http://localhost:5173](http://localhost:5173) in your browser.
2. **Select an Area**: Use the drawing tools to select an area on the map.
3. **Choose Data Layers**: Select the data layers you wish to download.
4. **Payment**: Proceed to payment if required.
5. **Download Data**: After processing, download your data in the desired format.

---

### Project Structure

- **backend/**: Contains the FastAPI backend application.
  - `app/`: FastAPI application code.
  - `db/`: Database initialization scripts.
  - `ingestion/`: Scripts for data ingestion and processing.
- **frontend/**: Contains the React frontend application.
  - `src/`: React application source code.
  - `public/`: Static assets.

---

### Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your changes. Ensure all code adheres to the style guide and includes proper documentation.

---

### License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

---

### Contact

For questions, feedback, or support, contact us at:

- **Email**: support@easyopendata.com