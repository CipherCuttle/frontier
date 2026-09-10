import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserPublicReadTransport } from "./api";
import { DiscoverApp } from "./DiscoverApp";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("terminal root element is missing");

const transport = new BrowserPublicReadTransport(import.meta.env.VITE_FRONTIER_API_BASE ?? "");

createRoot(root).render(
  <StrictMode>
    <DiscoverApp transport={transport} />
  </StrictMode>,
);
