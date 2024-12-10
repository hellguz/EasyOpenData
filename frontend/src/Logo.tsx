import React from "react";
import "bootstrap/dist/css/bootstrap.min.css";
import "./styles.css";

const Logo: React.FC = () => {
  return (
    <div
      className="d-inline-block px-5 py-2 rounded shadow bg-light"
      style={{
        color: "black",
        pointerEvents: "auto",
        fontWeight: 500,
      }}
    >
      <span
        className="space-grotesk-regular"
        style={{
          fontSize: "2rem",
        }}
      >
        EasyOpenData
      </span>
    </div>
  );
};

export default Logo;
