# EasyOpenData 🗺️

*A user-friendly platform for accessing and downloading German 3D building models.*

Tired of wrestling with complex German spatial data formats? **EasyOpenData** simplifies the process by providing an intuitive map-based interface to select, purchase, and download high-quality 3D building models for any region in Germany.



---

## ✨ Key Features

* **🗺️ Interactive Map Interface**: Visually select your area of interest using powerful drawing tools.
* **⚙️ On-Demand Processing**: Data is fetched and processed only for your selected area, ensuring efficiency and speed.
* **💻 3D Visualization**: Preview 3D building data directly on the map using Deck.gl.
* **💳 Secure Stripe Payments**: A seamless and secure payment process for paid datasets.
* **🏗️ Simple Single-Port Architecture**: The entire application runs behind a reverse proxy, exposing just one port for easy deployment.

---

## 🚀 Quick Start Guide

Get the application running in just a few steps.

### 1. Prerequisites

You'll need **Docker** and **Docker Compose** installed on your system.

### 2. Configuration

Before you start, create a configuration file.

1.  Copy the sample environment file:
    ```bash
    cp .env.sample .env
    ```
2.  Open the new **.env** file and fill in your specific details (like database passwords and Stripe API keys).

### 3. Running the Application

You can run the app in either development or production mode.

#### For Development 👩‍💻

This mode enables **hot-reloading** for both the frontend and backend and runs helpful tools like **pgAdmin**. Services are exposed on separate ports for easy debugging.

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build
````

  * **Frontend**: http://localhost:5173
  * **Backend API**: http://localhost:5400
  * **pgAdmin**: http://localhost:5050

#### For Production 🚢

This command builds and runs the optimized production containers. The entire application is served through a **single port** via the reverse proxy.

```bash
docker-compose up --build -d
```

  * **Application**: http://localhost:5173

-----

## 🖥️ How to Use the App

1.  **Open the Web Application**: Navigate to the application in your browser.
2.  **Find a Location**: Use the search bar to find a specific location.
3.  **Select an Area**: Use the drawing tools to draw a polygon on the map. The area in km² will be calculated automatically.
4.  **Proceed to Download**: Use the "Herunterladen" (Download) panel to proceed.
5.  **Payment**: If the area is large enough to require payment, fill in the secure Stripe payment form.
6.  **Download Data**: After payment, your `.obj` file download will begin automatically.

-----

## 🛠️ Tech Stack

The project uses a modern, containerized tech stack.

  * **Frontend**: React, MapLibre GL JS, Deck.gl
  * **Backend**: Python, FastAPI
  * **Database**: PostgreSQL with PostGIS
  * **Infrastructure**: Docker, Nginx (as Reverse Proxy and Web Server)

-----

## 📂 Project Structure

The repository is organized into three main directories.

```
/
├── backend/        # FastAPI application and data ingestion scripts
├── frontend/       # React user interface
└── nginx/          # Configuration for the main reverse proxy
```

-----

## ⚙️ Management & Operations

### Deployment

The production setup uses an Nginx reverse proxy to route traffic to the appropriate services. All traffic is handled through the single port exposed by the `nginx_proxy` service.

  * Requests to `/api/*` are forwarded to the backend service.
  * All other requests are served by the frontend service.

For a live deployment, you would point your domain's DNS records to the server running Docker and ensure the proxy's port (e.g., 5173) is accessible. For HTTPS, you would configure the `nginx_proxy` service to handle SSL termination.

### Backup and Restore

You can perform backups and restores using `docker-compose exec`.

#### Create a Backup

Execute this command to create a backup of your database. The file will be saved in the `./data/postgres_backups/` directory.

```bash
mkdir -p ./data/postgres_backups && \
docker-compose exec -T easyopen_postgis pg_dump -U ${DATABASE_USER} -d ${DATABASE_NAME} -F c > ./data/postgres_backups/backup_$(date +%Y-%m-%d_%H-%M-%S).dump
```

#### Restore from a Backup

To restore the database, place your `.dump` file in `./data/postgres_backups/` and run:

```bash
docker-compose exec -T easyopen_postgis pg_restore -U ${DATABASE_USER} -d ${DATABASE_NAME} --clean --if-exists < ./data/postgres_backups/your_backup_file.dump
```

Make sure to replace `your_backup_file.dump` with the actual name of your backup file.

-----

## 🤝 Contributing

Contributions are welcome\! Please fork the repository and submit a pull request with your changes.

-----

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for more details.

-----

## 📧 Contact

For questions or feedback, please contact us at **hellguz@gmail.com**.
