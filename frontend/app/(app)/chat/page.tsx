"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Send,
  FileText,
  AlertCircle,
  Copy,
  Check,
  Trash2,
  ChevronDown,
  Sparkles,
} from "lucide-react";
import { getApiErrorMessage, streamChat, type ChatStreamEvent } from "@/lib/api-client";
import { useAuthStore } from "@/lib/auth-store";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

interface Citation {
  document: string;
  document_id: string;
  section: string | null;
  page: number | null;
  relevance_score: number;
}

interface Turn {
  id: number;
  role: "user" | "assistant";
  content: string;
  intent?: string;
  citations?: Citation[];
  confidence?: number;
  requiresHumanReview?: boolean;
  streaming?: boolean;
}

const SUGGESTIONS = [
  "What is the reverse charge mechanism under GST?",
  "Calculate GST on ₹100000 at 18% intra-state",
  "How does input tax credit work?",
  "What are the mandatory fields on a GST invoice?",
];

function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const tone =
    value >= 0.7 ? "var(--status-good)" : value >= 0.35 ? "var(--status-warning)" : "var(--status-critical)";

  return (
    <div className="flex items-center gap-2" title={`Model confidence: ${pct}%`}>
      <span className="text-[11px] text-muted-foreground">Confidence</span>
      <div className="h-1 w-16 overflow-hidden rounded-full bg-elevated">
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{ width: `${pct}%`, background: tone }}
        />
      </div>
      <span className="text-[11px] tabular-nums text-muted-foreground">{pct}%</span>
    </div>
  );
}

