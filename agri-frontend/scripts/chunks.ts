/**
 * Découpage du JavaScript : les bibliothèques changent rarement et restent en cache,
 * une mise à jour de l'application ne retélécharge que le code métier (réseau 3G).
 */
export const codeSplitting = {
  groups: [
    // Cartographie : chargée seulement avec les écrans de carte (puis gardée pour le hors ligne)
    { name: "carte", test: /node_modules[\\/](maplibre-gl|pmtiles|@protomaps)[\\/]/, priority: 4 },
    { name: "react", test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/, priority: 3 },
    { name: "router", test: /node_modules[\\/](react-router|react-router-dom|@remix-run)[\\/]/, priority: 2 },
    { name: "vendor", test: /node_modules[\\/]/, priority: 1 },
  ],
};
