import React, {useCallback, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Map, NavigationControl, Popup, useControl} from 'react-map-gl/maplibre';
import {GeoJsonLayer, ArcLayer, MapViewState, Tile3DLayer} from 'deck.gl';
import {MapboxOverlay as DeckOverlay} from '@deck.gl/mapbox';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Tileset3D } from "@loaders.gl/tiles";
import MapboxDraw from '@mapbox/mapbox-gl-draw';
import { Editor, DrawPolygonMode } from 'react-map-gl-draw';
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
function DeckGLOverlay(props) {
  const overlay = useControl(() => new DeckOverlay(props));
  overlay.setProps(props);
  return null;
}

function Root() {
  const [selected, setSelected] = useState(null);
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

  };
  const [features, setFeatures] = useState({});

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
  const layers = [
    new Tile3DLayer({
      id: "tile-3d-layer",
      pointSize: 2,
      data: TILESET_URL,
      onTilesetLoad,
    }),
    new GeoJsonLayer({
      id: 'airports',
      data: AIR_PORTS,
      // Styles
      filled: true,
      pointRadiusMinPixels: 2,
      pointRadiusScale: 2000,
      getPointRadius: f => 11 - f.properties.scalerank,
      getFillColor: [200, 0, 80, 180],
      // Interactive props
      pickable: true,
      autoHighlight: true,
      onClick: info => setSelected(info.object)
      // beforeId: 'watername_ocean' // In interleaved mode, render the layer under map labels
    })
  ];

  return (
    <Map initialViewState={INITIAL_VIEW_STATE} mapStyle={MAP_STYLE}>
      {selected && (
        <Popup
          key={selected.properties.name}
          anchor="bottom"
          style={{zIndex: 10}} /* position above deck.gl canvas */
          longitude={selected.geometry.coordinates[0]}
          latitude={selected.geometry.coordinates[1]}
        >
          {selected.properties.name} ({selected.properties.abbrev})
        </Popup>
      )}
 
      <DeckGLOverlay layers={layers} /* interleaved*/ />
      <DrawControl
        position="top-left"
        displayControlsDefault={false}
        controls={{
          polygon: true,
          trash: true
        }}
        defaultMode="draw_polygon"
        onCreate={onUpdate}
        onUpdate={onUpdate}
        onDelete={onDelete}
      />
      <NavigationControl position="top-left" />
    </Map>
  );
}

function DrawControl(props) {
  useControl(
    ({ map }) => {
      const draw = new MapboxDraw(props);
      map.addControl(draw);
      return draw;
    },
    { position: props.position }
  );

  return null;
}
/* global document */
const container = document.body.appendChild(document.createElement('div'));
createRoot(container).render(<Root />);