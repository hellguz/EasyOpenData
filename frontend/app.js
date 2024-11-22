// app.js

function initializeDeck() {
  // Initialize MapLibre Map
  const map = new maplibregl.Map({
    container: 'map',
    style: 'https://api.maptiler.com/maps/basic/style.json?key=get_your_own_OpIi9ZULNHzrESv6T2vL', // Basemap style
    center: [11.0767, 49.4521], // Nürnberg coordinates [lng, lat]
    zoom: 15,
    pitch: 45,
    bearing: 0,
    minZoom: 10,
    maxZoom: 20,
    antialias: false, // Enables smoother rendering for 3D layers
  });

  map.on('load', () => {
    // Create a Deck instance
    const deckOverlay = new deck.MapboxOverlay({
      layers: [
        new deck.Tile3DLayer({
          id: 'tile-3d-layer',
          data: 'http://localhost:8000/cache/tileset.json', // Replace with your tileset URL
          pointSize: 2,
          onTilesetLoad: (tileset) => {
            const { cartographicCenter, zoom } = tileset;
          },
        })
      ]
    });

    // Add the Deck overlay to the map as a control
    map.addControl(deckOverlay);
  });
}

// Initialize the map and Deck.gl layer
initializeDeck();