export type CopilotMode = "normal" | "temporary";
export type CopilotPolicy = {
  temporary_default: boolean;
  memory_turn_limit: number;
};
export type CopilotConversation = {
  id: string;
  finding_id: string | null;
  audit_id: string | null;
  scope: "organization" | "finding" | "audit";
  mode: CopilotMode;
  status: "active" | "pending" | "rejected";
  created_at: string;
  expires_at: string | null;
};
export type CopilotTurn = {
  id: string;
  conversation_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  question: string;
  answer: string | null;
  limitation: string | null;
  citations: { evidence_id: string; finding_id: string; audit_id: string }[];
  created_at: string;
};
export type CopilotDetail = {
  conversation: CopilotConversation;
  turns: CopilotTurn[];
  next_cursor: string | null;
};
export type CopilotApproval = CopilotConversation & { author_id: string };
