import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { fr } from "./fr";

export type LanguageCode = "fr" | "fon" | "yo" | "en";

/**
 * Langues proposées. Les écrans n'existent qu'en français pour l'instant : pour les autres langues,
 * i18next se replie sur le français. Les traductions en fon et yoruba doivent être rédigées et
 * relues par des locuteurs natifs, jamais générées automatiquement.
 */
export const LANGUAGES: { code: LanguageCode; label: string; screensTranslated: boolean }[] = [
  { code: "fr", label: "Français", screensTranslated: true },
  { code: "fon", label: "Fɔngbè", screensTranslated: false },
  { code: "yo", label: "Yorùbá", screensTranslated: false },
  { code: "en", label: "English", screensTranslated: false },
];

export function initI18n(lng: LanguageCode = "fr") {
  if (!i18n.isInitialized) {
    void i18n.use(initReactI18next).init({
      resources: { fr: { translation: fr } },
      lng,
      fallbackLng: "fr",
      interpolation: { escapeValue: false }, // React échappe déjà le contenu
    });
  }
  return i18n;
}

export { i18n, fr };
