"use client";

import { useParams } from "next/navigation";
import ChatWorkspace from "@/components/ChatWorkspace";

export default function ConversationPage() {
  const params = useParams<{ id: string }>();
  return <ChatWorkspace conversationId={params.id} />;
}