function SourceList({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="w-full max-w-[85%]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronDown
          className={cn("h-3 w-3 transition-transform duration-200", open && "rotate-180")}
        />
        {citations.length} source{citations.length === 1 ? "" : "s"}
      </button>

      {open && (
        <div className="animate-fade-in mt-2 flex flex-col gap-1.5">
          {citations.map((c, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs transition-colors hover:border-border-strong"
            >
              <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className="font-medium text-foreground">
                  <span className="mr-1.5 text-muted-foreground">[{i + 1}]</span>
                  {c.document}
                </div>
                <div className="mt-0.5 text-muted-foreground">
                  {c.section && `Section ${c.section}`}
                  {c.page ? ` · Page ${c.page}` : ""}
                  {` · Relevance ${Math.round(c.relevance_score * 100)}%`}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Couldn't copy", "Clipboard access was blocked by the browser.");
    }
  }

  return (
    <button
      onClick={copy}
      aria-label="Copy answer"
      className="text-muted-foreground transition-colors hover:text-foreground"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-good" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

export default function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const nextId = useRef(1);
  const sendingRef = useRef(false);
  const accessToken = useAuthStore((state) => state.accessToken);
  const authStatus = useAuthStore((state) => state.authStatus);
  const canSend = authStatus === "authenticated" && Boolean(accessToken);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, loading]);

  // Auto-grow the composer up to a cap.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const send = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed || loading || sendingRef.current || !canSend) return;

      sendingRef.current = true;
      const assistantId = nextId.current + 1;
      nextId.current += 2;
      setTurns((prev) => [
        ...prev,
        { id: assistantId - 1, role: "user", content: trimmed },
        { id: assistantId, role: "assistant", content: "", streaming: true },
      ]);
      setInput("");
      setLoading(true);

      const patch = (fn: (t: Turn) => Turn) =>
        setTurns((prev) => prev.map((t) => (t.id === assistantId ? fn(t) : t)));

      try {
        await streamChat(
          { message: trimmed, session_id: sessionId },
          (event: ChatStreamEvent) => {
            if (event.type === "session" && event.session_id) {
              setSessionId(event.session_id);
            } else if (event.type === "intent") {
              patch((t) => ({ ...t, intent: event.intent }));
            } else if (event.type === "delta" && event.text) {
              patch((t) => ({ ...t, content: t.content + event.text }));
            } else if (event.type === "done") {
              patch((t) => ({
                ...t,
                content: event.answer ?? t.content,
                intent: event.intent ?? t.intent,
                citations: (event.citations as Citation[]) ?? [],
                confidence: event.confidence,
                requiresHumanReview: event.requires_human_review,
                streaming: false,
              }));
              if (event.requires_human_review) {
                toast.warning(
                  "Human review recommended",
                  "The assistant flagged this answer as low-confidence."
                );
              }
            } else if (event.type === "error") {
              throw new Error(event.message ?? "The assistant stream failed.");
            }
          }
        );
      } catch (err) {
        const message = getApiErrorMessage(err, "Check the API is running.");
        patch((t) => ({
          ...t,
          content:
            t.content ||
            `I couldn't complete that request. ${message}`,
          intent: t.intent ?? "SUPPORT",
          confidence: 0,
          requiresHumanReview: true,
          streaming: false,
        }));
        toast.error("Couldn't reach the assistant", message);
      } finally {
        sendingRef.current = false;
        setLoading(false);
      }
    },
    [canSend, loading, sessionId]
  );

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">GST Chat</h1>
          <p className="text-xs text-muted-foreground">
            Grounded answers with citations · calculations run on the deterministic engine
          </p>
        </div>
        {turns.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setTurns([]);
              setSessionId(null);
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Clear
          </Button>
        )}
      </header>

      <main className="flex-1 overflow-y-auto px-6 py-6">
        {turns.length === 0 && !loading && (
          <div className="animate-fade-in-up mx-auto flex max-w-2xl flex-col items-center pt-12 text-center">
            <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-primary-wash">
              <Sparkles className="h-5 w-5 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">Ask about GST</h2>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">
              Answers are grounded in your indexed GST documents and always cite their sources.
              Tax figures come from the deterministic rule engine, never the model.
            </p>
            <div className="mt-6 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  disabled={!canSend || loading}
                  className="rounded-lg border border-border bg-card px-4 py-3 text-left text-sm text-secondary shadow-[var(--elev-1),var(--edge-top)] transition-all duration-200 ease-out hover:-translate-y-1 hover:border-border-strong hover:text-foreground hover:shadow-[var(--elev-3),var(--edge-top-strong)] active:translate-y-0 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
          {turns.map((turn) => (
            <div
              key={turn.id}
              className={cn(
                "animate-fade-in-up flex flex-col gap-2",
                turn.role === "user" ? "items-end" : "items-start"
              )}
            >
              <div
                className={cn(
                  "max-w-[85%] rounded-lg px-4 py-2.5 text-sm leading-relaxed transition-shadow duration-200",
                  turn.role === "user"
                    ? "bg-primary text-primary-foreground shadow-[var(--elev-2),var(--edge-top-strong)]"
                    : "border border-border bg-card shadow-[var(--elev-1),var(--edge-top)] hover:shadow-[var(--elev-2),var(--edge-top)]"
                )}
              >
                {turn.role === "assistant" ? (
                  <div className="prose-sm space-y-2 [&_code]:rounded [&_code]:bg-elevated [&_code]:px-1 [&_code]:py-0.5 [&_li]:ml-4 [&_ol]:list-decimal [&_strong]:font-semibold [&_ul]:list-disc">
                    {turn.content ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.content}</ReactMarkdown>
                    ) : (
                      <span className="flex items-center gap-2 text-muted-foreground">
                        <span className="flex gap-1">
                          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
                          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
                          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
                        </span>
                        {turn.intent === "GST_QUERY" || turn.intent === "DOCUMENT_SEARCH"
                          ? "Researching your GST sources…"
                          : "Thinking…"}
                      </span>
                    )}
                    {turn.streaming && turn.content && (
                      <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-primary align-middle" />
                    )}
                  </div>
                ) : (
                  turn.content
                )}
              </div>

              {turn.role === "assistant" && (
                <div className="flex max-w-[85%] flex-wrap items-center gap-2.5">
                  {turn.intent && <Badge variant="outline">{turn.intent}</Badge>}
                  {typeof turn.confidence === "number" && (
                    <ConfidenceMeter value={turn.confidence} />
                  )}
                  {turn.requiresHumanReview && (
                    <Badge variant="warning">
                      <AlertCircle className="h-3 w-3" />
                      Review recommended
                    </Badge>
                  )}
                  <CopyButton text={turn.content} />
                </div>
              )}

              {turn.citations && turn.citations.length > 0 && (
                <SourceList citations={turn.citations} />
              )}
            </div>
          ))}

          <div ref={bottomRef} />
        </div>
      </main>

      <div className="glass shrink-0 border-t border-border p-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="mx-auto flex max-w-3xl items-end gap-2"
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && canSend) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="Ask a GST question…  (Shift + Enter for a new line)"
            rows={1}
            disabled={!canSend || loading}
            className="flex-1 resize-none rounded-md border border-border bg-elevated px-3 py-2.5 text-sm transition-colors duration-200 placeholder:text-muted-foreground hover:border-border-strong focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          />
          <Button type="submit" size="icon" disabled={!input.trim() || !canSend} loading={loading}>
            {!loading && <Send className="h-4 w-4" />}
          </Button>
        </form>
      </div>
    </div>
  );
}
