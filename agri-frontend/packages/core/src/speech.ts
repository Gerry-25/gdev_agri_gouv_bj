/**
 * Lecture à voix haute des libellés de l'interface, sans réseau (synthèse vocale du téléphone).
 * Les conseils détaillés utilisent l'audio du serveur (Gemini TTS), plus naturel.
 */
export const speechAvailable = (): boolean => typeof window !== "undefined" && "speechSynthesis" in window;

export function speak(text: string, lang = "fr-FR"): void {
  if (!speechAvailable()) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  utterance.rate = 0.9;
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (speechAvailable()) window.speechSynthesis.cancel();
}
