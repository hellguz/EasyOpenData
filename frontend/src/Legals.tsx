
import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';

const LegalDocumentPanel: React.FC<{ documentType: string }> = ({ documentType }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [content, setContent] = useState('');

  const handleClick = async () => {
    if (!isOpen) {
      try {
        const response = await fetch(`/docs/${documentType}.md`);
        const text = await response.text();
        setContent(text);
      } catch (error) {
        console.error(`Error loading ${documentType}:`, error);
        setContent('Failed to load content.');
      }
    }
    setIsOpen(!isOpen);
  };

  return (
    <>
      <button
        onClick={handleClick}
        className="btn btn-sm btn-light"
        style={{
          display: 'inline-block',
          padding: '0.25rem 0.5rem',
        }}
      >
        {documentType.charAt(0).toUpperCase() + documentType.slice(1)}
      </button>

      {isOpen && (
        <div className="bg-white rounded shadow p-3" style={{
          position: 'absolute',
          top: '50px',
          right: '10px',
          maxWidth: '600px',
          width: '80vw',
          maxHeight: '50vh',
          overflowY: 'auto',
          zIndex: 1070,
        }}>
          <button
            className="btn btn-sm btn-close float-end"
            onClick={() => setIsOpen(false)}
          />
          <h5 className="mb-3">{documentType.charAt(0).toUpperCase() + documentType.slice(1)}</h5>
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      )}
    </>
  );
};

const LegalDocuments: React.FC = () => {
  return (
    <div style={{
      position: 'absolute',
      top: '10px',
      right: '10px',
      display: 'flex',
      gap: '20px',
      zIndex: 1060,
    }}>
      <LegalDocumentPanel documentType="impressum" />
      <LegalDocumentPanel documentType="datenschutz" />
      <LegalDocumentPanel documentType="agb" />
      <LegalDocumentPanel documentType="widerruf" />
    </div>
  );
};

export default LegalDocuments;