// App.tsx
import React, { useCallback, useState, useRef, useEffect } from "react"; // Removed useMemo if not used
import { mat4, vec3 } from 'gl-matrix'; // For vector and matrix math
import { createRoot } from "react-dom/client";
import {
  Map,
  NavigationControl,
  Popup,
  useControl,
} from "react-map-gl/maplibre";
import { Tile3DLayer, MapViewState, AmbientLight, DirectionalLight, LightingEffect, PolygonLayer } from "deck.gl"; // Added PolygonLayer
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
  latitude: 49.8917,
  longitude: 10.8863,
  pitch: 45,
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
  const [allTiles, setAllTiles] = useState<any[]>([]); // Existing from step 1
  const [subtilesetBoundaryPolygons, setSubtilesetBoundaryPolygons] = useState<any[]>([]); // New state
  const [showSubtilesetBoundaries, setShowSubtilesetBoundaries] = useState(false); // New state
  const [isLod2Visible, setIsLod2Visible] = useState(true);
  const [polygonArea, setPolygonArea] = useState<number | null>(null);
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

  const onTilesetLoad = (tileset: Tileset3D) => {
    // Option 2: Store only root and its direct children, or tiles with content.uri
    // This is a more targeted approach if "subtilesets" are expected to be direct children
    // or explicitly defined by a content URI pointing to another tileset.json
    const relevantTiles: any[] = []; // Use any[] for now, refine if needed

    // function findRelevantTiles(tile, depth = 0) {
    //   if (!tile) return;

    //   // Heuristic: A tile that has content with a URI is a candidate for a "subtileset root"
    //   // Or, any direct child of the main root might be considered a subtileset.
    //   // For now, let's collect all tiles and their content URIs to allow flexible processing later.
    //   relevantTiles.push({
    //     id: tile.id,
    //     boundingVolume: tile.boundingVolume, // This is what we need for the box
    //     contentUri: tile.content?.uri, // URI of the content (e.g., b3dm, or another tileset.json)
    //     lodMetricValue: tile.lodMetricValue,
    //     transform: tile.transform, // Matrix to transform the boundingVolume to world space
    //     children: tile.children // Keep children to potentially traverse deeper if needed
    //   });

    //   // If we only want direct children of the root, or tiles that are external tilesets:
    //   // if (depth === 0 || (tile.content?.uri && tile.content.uri.endsWith('.json'))) {
    //   //   relevantTiles.push({ id: tile.id, boundingVolume: tile.boundingVolume, contentUri: tile.content?.uri });
    //   // }
    //   // if (tile.children && depth < 1) { // Only go one level deep from root for example
    //   // tile.children.forEach(child => findRelevantTiles(child, depth + 1));
    //   // }
    // }

    if (tileset && tileset.root) {
      // To get all tiles, we need to traverse the tree:
      const queue = [tileset.root];
      while (queue.length > 0) {
          const tile = queue.pop();
          if (tile) {
              relevantTiles.push({
                  id: tile.id,
                  boundingVolume: tile.boundingVolume,
                  contentUri: tile.content?.uri,
                  lodMetricValue: tile.lodMetricValue,
                  transform: tile.transform,
                  // Store a simplified children array or just their IDs if the full objects are too much
                  // For now, let's not store children in this flattened list to avoid circular refs in state,
                  // unless we process them carefully. The main `tileset` object itself can be traversed if needed.
                  // We are primarily interested in the bounding volumes of tiles that represent subtilesets.
              });
              if (tile.children) {
                  tile.children.forEach(child => queue.push(child));
              }
          }
      }
    }
    setAllTiles(relevantTiles);

    // Original onTilesetLoad logic for camera positioning (if it was there)
    // const { cartographicCenter, zoom } = tileset;
    // setViewState((prev) => ({
    //   ...prev,
    //   longitude: cartographicCenter[0],
    //   latitude: cartographicCenter[1],
    //   zoom,
    // }));
  };

  useEffect(() => {
    if (!allTiles || allTiles.length === 0) {
      setSubtilesetBoundaryPolygons([]);
      return;
    }

    const newPolygons: any[] = [];
    allTiles.forEach(tile => {
      // Filter for tiles that might be subtilesets.
      // Given user feedback, tiles with content.uri ending in .json are subtilesets.
      // Also, these subtilesets in the example use `boundingVolume.region`.
      if (tile.contentUri && tile.contentUri.endsWith('.json') && tile.boundingVolume) {
        let polygonCoordinates: number[][] | null = null;

        if (tile.boundingVolume.region) {
          // Region: [west, south, east, north, minHeight, maxHeight] in radians
          const region = tile.boundingVolume.region;
          const radToDeg = (rad: number) => rad * 180 / Math.PI;

          polygonCoordinates = [
            [radToDeg(region[0]), radToDeg(region[1])], // west, south
            [radToDeg(region[2]), radToDeg(region[1])], // east, south
            [radToDeg(region[2]), radToDeg(region[3])], // east, north
            [radToDeg(region[0]), radToDeg(region[3])], // west, north
            [radToDeg(region[0]), radToDeg(region[1])]  // close polygon (repeating first point)
          ];
        } else if (tile.boundingVolume.box) {
          // Fallback for boxes, though user example uses regions
          const boxData = tile.boundingVolume.box; // [cx, cy, cz, uxx, uxy, uxz, uyx, uyy, uyz, uzx, uzy, uzz]

          const center = vec3.fromValues(boxData[0], boxData[1], boxData[2]);
          // Half-axis vectors for x, y, z
          const halfX = vec3.fromValues(boxData[3], boxData[4], boxData[5]);
          const halfY = vec3.fromValues(boxData[6], boxData[7], boxData[8]);
          // const halfZ = vec3.fromValues(boxData[9], boxData[10], boxData[11]);


          // Calculate the 8 corners of the box in its local coordinate system
          // For a 2D footprint, we're interested in the projection onto the XY plane.
          // Let's define corners based on the center and half-axis vectors.
          // These are corners of the base of the box if Z points up.
          const localCorners = [
            vec3.create(), vec3.create(), vec3.create(), vec3.create()
          ];

          // Corner 1: center - halfX - halfY
          vec3.sub(localCorners[0], center, halfX);
          vec3.sub(localCorners[0], localCorners[0], halfY);

          // Corner 2: center + halfX - halfY
          vec3.add(localCorners[1], center, halfX);
          vec3.sub(localCorners[1], localCorners[1], halfY);

          // Corner 3: center + halfX + halfY
          vec3.add(localCorners[2], center, halfX);
          vec3.add(localCorners[2], localCorners[2], halfY);

          // Corner 4: center - halfX + halfY
          vec3.sub(localCorners[3], center, halfX);
          vec3.add(localCorners[3], localCorners[3], halfY);

          const worldCorners = localCorners.map(lc => {
            const wc = vec3.create();
            if (tile.transform && tile.transform.length === 16) {
              vec3.transformMat4(wc, lc, tile.transform);
            } else {
              vec3.copy(wc, lc); // No transform, use local coordinates directly
            }
            return wc;
          });

          // Assuming the X and Y coordinates of the transformed corners represent Lon/Lat
          // This is a placeholder and might need adjustment if the CRS is not geographic
          const lonLatCorners = worldCorners.map(wc => [wc[0], wc[1]]);

          if (lonLatCorners.length === 4) {
             polygonCoordinates = [...lonLatCorners, lonLatCorners[0]]; // Close the polygon
          }
        }

        if (polygonCoordinates) {
          newPolygons.push({
            id: tile.id || tile.contentUri, // Use contentUri as a fallback id
            tileInfo: { id: tile.id, contentUri: tile.contentUri, boundingVolume: tile.boundingVolume },
            polygon: polygonCoordinates
          });
        }
      }
    });
    setSubtilesetBoundaryPolygons(newPolygons);
  }, [allTiles]);

  // useEffect for keyboard listener to toggle boundary visibility
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 'b') {
        setShowSubtilesetBoundaries(prevShowBoundaries => !prevShowBoundaries);
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    // Cleanup function to remove the event listener
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, []); // Empty dependency array ensures this runs once on mount and cleans up on unmount

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
          const response = await fetch(BASE_URL + "/retrieve_obj", {
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
    if (newZoom < 12) {
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
    color: [255, 220, 255],
    intensity: 1,
    direction: [1, -3, 1]
  });

  // Create lighting effect
  const lightingEffect = new LightingEffect({ ambientLight, directionalLight1, directionalLight2 });


  const layers = [
    new Tile3DLayer({
      id: "tile-3d-layer",
      data: TILESET_URL,
      // pickable: true,
      // autoHighlight: false,
      // onClick: (info, event) => console.log("Clicked:", info, event),
      // getPickingInfo: (pickParams) => console.log("PickInfo", pickParams),
      onTilesetLoad, // Add this
      visible: isLod2Visible,
      // For ScenegraphLayer (b3dm or i3dm format)
      //_lighting: 'pbr',
      //effects: [lightingEffect],
      // loadOptions: {
      //   tileset: {
      //     maxRequests: 16,
      //     updateTransforms: false,
      //     maximumMemoryUsage: 512
      //     //maximumScreenSpaceError: 16, // Adjust this value as needed
      //     //viewDistanceScale: 1.5 // Adjust this value as needed
      //   }
      // },
      // Additional sublayer props for fine-grained control
      _subLayerProps: {
        scenegraph: {
          getColor: (d) => [255, 255, 255, 255], // Blue color for scenegraph models (alternative method)
          //effects: [lightingEffect]
        }
      }
    }),
    // Add the new PolygonLayer for boundaries
    new PolygonLayer({
      id: 'subtileset-boundaries-layer',
      data: subtilesetBoundaryPolygons, // Data from state
      pickable: false,
      stroked: true,
      filled: false,
      lineWidthUnits: 'pixels', // Use pixels for line width
      lineWidthMinPixels: 1,
      getPolygon: (d: any) => {
        // Check if d and d.polygon exist and d.polygon is an array
        if (d && d.polygon && Array.isArray(d.polygon)) {
          // Ensure each point in the polygon is also an array (lon, lat)
          // This helps prevent errors if data is malformed.
          const isPolygonValid = d.polygon.every((point: any) => Array.isArray(point) && point.length >= 2);
          if (isPolygonValid) {
            return d.polygon;
          }
        }
        // Return a dummy or empty polygon if data is invalid to avoid layer crashing
        return [];
      },
      getLineColor: [0, 0, 255, 255], // Blue color (R, G, B, A)
      getLineWidth: 1,
      visible: showSubtilesetBoundaries, // Control visibility with the new state
    })
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
    <div style={{ position: "fixed", width: "100%", height: "100%" }}>
      <Map
        initialViewState={viewState}
        mapStyle={MAP_STYLE}
        onLoad={handleMapLoad} // Ensure map is passed here
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
        <DeckGLOverlay layers={layers}   //effects={[lightingEffect]} // Apply the custom lighting effect globally
        />
        {/* <DrawControl
          ref={drawRef}
          onCreate={onUpdate}
          onUpdate={onUpdate}
          onDelete={onDelete}
        /> */}
        {/* <div
          style={{
            position: 'absolute',
            bottom: '240px', // Adjust as needed to ensure a 20px gap above Auswahl panel
            left: '20px',
            zIndex: 2000,
            pointerEvents: 'none',
          }}
        >
          <div style={{ pointerEvents: 'auto' }}>
            <NavigationControl />
          </div>
        </div> */}
        {/* <DrawControl
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
        /> */}
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

interface DrawControlProps {
  onCreate: (e: any) => void;
  onUpdate: (e: any) => void;
  onDelete: (e: any) => void;
}

export default Root;
