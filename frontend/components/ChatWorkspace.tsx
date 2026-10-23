"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Sidebar from "@/components/Sidebar";
import {
  createConversation,
  getConversation,
  getHealth,
  listConversations,
  sendMessage,
  speakText,
  transcribeAudio,
  uploadFile,
} from "@/lib/api";
import type { ChatMessage, Conversation, UploadedFile } from "@/lib/types";

const EXAMPLES = [
  "Why did TCS fall today?",
  "Is Infosys a good business?",
  "What are the biggest risks facing Tata Motors?",
  "Why has HDFC Bank underperformed the NIFTY recently?",
  "What is the valuation of Reliance Industries?",
  "Compare TCS vs Infosys financial performance",
];

type ChatWorkspaceProps = {
  conversationId?: string;
};

export default function ChatWorkspace({ conversationId }: ChatWorkspaceProps) {
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [backendLabel, setBackendLabel] = useState("Checking backend...");
  const [backendOk, setBackendOk] = useState(false);
  const [recording, setRecording] = useState(false);
  const [voiceMode, setVoiceMode] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const title = useMemo(() => {
    const match = conversations.find((item) => item.id === conversationId);
    return match?.title || "Docstox Research Agent";
  }, [conversations, conversationId]);

  async function refreshSidebar() {
    try {
      setConversations(await listConversations());
    } catch {
      setConversations([]);
    }
  }

  useEffect(() => {
    getHealth()
      .then((health) => {
        const providers = health.providers;
        const parts = [
          providers?.groq ? "Groq" : "Groq missing",
          providers?.exa ? "Exa" : "Exa missing",
          providers?.gemini ? "Gemini" : "Gemini missing",
        ];
        setBackendOk(Boolean(providers?.groq));
        setBackendLabel(parts.join(" · "));
      })
      .catch(() => {
        setBackendOk(false);
        setBackendLabel("Backend offline");
      });
    refreshSidebar();
  }, []);

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      setFiles([]);
      return;
    }
    getConversation(conversationId)
      .then((conversation) => {
        setMessages(conversation.messages || []);
        setFiles(conversation.files || []);
      })
      .catch(() => setError("This chat could not be loaded."));
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function playAssistant(text: string) {
    if (!voiceMode) return;
    try {
      const blob = await speakText(text);
      const url = URL.createObjectURL(blob);
      if (audioRef.current) {
        audioRef.current.pause();
      }
      const audio = new Audio(url);
      audioRef.current = audio;
      await audio.play();
    } catch {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
      } else {
        setError("Voice reply could not be played on this device.");
      }
    }
  }

  async function submitText(text: string) {
    const content = text.trim();
    if (!content) return;
    setError("");
    setBusy(true);
    setQuestion("");
    try {
      let id = conversationId;
      if (!id) {
        const created = await createConversation(content);
        id = created.id;
        const result = await sendMessage(id, content);
        await refreshSidebar();
        const assistant = result.assistant as ChatMessage;
        if (assistant?.content) {
          await playAssistant(assistant.content);
        }
        router.push(`/c/${id}`);
        return;
      }
      setMessages((current) => [
        ...current,
        {
          id: `local-${Date.now()}`,
          conversation_id: id,
          role: "user",
          content,
          tools: [],
          citations: [],
          trace: [],
          created_at: new Date().toISOString(),
        },
      ]);
      const result = await sendMessage(id, content);
      const conversation = await getConversation(id);
      setMessages(conversation.messages || []);
      setFiles(conversation.files || []);
      await refreshSidebar();
      const assistant = result.assistant as ChatMessage;
      if (assistant?.content) {
        await playAssistant(assistant.content);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "The agent could not reply.");
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await submitText(question);
  }

  async function onUpload(fileList: FileList | null) {
    if (!fileList?.length) return;
    setError("");
    setBusy(true);
    try {
      let id = conversationId;
      if (!id) {
        const created = await createConversation("Document research");
        id = created.id;
      }
      for (const file of Array.from(fileList)) {
        const uploaded = await uploadFile(id, file);
        setFiles((current) => [uploaded, ...current.filter((item) => item.id !== uploaded.id)]);
      }
      await refreshSidebar();
      if (!conversationId) {
        router.replace(`/c/${id}`);
        return;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "File upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleRecording() {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        try {
          const text = await transcribeAudio(blob);
          await submitText(text);
        } catch (err) {
          setError(err instanceof Error ? err.message : "Transcription failed.");
        }
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setVoiceMode(true);
      setError("");
    } catch {
      setError("Microphone access was denied.");
    }
  }

  const empty = messages.length === 0;

  return (
    <div className={`app ${sidebarOpen ? "sidebar-open" : ""}`}>
      <Sidebar
        conversations={conversations}
        backendLabel={backendLabel}
        backendOk={backendOk}
        onClose={() => setSidebarOpen(false)}
      />

      <main className="main">
        <header className="main-header">
          <button className="menu-btn" type="button" onClick={() => setSidebarOpen((open) => !open)}>
            ☰
          </button>
          <div className="header-title">{title}</div>
          <div className="header-actions">
            <div className={`status ${backendOk ? "ok" : ""}`}>
              <span className={`status-dot ${backendOk ? "ok" : ""}`}></span>
              {backendLabel}
            </div>
          </div>
        </header>

        {empty ? (
          <section className="welcome-screen">
            <div className="welcome-header">
              <div className="welcome-icon">D</div>
              <h1 className="greeting">What would you like to research?</h1>
              <p className="subhead">
                Ask a question, upload a filing, or speak. Exa web search grounds
                factual answers in current sources. Gemini File Search can search
                documents you attach.
              </p>
            </div>
            <Composer
              question={question}
              setQuestion={setQuestion}
              busy={busy}
              recording={recording}
              voiceMode={voiceMode}
              onSubmit={onSubmit}
              onUpload={onUpload}
              onToggleVoice={toggleRecording}
              onToggleSpeak={() => setVoiceMode((value) => !value)}
            />
            <div className="examples">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  className="example"
                  type="button"
                  onClick={() => submitText(example)}
                >
                  {example}
                </button>
              ))}
            </div>
          </section>
        ) : (
          <>
            <section className="thread">
              <div className="thread-inner">
                {files.length > 0 && (
                  <>
                    <div className="file-row">
                      {files.map((file) => (
                        <span key={file.id} className={`file-chip ${file.status}`}>
                          {file.filename}
                          <em>{file.status}</em>
                        </span>
                      ))}
                    </div>
                    {files.some((file) => file.status !== "ready") && (
                      <p className="file-warning" role="status">
                        Some attached files are not indexed yet and will not be used as evidence.
                      </p>
                    )}
                  </>
                )}
                {messages.map((message) => (
                  <article key={message.id} className={`bubble ${message.role}`}>
                    <div className="bubble-meta">
                      <span className={`bubble-avatar ${message.role}`}>
                        {message.role === "user" ? "You" : "D"}
                      </span>
                      {message.tools?.length > 0 && (
                        <span className="tools">{message.tools.join(" · ")}</span>
                      )}
                    </div>
                    <div className="bubble-body">
                      {message.role === "assistant" ? (
                        <MarkdownContent content={message.content} />
                      ) : (
                        message.content
                      )}
                    </div>
                    {message.trace?.length > 0 && (
                      <details className="research-trace">
                        <summary>Research trace · {message.trace.length} steps</summary>
                        <ol>
                          {message.trace.map((step, index) => (
                            <li key={`${step.label}-${index}`}>
                              <span className={`trace-status ${step.status}`}>{step.status}</span>
                              <div>
                                <strong>{step.label}</strong>
                                <small>{step.detail}</small>
                              </div>
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}
                    {message.citations?.length > 0 && (
                      <div className="citations">
                        {message.citations.map((citation, index) => (
                          <a
                            key={`${citation.title}-${index}`}
                            className="citation"
                            href={citation.url || undefined}
                            target={citation.url ? "_blank" : undefined}
                            rel="noreferrer"
                          >
                            <strong>
                              [{index + 1}] {citation.source_name || citation.title}
                            </strong>
                            <span>{citation.title}</span>
                            {citation.reliability && <em>{citation.reliability}</em>}
                            {citation.published_date && (
                              <small>Published {citation.published_date}</small>
                            )}
                            {citation.why && <small>{citation.why}</small>}
                          </a>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
                {busy && (
                  <div className="thinking">
                    <div className="thinking-dots">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                    Researching…
                  </div>
                )}
              </div>
              <div ref={bottomRef} />
            </section>
            <div className="composer-dock">
              <Composer
                question={question}
                setQuestion={setQuestion}
                busy={busy}
                recording={recording}
                voiceMode={voiceMode}
                onSubmit={onSubmit}
                onUpload={onUpload}
                onToggleVoice={toggleRecording}
                onToggleSpeak={() => setVoiceMode((value) => !value)}
              />
            </div>
          </>
        )}

        {error && <p className="error-banner">{error}</p>}
      </main>
    </div>
  );
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}

type ComposerProps = {
  question: string;
  setQuestion: (value: string) => void;
  busy: boolean;
  recording: boolean;
  voiceMode: boolean;
  onSubmit: (event: FormEvent) => void;
  onUpload: (files: FileList | null) => void;
  onToggleVoice: () => void;
  onToggleSpeak: () => void;
};

function Composer({
  question,
  setQuestion,
  busy,
  recording,
  voiceMode,
  onSubmit,
  onUpload,
  onToggleVoice,
  onToggleSpeak,
}: ComposerProps) {
  const fileRef = useRef<HTMLInputElement | null>(null);

  return (
    <form className="composer" onSubmit={onSubmit}>
      <input
        ref={fileRef}
        className="hidden-input"
        type="file"
        multiple
        accept=".pdf,.txt,.md,.csv,.json,.doc,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.html,.htm"
        onChange={(event) => {
          onUpload(event.target.files);
          event.target.value = "";
        }}
      />
      <button
        className="icon-btn"
        type="button"
        title="Upload file"
        onClick={() => fileRef.current?.click()}
        disabled={busy}
      >
        +
      </button>
      <textarea
        rows={1}
        value={question}
        placeholder={recording ? "Listening..." : "Ask about a listed company, or a document..."}
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
      />
      <button
        className={`icon-btn ${voiceMode ? "active" : ""}`}
        type="button"
        title="Voice replies"
        onClick={onToggleSpeak}
      >
        ♪
      </button>
      <button
        className={`icon-btn ${recording ? "recording" : ""}`}
        type="button"
        title="Voice conversation"
        onClick={onToggleVoice}
        disabled={busy && !recording}
      >
        ●
      </button>
      <button className="send" type="submit" disabled={!question.trim() || busy}>
        ↑
      </button>
    </form>
  );
}
