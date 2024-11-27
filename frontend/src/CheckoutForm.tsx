import React, { useState } from "react";
import { useStripe, useElements, CardElement } from "@stripe/react-stripe-js";

interface CheckoutFormProps {
  price: number;
  onFetchObjFile: () => void;
}

const CheckoutForm: React.FC<CheckoutFormProps> = ({ price, onFetchObjFile }) => {
  const stripe = useStripe();
  const elements = useElements();
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!stripe || !elements) {
      console.error("Stripe has not loaded yet.");
      return;
    }

    setLoading(true);

    try {
      // Create PaymentIntent on the server
      const response = await fetch("http://localhost:3303/create-payment-intent", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ amount: Math.round(price * 100) }), // Amount in cents
      });

      if (!response.ok) {
        throw new Error("Failed to create PaymentIntent.");
      }

      const { clientSecret } = await response.json();

      // Confirm Card Payment
      const result = await stripe.confirmCardPayment(clientSecret, {
        payment_method: {
          card: elements.getElement(CardElement)!,
        },
      });

      if (result.error) {
        console.error(result.error.message);
        document.getElementById("payment-message")!.textContent = result.error.message;
      } else if (result.paymentIntent?.status === "succeeded") {
        document.getElementById("payment-message")!.textContent =
          "Success! Thank you! Your download should start soon.";
        onFetchObjFile(); // Trigger download
      }
    } catch (error) {
      console.error("An error occurred during payment:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: "10px" }}>
      <CardElement />
      <button type="submit" disabled={!stripe || loading} style={{ marginTop: "10px" }}>
        {loading ? "Processing..." : `Pay €${price.toFixed(2)}`}
      </button>
    </form>
  );
};

export default CheckoutForm;
