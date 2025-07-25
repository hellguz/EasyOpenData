import React, { useCallback, useState, useRef, useEffect, useMemo } from "react";
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
import Logo from "./Logo";
import * as turf from "@turf/turf";
import "bootstrap/dist/css/bootstrap.min.css";

import DrawControl from './draw-control';
import LegalDocuments from "./Legals";

import './styles.css'
import './colors.css'

const BASE_URL = import.meta.env.VITE_BASE_URL;
const TILESET_URL = import.meta.env.VITE_TILESET_URL;

const INITIAL_VIEW_STATE: MapViewState = {
  latitude: 49.97445,
  longitude: 9.1464,
  pitch: 28,
  maxPitch: 60,
  bearing: 0,
  minZoom: 2,
  maxZoom: 30,
  zoom: 17,
};

const MAP_STYLE = "/basemap.json";

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
  const [showBoundaries, setShowBoundaries] = useState(false);
  const mapRef = useRef<any>(null); // Reference to the map instance

  const drawRef = useRef<MapboxDraw | null>(null); // Reference to the MapboxDraw instance

  const rootStyles = getComputedStyle(document.documentElement);
  const POLYGON_COLOR = rootStyles.getPropertyValue('--bs-secondary').trim();
  const POLYGON_SELECTED_COLOR = rootStyles.getPropertyValue('--bs-secondary-selected').trim();

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
        styles: [
          {
            id: 'gl-draw-polygon-fill',
            type: 'fill',
            paint: {
              'fill-color': POLYGON_COLOR,
              'fill-opacity': 0.5, // Adjust transparency if needed
            },
          },
          // Selected Polygon Fill
          {
            id: 'gl-draw-polygon-fill-active',
            type: 'fill',
            filter: ['all', ['==', '$type', 'Polygon'], ['==', 'active', 'true']],
            paint: {
              'fill-color': POLYGON_SELECTED_COLOR,
              'fill-opacity': 0.5,
            },
          },
          // Default Polygon Stroke
          {
            id: 'gl-draw-polygon-stroke',
            type: 'line',
            paint: {
              'line-color': POLYGON_SELECTED_COLOR,
              'line-width': 4,
            },
          },
          // Selected Polygon Stroke
          {
            id: 'gl-draw-polygon-stroke-active',
            type: 'line',
            filter: ['all', ['==', '$type', 'Polygon'], ['==', 'active', 'true']],
            paint: {
              'line-color': POLYGON_SELECTED_COLOR,
              'line-width': 6,
            },
          },
          {
            id: 'gl-draw-point',
            type: 'circle',
            filter: ['all', ['!=', 'meta', 'midpoint']],
            paint: {
              'circle-radius': 12,
              'circle-color': POLYGON_SELECTED_COLOR,
            },
          },
          {
            id: 'gl-draw-point-active',
            type: 'circle',
            filter: ['all', ['!=', 'meta', 'midpoint'], ['==', 'active', 'true']],
            paint: {
              'circle-radius': 8,
              'circle-color': POLYGON_COLOR,
            },
          },
          // Midpoints
          {
            id: 'gl-draw-midpoint',
            type: 'circle',
            filter: ['all', ['==', 'meta', 'midpoint']],
            paint: {
              'circle-radius': 8,
              'circle-color': POLYGON_SELECTED_COLOR,
            },
          },
        ]
      });
      map.addControl(drawRef.current);
    }

    // Bind event listeners for onUpdate and onDelete
    map.on('draw.create', onUpdate); // Bind onUpdate callback
    map.on('draw.update', onUpdate); // Bind onUpdate callback
    map.on('draw.delete', onDelete); // Bind onDelete callback

    // Fetch the tileset JSON, extract subtiles regions, and add a GeoJSON layer for boundaries
    fetch(TILESET_URL)
      .then(res => res.json())
      .then((data: any) => {
        const regions: number[][] = [];
        // Recursive traversal to collect regions from any node that has content (i.e., subtiles)
        function traverse(node: any) {
          if (node.boundingVolume && node.boundingVolume.region && node.content) {
            regions.push(node.boundingVolume.region);
          }
          if (node.children) {
            node.children.forEach((child: any) => traverse(child));
          }
        }
        traverse(data.root);
        // Convert each region (in radians) to a GeoJSON polygon in degrees
        const geojsonFeatures = regions.map(region => {
          const [west, south, east, north] = region;
          const westDeg = (west * 180) / Math.PI;
          const southDeg = (south * 180) / Math.PI;
          const eastDeg = (east * 180) / Math.PI;
          const northDeg = (north * 180) / Math.PI;
          return {
            type: 'Feature',
            geometry: {
              type: 'Polygon',
              coordinates: [[
                [westDeg, southDeg],
                [eastDeg, southDeg],
                [eastDeg, northDeg],
                [westDeg, northDeg],
                [westDeg, southDeg],
              ]],
            },
            properties: {},
          };
        });
        const geojson = { type: 'FeatureCollection', features: geojsonFeatures };

        // Add the source and layer for subtiles boundaries
        if (!map.getSource('subtiles-boundaries')) {
          map.addSource('subtiles-boundaries', {
            type: 'geojson',
            data: geojson,
          });
          map.addLayer({
            id: 'subtiles-boundaries-layer',
            type: 'line',
            source: 'subtiles-boundaries',
            layout: {
              visibility: showBoundaries ? 'visible' : 'none',
            },
            paint: {
              'line-color': '#0000FF',
              'line-width': 1,
            },
          });
        }
      })
      .catch(err => console.error("Error fetching tileset JSON", err));
  }, [showBoundaries]);

  // Update layer visibility whenever showBoundaries changes
  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (map && map.getLayer('subtiles-boundaries-layer')) {
      map.setLayoutProperty(
        'subtiles-boundaries-layer',
        'visibility',
        showBoundaries ? 'visible' : 'none'
      );
    }
  }, [showBoundaries]);

  // Listen for the 'B' key to toggle boundaries
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'b' || event.key === 'B') {
        setShowBoundaries(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const onUpdate = useCallback((e: { features: any[]; }) => {
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

  const onDelete = useCallback((e: { features: any[]; }) => {
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
    if (drawRef.current) {
      const data = drawRef.current.getAll();
      if (data.features.length > 0) {
        try {
          const response = await fetch(`${BASE_URL}/retrieve_obj`, {
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

    if (newZoom < 16) {
      setIsLod2Visible(false);
    } else {
      setIsLod2Visible(true);
    }
  };

  const ambientLight = new AmbientLight({
    color: [240, 255, 255],
    intensity: 1.0
  });

  const directionalLight1 = new DirectionalLight({
    color: [220, 255, 255],
    intensity: 0.6,
    direction: [-1, -3, -1]
  });

  const directionalLight2 = new DirectionalLight({
    color: [255, 220, 255],
    intensity: 1,
    direction: [1, -3, 1]
  });

  const lightingEffect = new LightingEffect({ ambientLight, directionalLight1, directionalLight2 });

  const layers = useMemo(() => [
    new Tile3DLayer({
      id: "tile-3d-layer",
      data: TILESET_URL,
      visible: isLod2Visible,
      loadOptions: {
        fetch: (url, options) => {
          return fetch(url, options);
        },
        tileset: {
          maxRequests: 32,
        }
      },
      _subLayerProps: {
        scenegraph: {
          getColor: () => [255, 255, 255, 255],
        }
      }
    }),
  ], [TILESET_URL, isLod2Visible]);

  const handleSearch = async (query: string) => {
    const response = await fetch(
      `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&countrycodes=de`
    );
    const data = await response.json();
    return data;
  };

  const handleSelectResult = (result: any) => {
    const map = mapRef.current.getMap();
    map.flyTo({
      center: [parseFloat(result.lon), parseFloat(result.lat)],
      zoom: 14
    });
  };

  return (
    <div style={{ position: "fixed", width: "100%", height: "100%" }}>
      <Map
        initialViewState={viewState}
        mapStyle={MAP_STYLE}
        onLoad={handleMapLoad}
        onMove={handleZoomChange}
        ref={mapRef}
        style={{ width: "100%", height: "100%" }}
        hash={true}
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
        <DeckGLOverlay layers={layers} />
      </Map>
      <FloatingPanel
        onDrawPolygon={handleDrawPolygon}
        onRemovePolygon={handleRemovePolygon}
        onFetchObjFile={handleFetchObjFile}
        polygonArea={polygonArea}
        onSearch={handleSearch}
        onSelectResult={handleSelectResult}
      />
      <div className="top-bar-container">
        <div className="top-bar-section legals">
          <LegalDocuments />
        </div>
        <div className="top-bar-section logo">
          <Logo />
        </div>
      </div>
    </div>
  );
}
 
export default Root;
