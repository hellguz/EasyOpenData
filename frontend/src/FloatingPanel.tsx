import React, { useState, useEffect } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { Elements } from "@stripe/react-stripe-js";
import CheckoutForm from "./CheckoutForm";
import "bootstrap/dist/css/bootstrap.min.css";

// Initialize Stripe with your publishable key
const stripePromise = loadStripe("hidden_api");

interface FloatingPanelProps {
  onDrawPolygon: () => void;
  onRemovePolygon: () => void;
  onFetchObjFile: () => void;
  polygonArea: number | null; // in square kilometers
}
const FloatingPanel: React.FC<FloatingPanelProps> = ({
  onDrawPolygon,
  onRemovePolygon,
  onFetchObjFile,
  polygonArea,
}) => {
  const [price, setPrice] = useState<number>(0);
  const [gelandeActive, setGelandeActive] = useState<boolean>(false);
  const [gebaudeActive, setGebaudeActive] = useState<boolean>(false);
  const [flurstuckeActive, setFlurstuckeActive] = useState<boolean>(false);

  useEffect(() => {
    if (polygonArea !== null) {
      if (polygonArea < 0.2) {
        setPrice(0);
      } else {
        setPrice(5 * polygonArea);
      }
    }
  }, [polygonArea]);

  return (
    <div
      className="d-flex align-items-end"
      style={{
        position: "absolute",
        bottom: "20px",
        left: "20px",
        right: "20px",
        gap: "20px",
        zIndex: 1050,
      }}
    >
      <div className="d-flex gap-3" style={{ marginRight: "auto" }}>
        
        {/* Region Panel */}
        <div
          className="bg-white rounded shadow p-3 d-flex flex-column align-items-center justify-content-center"
          style={{
            width: "300px",
            height: "200px",
          }}
        >
          <h5 className="mb-3 text-center">Region</h5>
          {polygonArea !== null ? (
            <div className="text-center mb-3">
              <p>
                <strong>Polygon Area:</strong> {polygonArea.toFixed(2)} km²
              </p>
              <p>
                <strong>Price:</strong> €{price.toFixed(2)}
              </p>
            </div>
          ) : (
            <p className="text-center mb-3">No area selected.</p>
          )}
          <div className="btn-group w-100" role="group">
            <button
              type="button"
              className="btn btn-outline-primary"
              onClick={onDrawPolygon}
            >
              Draw Polygon
            </button>
            <button
              type="button"
              className="btn btn-outline-danger"
              onClick={onRemovePolygon}
            >
              Delete Polygon
            </button>
          </div>
        </div>
        {/* Options Panel */}
        <div
          className="bg-white rounded shadow p-3 d-flex flex-column align-items-center justify-content-center"
          style={{
            width: "200px",
            height: "200px",
          }}
        >
          <h5 className="mb-3 text-center">Options</h5>
          <button
            className={`btn w-100 mb-2 ${gelandeActive ? "btn-outline-primary" : "btn-outline-secondary"}`}
            onClick={() => setGelandeActive(!gelandeActive)}
          >
            Gelände {gelandeActive ? "Active" : "Inactive"}
          </button>
          <button
            className={`btn w-100 mb-2 ${gebaudeActive ? "btn-outline-primary" : "btn-outline-secondary"}`}
            onClick={() => setGebaudeActive(!gebaudeActive)}
          >
            Gebäude {gebaudeActive ? "Active" : "Inactive"}
          </button>
          <button
            className={`btn w-100 ${flurstuckeActive ? "btn-outline-primary" : "btn-outline-secondary"}`}
            onClick={() => setFlurstuckeActive(!flurstuckeActive)}
          >
            Flurstücke {flurstuckeActive ? "Active" : "Inactive"}
          </button>
        </div>

      </div>

      {/* Payment Panel */}
<div
  className="bg-white rounded shadow p-3 d-flex flex-column justify-content-center"
  style={{
    width: "300px",
    minHeight: "200px",
    height: "auto",
    marginLeft: "auto",
    transition: "height 0.3s ease-in-out",
  }}
>
  <h5 className="mb-3 text-center">Payment</h5>
  <Elements stripe={stripePromise}>
    <CheckoutForm price={price} onFetchObjFile={onFetchObjFile} />
  </Elements>
  <button 
    className="btn btn-secondary w-100 mt-3" 
    onClick={onFetchObjFile}
  >
    Download OBJ Without Payment
  </button>
</div>
    </div>
  );
};
export default FloatingPanel;
