import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createItaaApi } from "./api/client.js";
import { App } from "./App.js";
import "./styles.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("Reservedge web root element is missing");
}

createRoot(root).render(
  <StrictMode>
    <App api={createItaaApi()} />
  </StrictMode>,
);
