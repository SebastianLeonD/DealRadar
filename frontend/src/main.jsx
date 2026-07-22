import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";

// Self-hosted fonts — no CDN dependency
import "@fontsource/young-serif/400.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/700.css";
import "@fontsource/libre-franklin/400.css";
import "@fontsource/libre-franklin/600.css";

import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
