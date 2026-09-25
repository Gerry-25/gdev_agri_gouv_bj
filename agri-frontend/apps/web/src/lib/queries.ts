import { api, apiErrorMessage, type components } from "@agri/core";
import { useQuery } from "@tanstack/react-query";

export type Land = components["schemas"]["LandOut"];
export type Offer = components["schemas"]["HarvestOfferOut"];

/** Lève une erreur lisible si l'API renvoie une erreur. */
export function unwrap<T>(res: { data?: T; error?: unknown }): T {
  if (res.error !== undefined) throw new Error(apiErrorMessage(res.error));
  return res.data as T;
}

export interface ScoreComponent {
  key: string;
  label: string;
  score: number;
  weight: number;
  detail: string;
}

export interface Performance {
  npi: string;
  score: number;
  eligible: boolean;
  ineligibility_reasons: string[];
  components: ScoreComponent[];
  stats: { seasons: number; harvests_counted: number; verified_surface_ha: number; parcels: number; crops: string[]; departments: string[] };
}

export interface WeatherDay {
  date: string;
  tmin: number | null;
  tmax: number;
  precipitation_mm: number;
  precipitation_probability: number;
  wind_kmh: number;
  color: "green" | "orange" | "red";
  pictogram: string;
}

export interface Weather {
  commune?: string;
  summary: {
    color: "green" | "orange" | "red";
    indicator: string;
    message: string;
    pictogram: string;
    sowing_favorable: boolean;
    spraying_advised: boolean;
    rain_next_3_days_mm: number;
  };
  days: WeatherDay[];
}

export const useMyLands = () =>
  useQuery({ queryKey: ["lands", "me"], queryFn: async () => unwrap(await api.GET("/api/v1/lands/me")) });

export const useMyOffers = () =>
  useQuery({ queryKey: ["offers", "me"], queryFn: async () => unwrap(await api.GET("/api/v1/market/offers/me")) });

export const useMyPerformance = () =>
  useQuery({
    queryKey: ["performance", "me"],
    queryFn: async () => unwrap(await api.GET("/api/v1/performance/me")) as unknown as Performance,
  });

export const useHealth = () =>
  useQuery({
    queryKey: ["health"],
    staleTime: Infinity,
    retry: 0,
    queryFn: async () => {
      const r = await fetch("/health");
      return r.ok ? ((await r.json()) as { sms_mode: string; ai_mode: string; env: string }) : null;
    },
  });
