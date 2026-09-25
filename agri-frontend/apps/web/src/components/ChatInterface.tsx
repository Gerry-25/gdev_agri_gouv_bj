import { API_ORIGIN, authStore, LANGUAGES, type LanguageCode, speak, stopSpeaking, useSession } from "@agri/core";
import {
  Bot,
  ExternalLink,
  Globe,
  Loader2,
  Mic,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  User,
  Volume2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

export interface SourceItem {
  source_type: "database" | "web";
  title: string;
  url?: string | null;
  snippet?: string | null;
}

export interface Message {
  id?: string;
  role: "user" | "assistant";
  content: string;
  audio_summary?: string;
  audio_url?: string;
  sources?: SourceItem[];
  used_web?: boolean;
  isVoice?: boolean;
  created_at?: string;
}

const SUGGESTIONS = [
  "Quelles sont les meilleures techniques pour cultiver le maïs au Bénin ?",
  "Que faire contre la chenille légionnaire d'automne ?",
  "Quels sont les prix actuels des produits agricoles sur le marché ?",
  "Comment bien fertiliser une parcelle d'ananas ?",
  "Quelles sont les étapes pour enregistrer une parcelle au cadastre ?",
];

const getLangLabel = (code: string) => LANGUAGES.find((l) => l.code === code)?.label || code;

/** Rendu simplifié et sécurisé du texte Markdown */
function MarkdownView({ text }: { text: string }) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let inList = false;
  let listItems: React.ReactNode[] = [];

  const flushList = () => {
    if (inList) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="list-disc pl-5 my-2 space-y-1">
          {listItems}
        </ul>
      );
      inList = false;
      listItems = [];
    }
  };

  const formatInline = (str: string) => {
    const boldSplit = str.split(/(\*\*.*?\*\*)/g);
    return boldSplit.map((chunk, i) => {
      if (chunk.startsWith("**") && chunk.endsWith("**") && chunk.length >= 4) {
        return <strong key={i} className="font-semibold text-neutral-900">{chunk.slice(2, -2)}</strong>;
      }
      return chunk;
    });
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }

    if (trimmed.startsWith("### ")) {
      flushList();
      elements.push(
        <h4 key={idx} className="font-bold text-neutral-900 text-sm mt-3 mb-1">
          {formatInline(trimmed.slice(4))}
        </h4>
      );
    } else if (trimmed.startsWith("## ")) {
      flushList();
      elements.push(
        <h3 key={idx} className="font-bold text-neutral-900 text-base mt-4 mb-2">
          {formatInline(trimmed.slice(3))}
        </h3>
      );
    } else if (trimmed.startsWith("# ")) {
      flushList();
      elements.push(
        <h2 key={idx} className="font-bold text-neutral-900 text-lg mt-4 mb-2">
          {formatInline(trimmed.slice(2))}
        </h2>
      );
    } else if (trimmed.startsWith("* ") || trimmed.startsWith("- ")) {
      inList = true;
      listItems.push(
        <li key={idx} className="text-neutral-800 leading-relaxed text-sm">
          {formatInline(trimmed.slice(2))}
        </li>
      );
    } else {
      flushList();
      elements.push(
        <p key={idx} className="text-neutral-800 text-sm leading-relaxed my-1.5">
          {formatInline(trimmed)}
        </p>
      );
    }
  });

  flushList();

  return <div className="space-y-1">{elements}</div>;
}

interface ChatInterfaceProps {
  fullPage?: boolean;
  onClose?: () => void;
}

