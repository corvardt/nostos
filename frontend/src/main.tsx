import React from "react";
import ReactDOM from "react-dom/client";

// Self-hosted: this app must work with no network beyond the media hosts.
// One typeface throughout - an instrument has no proportional text.
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";

import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
