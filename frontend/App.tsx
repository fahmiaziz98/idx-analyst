
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';
import Sidebar from './components/Sidebar';
import ChatWindow from './components/ChatWindow';
import { User, Conversation, Message, ChatMode } from './types';
import { STORAGE_KEYS, CHAT_ENDPOINTS, AUTH_ENDPOINTS } from './constants';
import { fetchMe } from './services/api';
import { LogIn, Sparkles } from 'lucide-react';

const App: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<User | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [mode, setMode] = useState<ChatMode>('SSE');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [currentPath, setCurrentPath] = useState(window.location.pathname);

  const wsRef = useRef<WebSocket | null>(null);

  // Handle Internal Routing
  useEffect(() => {
    const handleLocationChange = () => setCurrentPath(window.location.pathname);
    window.addEventListener('popstate', handleLocationChange);
    return () => window.removeEventListener('popstate', handleLocationChange);
  }, []);

  const navigate = (path: string) => {
    window.history.pushState({}, '', path);
    setCurrentPath(path);
  };

  // Initialize Auth
  useEffect(() => {
    const init = async () => {
      const currentUser = await fetchMe();
      if (currentUser) {
        setUser(currentUser);
        setIsAuthenticated(true);

        // Load history from local storage
        const saved = localStorage.getItem(STORAGE_KEYS.CONVERSATIONS);
        if (saved) setConversations(JSON.parse(saved));

        // Redirect to /chat if at root
        if (window.location.pathname === '/') {
          navigate('/chat');
        }
      } else {
        // Not authenticated, redirect to / if at /chat
        if (window.location.pathname !== '/') {
          navigate('/');
        }
      }
      setIsLoading(false);
    };
    init();
  }, []);

  // Persist History
  useEffect(() => {
    if (conversations.length > 0) {
      localStorage.setItem(STORAGE_KEYS.CONVERSATIONS, JSON.stringify(conversations));
    }
  }, [conversations]);

  // WebSocket Connection Management
  useEffect(() => {
    if (isAuthenticated && mode === 'WS' && currentPath === '/chat') {
      // WS typically requires a token in URL if cookies can't be passed easily,
      // but if the server supports cookie auth for WS, we don't need a token param.
      // Assuming backend reads cookies for WS as well.
      const wsUrl = CHAT_ENDPOINTS.WEBSOCKET;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'message') {
          updateStreamingMessage(data.content, data.conversation_id);
        } else if (data.content === '[DONE]') {
          setIsStreaming(false);
        }
      };

      return () => ws.close();
    } else {
      wsRef.current?.close();
      wsRef.current = null;
    }
  }, [isAuthenticated, mode, currentPath]);

  const updateStreamingMessage = useCallback((content: string, conversationId: string) => {
    setConversations(prev => {
      const active = prev.find(c => c.id === conversationId);
      if (!active) return prev;

      const lastMsg = active.messages[active.messages.length - 1];
      if (lastMsg && lastMsg.role === 'assistant') {
        const updatedMessages = [...active.messages];
        updatedMessages[updatedMessages.length - 1] = {
          ...lastMsg,
          content: lastMsg.content + content
        };
        return prev.map(c => c.id === conversationId ? { ...c, messages: updatedMessages, updatedAt: Date.now() } : c);
      } else {
        const assistantMsg: Message = {
          id: uuidv4(),
          role: 'assistant',
          content: content,
          timestamp: Date.now()
        };
        return prev.map(c => c.id === conversationId ? { ...c, messages: [...active.messages, assistantMsg], updatedAt: Date.now() } : c);
      }
    });
  }, []);

  const handleSendMessage = async (content: string) => {
    let currentId = activeId;
    let currentConversations = [...conversations];

    if (!currentId) {
      currentId = uuidv4();
      const newConv: Conversation = {
        id: currentId,
        title: content.substring(0, 30) + '...',
        messages: [],
        updatedAt: Date.now()
      };
      currentConversations = [newConv, ...currentConversations];
      setConversations(currentConversations);
      setActiveId(currentId);
    }

    const userMsg: Message = { id: uuidv4(), role: 'user', content, timestamp: Date.now() };
    const updatedConversations = currentConversations.map(c =>
      c.id === currentId ? { ...c, messages: [...c.messages, userMsg], updatedAt: Date.now() } : c
    );
    setConversations(updatedConversations);
    setIsStreaming(true);

    if (mode === 'SSE') {
      try {
        const response = await fetch(CHAT_ENDPOINTS.STREAM, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            messages: content,
            conversation_id: currentId
          })
        });

        if (!response.body) throw new Error('No body');
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        let done = false;
        while (!done) {
          const { value, done: doneReading } = await reader.read();
          done = doneReading;
          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.substring(6));
                try {
                  const data = JSON.parse(line.substring(6));
                  if (data.content) updateStreamingMessage(data.content, currentId);
                  if (data.done) done = true;
                } catch (e) { }
                if (data.done) done = true;
              } catch (e) { }
            }
          }
        }
      } catch (error) {
        console.error('SSE Stream error:', error);
      } finally {
        setIsStreaming(false);
      }
    } else if (mode === 'WS' && wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          message: content,
          conversation_id: currentId
        }));
      } else {
        setIsStreaming(false);
      }
    }
  };

  if (isLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-white">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-gray-100 border-t-gray-900 rounded-full animate-spin" />
          <p className="text-sm font-medium text-gray-400">Verifying session...</p>
        </div>
      </div>
    );
  }

  // LANDING / LOGIN PAGE (/)
  if (!isAuthenticated || currentPath === '/') {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-white p-6">
        <div className="max-w-md w-full text-center">
          <div className="w-16 h-16 bg-black text-white rounded-2xl flex items-center justify-center mx-auto mb-8 shadow-2xl rotate-3">
            <Sparkles size={32} />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-3 tracking-tight">Modern Chatbot</h1>
          <p className="text-gray-500 mb-10 text-sm leading-relaxed">
            Welcome to the minimalist AI interface. <br /> Log in to start your conversation.
          </p>

          <a
            href={`${AUTH_ENDPOINTS.LOGIN}?redirect_url=${encodeURIComponent(window.location.origin + '/chat')}`}
            className="flex items-center justify-center gap-3 w-full py-4 px-6 bg-white border-2 border-gray-100 rounded-2xl font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-200 transition-all active:scale-[0.98] shadow-sm group"
          >
            <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="Google" className="w-5 h-5" />
            Sign in with Google
          </a>

          <div className="mt-12 flex items-center justify-center gap-4 text-gray-300">
            <div className="h-[1px] w-8 bg-gray-100"></div>
            <span className="text-[10px] font-bold uppercase tracking-[0.2em]">Secure Session</span>
            <div className="h-[1px] w-8 bg-gray-100"></div>
          </div>
        </div>
      </div>
    );
  }

  // CHAT INTERFACE (/chat)
  const activeMessages = conversations.find(c => c.id === activeId)?.messages || [];

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={setActiveId}
        onNewChat={() => setActiveId(null)}
        onDelete={(id) => {
          setConversations(prev => prev.filter(c => c.id !== id));
          if (activeId === id) setActiveId(null);
        }}
        user={user}
        mode={mode}
        onModeChange={setMode}
      />
      <ChatWindow
        messages={activeMessages}
        onSendMessage={handleSendMessage}
        isStreaming={isStreaming}
        mode={mode}
      />
    </div>
  );
};

export default App;
