import React, { useState, useEffect } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { Elements, CardElement, useStripe, useElements } from "@stripe/react-stripe-js";
import CheckoutForm from "./CheckoutForm";

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
      style={{
        position: "absolute",
        bottom: "20px",
        right: "20px",
        backgroundColor: "white",
        padding: "20px",
        borderRadius: "10px",
        boxShadow: "0 2px 10px rgba(0,0,0,0.1)",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        zIndex: 100,
        width: "300px",
      }}
    >
      <button onClick={onDrawPolygon}>Draw Polygon</button>
      <button onClick={onRemovePolygon}>Remove Polygon</button>
      <Elements stripe={stripePromise}>
        <CheckoutForm price={price} onFetchObjFile={onFetchObjFile} />
      </Elements>
      <button onClick={onFetchObjFile}>Download obj without Payment</button>
      {polygonArea !== null && (
        <div>
          <strong>Polygon Area:</strong> {polygonArea.toFixed(2)} km²
        </div>
      )}
      <div id="payment-message" style={{ marginTop: "10px", color: "green" }}>
        <strong>Payment Info:</strong>
      </div>
    </div>
  );
};

export default FloatingPanel;
