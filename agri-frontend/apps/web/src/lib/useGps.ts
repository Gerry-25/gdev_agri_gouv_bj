import { useEffect, useRef, useState } from "react";
import type { Position } from "../components/MapView";

type WakeLockLike = { release: () => Promise<void> };

/**
 * Position GPS en continu, avec l'écran maintenu allumé : sur la plupart des téléphones, le GPS
 * d'une application web s'arrête quand l'écran s'éteint.
 */
export function useGps(active: boolean) {
  const [position, setPosition] = useState<Position | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lock = useRef<WakeLockLike | null>(null);

  useEffect(() => {
    if (!active) return;
    if (!("geolocation" in navigator)) {
      setError("Ce téléphone ne fournit pas de position GPS.");
      return;
    }
    const nav = navigator as Navigator & { wakeLock?: { request: (t: "screen") => Promise<WakeLockLike> } };
    nav.wakeLock?.request("screen").then((l) => (lock.current = l)).catch(() => undefined);
    const id = navigator.geolocation.watchPosition(
      (p) => {
        setError(null);
        setPosition({ lngLat: [p.coords.longitude, p.coords.latitude], accuracy: p.coords.accuracy });
      },
      (e) =>
        setError(
          e.code === e.PERMISSION_DENIED
            ? "Autorisez la localisation pour ce site dans les réglages du téléphone."
            : "Position GPS indisponible : placez-vous à découvert et patientez.",
        ),
      { enableHighAccuracy: true, maximumAge: 0, timeout: 20_000 },
    );
    return () => {
      navigator.geolocation.clearWatch(id);
      lock.current?.release().catch(() => undefined);
      lock.current = null;
    };
  }, [active]);

  return { position, error };
}
