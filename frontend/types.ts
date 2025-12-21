
export interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  avatar_url: string | null;
  last_login: string;
  created_at: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
}

export type ChatMode = 'SSE' | 'WS';

export interface StreamChunk {
  content: string;
  done: boolean;
  metadata?: {
    conversation_id?: string;
  };
}
