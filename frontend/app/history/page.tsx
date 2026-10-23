"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { deleteConversation, getHealth, listConversations } from "@/lib/api";
import type { Conversation } from "@/lib/types";

export default function HistoryPage() {
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [backendLabel, setBackendLabel] = useState("Checking backend...");
  const [backendOk, setBackendOk] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const filteredConversations = conversations.filter((conversation) =>
    `${conversation.title} ${conversation.preview ?? ""}`
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase()),
  );

  async function load() {
    try {
      setConversations(await listConversations());
    } catch {
      setError("Could not load chat history.");
    }
  }

  useEffect(() => {
    getHealth()
      .then((health) => {
        const providers = health.providers;
        setBackendOk(Boolean(providers?.groq));
        setBackendLabel(
          [
            providers?.groq ? "Groq" : "Groq missing",
            providers?.exa ? "Exa" : "Exa missing",
            providers?.gemini ? "Gemini" : "Gemini missing",
          ].join(" · "),
        );
      })
      .catch(() => {
        setBackendOk(false);
        setBackendLabel("Backend offline");
      });
    load();
  }, []);

  async function remove(id: string) {
    try {
      await deleteConversation(id);
      setConversations((current) => current.filter((item) => item.id !== id));
    } catch {
      setError("Could not delete that chat.");
    }
  }

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        backendLabel={backendLabel}
        backendOk={backendOk}
      />
      <main className="main">
        <header className="main-header">
          <div className="header-title">History</div>
          <button className="text-btn" type="button" onClick={() => router.push("/")}>
            New research
          </button>
        </header>
        <section className="history">
          <h1>All chats</h1>
          <p className="subhead left">Pick up where you left off.</p>
          {error && <p className="error-banner">{error}</p>}
          {conversations.length > 0 && (
            <label className="history-search history-page-search">
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m16 16 4 4" /></svg>
              <input
                aria-label="Search all chats"
                placeholder="Search your chats"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              {search && <button type="button" aria-label="Clear search" onClick={() => setSearch("")}>×</button>}
            </label>
          )}
          {conversations.length === 0 && <p className="empty-list">No saved chats yet. Start a research chat and it will show up here.</p>}
          {conversations.length > 0 && filteredConversations.length === 0 && <p className="empty-list">No chats match “{search}”.</p>}
          <div className="history-list">
            {filteredConversations.map((conversation) => (
              <article key={conversation.id} className="history-card">
                <Link href={`/c/${conversation.id}`} className="history-card-link">
                  <h2>{conversation.title}</h2>
                  <p>{conversation.preview || "No messages yet."}</p>
                  <small>
                    {new Date(conversation.updated_at).toLocaleString()} ·{" "}
                    {conversation.message_count || 0} messages
                  </small>
                </Link>
                <button type="button" onClick={() => remove(conversation.id)}>
                  Delete
                </button>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
