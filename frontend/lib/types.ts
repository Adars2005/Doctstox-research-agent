export type Citation = {
  title: string;
  url?: string;
  source_name?: string;
  published_date?: string | null;
  reliability?: string;
  why?: string;
  excerpt?: string;
};

export type ChatMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  tools: string[];
  citations: Citation[];
  created_at: string;
};

export type UploadedFile = {
  id: string;
  conversation_id: string;
  filename: string;
  mime_type?: string | null;
  size_bytes?: number;
  status: "indexing" | "ready" | "error" | "local_only" | string;
  error?: string | null;
  created_at: string;
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  preview?: string;
  message_count?: number;
  messages?: ChatMessage[];
  files?: UploadedFile[];
};

export type Health = {
  status: string;
  service: string;
  providers?: {
    groq: boolean;
    exa: boolean;
    gemini: boolean;
  };
};
