import { api, apiErrorMessage, authStore, type components, useSession } from "@agri/core";
import { AlertCircle, ArrowRight, KeyRound, Phone, ShieldCheck, ShoppingBasket, Sprout, UserCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Alert, Button } from "../components/ui";
import { useHealth } from "../lib/queries";

type OtpResponse = components["schemas"]["OtpRequestResponse"];

// Comptes créés par le script de démonstration du backend
const DEMO = [
  { npi: "0100000001", phone: "0190000001", name: "Démo Exploitant", role: "Exploitant (Dangbo)" },
  { npi: "0100000002", phone: "0190000002", name: "Démo Acheteur", role: "Acheteur" },
  { npi: "0100000003", phone: "0190000003", name: "Démo Agent État", role: "Agent de l'État" },
  { npi: "0100000004", phone: "0190000004", name: "Démo Superviseur", role: "Superviseur" },
];

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none";

export function LoginPage() {
  const { user } = useSession();
  const health = useHealth();
  const [step, setStep] = useState<"request" | "verify">("request");
  const [npi, setNpi] = useState("");
  const [phone, setPhone] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<"farmer" | "buyer">("farmer");
  const [needsProfile, setNeedsProfile] = useState(false);
  const [code, setCode] = useState("");
  const [otp, setOtp] = useState<OtpResponse | null>(null);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (step !== "verify") return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [step]);

  if (user) return <Navigate to="/" replace />;

  async function requestCode(e?: FormEvent, override?: { npi: string; phone: string }) {
    e?.preventDefault();
    setError(null);
    setLoading(true);
    const id = override ?? { npi, phone };
    const body = needsProfile && !override ? { ...id, full_name: fullName, role } : id;
    try {
      const { data, error: err, response } = await api.POST("/api/v1/auth/otp/request", { body });
      if (err) {
        const detail = (err as { detail?: unknown }).detail;
        if (response.status === 422 && typeof detail === "string" && detail.startsWith("Première connexion")) setNeedsProfile(true);
        else setError(apiErrorMessage(err));
        return null;
      }
      setOtp(data);
      setCode("");
      setResendAt(Date.now() + data.resend_in * 1000);
      setStep("verify");
      return data;
    } catch (err) {
      setError(apiErrorMessage(err));
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function verify(e?: FormEvent, override?: { npi: string; code: string }) {
    e?.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { data, error: err } = await api.POST("/api/v1/auth/otp/verify", { body: override ?? { npi, code } });
      if (err) setError(apiErrorMessage(err));
      else authStore.setSession(data);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  /** Accès démo : passe par la vraie connexion par code (le code simulé est renvoyé par l'API). */
  async function demoLogin(account: (typeof DEMO)[number]) {
    setNpi(account.npi);
    setPhone(account.phone);
    const res = await requestCode(undefined, { npi: account.npi, phone: account.phone });
    if (res?.simulated_code) await verify(undefined, { npi: account.npi, code: res.simulated_code });
  }

  const wait = Math.max(0, Math.ceil((resendAt - now) / 1000));
  const length = otp?.simulated_code?.length ?? 6;
  const demoMode = health.data?.sms_mode === "simulation";

  return (
    <main className="min-h-screen flex items-start sm:items-center justify-center p-4 pt-[max(2rem,env(safe-area-inset-top))]">
      <div className="bg-white rounded-lg border border-neutral-200 shadow-sm max-w-md w-full overflow-hidden">
        <div className="px-5 sm:px-6 py-4 border-b border-neutral-100 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-emerald-800" aria-hidden />
          <h1 className="text-lg font-bold text-neutral-900">Connexion à AgriSmart Bénin</h1>
        </div>

        <div className="p-5 sm:p-6 space-y-4">
          <p className="text-sm text-neutral-600 leading-relaxed">
            Identifiez-vous avec votre Numéro Personnel d'Identification (NPI) et le code reçu par SMS.
          </p>
          {error && (
            <div role="alert" className="p-3 bg-red-50 border border-red-200 text-red-800 text-sm rounded flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 text-red-600 mt-0.5" aria-hidden />
              <span>{error}</span>
            </div>
          )}

          {step === "request" ? (
            <form onSubmit={requestCode} className="space-y-4" noValidate>
              <div>
                <label htmlFor="npi" className="block text-sm font-semibold text-neutral-800 mb-1">Numéro NPI</label>
                <input id="npi" inputMode="numeric" autoComplete="off" maxLength={10} placeholder="10 chiffres" value={npi}
                       onChange={(e) => setNpi(e.target.value.replace(/\D/g, ""))} className={`${inputCls} tabular-nums`} required />
                <span className="text-xs text-neutral-500 mt-1 block">Les 10 chiffres inscrits sur votre carte d'identité</span>
              </div>
              <div>
                <label htmlFor="phone" className="block text-sm font-semibold text-neutral-800 mb-1">Téléphone mobile</label>
                <div className="relative">
                  <Phone className="w-4 h-4 text-neutral-400 absolute left-3 top-3.5" aria-hidden />
                  <input id="phone" type="tel" inputMode="tel" autoComplete="tel" placeholder="01 XX XX XX XX" value={phone}
                         onChange={(e) => setPhone(e.target.value)} className={`${inputCls} pl-9`} required />
                </div>
              </div>

              {needsProfile && (
                <div className="space-y-4">
                  <Alert tone="info">C'est votre première connexion. Indiquez votre nom et votre activité.</Alert>
                  <div>
                    <label htmlFor="name" className="block text-sm font-semibold text-neutral-800 mb-1">Nom et prénom</label>
                    <input id="name" autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} className={inputCls} autoFocus required />
                  </div>
                  <fieldset className="grid grid-cols-2 gap-2">
                    <legend className="text-sm font-semibold text-neutral-800 mb-1">Votre activité</legend>
                    {([["farmer", "Je cultive", Sprout], ["buyer", "J'achète des récoltes", ShoppingBasket]] as const).map(([value, label, Icon]) => (
                      <label key={value} className={`p-3 border rounded cursor-pointer text-sm font-semibold flex flex-col items-center gap-1.5 text-center has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-emerald-700 ${role === value ? "border-emerald-800 bg-emerald-50 text-emerald-950" : "border-neutral-200 text-neutral-700"}`}>
                        <input type="radio" name="role" className="sr-only" checked={role === value} onChange={() => setRole(value)} />
                        <Icon className="w-6 h-6" aria-hidden /> {label}
                      </label>
                    ))}
                  </fieldset>
                </div>
              )}

              <Button type="submit" className="w-full" loading={loading}
                      disabled={npi.length !== 10 || phone.replace(/\D/g, "").length < 8 || (needsProfile && fullName.trim().length < 2)}>
                Recevoir le code SMS <ArrowRight className="w-4 h-4" aria-hidden />
              </Button>
            </form>
          ) : (
            <form onSubmit={verify} className="space-y-4" noValidate>
              <div className="p-3 bg-neutral-50 border border-neutral-200 rounded text-sm">
                <div className="text-neutral-700">{otp?.message}</div>
                {otp?.simulated_code && (
                  <div className="mt-2 space-y-2">
                    <div className="text-xs text-neutral-500">Mode démonstration : aucun SMS n'est envoyé.</div>
                    <div className="flex items-center justify-between gap-2 bg-emerald-100/70 p-2 rounded">
                      <span className="text-emerald-900 font-bold text-lg tracking-widest tabular-nums">{otp.simulated_code}</span>
                      <button type="button" onClick={() => setCode(otp.simulated_code ?? "")} className="text-sm font-semibold text-emerald-900 underline cursor-pointer">
                        Remplir le code
                      </button>
                    </div>
                  </div>
                )}
              </div>
              <div>
                <label htmlFor="code" className="block text-sm font-semibold text-neutral-800 mb-1">Code à {length} chiffres</label>
                <div className="relative">
                  <KeyRound className="w-4 h-4 text-neutral-400 absolute left-3 top-3.5" aria-hidden />
                  <input id="code" inputMode="numeric" autoComplete="one-time-code" maxLength={length} value={code} autoFocus
                         onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                         className={`${inputCls} pl-9 text-xl tracking-[0.4em] text-center tabular-nums`} required />
                </div>
                <div className="flex items-center justify-between gap-2 text-sm mt-2">
                  <button type="button" onClick={() => setStep("request")} className="text-emerald-800 font-semibold hover:underline cursor-pointer">
                    Changer de numéro
                  </button>
                  <button type="button" onClick={() => requestCode()} disabled={wait > 0 || loading}
                          className="text-emerald-800 font-semibold hover:underline cursor-pointer disabled:text-neutral-400 disabled:no-underline">
                    {wait > 0 ? `Renvoyer dans ${wait} s` : "Renvoyer le code"}
                  </button>
                </div>
              </div>
              <Button type="submit" className="w-full" loading={loading} disabled={code.length !== length}>
                Se connecter <UserCheck className="w-4 h-4" aria-hidden />
              </Button>
            </form>
          )}

          {demoMode && step === "request" && (
            <div className="pt-4 border-t border-neutral-100">
              <p className="text-xs font-semibold text-neutral-500 mb-2">Accès rapide aux comptes de démonstration</p>
              <div className="grid grid-cols-2 gap-2">
                {DEMO.map((a) => (
                  <button key={a.npi} type="button" onClick={() => demoLogin(a)} disabled={loading}
                          className="p-2.5 text-left border border-neutral-200 rounded hover:bg-neutral-50 cursor-pointer disabled:opacity-50">
                    <div className="text-sm font-semibold text-neutral-900">{a.name}</div>
                    <div className="text-xs text-neutral-500">{a.role}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
