import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Map } from "react-map-gl/maplibre";
import DeckGL from "@deck.gl/react";
import { Tile3DLayer } from "@deck.gl/geo-layers";
import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import type { MapViewState } from "@deck.gl/core";
import type { Tileset3D } from "@loaders.gl/tiles";

const TILESET_URL = `http://localhost:8000/cache/tileset.json`;
const INITIAL_VIEW_STATE: MapViewState = {
  latitude: 49.4521,
  longitude: 11.0767,
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
  const mapRef = useRef(null);
  const [map, setMap] = useState(null);

  const [initialViewState, setInitialViewState] = useState(INITIAL_VIEW_STATE);

  useEffect(() => {
    if (map) {
      const mapInstance = map.getMap();

      // Wait for the style to load before accessing layers
      mapInstance.once("style.load", () => {
        const firstLabelLayer = mapInstance
          .getStyle()
          .layers.find((layer) => layer.type === "symbol");

        if (!firstLabelLayer) {
          console.error("No symbol layers found in the map style.");
          return;
        }

        const firstLabelLayerId = firstLabelLayer.id;

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


        // Add DeckGL overlay
        const overlay = new MapboxOverlay({
          interleaved: true,
          layers: [tile3DLayer],
        });

        mapInstance.addControl(overlay);
      });
    }
  }, [map]);

  return (
    <DeckGL initialViewState={INITIAL_VIEW_STATE} controller={true}>
      <Map reuseMaps mapStyle={mapStyle} ref={(ref) => ref && setMap(ref)} />
    </DeckGL>
  );
}

export function renderToDOM(container: HTMLElement) {
  createRoot(container).render(<App />);
}
