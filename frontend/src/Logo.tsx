import React from "react";
import "bootstrap/dist/css/bootstrap.min.css";
import "./styles.css"; // Assuming the CSS class `.space-grotesk-extrabold` is defined here

const Logo: React.FC = () => {
  return (
    <div
      className="position-fixed text-center"
      style={{
        top: "60px",
        left: "0",
        right: "0",
        zIndex: 1050,
        pointerEvents: "none", // Makes it non-interactive
      }}
    >
      <div
        className="d-inline-block px-5 py-2 rounded shadow bg-light"
        style={{
          color: "black",
          maxWidth: "90%", // Ensure it fits smaller screens
          pointerEvents: "auto", // Enables interactions if needed
          fontWeight: 500, // Ensures the font is clearly visible
        }}
      >
        <span
          className="space-grotesk-regular"
          style={{
            fontSize: "1.5rem",
          }}
        >
          EasyOpenData
        </span>
      </div>
    </div>
  );
};

export default Logo;
