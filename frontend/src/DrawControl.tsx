// DrawControl.tsx
import React, { useEffect, useRef } from "react";
import { useControl } from "react-map-gl"; // Ensure you're importing from the correct package
import MapboxDraw from "@mapbox/mapbox-gl-draw";
import "@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css";

interface DrawControlProps {
  onCreate: (e: any) => void;
  onUpdate: (e: any) => void;
  onDelete: (e: any) => void;
}

const DrawControl = React.forwardRef<MapboxDraw, DrawControlProps>(
  ({ onCreate, onUpdate, onDelete }, ref) => {
    const drawRef = useRef<MapboxDraw | null>(null);

    useEffect(() => {
      if (!drawRef.current) {
        // Initialize MapboxDraw
        const draw = new MapboxDraw({
          displayControlsDefault: false,
          controls: {
            polygon: false,
            trash: false,
          },
          defaultMode: "simple_select",
          styles: [
            // [Your existing styles here]
            // ... (omitted for brevity)
          ],
        });

        // Add the draw control to the map
        map.addControl(draw, "top-left");
        drawRef.current = draw;

        // Set up event listeners
        map.on("draw.create", onCreate);
        map.on("draw.update", onUpdate);
        map.on("draw.delete", onDelete);

        // Expose the draw instance to parent via ref
        if (ref && typeof ref !== "function") {
          ref.current = draw;
        }
      }

      // Cleanup function to remove the control and listeners
      return () => {
        if (drawRef.current) {
          map.removeControl(drawRef.current);
          map.off("draw.create", onCreate);
          map.off("draw.update", onUpdate);
          map.off("draw.delete", onDelete);
          drawRef.current = null;
        }
      };
    }, [onCreate, onUpdate, onDelete, ref]);

    return null;
  }
);

export default DrawControl;
