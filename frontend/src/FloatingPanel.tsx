import React, { useState, useEffect } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { Elements } from "@stripe/react-stripe-js";
import CheckoutForm from "./CheckoutForm";
import "bootstrap/dist/css/bootstrap.min.css";

// Initialize Stripe with your publishable key
const stripePromise = loadStripe(
  "hidden_api"
);

interface FloatingPanelProps {
  onDrawPolygon: () => void;
  onRemovePolygon: () => void;
  onFetchObjFile: () => void;
  polygonArea: number | null; // in square kilometers
  onSearch: (query: string) => Promise<any>;
  onSelectResult: (result: any) => void;
}
const FloatingPanel: React.FC<FloatingPanelProps> = ({
  onDrawPolygon,
  onRemovePolygon,
  onFetchObjFile,
  polygonArea,
  onSearch,
  onSelectResult
}) => {
  const [price, setPrice] = useState<number>(0);
  const [gelandeActive, setGelandeActive] = useState<boolean>(false);
  const [gebaudeActive, setGebaudeActive] = useState<boolean>(false);
  const [flurstuckeActive, setFlurstuckeActive] = useState<boolean>(false);

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    if (polygonArea !== null) {
      if (polygonArea < 0.2) {
        setPrice(0);
      } else {
        setPrice(5 * polygonArea);
      }
    }
  }, [polygonArea]);

  
// Add this function to handle search
const handleSearch = async (e: React.ChangeEvent<HTMLInputElement>) => {
  const query = e.target.value;
  setSearchQuery(query);
  
  if (query.length > 2) {
    setIsSearching(true);
    try {
      const results = await onSearch(query);
      setSearchResults(results);
    } catch (error) {
      console.error('Search error:', error);
      setSearchResults([]);
    }
    setIsSearching(false);
  } else {
    setSearchResults([]);
  }
};


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
        pointerEvents: "none", // Add this line
      }}
    >
      <div
        className="d-flex gap-3"
        style={{
          marginRight: "auto",
          pointerEvents: "none", // Add this line
        }}
      >
        {/* Region Panel */}
        <div
  className="bg-white rounded shadow p-3 d-flex flex-column align-items-center justify-content-center"
  style={{
    width: "300px",
    height: "auto",
    minHeight: "200px",
    pointerEvents: "auto",
  }}
>
  <h5 className="mb-3 text-center">Region</h5>
  
  {/* Search Input */}
  <div className="w-100 mb-3">
    <input
      type="text"
      className="form-control form-control-sm"
      placeholder="Search location..."
      value={searchQuery}
      onChange={handleSearch}
    />
    
    {/* Search Results */}
    {searchResults.length > 0 && (
      <div 
        className="position-absolute bg-white shadow-sm rounded mt-1 w-100 overflow-auto"
        style={{ maxHeight: '150px', zIndex: 1060 }}
      >
        {searchResults.map((result, index) => (
          <div
            key={index}
            className="p-2 hover-bg-light cursor-pointer"
            onClick={() => {
              onSelectResult(result);
              setSearchResults([]);
              setSearchQuery('');
            }}
            style={{ cursor: 'pointer' }}
          >
            {result.display_name || result.name}
          </div>
        ))}
      </div>
    )}
    
    {isSearching && (
      <div className="text-center mt-2">
        <small>Searching...</small>
      </div>
    )}
  </div>

  {/* Existing Area and Price Display */}
  {polygonArea !== null ? (
    <div className="text-center mb-3">
        <strong>Polygon Area:</strong> {polygonArea.toFixed(2)} km²
    </div>
  ) : (
    <p className="text-center mb-3">No area selected.</p>
  )}

  {/* Existing Buttons */}
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
            pointerEvents: "auto", // Add this line
          }}
        >
          <h5 className="mb-3 text-center">Options</h5>
          <button
            className={`btn w-100 mb-2 ${
              gelandeActive ? "btn-outline-primary" : "btn-outline-secondary"
            }`}
            onClick={() => setGelandeActive(!gelandeActive)}
          >
            Gelände {gelandeActive ? "Active" : "Inactive"}
          </button>
          <button
            className={`btn w-100 mb-2 ${
              gebaudeActive ? "btn-outline-primary" : "btn-outline-secondary"
            }`}
            onClick={() => setGebaudeActive(!gebaudeActive)}
          >
            Gebäude {gebaudeActive ? "Active" : "Inactive"}
          </button>
          <button
            className={`btn w-100 ${
              flurstuckeActive ? "btn-outline-primary" : "btn-outline-secondary"
            }`}
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
          pointerEvents: "auto", // Add this line

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
