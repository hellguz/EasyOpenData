import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { Map } from "react-map-gl/maplibre";
import DeckGL from "@deck.gl/react";
import { Tile3DLayer } from "@deck.gl/geo-layers";
import { CesiumIonLoader } from "@loaders.gl/3d-tiles";
import MapboxDraw from "@mapbox/mapbox-gl-draw";
import * as turf from "@turf/turf";
import "@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css";

import type { MapViewState } from "@deck.gl/core";
import type { Tileset3D } from "@loaders.gl/tiles";

const TILESET_URL = `http://localhost:8000/cache/tileset.json`;

const INITIAL_VIEW_STATE: MapViewState = {
  latitude: 40,
  longitude: -75,
  pitch: 25,
  maxPitch: 90,
  bearing: 0,
  minZoom: 2,
  maxZoom: 30,
  zoom: 14,
};

export default function App({
  mapStyle = "https://api.maptiler.com/maps/basic/style.json?key=get_your_own_OpIi9ZULNHzrESv6T2vL",
  updateAttributions,
}: {
  mapStyle?: string;
  updateAttributions?: (attributions: any) => void;
}) {
  const [initialViewState, setInitialViewState] = useState(INITIAL_VIEW_STATE);
  const [map, setMap] = useState(null);
  const drawRef = useRef(null);

  const onTilesetLoad = (tileset: Tileset3D) => {
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
  useEffect(() => {
    if (map) {
      // Initialize draw control
      drawRef.current = new MapboxDraw({
        displayControlsDefault: false,
        controls: {
          polygon: true,
          trash: true
        },
        defaultMode: 'draw_polygon',
        styles: [
          {
            id: 'gl-draw-polygon-fill',
            type: 'fill',
            filter: ['all', ['==', '$type', 'Polygon']],
            paint: {
              'fill-color': '#0000ff',
              'fill-opacity': 0.5
            }
          },
          {
            id: 'gl-draw-polygon-stroke',
            type: 'line',
            filter: ['all', ['==', '$type', 'Polygon']],
            paint: {
              'line-color': '#0000ff',
              'line-width': 2
            }
          }
        ]
      });

      map.addControl(drawRef.current);
    }
  }, [map]);

  return (
    <DeckGL
      layers={[tile3DLayer]}
      initialViewState={initialViewState}
      controller={true}
    >
      <Map
        reuseMaps
        mapStyle={mapStyle}
        ref={(ref) => ref && setMap(ref.getMap())}
      />
    </DeckGL>
  );
}

export function renderToDOM(container: HTMLDivElement) {
  createRoot(container).render(<App />);
}