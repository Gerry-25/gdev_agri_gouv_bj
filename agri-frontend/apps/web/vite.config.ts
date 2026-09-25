import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";
import { codeSplitting } from "../../scripts/chunks.ts";

export default defineConfig({
  build: { rolldownOptions: { output: { codeSplitting } } },
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "apple-touch-icon.png"],
      manifest: {
        name: "AgriSmart Bénin",
        short_name: "AgriSmart",
        description: "Parcelles, santé des cultures, marché et terres de l'État.",
        lang: "fr",
        start_url: "/",
        scope: "/",
        display: "standalone",
        background_color: "#fafafa",
        theme_color: "#065f46",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/health/, /^\/tiles\//],
        // Les polices de carte sont mises en cache à l'usage (1,6 Mo : pas dans le préchargement)
        globIgnores: ["map-assets/**"],
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        runtimeCaching: [
          {
            urlPattern: ({ url }) =>
              ["/api/v1/knowledge", "/api/v1/monitoring/weather", "/api/v1/market/offers", "/api/v1/market/prices", "/api/v1/calls"].some((p) =>
                url.pathname.startsWith(p),
              ),
            handler: "NetworkFirst",
            method: "GET",
            options: { cacheName: "api-lectures", networkTimeoutSeconds: 6, expiration: { maxEntries: 300, maxAgeSeconds: 7 * 24 * 3600 } },
          },
          {
            urlPattern: ({ url }) => url.pathname.startsWith("/map-assets/"),
            handler: "CacheFirst",
            method: "GET",
            options: { cacheName: "carte-polices", expiration: { maxEntries: 60, maxAgeSeconds: 365 * 24 * 3600 } },
          },
          {
            // Tuiles satellite Esri : cache du navigateur de l'utilisateur uniquement (autorisé), pas d'export
            urlPattern: ({ url }) => url.hostname === "ibasemaps-api.arcgis.com",
            handler: "CacheFirst",
            method: "GET",
            options: { cacheName: "satellite", expiration: { maxEntries: 400, maxAgeSeconds: 7 * 24 * 3600 } },
          },
          {
            urlPattern: ({ url }) => url.pathname.endsWith("/audio"),
            handler: "CacheFirst",
            method: "GET",
            options: { cacheName: "audio", expiration: { maxEntries: 80, maxAgeSeconds: 30 * 24 * 3600 } },
          },
        ],
      },
    }),
  ],
  server: { proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" } },
});
