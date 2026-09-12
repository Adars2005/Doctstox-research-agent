import type { Conversation, Health, UploadedFile } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let detail = "Request failed.";
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }
  return response.json();
}

export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}

export function listConversations(): Promise<Conversation[]> {
  return request<Conversation[]>("/api/conversations");
}

export function createConversation(title?: string): Promise<Conversation> {
  return request<Conversation>("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title || "New research" }),
  });
}

export function getConversation(id: string): Promise<Conversation> {
  return request<Conversation>(`/api/conversations/${id}`);
}

export function deleteConversation(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/conversations/${id}`, {
    method: "DELETE",
  });
}

export function sendMessage(conversationId: string, content: string) {
  return request<{ user: unknown; assistant: unknown }>(
    `/api/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    },
  );
}

export async function uploadFile(
  conversationId: string,
  file: File,
): Promise<UploadedFile> {
  const body = new FormData();
  body.append("file", file);
  return request<UploadedFile>(`/api/conversations/${conversationId}/files`, {
    method: "POST",
    body,
  });
}

export async function transcribeAudio(file: Blob): Promise<string> {
  const body = new FormData();
  body.append("file", file, "speech.webm");
  const payload = await request<{ text: string }>("/api/voice/transcribe", {
    method: "POST",
    body,
  });
  return payload.text;
}

export async function speakText(text: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/voice/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    throw new Error("Voice playback failed.");
  }
  return response.blob();
}
