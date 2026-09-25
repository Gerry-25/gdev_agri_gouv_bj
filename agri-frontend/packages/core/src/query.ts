import { QueryClient } from "@tanstack/react-query";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        retry: 1,
        // Affiche les données en cache même hors ligne, puis actualise au retour du réseau
        networkMode: "offlineFirst",
        refetchOnWindowFocus: false,
      },
    },
  });
}
