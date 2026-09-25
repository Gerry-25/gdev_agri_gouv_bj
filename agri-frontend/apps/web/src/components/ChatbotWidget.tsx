import { Maximize2, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChatInterface } from "./ChatInterface";

export function ChatbotWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const location = useLocation();

  if (location.pathname === "/chat") {
    return null;
  }

  return (
    <>
      {!isOpen && (
        <div className="fixed bottom-20 right-4 lg:bottom-6 lg:right-6 z-40">
          <button
            type="button"
            onClick={() => setIsOpen(true)}
            aria-label="Ouvrir l'Assistant Agricole Intelligent"
            className="group relative flex items-center gap-2.5 bg-emerald-800 hover:bg-emerald-900 text-white pl-4 pr-5 py-3 rounded-full shadow-xl transition-all duration-200 hover:scale-105 active:scale-95 border-2 border-emerald-700/60 cursor-pointer"
          >
            <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-400" />
            </span>

            <Sparkles className="w-5 h-5 text-emerald-300 animate-pulse" />
            <div className="flex flex-col text-left">
              <span className="text-xs font-bold leading-tight">Conseiller IA</span>
              <span className="text-[10px] text-emerald-200 font-medium">Texte & Voix</span>
            </div>
          </button>
        </div>
      )}

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:justify-end p-2 sm:p-6 bg-black/40 backdrop-blur-xs sm:bg-transparent">
          <div className="w-full max-w-lg sm:w-[440px] shadow-2xl rounded-xl overflow-hidden bg-white border border-neutral-300 animate-in slide-in-from-bottom-5 duration-200">
            <div className="bg-emerald-950 text-white px-3 py-1.5 flex items-center justify-between text-xs border-b border-emerald-900">
              <span className="text-emerald-300 font-medium">Fenêtre d'assistance</span>
              <div className="flex items-center gap-2">
                <Link
                  to="/chat"
                  onClick={() => setIsOpen(false)}
                  className="hover:text-emerald-200 flex items-center gap-1 transition-colors"
                  title="Ouvrir en plein écran"
                >
                  <Maximize2 className="w-3.5 h-3.5" />
                  <span>Plein écran</span>
                </Link>
              </div>
            </div>

            <ChatInterface onClose={() => setIsOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}
