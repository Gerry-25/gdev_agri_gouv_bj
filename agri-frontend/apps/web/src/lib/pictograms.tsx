import {
  AlertTriangle, Bell, Bug, Check, Handshake, Landmark, type LucideIcon, Megaphone, Scale, ShoppingBag, Tractor, Trophy, Warehouse,
} from "lucide-react";

const ICONS: Record<string, { icon: LucideIcon; color: string }> = {
  law: { icon: Scale, color: "text-red-600" },
  handshake: { icon: Handshake, color: "text-purple-600" },
  check: { icon: Check, color: "text-emerald-700" },
  buyer: { icon: ShoppingBag, color: "text-emerald-700" },
  bug: { icon: Bug, color: "text-amber-600" },
  megaphone: { icon: Megaphone, color: "text-purple-600" },
  trophy: { icon: Trophy, color: "text-emerald-700" },
  field: { icon: Tractor, color: "text-emerald-700" },
  warehouse: { icon: Warehouse, color: "text-amber-600" },
  landmark: { icon: Landmark, color: "text-purple-600" },
  alert: { icon: AlertTriangle, color: "text-red-600" },
};

export function Pictogram({ code, className = "w-4 h-4" }: { code?: string | null; className?: string }) {
  const { icon: Icon, color } = (code && ICONS[code]) || { icon: Bell, color: "text-neutral-500" };
  return <Icon className={`${className} ${color} shrink-0`} aria-hidden />;
}
