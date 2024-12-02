# EasyOpenData Frontend

## Overview

The frontend of EasyOpenData is a React application that provides an interactive map interface for users to select areas of interest, choose data layers, and download spatial data. It integrates with the backend API and handles payment processing via Stripe.

---

## Key Features

- **Interactive Map Interface**: Built with React and MapLibre GL JS for map rendering.
- **Drawing Tools**: Allows users to draw polygons to select regions.
- **3D Visualization**: Uses Deck.gl to render 3D buildings.
- **Search Functionality**: Integrated with Nominatim for location search.
- **Payment Processing**: Secure payments via Stripe.
- **Responsive Design**: Adapts to mobile and desktop screens.

---

## Setup Instructions

### Prerequisites

- **Node.js** and **npm** or **yarn**

### Installation

1. **Install Dependencies**

```bash
cd frontend
yarn install
# or
npm install
```

### Running the Development Server

```bash
yarn dev
# or
npm run dev
```

The application will be available at [http://localhost:5173](http://localhost:5173)

### Build for Production

```bash
yarn build
# or
npm run build
```

The production build will be in the `dist/` directory.

---

## Configuration

### Environment Variables

Create a `.env` file in the `frontend` directory to set environment variables.

- **VITE_BACKEND_URL**: The URL of the backend API.

Example `.env` file:

```
VITE_BACKEND_URL=http://localhost:5400
```

### Map Style

The map uses a custom style defined in `src/basemap.json`. You can customize the map style by modifying this file or replacing it with another style.

---

## Project Structure

- **src/**: Contains the source code of the React application.
  - `App.tsx`: Main application component.
  - `CheckoutForm.tsx`: Handles payment form and Stripe integration.
  - `FloatingPanel.tsx`: UI component for user interactions.
  - `Legals.tsx`: Displays legal documents.
  - `draw-control.ts`: Custom control for drawing polygons.
  - `basemap.json`: Custom map style.

- **public/**: Contains static assets.

---

## Key Components

- **Map Integration**: Uses MapLibre GL JS for map rendering and Mapbox Draw for drawing tools.
- **3D Rendering**: Deck.gl is used to render 3D buildings.
- **Payment Integration**: Stripe is integrated using `@stripe/react-stripe-js` and `@stripe/stripe-js`.
- **Legal Documents**: Legal documents are displayed using `ReactMarkdown`.

---

## Customization

- **Map Style**: Modify `src/basemap.json` to change the map appearance.
- **API Endpoints**: Ensure `VITE_BACKEND_URL` points to the correct backend API.
- **Stripe Keys**: Update the publishable key in `FloatingPanel.tsx` and ensure the backend has the correct secret key.

---

## Legal Documents

The `docs/` directory contains Markdown files for legal documents such as:

- `agb.md`: Terms and Conditions
- `datenschutz.md`: Privacy Policy
- `impressum.md`: Imprint
- `widerruf.md`: Cancellation Policy

These documents are displayed in the application using the `Legals.tsx` component.

---

## Contributing

Contributions are welcome! Please ensure any changes to the frontend code are thoroughly tested.

---

## License

This project is licensed under the MIT License.