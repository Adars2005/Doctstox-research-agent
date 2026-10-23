"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { Conversation } from "@/lib/types";

type SidebarProps = {
  conversations: Conversation[];
  backendLabel: string;
  backendOk: boolean;
  onClose?: () => void;
};

const groupOrder = ["Today", "Yesterday", "Previous 7 days", "Previous 30 days", "Older"];

function historyGroup(dateValue: string): string {
  const date = new Date(dateValue);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const daysAgo = Math.floor((today.getTime() - day.getTime()) / 86_400_000);
  if (daysAgo <= 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  if (daysAgo < 7) return "Previous 7 days";
  if (daysAgo < 30) return "Previous 30 days";
  return "Older";
}

export default function Sidebar({
  conversations,
  backendLabel,
  backendOk,
  onClose,
}: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [search, setSearch] = useState("");
  const groupedConversations = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    const groups = new Map<string, Conversation[]>();
    for (const conversation of conversations) {
      if (query && !`${conversation.title} ${conversation.preview ?? ""}`.toLocaleLowerCase().includes(query)) continue;
      const group = historyGroup(conversation.updated_at);
      groups.set(group, [...(groups.get(group) ?? []), conversation]);
    }
    return groupOrder
      .filter((group) => groups.has(group))
      .map((group) => ({ title: group, items: groups.get(group)! }));
  }, [conversations, search]);

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">D</div>
        <div className="brand-name">Docstox Research</div>
      </div>

      <button
        className="new-chat"
        type="button"
        onClick={() => {
          onClose?.();
          router.push("/");
        }}
      >
        New research
      </button>

      <label className="history-search">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m16 16 4 4" /></svg>
        <input
          aria-label="Search chats"
          placeholder="Search chats"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        {search && <button type="button" aria-label="Clear search" onClick={() => setSearch("")}>×</button>}
      </label>

      <Link
        className={`nav-link history-link ${pathname === "/history" ? "active" : ""}`}
        href="/history"
        onClick={onClose}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12a9 9 0 1 0 2.64-6.36L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></svg>
        All chats
      </Link>

      <nav className="chat-list" aria-label="Chat history">
        {conversations.length === 0 && <p className="empty-list">Your conversations will appear here.</p>}
        {conversations.length > 0 && groupedConversations.length === 0 && (
          <p className="empty-list">No chats match “{search}”.</p>
        )}
        {groupedConversations.map(({ title, items }) => (
          <section className="chat-group" key={title}>
            <h2 className="sidebar-label">{title}</h2>
            {items.map((conversation) => {
              const href = `/c/${conversation.id}`;
              return (
                <Link
                  key={conversation.id}
                  href={href}
                  className={`chat-item ${pathname === href ? "active" : ""}`}
                  onClick={onClose}
                  title={conversation.title}
                >
                  <span>{conversation.title || "Untitled chat"}</span>
                </Link>
              );
            })}
          </section>
        ))}
      </nav>

      <div className={`sidebar-footer ${backendOk ? "ok" : ""}`}>
        <span className="status-indicator" aria-hidden="true" />
        <span>{backendLabel}</span>
      </div>
    </aside>
  );
}
