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
        maxWidth: "500px",
        position: "relative",
      }}
    >
      <div
        className="space-grotesk-regular text-end"
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
            fontSize: "0.9rem",
            marginTop: "0.5rem",
            lineHeight: "1.5",
          }}
        >
          <strong>
            Laden Sie präzise Gebäudegeometrie als .obj-Dateien herunter.<br />
            Kosten: Polygonfläche × 50 €/km²<br />
            Nach Zahlung erhalten Sie direkt Ihren Download-Link.
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
