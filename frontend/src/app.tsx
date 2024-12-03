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

import './App.css'

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL
const TILESET_URL = BACKEND_URL + '/tileset/tileset.json';

const INITIAL_VIEW_STATE: MapViewState = { 
  latitude: 48.1351,
  longitude: 11.5820,
  pitch: 45, 
  maxPitch: 60,
  bearing: 0,
  minZoom: 2,
  maxZoom: 30,
  zoom: 17,
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
  // const onTilesetLoad = (tileset: Tileset3D) => {
  //   const { cartographicCenter, zoom } = tileset;
  //   setViewState((prev) => ({
  //     ...prev,
  //     longitude: cartographicCenter[0],
  //     latitude: cartographicCenter[1],
  //     zoom,
  //   }));
  // };


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
      // pickable: true,
      // autoHighlight: false,
      // onClick: (info, event) => console.log("Clicked:", info, event),
      // getPickingInfo: (pickParams) => console.log("PickInfo", pickParams),
      // onTilesetLoad,
      visible: isLod2Visible,
      // For ScenegraphLayer (b3dm or i3dm format)
      _lighting: 'pbr',
      effects: [lightingEffect],
      loadOptions: {
        tileset: {
          maximumScreenSpaceError: 16, // Adjust this value as needed
          viewDistanceScale: 1.5 // Adjust this value as needed
        }
      },
      // Additional sublayer props for fine-grained control
      _subLayerProps: {
        scenegraph: {
          getColor: (d) => [254, 254, 254, 255], // Blue color for scenegraph models (alternative method)
      effects: [lightingEffect]
        }
      }
    }),
  ];

  const handleSearch = async (query: string) => {
    const response = await fetch(
      `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&countrycodes=de`
    );
    const data = await response.json();
    return data;
  };
  
  const handleSelectResult = (result: any) => {
    // Fly to the selected location
    const map = mapRef.current.getMap();

    map.flyTo({
      center: [parseFloat(result.lon), parseFloat(result.lat)],
      zoom: 14
    });
  };

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
  onSearch={handleSearch}
  onSelectResult={handleSelectResult}
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

const container = document.body.appendChild(document.createElement("div"));
createRoot(container).render(<Root />);
