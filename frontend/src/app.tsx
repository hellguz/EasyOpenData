import React, { useCallback, useState, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { Map, NavigationControl, Popup, useControl } from 'react-map-gl/maplibre';
import { GeoJsonLayer, ArcLayer, MapViewState, Tile3DLayer } from 'deck.gl';
import { MapboxOverlay as DeckOverlay } from '@deck.gl/mapbox';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Tileset3D } from "@loaders.gl/tiles";
import MapboxDraw from '@mapbox/mapbox-gl-draw';
import '@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css';


// source: Natural Earth http://www.naturalearthdata.com/ via geojson.xyz
const AIR_PORTS =
  'https://d2ad6b4ur7yvpq.cloudfront.net/naturalearth-3.3.0/ne_10m_airports.geojson';

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

const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';


function DeckGLOverlay(props: any) {
  const overlay = useControl(() => new DeckOverlay(props));
  overlay.setProps(props);
  return null;
}

function Root() {
  const [selected, setSelected] = useState<any>(null);
  const [initialViewState, setInitialViewState] = useState<MapViewState>(INITIAL_VIEW_STATE);
  const [features, setFeatures] = useState<Record<string, any>>({});
  const drawRef = useRef<MapboxDraw | null>(null);

  const onTilesetLoad = (tileset: Tileset3D) => {
    // Recenter view to cover the new tileset
    const { cartographicCenter, zoom } = tileset;
    setInitialViewState({
      ...INITIAL_VIEW_STATE,
      longitude: cartographicCenter[0],
      latitude: cartographicCenter[1],
      zoom,
    });

  };
  const onUpdate = useCallback((e) => {
    setFeatures(currFeatures => {
      const newFeatures = { ...currFeatures };
      for (const f of e.features) {
        newFeatures[f.id] = f;
      }
      return newFeatures;
    });
  }, []);

  const onDelete = useCallback((e) => {
    setFeatures(currFeatures => {
      const newFeatures = { ...currFeatures };
      for (const f of e.features) {
        delete newFeatures[f.id];
      }
      return newFeatures;
    });
  }, []);

  const handleDrawPolygon = () => {
    if (drawRef.current) {
      drawRef.current.deleteAll();
      drawRef.current.changeMode('draw_polygon');
    }
  };

  const handleRemovePolygon = () => {
    if (drawRef.current) {
      drawRef.current.deleteAll();
    }
  };

  const handlePrintJSON = () => {
    if (drawRef.current) {
      const data = drawRef.current.getAll();
      console.log(JSON.stringify(data, null, 2));
    }
  };

  const layers = [
    new Tile3DLayer({
      id: "tile-3d-layer",
      pointSize: 2,
      data: TILESET_URL,
      onTilesetLoad,
    }),
    // new GeoJsonLayer({
    //   id: 'airports',
    //   data: AIR_PORTS,
    //   // Styles
    //   filled: true,
    //   pointRadiusMinPixels: 2,
    //   pointRadiusScale: 2000,
    //   getPointRadius: f => 11 - f.properties.scalerank,
    //   getFillColor: [200, 0, 80, 180],
    //   // Interactive props
    //   pickable: true,
    //   autoHighlight: true,
    //   onClick: info => setSelected(info.object)
    //   // beforeId: 'watername_ocean' // In interleaved mode, render the layer under map labels
    // })
  ];
  return (
    <div style={{ position: 'relative', width: '100%', height: '100vh' }}>
      <Map initialViewState={initialViewState} mapStyle={MAP_STYLE} style={{ width: '100%', height: '100%' }}>
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
        <DrawControl
          ref={drawRef}
          onCreate={onUpdate}
          onUpdate={onUpdate}
          onDelete={onDelete}
        />
        <NavigationControl position="top-left" />
      </Map>
      <div style={{
        position: 'absolute',
        bottom: '20px',
        right: '20px',
        backgroundColor: 'white',
        padding: '20px',
        borderRadius: '10px',
        boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        zIndex: 100
      }}>
        <button onClick={handleDrawPolygon}>Draw Polygon</button>
        <button onClick={handleRemovePolygon}>Remove Polygon</button>
        <button onClick={handlePrintJSON}>Print Polygon JSON</button>
      </div>
    </div>
  );
}

interface DrawControlProps {
  onCreate: (e: any) => void;
  onUpdate: (e: any) => void;
  onDelete: (e: any) => void;
}

const DrawControl = React.forwardRef<MapboxDraw, DrawControlProps>((props, ref) => {
  useControl(
    ({ map }) => {
      const draw = new MapboxDraw({
        displayControlsDefault: false,
        controls: {
          polygon: false,
          trash: false
        },
        defaultMode: "simple_select"
      });
      map.addControl(draw);
      if (ref && typeof ref !== 'function') {
        ref.current = draw;
      }
      return draw;
    },
    { position: 'top-left' }
  );

  return null;
});

const container = document.body.appendChild(document.createElement('div'));
createRoot(container).render(<Root />);