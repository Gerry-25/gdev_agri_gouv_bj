/**
 * Lecture à voix haute des libellés de l'interface, sans réseau (synthèse vocale du téléphone).
 * Les conseils détaillés utilisent l'audio du serveur (Gemini TTS), plus naturel.
 */
export const speechAvailable = (): boolean => typeof window !== "undefined" && "speechSynthesis" in window;

export function speak(text: string, lang = "fr-FR", onEnd?: () => void): void {
  if (!speechAvailable()) {
    onEnd?.();
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  utterance.rate = 0.95;
  if (onEnd) {
    utterance.onend = () => onEnd();
    utterance.onerror = () => onEnd();
  }
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (speechAvailable()) window.speechSynthesis.cancel();
}
