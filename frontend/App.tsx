
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';
import Sidebar from './components/Sidebar';
import ChatWindow from './components/ChatWindow';
import { User, Conversation, Message } from './types';
import { CHAT_ENDPOINTS, AUTH_ENDPOINTS } from './constants';
import {
  fetchMe,
  getConversations,
  getConversation,
  createConversation,
  deleteConversation,
  addFeedback
} from './services/api';
import { Sparkles } from 'lucide-react';

const App: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<User | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
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

  // Load Conversations on Auth
  useEffect(() => {
    if (isAuthenticated) {
      loadConversations();
    }
  }, [isAuthenticated]);

  const loadConversations = async () => {
    try {
      const data = await getConversations();
      setConversations(data.items);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  // Handle URL Routing /chat/:id
  useEffect(() => {
    if (!isAuthenticated) return;

    const match = currentPath.match(/\/chat\/([a-zA-Z0-9-]+)/);
    if (match) {
      const id = match[1];
      if (id !== activeId) {
        setActiveId(id);
        loadConversationDetails(id);
      }
    } else if (currentPath === '/chat') {
      setActiveId(null);
    }
  }, [currentPath, isAuthenticated]);

  const loadConversationDetails = async (id: string) => {
    try {
      const conv = await getConversation(id);
      setConversations(prev => {
        const index = prev.findIndex(c => c.id === id);
        if (index >= 0) {
          const newConvs = [...prev];
          newConvs[index] = conv;
          return newConvs;
        }
        return [conv, ...prev];
      });
    } catch (error) {
      console.error('Failed to load conversation details:', error);
      // If failed (e.g. 404), navigate back to main chat
      navigate('/chat');
    }
  };

  // WebSocket Connection Management
  useEffect(() => {
    // Only connect if we are authenticated and have an active conversation
    if (isAuthenticated && activeId) {
      const wsUrl = CHAT_ENDPOINTS.WEBSOCKET;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WS Connected');
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'message') {
          updateStreamingMessage(data.content, data.conversation_id);
        } else if (data.content === '[DONE]') {
          setIsStreaming(false);
        } else if (data.type === 'error') {
          console.error("WS Backend Error:", data.content);
          setIsStreaming(false);
          // Optional: You could also add a system message to the chat here
          alert(`Error: ${data.content}`);
        }
      };

      ws.onerror = (error) => {
        console.error("WS Error", error);
        setIsStreaming(false);
      }

      return () => ws.close();
    } else {
      wsRef.current?.close();
      wsRef.current = null;
    }
  }, [isAuthenticated, activeId]);

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

    // Create new conversation if needed
    if (!currentId) {
      try {
        const newConv = await createConversation(content.substring(0, 30));
        currentId = newConv.id;

        // Optimistically add to list
        const convWithMsg: Conversation = {
          ...newConv,
          messages: []
        };

        setConversations(prev => [convWithMsg, ...prev]);
        navigate(`/chat/${currentId}`);
        // Wait for state update/routing effects to trigger WS connection
        // The activeId effect will run and initialize wsRef.current
      } catch (error) {
        console.error('Failed to create conversation', error);
        return;
      }
    }

    // Optimistically add user message
    const userMsg: Message = {
      id: uuidv4(),
      role: 'user',
      content,
      timestamp: Date.now()
    };

    setConversations(prev =>
      prev.map(c =>
        c.id === currentId ? { ...c, messages: [...c.messages, userMsg], updatedAt: Date.now() } : c
      )
    );

    setIsStreaming(true);

    // Wait for WS to be ready
    const waitForWs = async () => {
      let attempts = 0;
      while (attempts < 50) { // 5 seconds max wait
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            message: content,
            conversation_id: currentId
          }));
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 100));
        attempts++;
      }
      console.error("WS failed to connect in time");
      setIsStreaming(false);
    };

    waitForWs();
  };

  const handleDeleteConversation = async (id: string) => {
    if (confirm('Are you sure you want to delete this conversation?')) {
      try {
        await deleteConversation(id);
        setConversations(prev => prev.filter(c => c.id !== id));
        if (activeId === id) {
          navigate('/chat');
        }
      } catch (error) {
        console.error('Failed to delete conversation', error);
      }
    }
  };

  const handleSelectConversation = (id: string) => {
    navigate(`/chat/${id}`);
  };

  const handleNewChat = () => {
    navigate('/chat');
  };

  const handleFeedbackSubmit = async (messageId: string, feedback: 'positive' | 'negative', comment?: string) => {
    try {
      await addFeedback(messageId, feedback, comment);
      // Update local state to reflect feedback
      setConversations(prev => {
        return prev.map(conv => {
          if (conv.id === activeId) {
            return {
              ...conv,
              messages: conv.messages.map(msg => {
                if (msg.id === messageId) {
                  return { ...msg, feedback, feedback_comment: comment };
                }
                return msg;
              })
            };
          }
          return conv;
        });
      });
    } catch (error) {
      console.error('Failed to submit feedback', error);
      throw error; // Propagate to component
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
        onSelect={handleSelectConversation}
        onNewChat={handleNewChat}
        onDelete={handleDeleteConversation}
        user={user}
      />
      <ChatWindow
        messages={activeMessages}
        onSendMessage={handleSendMessage}
        isStreaming={isStreaming}
        onFeedbackSubmit={handleFeedbackSubmit}
      />
    </div>
  );
};

export default App;
