import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { Map } from "react-map-gl/maplibre";
import DeckGL from "@deck.gl/react";
import { Tile3DLayer } from "@deck.gl/geo-layers";
import { CesiumIonLoader } from "@loaders.gl/3d-tiles";

import type { MapViewState } from "@deck.gl/core";
import type { Tileset3D } from "@loaders.gl/tiles";

const TILESET_URL = `http://localhost:8000/cache/tileset.json`;

const INITIAL_VIEW_STATE: MapViewState = {
  latitude: 40,
  longitude: -75,
  pitch: 45,
  maxPitch: 60,
  bearing: 0,
  minZoom: 2,
  maxZoom: 30,
  zoom: 17,
};

export default function App({
  mapStyle = "https://api.maptiler.com/maps/basic/style.json?key=get_your_own_OpIi9ZULNHzrESv6T2vL",

  updateAttributions,
}: {
  mapStyle?: string;
  updateAttributions?: (attributions: any) => void;
}) {
  const [initialViewState, setInitialViewState] = useState(INITIAL_VIEW_STATE);

  const onTilesetLoad = (tileset: Tileset3D) => {
    // Recenter view to cover the new tileset
    const { cartographicCenter, zoom } = tileset;
    setInitialViewState({
      ...INITIAL_VIEW_STATE,
      longitude: cartographicCenter[0],
      latitude: cartographicCenter[1],
      zoom,
    });

    if (updateAttributions) {
      updateAttributions(tileset.credits && tileset.credits.attributions);
    }
  };

  const tile3DLayer = new Tile3DLayer({
    id: "tile-3d-layer",
    pointSize: 2,
    data: TILESET_URL,
    onTilesetLoad,
  });

  return (
    <DeckGL
      layers={[tile3DLayer]}
      initialViewState={initialViewState}
      controller={true}
    >
      <Map reuseMaps mapStyle={mapStyle} />
    </DeckGL>
  );
}

export function renderToDOM(container: HTMLDivElement) {
  createRoot(container).render(<App />);
}
