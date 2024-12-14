import React, { useState, useEffect } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { Elements } from "@stripe/react-stripe-js";
import CheckoutForm from "./CheckoutForm";
import "bootstrap/dist/css/bootstrap.min.css";
// Import FontAwesome
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronUp, faChevronDown } from '@fortawesome/free-solid-svg-icons';

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
  onSelectResult,
}) => {
  const [price, setPrice] = useState<number>(0);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  // New state for expanded tab
  const [expandedTab, setExpandedTab] = useState<string | null>(null);

  const [isMobile, setIsMobile] = useState<boolean>(
    window.innerWidth <= 768
  );

  useEffect(() => {
    if (polygonArea !== null) {
      if (polygonArea < 0.05) {
        setPrice(0);
      } else {
        setPrice(20 * polygonArea);
      }
    }
  }, [polygonArea]);

  // Handle window resize to update isMobile state
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Handle search functionality
  const handleSearch = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    setSearchQuery(query);

    if (query.length > 2) {
      setIsSearching(true);
      try {
        const results = await onSearch(query);
        setSearchResults(results);
      } catch (error) {
        console.error("Search error:", error);
        setSearchResults([]);
      }
      setIsSearching(false);
    } else {
      setSearchResults([]);
    }
  };

  // Extracted content functions for reuse
  const renderAuswahlContent = () => (
    <>
      {/* Search Input */}
      <div className="w-100 mb-3 position-relative">
        <input
          type="text"
          className="form-control form-control-sm"
          placeholder="Standort finden..."
          value={searchQuery}
          onChange={handleSearch}
        />

        {/* Search Results */}
        {searchResults.length > 0 && (
          <div
            className="position-absolute bg-white shadow-sm rounded mt-1 w-100 overflow-auto"
            style={{
              maxHeight: "150px",
              zIndex: 1060,
            }}
          >
            {searchResults.map((result, index) => (
              <div
                key={index}
                className="p-2 hover-bg-light cursor-pointer"
                onClick={() => {
                  onSelectResult(result);
                  setSearchResults([]);
                  setSearchQuery("");
                }}
                style={{ cursor: "pointer" }}
              >
                {result.display_name || result.name}
              </div>
            ))}
          </div>
        )}

        {isSearching && (
          <div className="text-center mt-2">
            <small>Suche...</small>
          </div>
        )}
      </div>

      {/* Polygon Area and Price Display */}
      {polygonArea !== null ? (
        <div className="text-center mb-3">
          <strong>Gebietfläche:</strong> {polygonArea.toFixed(2)} km²
        </div>
      ) : (
        <p className="text-center mb-3">Zeichnen Sie das Gebiet ein</p>
      )}

      {/* Action Buttons */}
      <div className="btn-group w-100" role="group">
        <button
          type="button"
          className="btn btn-secondary btn mt-2"
          onClick={onDrawPolygon}
        >
          Polygon zeichnen
        </button>
        <button
          type="button"
          className="btn btn-danger btn mt-2"
          onClick={onRemovePolygon}
        >
          Entfernen
        </button>
      </div>
    </>
  );

  const renderHerunterladenContent = () => (
    <>
      <Elements stripe={stripePromise}>
        <CheckoutForm price={price} onFetchObjFile={onFetchObjFile} />
      </Elements>
    </>
  );

  // Mobile Layout
  if (isMobile) {
    return (
      <div
        className="position-fixed"
        style={{
          bottom: "40px",
          left: "0",
          right: "0",
          zIndex: 1050,
          pointerEvents: "none",
        }}
      >
        {/* Auswahl Tab */}
        <div
          style={{
            pointerEvents: "auto",
            marginBottom: expandedTab === 'Auswahl' ? '0' : '10px',
          }}
        >
          <div
            className={`bg-white shadow p-3 d-flex justify-content-between align-items-center ${
              expandedTab === 'Auswahl' ? 'rounded-top' : 'rounded'
            }`}
            style={{
              margin: "0 20px",
              cursor: "pointer",
            }}
            onClick={() => {
              setExpandedTab(expandedTab === 'Auswahl' ? null : 'Auswahl');
            }}
          >
            <h5 className="mb-0">Auswahl</h5>
            {/* Expand/Collapse Icon */}
            <FontAwesomeIcon
              icon={expandedTab === 'Auswahl' ? faChevronUp : faChevronDown}
            />
          </div>
          {expandedTab === 'Auswahl' && (
            <div
              className="bg-white shadow p-3 rounded-bottom"
              style={{
                margin: "0 20px 20px",
              }}
            >
              {renderAuswahlContent()}
            </div>
          )}
        </div>

        {/* Herunterladen Tab */}
        <div
          style={{
            pointerEvents: "auto",
            marginBottom: expandedTab === 'Herunterladen' ? '0' : '10px',
          }}
        >
          <div
            className={`bg-white shadow p-3 d-flex justify-content-between align-items-center ${
              expandedTab === 'Herunterladen' ? 'rounded-top' : 'rounded'
            }`}
            style={{
              margin: "0 20px",
              cursor: "pointer",
            }}
            onClick={() => {
              setExpandedTab(expandedTab === 'Herunterladen' ? null : 'Herunterladen');
            }}
          >
            <h5 className="mb-0">Herunterladen</h5>
            {/* Expand/Collapse Icon */}
            <FontAwesomeIcon
              icon={expandedTab === 'Herunterladen' ? faChevronUp : faChevronDown}
            />
          </div>
          {expandedTab === 'Herunterladen' && (
            <div
              className="bg-white shadow p-3 rounded-bottom"
              style={{
                margin: "0 20px 20px",
              }}
            >
              {renderHerunterladenContent()}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Desktop Layout remains unchanged
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
        pointerEvents: "none",
      }}
    >
      <div
        className="d-flex gap-3"
        style={{
          marginRight: "auto",
          pointerEvents: "none",
        }}
      >
        {/* Auswahl Panel */}
        <div
          className="bg-white rounded shadow p-3 d-flex flex-column align-items-center justify-content-center"
          style={{
            width: "300px",
            minHeight: "200px",
            pointerEvents: "auto",
          }}
        >
          <h5 className="mb-3 text-center">Auswahl</h5>
          {renderAuswahlContent()}
        </div>
      </div>

      {/* Herunterladen Panel */}
      <div
        className="bg-white rounded shadow p-3 d-flex flex-column "
        style={{
          width: "300px",
          minHeight: "50px",
          marginLeft: "auto",
          transition: "height 0.3s ease-in-out",
          pointerEvents: "auto",
        }}
      >
        <h5 className="mb-3 text-center">Herunterladen</h5>
        {renderHerunterladenContent()}
      </div>
    </div>
  );
};

export default FloatingPanel;