export function ChatInterface({ fullPage = false, onClose }: ChatInterfaceProps) {
  const { user } = useSession();
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Bonjour ! Je suis votre conseiller agricole intelligent. Je peux vous renseigner sur les techniques culturales, les prix, la météo, la santé de vos cultures ou vos démarches foncières. Vous pouvez me poser vos questions à l'écrit ou me parler directement à la voix !",
      audio_summary:
        "Bonjour ! Je suis votre assistant agricole intelligent. Posez-moi vos questions par écrit ou par la voix.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [forceWebSearch, setForceWebSearch] = useState(false);
  const [selectedLang, setSelectedLang] = useState<LanguageCode>(
    (user?.preferred_language as LanguageCode) || "fr"
  );

  // Enregistrement vocal (Microphone)
  const [isRecording, setIsRecording] = useState(false);
  const [recordDuration, setRecordDuration] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<any>(null);

  // Audio playback
  const [playingMessageId, setPlayingMessageId] = useState<string | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    return () => {
      stopCurrentAudio();
      stopRecordingTracks();
    };
  }, []);

  const stopCurrentAudio = () => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    stopSpeaking();
    setPlayingMessageId(null);
  };

  const stopRecordingTracks = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    setRecordDuration(0);
  };

  // Jouer l'audio de synthèse d'un message
  const playAudio = async (msg: Message, index: number) => {
    const key = msg.id || `msg-${index}`;
    if (playingMessageId === key) {
      stopCurrentAudio();
      return;
    }

    stopCurrentAudio();
    setPlayingMessageId(key);

    const textToSpeak = msg.audio_summary || msg.content;
    const targetUrl = msg.audio_url ? `${API_ORIGIN}${msg.audio_url}` : null;

    if (targetUrl) {
      setAudioLoading(true);
      try {
        const res = await fetch(targetUrl);
        if (res.ok) {
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const audio = new Audio(url);
          currentAudioRef.current = audio;
          audio.onended = () => {
            setPlayingMessageId(null);
            setAudioLoading(false);
          };
          audio.onerror = () => {
            fallbackSpeak(textToSpeak);
          };
          await audio.play();
          setAudioLoading(false);
          return;
        }
      } catch (err) {
        console.warn("Audio serveur indisponible, passage sur synthèse vocale locale :", err);
      }
      setAudioLoading(false);
    }

    fallbackSpeak(textToSpeak);
  };

  const fallbackSpeak = (text: string) => {
    const langTag = selectedLang === "en" ? "en-US" : "fr-FR";
    speak(text, langTag);
  };

  // Démarrer l'enregistrement micro
  const startRecording = async () => {
    stopCurrentAudio();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : MediaRecorder.isTypeSupported("audio/mp4")
        ? "audio/mp4"
        : "";
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.start(100);
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
      setRecordDuration(0);

      timerRef.current = setInterval(() => {
        setRecordDuration((prev) => {
          if (prev >= 59) {
            handleStopAndSendVoice();
            return 60;
          }
          return prev + 1;
        });
      }, 1000);
    } catch (err) {
      console.error("Microphone non autorisé :", err);
      alert("Veuillez autoriser l'accès au microphone dans votre navigateur pour parler au conseiller.");
    }
  };

  // Arrêter l'enregistrement et envoyer
  const handleStopAndSendVoice = async () => {
    if (!mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") return;

    if (timerRef.current) clearInterval(timerRef.current);
    setIsRecording(false);

    const recorder = mediaRecorderRef.current;
    recorder.onstop = async () => {
      recorder.stream.getTracks().forEach((track) => track.stop());
      const mime = recorder.mimeType || "audio/webm";
      const blob = new Blob(audioChunksRef.current, { type: mime });
      if (blob.size < 100) return;

      await sendVoiceMessage(blob);
    };

    recorder.stop();
  };

  const sendVoiceMessage = async (audioBlob: Blob) => {
    setLoading(true);
    const tempUserMsg: Message = {
      role: "user",
      content: "🎤 Question vocale enregistrée... (analyse en cours)",
      isVoice: true,
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    try {
      const formData = new FormData();
      formData.append("file", audioBlob, "question.webm");
      formData.append("language", selectedLang);
      if (forceWebSearch) formData.append("force_web_search", "true");

      const historyPayload = messages
        .filter((m) => m.content && !m.content.startsWith("🎤 Question vocale"))
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content }));
      formData.append("history", JSON.stringify(historyPayload));

      const headers: Record<string, string> = {};
      const token = authStore.get().accessToken;
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${API_ORIGIN}/api/v1/chatbot/message-voice`, {
        method: "POST",
        headers,
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`Erreur serveur (${res.status})`);
      }

      const data = await res.json();

      setMessages((prev) => {
        const next = [...prev];
        const lastIdx = next.length - 1;
        if (lastIdx >= 0 && next[lastIdx].role === "user") {
          next[lastIdx] = {
            role: "user",
            content: data.user_transcript || "Question vocale",
            isVoice: true,
          };
        }
        next.push({
          id: data.id,
          role: "assistant",
          content: data.answer,
          audio_summary: data.audio_summary,
          audio_url: data.audio_url,
          sources: data.sources,
          used_web: data.used_web,
        });
        return next;
      });

      if (data.audio_summary) {
        setTimeout(() => {
          fallbackSpeak(data.audio_summary);
        }, 500);
      }
    } catch (err: any) {
      console.error("Erreur message vocal :", err);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Désolé, je n'ai pas pu analyser votre message vocal. Merci de réessayer ou d'écrire votre question.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Envoi de message texte
  const sendTextMessage = async (textToSend?: string) => {
    const text = (textToSend || input).trim();
    if (!text || loading) return;

    stopCurrentAudio();
    setInput("");
    const userMsg: Message = { role: "user", content: text };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setLoading(true);

    try {
      const historyPayload = nextMessages.slice(-7, -1).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const token = authStore.get().accessToken;
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${API_ORIGIN}/api/v1/chatbot/message`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          message: text,
          history: historyPayload,
          language: selectedLang,
          force_web_search: forceWebSearch,
        }),
      });

      if (!res.ok) {
        throw new Error(`Erreur (${res.status})`);
      }

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          id: data.id,
          role: "assistant",
          content: data.answer,
          audio_summary: data.audio_summary,
          audio_url: data.audio_url,
          sources: data.sources,
          used_web: data.used_web,
        },
      ]);
    } catch (err: any) {
      console.error("Erreur envoi message :", err);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Une erreur est survenue lors de la communication avec l'assistant. Vérifiez votre connexion et réessayez.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendTextMessage();
    }
  };

  const clearChat = () => {
    stopCurrentAudio();
    setMessages([
      {
        role: "assistant",
        content: "Conversation réinitialisée. Comment puis-je vous aider aujourd'hui ?",
      },
    ]);
  };

  return (
    <div className={`flex flex-col ${fullPage ? "h-[calc(100vh-140px)] min-h-[550px]" : "h-[560px]"} bg-neutral-50 rounded-lg overflow-hidden border border-neutral-200`}>
      {/* En-tête */}
      <div className="bg-emerald-900 text-white px-4 py-3 flex items-center justify-between gap-3 shrink-0 shadow-sm">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-9 h-9 rounded-full bg-emerald-800 border border-emerald-700 flex items-center justify-center text-white shrink-0">
            <Sparkles className="w-5 h-5 text-emerald-300" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-bold truncate flex items-center gap-2">
              <span>Assistant Intelligent Agri Bénin</span>
              <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" title="IA en direct" />
            </h3>
            <p className="text-xs text-emerald-200 truncate">
              {forceWebSearch ? "Recherche Web active" : "Données terrain & Web en direct"} · {getLangLabel(selectedLang)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {/* Sélecteur de langue */}
          <select
            value={selectedLang}
            onChange={(e) => setSelectedLang(e.target.value as LanguageCode)}
            className="bg-emerald-950 text-white text-xs border border-emerald-700 rounded px-2 py-1 focus:outline-none cursor-pointer"
            aria-label="Langue de l'assistant"
          >
            <option value="fr">🇫🇷 Français</option>
            <option value="fon">🇧🇯 Fɔngbè</option>
            <option value="yo">🇳🇬/🇧🇯 Yorùbá</option>
            <option value="en">🇬🇧 English</option>
          </select>

          <button
            type="button"
            onClick={clearChat}
            title="Effacer la conversation"
            className="p-1.5 rounded hover:bg-emerald-800 text-emerald-200 hover:text-white transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
          </button>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded hover:bg-emerald-800 text-emerald-200 hover:text-white transition-colors text-lg font-bold leading-none px-2"
              aria-label="Fermer"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Barre d'options rapides */}
      <div className="bg-white border-b border-neutral-200 px-3 py-1.5 flex items-center justify-between text-xs text-neutral-600 shrink-0">
        <label className="flex items-center gap-1.5 cursor-pointer hover:text-neutral-900 select-none">
          <input
            type="checkbox"
            checked={forceWebSearch}
            onChange={(e) => setForceWebSearch(e.target.checked)}
            className="rounded text-emerald-800 focus:ring-emerald-700"
          />
          <Globe className="w-3.5 h-3.5 text-blue-600" />
          <span>Recherche Web systématique</span>
        </label>

        <span className="text-[11px] text-neutral-500">
          🎙️ Dictée vocale multilingue disponible
        </span>
      </div>

      {/* Zone des messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((m, idx) => {
          const isUser = m.role === "user";
          const isPlaying = playingMessageId === (m.id || `msg-${idx}`);

          return (
            <div key={idx} className={`flex gap-2.5 ${isUser ? "justify-end" : "justify-start"}`}>
              {!isUser && (
                <div className="w-7 h-7 rounded-full bg-emerald-100 border border-emerald-300 flex items-center justify-center shrink-0 mt-0.5">
                  <Bot className="w-4 h-4 text-emerald-900" />
                </div>
              )}

              <div className={`max-w-[85%] sm:max-w-[75%] rounded-lg p-3 text-sm shadow-sm ${
                isUser
                  ? "bg-emerald-800 text-white rounded-tr-none"
                  : "bg-white border border-neutral-200 text-neutral-800 rounded-tl-none"
              }`}>
                {m.isVoice && (
                  <div className="flex items-center gap-1 text-xs text-emerald-200 mb-1 font-medium">
                    <Mic className="w-3 h-3" />
                    <span>Message vocal</span>
                  </div>
                )}

                {isUser ? (
                  <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                ) : (
                  <MarkdownView text={m.content} />
                )}

                {!isUser && (m.audio_summary || m.content) && (
                  <div className="mt-3 pt-2 border-t border-neutral-100 flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => playAudio(m, idx)}
                      disabled={audioLoading && isPlaying}
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                        isPlaying
                          ? "bg-amber-100 text-amber-900 border border-amber-300"
                          : "bg-emerald-50 hover:bg-emerald-100 text-emerald-900 border border-emerald-200"
                      }`}
                    >
                      {isPlaying ? (
                        <>
                          <Square className="w-3.5 h-3.5 fill-current" />
                          <span>Arrêter la lecture</span>
                        </>
                      ) : (
                        <>
                          <Volume2 className="w-3.5 h-3.5 text-emerald-700" />
                          <span>Écouter la réponse ({getLangLabel(selectedLang)})</span>
                        </>
                      )}
                    </button>

                    {m.used_web && (
                      <span className="text-[11px] text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200 flex items-center gap-1">
                        <Globe className="w-3 h-3" />
                        Web en direct
                      </span>
                    )}
                  </div>
                )}

                {!isUser && m.sources && m.sources.length > 0 && (
                  <div className="mt-2.5 pt-2 border-t border-neutral-100 text-xs text-neutral-600">
                    <p className="font-semibold text-neutral-700 mb-1 flex items-center gap-1">
                      <span>Sources consultées :</span>
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {m.sources.map((s, sIdx) => {
                        const isWeb = s.source_type === "web";
                        return (
                          <span
                            key={sIdx}
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium border ${
                              isWeb
                                ? "bg-blue-50 text-blue-900 border-blue-200"
                                : "bg-emerald-50 text-emerald-900 border-emerald-200"
                            }`}
                          >
                            {isWeb ? <Globe className="w-3 h-3 text-blue-600 shrink-0" /> : <Sparkles className="w-3 h-3 text-emerald-700 shrink-0" />}
                            <span className="max-w-[170px] truncate" title={s.title}>{s.title}</span>
                            {s.url && (
                              <a
                                href={s.url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-neutral-500 hover:text-neutral-900"
                              >
                                <ExternalLink className="w-2.5 h-2.5" />
                              </a>
                            )}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {isUser && (
                <div className="w-7 h-7 rounded-full bg-emerald-800 text-white flex items-center justify-center shrink-0 mt-0.5">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          );
        })}

        {loading && (
          <div className="flex gap-2.5 items-start">
            <div className="w-7 h-7 rounded-full bg-emerald-100 border border-emerald-300 flex items-center justify-center shrink-0">
              <Bot className="w-4 h-4 text-emerald-900" />
            </div>
            <div className="bg-white border border-neutral-200 rounded-lg rounded-tl-none p-3 shadow-sm text-neutral-600 text-xs flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-emerald-700" />
              <span>L'assistant consulte les données officielles et le web en direct…</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {messages.length <= 2 && (
        <div className="px-3 py-2 bg-neutral-100/70 border-t border-neutral-200 shrink-0 overflow-x-auto">
          <p className="text-[11px] font-semibold text-neutral-600 mb-1.5">Questions fréquentes :</p>
          <div className="flex gap-1.5 flex-nowrap sm:flex-wrap">
            {SUGGESTIONS.map((q, i) => (
              <button
                key={i}
                type="button"
                onClick={() => sendTextMessage(q)}
                className="bg-white hover:bg-emerald-50 text-neutral-800 hover:text-emerald-950 text-xs px-2.5 py-1 rounded border border-neutral-200 hover:border-emerald-300 whitespace-nowrap transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {isRecording && (
        <div className="bg-red-50 border-t border-red-200 px-4 py-2.5 flex items-center justify-between gap-3 text-red-900 animate-pulse shrink-0">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <span className="w-3 h-3 rounded-full bg-red-600 animate-ping" />
            <span>Enregistrement vocal en cours ({recordDuration}s / 60s)</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={stopRecordingTracks}
              className="text-xs text-neutral-600 hover:text-neutral-900 underline px-2 py-1"
            >
              Annuler
            </button>
            <button
              type="button"
              onClick={handleStopAndSendVoice}
              className="bg-red-700 hover:bg-red-800 text-white text-xs font-bold px-3 py-1.5 rounded flex items-center gap-1.5 shadow"
            >
              <Square className="w-3 h-3 fill-current" />
              <span>Terminer et envoyer</span>
            </button>
          </div>
        </div>
      )}

      {!isRecording && (
        <div className="p-3 bg-white border-t border-neutral-200 shrink-0">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendTextMessage();
            }}
            className="flex items-end gap-2"
          >
            <button
              type="button"
              onClick={startRecording}
              disabled={loading}
              title="Dicter ma question à la voix (Microphone)"
              className="w-11 h-11 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-900 border border-emerald-300 flex items-center justify-center shrink-0 transition-colors shadow-sm cursor-pointer disabled:opacity-50"
            >
              <Mic className="w-5 h-5 text-emerald-800" />
            </button>

            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Posez votre question (ou cliquez sur le micro)…"
                disabled={loading}
                className="w-full resize-none rounded-lg border border-neutral-300 focus:border-emerald-700 focus:ring-1 focus:ring-emerald-700 py-2.5 pl-3 pr-3 text-sm placeholder:text-neutral-400 max-h-28 outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={!input.trim() || loading}
              className="w-11 h-11 rounded-lg bg-emerald-800 hover:bg-emerald-900 text-white flex items-center justify-center shrink-0 transition-colors shadow-sm disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
