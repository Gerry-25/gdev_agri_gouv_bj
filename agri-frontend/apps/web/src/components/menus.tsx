import { api, apiErrorMessage, authStore, formatPhone, LANGUAGES, type LanguageCode, useSession, useSignOut } from "@agri/core";
import { useMutation } from "@tanstack/react-query";
import { Globe, LogOut, Shield, Smartphone } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ROLE_LABELS, type Role } from "../lib/nav";

function useDropdown() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return { open, setOpen, ref };
}

function Panel({ children, width = "w-64" }: { children: ReactNode; width?: string }) {
  return <div className={`absolute right-0 mt-2 ${width} bg-white rounded border border-neutral-200 shadow-lg py-1 z-50`}>{children}</div>;
}

/** Langue des conseils : utilisée par l'IA et l'audio (les écrans restent en français). */
export function LanguageMenu() {
  const { user } = useSession();
  const { open, setOpen, ref } = useDropdown();
  const save = useMutation({
    mutationFn: async (preferred_language: LanguageCode) => {
      const { data, error } = await api.PATCH("/api/v1/auth/me", { body: { preferred_language } });
      if (error) throw new Error(apiErrorMessage(error));
      authStore.setUser(data);
    },
    onSuccess: () => setOpen(false),
  });
  const current = user?.preferred_language ?? "fr";
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label="Langue des conseils"
        className="min-h-9 px-2 text-neutral-700 hover:bg-neutral-100 rounded border border-neutral-200 cursor-pointer flex items-center gap-1"
      >
        <Globe className="w-4 h-4" aria-hidden />
        <span className="text-xs font-bold uppercase">{current}</span>
      </button>
      {open && (
        <Panel width="w-60">
          <p className="px-3 py-2 text-xs text-neutral-500 border-b border-neutral-100">Langue des conseils de l'IA et de l'audio. Les écrans restent en français.</p>
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              onClick={() => save.mutate(l.code)}
              disabled={save.isPending}
              className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between cursor-pointer ${current === l.code ? "bg-emerald-50 text-emerald-900 font-semibold" : "text-neutral-700 hover:bg-neutral-50"}`}
            >
              {l.label}
              {current === l.code && <span aria-hidden>✓</span>}
            </button>
          ))}
          {save.isError && <p className="px-3 py-2 text-xs text-red-700">{(save.error as Error).message}</p>}
        </Panel>
      )}
    </div>
  );
}

export function UserMenu() {
  const { user } = useSession();
  const signOut = useSignOut();
  const { open, setOpen, ref } = useDropdown();
  if (!user) return null;
  const role = ROLE_LABELS[user.role as Role] ?? user.role;
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="min-h-9 px-2.5 text-neutral-800 bg-neutral-100 hover:bg-neutral-200 rounded border border-neutral-200 cursor-pointer flex items-center gap-2"
      >
        <Shield className="w-4 h-4 text-emerald-800" aria-hidden />
        <span className="text-left hidden md:block leading-tight">
          <span className="text-sm font-semibold block truncate max-w-36">{user.full_name}</span>
          <span className="text-xs text-neutral-500 block">{role}</span>
        </span>
        <span className="sr-only md:hidden">Mon compte</span>
      </button>
      {open && (
        <Panel width="w-72">
          <div className="px-3 py-2 border-b border-neutral-100">
            <div className="text-sm font-semibold text-neutral-900">{user.full_name}</div>
            <div className="text-xs text-neutral-500 mt-0.5">
              {role} · {formatPhone(user.phone)}
            </div>
            <div className="text-xs text-neutral-500 tabular-nums">NPI {user.npi}</div>
          </div>
          <button onClick={() => signOut.mutate(false)} className="w-full text-left px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-50 flex items-center gap-2 cursor-pointer">
            <LogOut className="w-4 h-4" aria-hidden /> Se déconnecter
          </button>
          <button onClick={() => signOut.mutate(true)} className="w-full text-left px-3 py-2 text-sm text-red-700 hover:bg-red-50 flex items-center gap-2 cursor-pointer">
            <Smartphone className="w-4 h-4" aria-hidden /> Déconnecter tous mes appareils
          </button>
        </Panel>
      )}
    </div>
  );
}
