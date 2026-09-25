/** Éléments de base au style du template : cartes blanches bordées, accent émeraude. */
import type { LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`bg-white border border-neutral-200 rounded-lg p-4 sm:p-5 ${className}`}>{children}</section>;
}

export function CardHeader({ icon: Icon, title, action }: { icon?: LucideIcon; title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 pb-3 mb-4 border-b border-neutral-100">
      <h2 className="text-sm font-bold text-neutral-900 flex items-center gap-2 min-w-0">
        {Icon && <Icon className="w-4 h-4 text-emerald-800 shrink-0" aria-hidden />}
        <span className="truncate">{title}</span>
      </h2>
      {action}
    </div>
  );
}

export function CardLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="text-sm font-semibold text-emerald-800 hover:underline whitespace-nowrap shrink-0">
      {children}
    </Link>
  );
}

const TONES = {
  green: "bg-emerald-100 text-emerald-900",
  amber: "bg-amber-100 text-amber-900",
  red: "bg-red-100 text-red-800",
  blue: "bg-blue-100 text-blue-900",
  neutral: "bg-neutral-100 text-neutral-700",
  purple: "bg-purple-100 text-purple-900",
};

export function Badge({ tone = "neutral", children }: { tone?: keyof typeof TONES; children: ReactNode }) {
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold ${TONES[tone]}`}>{children}</span>;
}

type Variant = "primary" | "soft" | "outline" | "danger" | "ghost";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-emerald-800 hover:bg-emerald-900 text-white border border-emerald-800",
  soft: "bg-emerald-50 hover:bg-emerald-100 text-emerald-950 border border-emerald-300",
  outline: "bg-white hover:bg-neutral-50 text-neutral-800 border border-neutral-300",
  danger: "bg-white hover:bg-red-50 text-red-700 border border-red-300",
  ghost: "bg-transparent hover:bg-neutral-100 text-neutral-700 border border-transparent",
};

export const buttonClass = (variant: Variant = "primary", extra = "") =>
  `inline-flex items-center justify-center gap-2 min-h-11 px-4 py-2 rounded text-sm font-semibold transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${extra}`;

/** Par défaut type="button" : dans un formulaire, un bouton sans type enverrait le formulaire. */
export function Button({ variant = "primary", loading, className = "", children, disabled, type = "button", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean }) {
  return (
    <button {...rest} type={type} disabled={disabled || loading} aria-busy={loading || undefined} className={buttonClass(variant, className)}>
      {children}
    </button>
  );
}

export function Alert({ tone = "info", children }: { tone?: "info" | "success" | "warning" | "error"; children: ReactNode }) {
  const cls = {
    info: "bg-blue-50 border-blue-200 text-blue-950",
    success: "bg-emerald-50 border-emerald-200 text-emerald-950",
    warning: "bg-amber-50 border-amber-200 text-amber-950",
    error: "bg-red-50 border-red-200 text-red-900",
  }[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`p-3 border rounded text-sm ${cls}`}>
      {children}
    </div>
  );
}

export function Metric({ label, value, unit, hint, hintTone = "neutral" }: { label: string; value: ReactNode; unit?: string; hint?: ReactNode; hintTone?: "neutral" | "green" | "blue" | "amber" }) {
  const hintCls = { neutral: "text-neutral-500", green: "text-emerald-800 font-semibold", blue: "text-blue-700 font-semibold", amber: "text-amber-800 font-semibold" }[hintTone];
  return (
    <div className="min-w-0">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="text-xl font-bold text-neutral-900 tabular-nums mt-0.5">
        {value} {unit && <span className="text-sm font-normal text-neutral-500">{unit}</span>}
      </div>
      {hint && <div className={`text-xs mt-0.5 ${hintCls}`}>{hint}</div>}
    </div>
  );
}

export function Loading({ label = "Chargement…" }: { label?: string }) {
  return <p className="p-4 text-center text-sm text-neutral-500">{label}</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="p-6 text-center text-sm text-neutral-500 border border-dashed border-neutral-300 rounded-lg">{children}</div>;
}
