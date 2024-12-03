import React, { useState } from "react";
import { useStripe, useElements, CardElement } from "@stripe/react-stripe-js";

interface CheckoutFormProps {
  price: number;
  onFetchObjFile: () => void;
}

interface CustomerData {
  email: string;
  name: string;
  address: {
    line1: string;
    postal_code: string;
    city: string;
    country: string;
  };
}
const CheckoutForm: React.FC<CheckoutFormProps> = ({ price, onFetchObjFile }) => {
  const stripe = useStripe();
  const elements = useElements();
  const [loading, setLoading] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [customerData, setCustomerData] = useState<CustomerData>({
    email: "",
    name: "",
    address: {
      line1: "",
      postal_code: "",
      city: "",
      country: "DE",
    },
  });

  // If price is 0, render only the download button
  if (price === 0) {
    return (
      <>
      <div className="text-center mb-3">
      Grundstücke unter 0.05 km² können kostenfrei heruntergeladen werden
      </div>
      <button 
        onClick={onFetchObjFile}
        className="btn btn-primary btn-sm mt-2"
      >
        Download File
      </button>
      </>
    );
  }

  const handleFocus = () => {
    setIsExpanded(true);
  };
  const handleFocusOut = () => {
    setIsExpanded(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!stripe || !elements) return;

    if (!customerData.email || !customerData.name || !customerData.address.line1 || 
        !customerData.address.postal_code || !customerData.address.city) {
      document.getElementById("payment-message")!.textContent = "Please fill in all required fields.";
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(import.meta.env.VITE_BACKEND_URL + "/create-payment-intent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          amount: Math.round(price * 100),
          customer: customerData
        }),
      });

      if (!response.ok) throw new Error("Failed to create PaymentIntent.");

      const { clientSecret } = await response.json();

      const result = await stripe.confirmCardPayment(clientSecret, {
        payment_method: {
          billing_details: {
            name: customerData.name,
            email: customerData.email,
            address: {
              line1: customerData.address.line1,
              postal_code: customerData.address.postal_code,
              city: customerData.address.city,
              country: customerData.address.country,
            },
          },
          card: elements.getElement(CardElement)!,
        },
      });

      if (result.error) {
        document.getElementById("payment-message")!.textContent = result.error.message;
      } else if (result.paymentIntent?.status === "succeeded") {
        document.getElementById("payment-message")!.textContent = "Success! Your download will start soon.";
        onFetchObjFile();
      }
    } catch (error) {
      console.error("Payment error:", error);
    } finally {
      setLoading(false);
    }
  };
  return (
    <form onSubmit={handleSubmit} className="d-flex flex-column gap-2">
      
      {/* Secure Payment Badge */}
      <div className="d-flex align-items-center gap-1 text-secondary small">
        <span className="bi bi-lock-fill"></span>
        Secure payment via Stripe
      </div>
  
      {/* Price Details */}
      <div className="text-secondary small">
        <p>
          <strong>Order Total:</strong> €{price.toFixed(2)}
        </p>
        <p>No additional fees. You’ll only be charged this amount.</p>
      </div>
  
      {isExpanded && (
        <div className="mt-2 animate__animated animate__fadeIn">
          {/* Customer Details */}
          <input
            type="email"
            placeholder="Email *"
            required
            value={customerData.email}
            onChange={(e) =>
              setCustomerData({ ...customerData, email: e.target.value })
            }
            className="form-control form-control-sm mb-2"
          />
          <input
            type="text"
            placeholder="Full Name *"
            required
            value={customerData.name}
            onChange={(e) =>
              setCustomerData({ ...customerData, name: e.target.value })
            }
            className="form-control form-control-sm mb-2"
          />
          <input
            type="text"
            placeholder="Street Address *"
            required
            value={customerData.address.line1}
            onChange={(e) =>
              setCustomerData({
                ...customerData,
                address: { ...customerData.address, line1: e.target.value },
              })
            }
            className="form-control form-control-sm mb-2"
          />
          <div className="d-flex gap-2 mb-2">
            <input
              type="text"
              placeholder="Postal Code *"
              required
              value={customerData.address.postal_code}
              onChange={(e) =>
                setCustomerData({
                  ...customerData,
                  address: {
                    ...customerData.address,
                    postal_code: e.target.value,
                  },
                })
              }
              className="form-control form-control-sm"
            />
            <input
              type="text"
              placeholder="City *"
              required
              value={customerData.address.city}
              onChange={(e) =>
                setCustomerData({
                  ...customerData,
                  address: { ...customerData.address, city: e.target.value },
                })
              }
              className="form-control form-control-sm"
            />
          </div>
        </div>
      )}
  
      {/* Card Element */}
      <CardElement
      
      onFocus={handleFocus}
      onFocusOut={handleFocusOut}
        options={{
          style: {
            base: {
              fontSize: "14px",
            },
          },
        }}
      />
      <div id="payment-message" className="text-danger small"></div>
  
      {/* Link to Stripe Security Info */}
      <div className="small mt-7">
        <a
          href="https://stripe.com/docs/security"
          target="_blank"
          rel="noopener noreferrer"
          className="text-secondary"
        >
          Learn more about how your payment information is secured.
        </a>
      </div>
  
      <button
        type="submit"
        disabled={!stripe || loading}
        className="btn btn-primary btn-sm mt-2"
      >
        {loading ? "Processing..." : `Pay €${price.toFixed(2)}`}
      </button>
    </form>
  );
  
};
export default CheckoutForm;