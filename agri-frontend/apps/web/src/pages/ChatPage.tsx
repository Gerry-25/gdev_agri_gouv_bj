import { CheckCircle2, Globe, Info, Mic, Sparkles, Volume2 } from "lucide-react";
import { ChatInterface } from "../components/ChatInterface";
import { Card } from "../components/ui";

export function ChatPage() {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-900 border border-emerald-300">
            <Sparkles className="w-3.5 h-3.5 text-emerald-800" />
            Gemini Multimodal · Web en direct
          </span>
          <span className="text-xs text-neutral-500">Service officiel Agri Bénin</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-neutral-900">
          Assistant Agricole Intelligent
        </h1>
        <p className="text-sm text-neutral-600 mt-1 max-w-3xl">
          Conseiller agricole interactif par texte et par la voix. Il croise les fiches officielles validées, vos parcelles déclarées, les alertes phytosanitaires du Bénin et des recherches en direct sur le Web (actualités, météo, cours de marché).
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-8">
          <ChatInterface fullPage />
        </div>

        <div className="lg:col-span-4 space-y-4">
          <Card className="bg-white border-neutral-200">
            <h3 className="text-sm font-bold text-neutral-900 flex items-center gap-2 pb-2 mb-3 border-b border-neutral-100">
              <Sparkles className="w-4 h-4 text-emerald-800" />
              <span>Capacités du conseiller</span>
            </h3>

            <ul className="space-y-3 text-xs text-neutral-700">
              <li className="flex items-start gap-2">
                <Mic className="w-4 h-4 text-emerald-700 shrink-0 mt-0.5" />
                <div>
                  <strong className="text-neutral-900 block">Dictée vocale multilingue</strong>
                  Cliquez sur le micro et posez votre question en <strong>Français</strong>, en <strong>Fɔngbè</strong> ou en <strong>Yorùbá</strong>.
                </div>
              </li>

              <li className="flex items-start gap-2">
                <Volume2 className="w-4 h-4 text-emerald-700 shrink-0 mt-0.5" />
                <div>
                  <strong className="text-neutral-900 block">Restitution audio</strong>
                  Chaque réponse propose une synthèse vocale claire pour les exploitants qui lisent difficilement.
                </div>
              </li>

              <li className="flex items-start gap-2">
                <Globe className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                <div>
                  <strong className="text-neutral-900 block">Recherche Web en temps réel</strong>
                  En cas de questions sur les prix récents, la météo ou l'actualité, l'IA consulte Google Actualités Bénin et Wikipédia.
                </div>
              </li>

              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-700 shrink-0 mt-0.5" />
                <div>
                  <strong className="text-neutral-900 block">Données officielles garanties</strong>
                  Priorité absolue accordée aux référentiels agricoles du Bénin et aux fiches techniques certifiées.
                </div>
              </li>
            </ul>
          </Card>

          <Card className="bg-amber-50/60 border-amber-200">
            <h4 className="text-xs font-bold text-amber-900 flex items-center gap-1.5 mb-1.5">
              <Info className="w-4 h-4 text-amber-700" />
              <span>Conseil d'utilisation</span>
            </h4>
            <p className="text-xs text-amber-900/90 leading-relaxed">
              Pour une recommandation sur mesure, précisez la culture (maïs, ananas, manioc…), votre commune au Bénin et la superficie concernée.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
