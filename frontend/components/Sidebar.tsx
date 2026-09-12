"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { Conversation } from "@/lib/types";

type SidebarProps = {
  conversations: Conversation[];
  backendLabel: string;
  backendOk: boolean;
  onClose?: () => void;
};

export default function Sidebar({
  conversations,
  backendLabel,
  backendOk,
  onClose,
}: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">D</div>
        <div className="brand-name">Docstox-research agent</div>
      </div>

      <button
        className="new-chat"
        type="button"
        onClick={() => {
          onClose?.();
          router.push("/");
        }}
      >
        + New research
      </button>

      <Link
        className={`nav-link ${pathname === "/history" ? "active" : ""}`}
        href="/history"
        onClick={onClose}
      >
        History
      </Link>

      <div className="sidebar-label">Recent</div>
      <nav className="chat-list">
        {conversations.length === 0 && (
          <p className="empty-list">No chats yet.</p>
        )}
        {conversations.slice(0, 20).map((conversation) => {
          const href = `/c/${conversation.id}`;
          const active = pathname === href;
          return (
            <Link
              key={conversation.id}
              href={href}
              className={`chat-item ${active ? "active" : ""}`}
              onClick={onClose}
            >
              {conversation.title}
            </Link>
          );
        })}
      </nav>

      <div className={`sidebar-footer ${backendOk ? "ok" : ""}`}>
        {backendLabel}
      </div>
    </aside>
  );
}
