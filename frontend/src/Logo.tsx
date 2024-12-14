import React, { useState, useEffect } from "react";
import "bootstrap/dist/css/bootstrap.min.css";
import "./styles.css";

const Logo: React.FC = () => {
  const [isExpanded, setIsExpanded] = useState(true); // Control visibility
  const [timeoutId, setTimeoutId] = useState<number | null>(null);

  const toggleDescription = () => {
    setIsExpanded((prev) => !prev);

    // Clear the timeout if the user manually toggles the button
    if (timeoutId) {
      clearTimeout(timeoutId);
      setTimeoutId(null);
    }

    // Reset auto-hide timer if expanded
    if (!isExpanded) {
      const id = window.setTimeout(() => setIsExpanded(false), 30000);
      setTimeoutId(id);
    }
  };

  useEffect(() => {
    // Auto-hide description after 30 seconds
    const id = window.setTimeout(() => setIsExpanded(false), 30000);
    setTimeoutId(id);

    return () => {
      if (id) clearTimeout(id);
    };
  }, []);

  return (
    <div
      className="d-inline-block px-4 py-2 rounded shadow bg-light"
      style={{
        color: "black",
        pointerEvents: "auto",
        fontWeight: 500,
        width: "450px",
        maxWidth: "80%",
        position: "relative",
      }}
    >
      <div
        className="space-grotesk-regular text-center"
        style={{
          fontSize: "2rem",
        }}
      >
        EasyOpenData
      </div>

      {isExpanded && (
        <div
          className="text-left mb-3"
          style={{
            position: "absolute", // Make it float independently
            top: "3rem",          // Adjust the vertical positioning
            left: 0,
            width: "100%",        // Ensure it spans the logo's width
            fontSize: "1rem",
            marginTop: "0.5rem",
            lineHeight: "1.5",
            backgroundColor: "#f8f9fa",
            padding: "0.5rem",
            borderRadius: "5px",
            boxShadow: "0px 4px 6px rgba(0, 0, 0, 0.1)",
          }}

        >
          <strong>
            Zeichnen Sie ein Polygon auf der Karte ein und laden präzise Gebäudegeometrie als .obj-Dateien herunter.
            Nach Zahlung erhalten Sie direkt Ihren Download-Link.<br />
            Kosten: Polygonfläche × 50 €/km²<br />
          </strong>
        </div>
      )}

      <button
        onClick={toggleDescription}
        style={{
          position: "absolute",
          top: "0.2rem",
          right: "0.2rem",
          background: "none",
          border: "none",
          cursor: "pointer",
          fontSize: "1rem",
          fontWeight: "bold",
        }}
      >
        {isExpanded ? "–" : "+"}
      </button>
    </div>
  );
};

export default Logo;
