// app.js

// Ensure that the script runs after all libraries have loaded
document.addEventListener('DOMContentLoaded', () => {
  initializeMap();
});

function initializeMap() {
  // Initialize MapLibre Map
  const map = new maplibregl.Map({
    container: 'map',
    style: 'https://api.maptiler.com/maps/basic/style.json?key=get_your_own_OpIi9ZULNHzrESv6T2vL', // Basemap style
    center: [11.0767, 49.4521], // Nürnberg coordinates [lng, lat]
    zoom: 15,
    pitch: 45,
    bearing: 0,
    minZoom: 10,
    maxZoom: 18, // Reduced maxZoom for performance
    antialias: false, // Disables antialiasing for better performance
    renderWorldCopies: false, // Prevents rendering multiple copies of the world
  });

  map.addControl(new maplibregl.NavigationControl(), 'top-right'); // Optional: Add navigation controls

  map.on('load', () => {
    // Create a Deck instance as a MapboxOverlay
    const deckOverlay = new deck.MapboxOverlay({
      layers: [
        new deck.Tile3DLayer({
          id: 'tile-3d-layer',
          data: 'http://localhost:8000/cache/tileset.json', // Replace with your tileset URL
          // loader: deck.loaders3DTiles, // Specify the loader explicitly
          onTileLoad: handleTileLoad, // Optional: Handle tile load events
          onTileError: handleTileError, // Optional: Handle tile load errors
          maxZoom: 18, // Align with map's maxZoom
          minZoom: 10, // Align with map's minZoom
          cull: true, // Enable frustum culling
          dynamic: true, // Enable dynamic rendering
          loadOptions: {
            workers: 4, // Number of worker threads
            useDraco: true, // Enable Draco compression if supported by tileset
          },
          pickable: false, // Disable picking for performance if not needed
        })
      ],
      parameters: {
        depthTest: true,
        blend: true,
      },
      //viewState: map.getFreeCameraOptions(), // Sync Deck.gl view with MapLibre
    });

    // Add the Deck overlay to the map
    map.addControl(deckOverlay);
  });
}

// Optional: Handle tile load success
function handleTileLoad(tile) {
  console.log(`Tile loaded: ${tile.url}`);
}

// Optional: Handle tile load errors
function handleTileError(error, tile) {
  console.error(`Error loading tile ${tile.url}:`, error);
}
