// Root.tsx
import React, { useCallback, useState, useRef, useEffect } from "react";
import { createRoot } from "react-dom/client";
import {
  Map,
  NavigationControl,
  Popup,
  useControl,
} from "react-map-gl/maplibre";
import { Tile3DLayer, MapViewState, AmbientLight, DirectionalLight, LightingEffect } from "deck.gl";
import { MapboxOverlay as DeckOverlay } from "@deck.gl/mapbox";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Tileset3D } from "@loaders.gl/tiles";
import MapboxDraw from "@mapbox/mapbox-gl-draw";
import "@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css";
import FloatingPanel from "./FloatingPanel";
import * as turf from "@turf/turf";
import "bootstrap/dist/css/bootstrap.min.css";

import DrawControl from './draw-control';
import LegalDocuments from "./Legals";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL
const TILESET_URL = BACKEND_URL + '/tileset/tileset.json';

const INITIAL_VIEW_STATE: MapViewState = {
  latitude: 49.8988,
  longitude: 10.9028,   
  pitch: 45,
  maxPitch: 60,
  bearing: 0,
  minZoom: 2,
  maxZoom: 30,
  zoom: 15,
};

const MAP_STYLE = "./src/basemap.json";

function DeckGLOverlay(props: any) {
  const overlay = useControl(() => new DeckOverlay(props));
  overlay.setProps(props);
  return null;
}

function Root() {
  const [selected, setSelected] = useState<any>(null);
  const [viewState, setViewState] = useState<MapViewState>(INITIAL_VIEW_STATE);
  const [features, setFeatures] = useState<Record<string, any>>({});
  const [isLod2Visible, setIsLod2Visible] = useState(true);
  const [polygonArea, setPolygonArea] = useState<number | null>(null);
  const mapRef = useRef<any>(null); // Reference to the map instance

  const drawRef = useRef<MapboxDraw | null>(null); // Reference to the MapboxDraw instance

  // Initialize MapboxDraw and add it to the map
  const handleMapLoad = useCallback(() => {
    const map = mapRef.current.getMap();

    // Initialize MapboxDraw if not already initialized
    if (!drawRef.current) {
      drawRef.current = new MapboxDraw({
        displayControlsDefault: false,
        controls: {
          polygon: false,
          trash: false,
        },
      });
      map.addControl(drawRef.current);
    }
  }, []);
  const onTilesetLoad = (tileset: Tileset3D) => {
    const { cartographicCenter, zoom } = tileset;
    setViewState((prev) => ({
      ...prev,
      longitude: cartographicCenter[0],
      latitude: cartographicCenter[1],
      zoom,
    }));
  };

  onTileLoad: (tile) => {
    tile.content.traverse((object) => {
      if (object.isMesh) {
        // Adjust colors if needed
        object.material.color.setHex(0xffffff);
      }
    });
  }

  const onUpdate = useCallback((e) => {
    setFeatures((currFeatures) => {
      const newFeatures = { ...currFeatures };
      for (const f of e.features) {
        newFeatures[f.id] = f;
      }
      return newFeatures;
    });

    // Calculate polygon area
    if (e.features && e.features.length > 0) {
      const polygon = e.features[0];
      const area = turf.area(polygon) / 1e6; // Convert from m² to km²
      setPolygonArea(area);
    }
  }, []);

  const onDelete = useCallback((e) => {
    setFeatures((currFeatures) => {
      const newFeatures = { ...currFeatures };
      for (const f of e.features) {
        delete newFeatures[f.id];
      }
      return newFeatures;
    });
    setPolygonArea(null);
  }, []);

  const handleDrawPolygon = () => {
    if (drawRef.current) {
      drawRef.current.deleteAll();
      drawRef.current.changeMode("draw_polygon");
    }
  };

  const handleRemovePolygon = () => {
    if (drawRef.current) {
      drawRef.current.deleteAll();
    }
  };

  const handleFetchObjFile = async () => {
    console.info("getFetchObjFile")
    if (drawRef.current) {
      const data = drawRef.current.getAll();
      if (data.features.length > 0) {
        try {
          const response = await fetch(BACKEND_URL + "/retrieve_obj", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ region: data }),
          });

          if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.style.display = "none";
            a.href = url;
            // Use the filename from the Content-Disposition header if available
            const contentDisposition = response.headers.get("Content-Disposition");
            const filenameMatch =
              contentDisposition && contentDisposition.match(/filename="?(.+)"?/i);
            a.download = filenameMatch
              ? filenameMatch[1]
              : `object_file.obj`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
          } else {
            console.error("Failed to fetch obj file");
          }
        } catch (error) {
          console.error("Error fetching obj file:", error);
        }
      } else {
        console.error("No polygon drawn");
      }
    }
  };

  const handleZoomChange = (event: any) => {
    const newZoom = event.viewState.zoom;
    setViewState(event.viewState);

    // Toggle visibility based on zoom level
    if (newZoom < 15) {
      setIsLod2Visible(false);
    } else {
      setIsLod2Visible(true);
    }
  };

