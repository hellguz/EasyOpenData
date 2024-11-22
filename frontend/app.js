export function initializeDeck(container) {
  // Access global deck.gl classes
  const { Deck, Tile3DLayer } = deck;

  // Define the Tile3DLayer
  const layer = new Tile3DLayer({
    id: 'tile-3d-layer',
    data: 'http://localhost:8000/cache/tileset.json',
    refinementStrategy: 'no-overlap',
    loadOptions: {
      tileset: {
        maximumScreenSpaceError: 8, // Reduce this value (default is 16)
        maximumMemoryUsage: 1024 // Increase memory usage (in MB)
      }
    },
    onTilesetLoad: (tileset) => {
      // Adjust the view to fit the tileset
      const { cartographicCenter, zoom } = tileset;
      deckInstance.setProps({
        initialViewState: {
          longitude: 11.0767, // Nürnberg longitude
          latitude: 49.4521,  // Nürnberg latitude
          zoom: 15,
          pitch: 45,
          bearing: 0,
          minZoom: 10,
          maxZoom: 20
        },
      });
    },
    pointSize: 2,
  });

  // Create a Deck.gl instance
  const deckInstance = new Deck({
    canvas: container,
    initialViewState: {
      longitude: 11.0767, // Nürnberg longitude
      latitude: 49.4521,  // Nürnberg latitude
      zoom: 15,
      pitch: 45,
      bearing: 0,
      minZoom: 10,
      maxZoom: 20
    },
    controller: true,
    layers: [layer],
  });
}
