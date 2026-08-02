"use client";

/**
 * The conversational surface.
 *
 * It answers from the evidence pack, and when a message asks for a change it produces a
 * proposal rather than acting. The server decides which of those happened; this component
 * only renders the outcome. That split is why a chat box can be safe here: the text box
 * cannot reach the pipeline, only the confirm button can.
 */

import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { ChatMessage } from "@/lib/types";
import { Badge, Banner, Button, Card, Prose } from "../ui";
import { RevisionCard } from "./RevisionCard";

export function AssistantPanel() {
  const { sessionId, state, credentials, applyState, llmAvailable } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const pendingRevision = state?.pending_revision ?? null;

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const loaded = await api.assistantState(sessionId, credentials);
        if (cancelled) return;
        setMessages(loaded.messages);
        setSuggestions(loaded.context.suggestions);
      } catch {
        // A failure to load suggestions is not worth interrupting the panel for.
      }
    })();
    return () => {
      cancelled = true;
    };
    // Reload when a new version lands so the suggestions reflect the current result.
  }, [sessionId, credentials, state?.versions.length]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const send = async (message: string) => {
    if (!sessionId || !message.trim()) return;
    setThinking(true);
    setError(null);
    setDraft("");
    setMessages((current) => [...current, { role: "user", content: message }]);
    try {
      const payload = await api.ask(sessionId, message, credentials);
      setMessages(payload.messages);
      applyState(payload.state);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
      setMessages((current) => current.slice(0, -1));
    } finally {
      setThinking(false);
    }
  };

  return (
    <div className="space-y-4">
      {pendingRevision ? <RevisionCard revision={pendingRevision} /> : null}

      <Card
        title="Ask about this analysis"
        description="Answers come from the evidence this run produced. Asking for a change produces a proposal, not a rerun."
        actions={
          messages.length ? (
            <Button
              onClick={() => {
                if (sessionId) void api.clearChat(sessionId);
                setMessages([]);
              }}
            >
              Clear
            </Button>
          ) : null
        }
      >
        {!llmAvailable ? (
          <div className="mb-4">
            <Banner tone="neutral">
              No model key is set, so replies are assembled deterministically from the
              evidence. They are terser, and every number in them is still one Atlas
              returned.
            </Banner>
          </div>
        ) : null}

        <div className="max-h-[28rem] space-y-3 overflow-y-auto">
          {messages.length === 0 ? (
            <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">
              I can explain why a region ranked where it did, which metrics were excluded
              and whether that matters, how much confidence the evidence supports, and what
              would change under a different weighting. I will not speculate past the
              evidence.
            </p>
          ) : null}

          {messages.map((message, index) => (
            <div
              key={index}
              className={
                message.role === "user"
                  ? "ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2.5 text-sm text-white"
                  : "mr-auto max-w-[92%] rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-2.5 text-sm text-slate-800"
              }
            >
              {message.role === "user" ? (
                <div className="whitespace-pre-wrap leading-relaxed">
                  {message.content}
                </div>
              ) : (
                <Prose text={message.content} className="text-slate-800" />
              )}
              {message.role === "assistant" ? (
                <div className="mt-2 space-y-1">
                  {message.refused ? <Badge tone="warning">Declined</Badge> : null}
                  {message.notes?.map((note) => (
                    <p key={note} className="text-xs text-amber-800">
                      ⚠ {note}
                    </p>
                  ))}
                  {message.generated_by ? (
                    <p className="text-xs text-slate-500">{message.generated_by}</p>
                  ) : null}
                </div>
              ) : null}
            </div>
          ))}

          {thinking ? (
            <div className="mr-auto rounded-2xl bg-slate-100 px-4 py-2.5 text-sm text-slate-500">
              Checking the evidence…
            </div>
          ) : null}
          <div ref={endRef} />
        </div>

        {error ? (
          <div className="mt-3">
            <Banner tone="negative">{error}</Banner>
          </div>
        ) : null}

        {suggestions.length && messages.length === 0 ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {suggestions.map((suggestion) => (
              <Button
                key={suggestion}
                onClick={() => void send(suggestion)}
                disabled={thinking}
                className="text-xs"
              >
                {suggestion}
              </Button>
            ))}
          </div>
        ) : null}

        <form
          className="mt-4 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void send(draft);
          }}
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask about the regions, or request a change to the analysis"
            aria-label="Message the assistant"
            disabled={thinking}
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <Button type="submit" variant="primary" disabled={thinking || !draft.trim()}>
            Send
          </Button>
        </form>
      </Card>
    </div>
  );
}