// Create ambient light
const ambientLight = new AmbientLight({
  color: [240, 255, 255],
  intensity: 1.0
});

// Create directional light
const directionalLight1 = new DirectionalLight({
  color: [220, 255, 255],
  intensity: 0.6,
  direction: [-1, -3, -1]
});

// Create directional light
const directionalLight2 = new DirectionalLight({
  color:  [255, 220, 255],
  intensity: 1,
  direction: [1, -3, 1]
});

// Create lighting effect
const lightingEffect = new LightingEffect({ambientLight, directionalLight1 ,directionalLight2});


  const layers = [
    new Tile3DLayer({
      id: "tile-3d-layer",
      data: TILESET_URL,
      pickable: true,
      autoHighlight: false,
      onClick: (info, event) => console.log("Clicked:", info, event),
      getPickingInfo: (pickParams) => console.log("PickInfo", pickParams),
      onTilesetLoad,
      visible: true,
      // For ScenegraphLayer (b3dm or i3dm format)
      _lighting: 'pbr',
      effects: [lightingEffect],
      // Additional sublayer props for fine-grained control
      _subLayerProps: {
        scenegraph: {
          getColor: (d) => [254, 254, 254, 255], // Blue color for scenegraph models (alternative method)
      effects: [lightingEffect]
        }
      }
    }),
  ];


  return (
    <div style={{ position: "relative", width: "100%", height: "100vh" }}>
      <Map
        initialViewState={viewState}
        mapStyle={MAP_STYLE}
        onLoad={handleMapLoad} // Ensure map is passed here
        onMove={handleZoomChange}
        ref={mapRef}
        style={{ width: "100%", height: "100%" }}
      >
        {selected && (
          <Popup
            key={selected.properties.name}
            anchor="bottom"
            style={{ zIndex: 10 }}
            longitude={selected.geometry.coordinates[0]}
            latitude={selected.geometry.coordinates[1]}
          >
            {selected.properties.name} ({selected.properties.abbrev})
          </Popup>
        )}
        <DeckGLOverlay layers={layers}   effects={[lightingEffect]} // Apply the custom lighting effect globally
 />
        {/* <DrawControl
          ref={drawRef}
          onCreate={onUpdate}
          onUpdate={onUpdate}
          onDelete={onDelete}
        /> */}
        <NavigationControl position="top-left" />

        <DrawControl
          position="top-right"
          displayControlsDefault={false}
          controls={{
            polygon: false,
            trash: false
          }}
          defaultMode="draw_polygon"
          onCreate={onUpdate}
          onUpdate={onUpdate}
          onDelete={onDelete}
        />
      </Map>
      <FloatingPanel
        onDrawPolygon={handleDrawPolygon}
        onRemovePolygon={handleRemovePolygon}
        onFetchObjFile={handleFetchObjFile}
        polygonArea={polygonArea}
      />
      
      <LegalDocuments />
    </div>
  );
}

interface DrawControlProps {
  onCreate: (e: any) => void;
  onUpdate: (e: any) => void;
  onDelete: (e: any) => void;
}

