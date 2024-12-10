import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const LegalDocumentPanel: React.FC<{
  documentType: string;
  isOpen: boolean;
  setOpenDocument: (doc: string | null) => void;
}> = ({ documentType, isOpen, setOpenDocument }) => {
  const [content, setContent] = useState('');

  useEffect(() => {
    if (isOpen && !content) {
      const fetchContent = async () => {
        try {
          const response = await fetch(`/docs/${documentType}.md`);
          const text = await response.text();
          setContent(text);
        } catch (error) {
          console.error(`Error loading ${documentType}:`, error);
          setContent('Failed to load content.');
        }
      };
      fetchContent();
    }
  }, [isOpen, content, documentType]);

  const handleClick = () => {
    setOpenDocument(isOpen ? null : documentType);
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
        <div
          className="bg-white rounded shadow p-3"
          style={{
            position: 'absolute',
            top: '50px',
            right: '10px',
            maxWidth: '600px',
            width: '80vw',
            maxHeight: '50vh',
            overflowY: 'auto',
            zIndex: 1070,
          }}
        >
          <button
            className="btn btn-sm btn-close float-end"
            onClick={() => setOpenDocument(null)}
          />
          <h5 className="mb-3">
            {documentType.charAt(0).toUpperCase() + documentType.slice(1)}
          </h5>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      )}
    </>
  );
};

const LegalDocuments: React.FC = () => {
  const [openDocument, setOpenDocument] = useState<string | null>(null);

  return (
    <div
      style={{
        display: 'flex',
        gap: '10px',
        pointerEvents: "auto"
      }}
    >
      <LegalDocumentPanel
        documentType="quellen"
        isOpen={openDocument === 'quellen'}
        setOpenDocument={setOpenDocument}
      />
      <LegalDocumentPanel
        documentType="impressum"
        isOpen={openDocument === 'impressum'}
        setOpenDocument={setOpenDocument}
      />
      <LegalDocumentPanel
        documentType="datenschutz"
        isOpen={openDocument === 'datenschutz'}
        setOpenDocument={setOpenDocument}
      />
      <LegalDocumentPanel
        documentType="AGB & Widerruf"
        isOpen={openDocument === 'AGB & Widerruf'}
        setOpenDocument={setOpenDocument}
      />
    </div>
  );
};


export default LegalDocuments;
