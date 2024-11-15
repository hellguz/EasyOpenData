# Database Setup Instructions for Windows

Follow these steps to create the PostgreSQL database with the PostGIS extension on Windows:

---

## 1. Install PostgreSQL and PostGIS

### **Download the Installer**

1. Visit the PostgreSQL official website: [PostgreSQL Downloads](https://www.postgresql.org/download/windows/).
2. Click on **"Download the installer"** to go to the EnterpriseDB download page.
3. Download the latest version of the PostgreSQL installer for Windows.

### **Run the Installer**

1. Run the downloaded `.exe` installer.
2. Follow the installation wizard steps:
   - **Installation Directory**: Choose your preferred installation directory.
   - **Select Components**: Ensure that **"PostGIS Bundle"** is checked to install PostGIS along with PostgreSQL.
   - **Password Setup**: Set a password for the default `postgres` superuser. Remember this password.
   - **Port Number**: Default is `5432`. You can change it if needed.
   - **Locale**: Choose the default locale or your preferred setting.
3. Complete the installation and wait for it to finish.

---

## 2. Create a New PostgreSQL Database and User

### **Open pgAdmin**

1. After installation, open **pgAdmin 4** from the Start Menu.
2. When prompted, enter the password you set for the `postgres` user during installation.

### **Create a New Database**

1. In pgAdmin, expand the server tree to see **"Databases"**.
2. Right-click on **"Databases"** and select **"Create"** > **"Database..."**.
3. In the **"Database"** dialog:
   - **Database Name**: Enter `your_db`.
   - **Owner**: Select `postgres` or your preferred user.
4. Click **"Save"**.

### **Create a New User (Role)**

1. Expand the **"Login/Group Roles"** under your server.
2. Right-click on **"Login/Group Roles"** and select **"Create"** > **"Login/Group Role..."**.
3. In the **"Properties"** tab:
   - **Role Name**: Enter `your_user`.
4. In the **"Definition"** tab:
   - **Password**: Enter `your_password`.
   - **Confirm Password**: Re-enter the password.
5. In the **"Privileges"** tab:
   - Set **"Can login?"** to **"Yes"**.
6. Click **"Save"**.

### **Grant Privileges to the User**

1. In pgAdmin, navigate to **"Databases"** > **"your_db"** > **"Schemas"** > **"public"**.
2. Right-click on **"public"** schema and select **"Properties"**.
3. Go to the **"Privileges"** tab.
4. Click on the **"Add"** icon (a plus sign).
5. In the new row:
   - **Role**: Select `your_user`.
   - **Privileges**: Check all the boxes (or at least **"Usage"** and **"Create"**).
6. Click **"Save"**.

### **Enable the PostGIS Extension**

1. Right-click on **"your_db"** and select **"Query Tool"**.
2. In the Query Editor, run the following SQL command:

   ```sql
   CREATE EXTENSION postgis;
   ```

3. Click the **"Execute/Refresh"** button (lightning bolt icon) to run the query.
4. You should see a message indicating that the extension was created successfully.

---

## 3. Update Your Database Configuration

### **Modify the `.env` File**

In your project directory, locate the `.env` file inside the `./backend` folder and update the `DATABASE_URL`:

```
DATABASE_URL=postgresql+asyncpg://your_user:your_password@localhost:5432/your_db
```

---

## 4. Run the Application to Create Tables

The `init_db()` function in `database.py` will automatically create the necessary tables when the application starts.

### **Open Command Prompt or PowerShell**

Navigate to your project's backend directory:

```cmd
cd path\to\your\project\backend
```

### **Create a Virtual Environment (Optional but Recommended)**

```cmd
python -m venv venv
venv\Scripts\activate
```

### **Install Dependencies**

Ensure all the required Python packages are installed:

```cmd
pip install -r requirements.txt
```

### **Start the FastAPI Application**

```cmd
uvicorn main:app --reload
```

---

## 5. Verify the Tables Have Been Created

### **Using pgAdmin**

1. In pgAdmin, right-click on **"Tables"** under **"your_db"** > **"Schemas"** > **"public"**, and select **"Refresh"**.
2. Expand the **"Tables"** section.
3. You should see the `buildings` table listed.

---

## 6. Ingest Data into the Database

Use the provided data ingestion scripts to populate the database with building data.

### **Install GDAL for Windows**

1. Download the GDAL Windows binaries from [GIS Internals](https://www.gisinternals.com/query.html?content=filelist&file=release-1930-x64-gdal-3-4-1-mapserver-7-6-4.zip).
2. Extract the contents to a directory (e.g., `C:\Program Files\GDAL`).
3. Add the GDAL bin directory to your system PATH:
   - Open **Control Panel** > **System** > **Advanced system settings**.
   - Click on **"Environment Variables"**.
   - Under **"System Variables"**, find and edit the **"Path"** variable.
   - Add the path to the GDAL `bin` directory (e.g., `C:\Program Files\GDAL\bin`).
4. Set the `GDAL_DATA` environment variable:
   - In **"System Variables"**, click **"New"**.
   - **Variable name**: `GDAL_DATA`
   - **Variable value**: `C:\Program Files\GDAL\gdal-data`

### **Place Your GML Files**

Add your `.gml` files into the appropriate directories under `data_local\{bundesland_name}\`.

### **Run the Ingestion Script**

```cmd
python data_ingest\ingest_baden_wuerttemberg.py
```

Replace `ingest_baden_wuerttemberg.py` with the script corresponding to your Bundesland.

**Note**: You may need to install `osgeo` dependencies for GDAL to work with Python scripts.

---

## 7. Test the Endpoint

You can now test the `/buildings` endpoint to retrieve buildings within a given boundary.

### **Example Request Using cURL**

```cmd
curl -X POST "http://localhost:8000/buildings" -H "Content-Type: application/json" -d "{\"type\":\"Polygon\",\"coordinates\":[[[9.0,48.0],[9.1,48.0],[9.1,48.1],[9.0,48.1],[9.0,48.0]]]}"
```

### **Example Request Using Python**

```python
import requests

url = "http://localhost:8000/buildings"
geometry = {
    "type": "Polygon",
    "coordinates": [
        [
            [9.0, 48.0],
            [9.1, 48.0],
            [9.1, 48.1],
            [9.0, 48.1],
            [9.0, 48.0]
        ]
    ]
}

response = requests.post(url, json=geometry)
print(response.json())
```

---

## Notes

- Ensure that the SRID (Spatial Reference System Identifier) matches between your data and the database. The default SRID in the model is `4326`.
- If you encounter any issues, check the application logs for errors and verify your database connection settings.
- Make sure that the `psycopg2` package is installed properly. On Windows, you might need to install `psycopg2-binary`.

---

## Troubleshooting

### **Common Issues**

- **GDAL Not Found**: Ensure that GDAL is correctly installed and added to your system PATH.
- **Database Connection Errors**: Double-check your `DATABASE_URL` in the `.env` file.
- **Permission Denied**: Run Command Prompt or PowerShell as an administrator if you encounter permission issues.
- **Port Conflicts**: Ensure that port `5432` (PostgreSQL) and `8000` (FastAPI default) are not being used by other applications.

---

## Additional Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [PostGIS Documentation](https://postgis.net/documentation/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [GDAL Documentation](https://gdal.org/)