// const DrawControl = React.forwardRef<MapboxDraw, DrawControlProps>(
//   (props, ref) => {
//     useControl(
//       ({ map }) => {
//         const draw = new MapboxDraw({
//           displayControlsDefault: false,
//           controls: {
//             polygon: false,
//             trash: false,
//           },
//           defaultMode: "simple_select",
//           styles: [
//             // === Active Polygon Styles ===
//             // Active polygon fill
//             {
//               id: "gl-draw-polygon-fill",
//               type: "fill",
//               filter: [
//                 "all",
//                 ["==", "$type", "Polygon"],
//                 ["!=", "mode", "static"],
//               ],
//               paint: {
//                 "fill-color": "#ff0000", // Red color
//                 "fill-opacity": 0.7, // 70% opacity
//               },
//             },
//             // Active polygon outline
//             {
//               id: "gl-draw-polygon-stroke-active",
//               type: "line",
//               filter: [
//                 "all",
//                 ["==", "$type", "Polygon"],
//                 ["!=", "mode", "static"],
//               ],
//               layout: {},
//               paint: {
//                 "line-color": "#ff0000", // Red color
//                 "line-width": 2,
//               },
//             },
//             // === Inactive Polygon Styles ===
//             // Inactive polygon fill
//             {
//               id: "gl-draw-polygon-fill-inactive",
//               type: "fill",
//               filter: [
//                 "all",
//                 ["==", "$type", "Polygon"],
//                 ["==", "mode", "static"],
//               ],
//               paint: {
//                 "fill-color": "#ff0000", // Red color
//                 "fill-opacity": 0.7, // 70% opacity
//               },
//             },
//             // Inactive polygon outline
//             {
//               id: "gl-draw-polygon-stroke-inactive",
//               type: "line",
//               filter: [
//                 "all",
//                 ["==", "$type", "Polygon"],
//                 ["==", "mode", "static"],
//               ],
//               layout: {},
//               paint: {
//                 "line-color": "#ff0000", // Red color
//                 "line-width": 2,
//               },
//             },
//             // === Line During Drawing ===
//             {
//               id: "gl-draw-polygon-and-line",
//               type: "line",
//               filter: [
//                 "all",
//                 ["==", "$type", "LineString"],
//                 ["!=", "mode", "static"],
//               ],
//               layout: {
//                 "line-cap": "round",
//                 "line-join": "round",
//               },
//               paint: {
//                 "line-color": "#ff0000", // Red color
//                 "line-dasharray": [0.2, 2],
//                 "line-width": 2,
//               },
//             },
//             // === Vertex Points During Drawing ===
//             {
//               id: "gl-draw-polygon-and-line-vertex",
//               type: "circle",
//               filter: [
//                 "all",
//                 ["==", "$type", "Point"],
//                 ["!=", "meta", "midpoint"],
//                 ["!=", "mode", "static"],
//               ],
//               paint: {
//                 "circle-radius": 5,
//                 "circle-color": "#ff0000", // Red color
//                 "circle-stroke-color": "#ffffff",
//                 "circle-stroke-width": 2,
//               },
//             },
//             // === Midpoint Points ===
//             {
//               id: "gl-draw-polygon-and-line-midpoint",
//               type: "circle",
//               filter: [
//                 "all",
//                 ["==", "$type", "Point"],
//                 ["==", "meta", "midpoint"],
//                 ["!=", "mode", "static"],
//               ],
//               paint: {
//                 "circle-radius": 5,
//                 "circle-color": "#ffffff",
//                 "circle-stroke-color": "#ff0000", // Red stroke
//                 "circle-stroke-width": 2,
//               },
//             },
//             // === Vertex Points Inactive ===
//             {
//               id: "gl-draw-polygon-and-line-vertex-inactive",
//               type: "circle",
//               filter: [
//                 "all",
//                 ["==", "$type", "Point"],
//                 ["!=", "meta", "midpoint"],
//                 ["==", "mode", "static"],
//               ],
//               paint: {
//                 "circle-radius": 5,
//                 "circle-color": "#ff0000", // Red color
//                 "circle-stroke-color": "#ffffff",
//                 "circle-stroke-width": 2,
//               },
//             },
//           ],
//         });
//         map.addControl(draw);

//         // Prevent adding the source multiple times
//         const existingSource = map.getSource("mapbox-gl-draw-cold");
//         if (existingSource) {
//           map.removeControl(draw);
//           return;
//         }

//         if (ref && typeof ref !== "function") {
//           ref.current = draw;
//         }
//         return draw;
//       },
//       { position: "top-left" }
//     );

//     return null;
//   }
// );

const container = document.body.appendChild(document.createElement("div"));
createRoot(container).render(<Root />);
