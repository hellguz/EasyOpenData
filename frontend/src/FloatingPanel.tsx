// FloatingPanel.tsx
import React, { useState, useEffect } from "react";
import { loadStripe } from "@stripe/stripe-js";

// Initialize Stripe with your publishable key
const stripePromise = loadStripe("your-publishable-key-here");

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
      if (polygonArea < 2) {
        setPrice(0);
      } else {
        setPrice(5 * polygonArea);
      }
    }
  }, [polygonArea]);

  const handlePayment = async () => {
    const stripe = await stripePromise;
    if (!stripe) {
      console.error("Stripe failed to load.");
      return;
    }

    // Create a Checkout Session on the server
    const response = await fetch("http://localhost:3303/create-checkout-session", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ amount: price }),
    });

    const session = await response.json();

    // Redirect to Stripe Checkout
    const result = await stripe.redirectToCheckout({
      sessionId: session.id,
    });

    if (result.error) {
      console.error(result.error.message);
    }
  };

  const handleDownloadWithoutPayment = () => {
    onFetchObjFile();
  };

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
        width: "300px", // Twice as broad assuming original was ~150px
      }}
    >
      <button onClick={onDrawPolygon}>Draw Polygon</button>
      <button onClick={onRemovePolygon}>Remove Polygon</button>
      <button onClick={handlePayment} >
        Download obj for {price.toFixed(2)} &euro;
      </button>
      <button onClick={handleDownloadWithoutPayment}>
        Download obj without Payment
      </button>
      {polygonArea !== null && (
        <div>
          <strong>Polygon Area:</strong> {polygonArea.toFixed(2)} km²
        </div>
      )}
    </div>
  );
};

export default FloatingPanel;
