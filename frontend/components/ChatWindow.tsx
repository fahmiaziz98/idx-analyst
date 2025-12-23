
import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Sparkles, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message, ChatMode } from '../types';

interface ChatWindowProps {
  messages: Message[];
  onSendMessage: (content: string) => void;
  isStreaming: boolean;
  mode: ChatMode;
}

const ChatWindow: React.FC<ChatWindowProps> = ({ messages, onSendMessage, isStreaming, mode }) => {
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;
    onSendMessage(input);
    setInput('');
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-white relative">
      {/* Header */}
      <header className="h-14 border-b border-gray-100 flex items-center px-6 justify-between shrink-0">
        <h2 className="text-sm font-medium text-gray-700">New Conversation</h2>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${mode === 'SSE' ? 'bg-orange-50 text-orange-600 border border-orange-100' : 'bg-blue-50 text-blue-600 border border-blue-100'
            }`}>
            {mode} Mode
          </span>
        </div>
      </header>

      {/* Messages */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto custom-scrollbar flex flex-col"
      >
        {messages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-300 p-8">
            <div className="w-16 h-16 bg-gray-50 rounded-2xl flex items-center justify-center mb-4">
              <Sparkles size={32} />
            </div>
            <h3 className="text-lg font-semibold text-gray-400">How can I help you today?</h3>
            <p className="text-sm text-center mt-2 max-w-xs">
              Select SSE or WebSocket mode in the sidebar to test different streaming methods.
            </p>
          </div>
        ) : (
          <div className="max-w-3xl w-full mx-auto p-4 space-y-8">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 shrink-0 rounded-lg bg-emerald-500 flex items-center justify-center text-white">
                    <Bot size={18} />
                  </div>
                )}
                <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${msg.role === 'user'
                  ? 'bg-gray-100 text-gray-900 border border-gray-200'
                  : 'bg-white text-gray-800'
                  }`}>
                  {msg.role === 'assistant' ? (
                    <div className="prose prose-sm prose-slate max-w-none prose-headings:font-bold prose-headings:text-gray-900 prose-p:text-gray-800 prose-a:text-blue-600 prose-strong:text-gray-900 prose-code:text-emerald-700 prose-pre:bg-gray-50 prose-pre:border prose-pre:border-gray-200 prose-table:border prose-table:border-collapse prose-th:bg-gray-50 prose-th:px-4 prose-th:py-2 prose-td:border prose-td:px-4 prose-td:py-2">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    msg.content
                  )}
                </div>
                {msg.role === 'user' && (
                  <div className="w-8 h-8 shrink-0 rounded-lg bg-gray-900 flex items-center justify-center text-white">
                    <User size={18} />
                  </div>
                )}
              </div>
            ))}
            {isStreaming && (
              <div className="flex gap-4 justify-start animate-pulse">
                <div className="w-8 h-8 shrink-0 rounded-lg bg-emerald-500 flex items-center justify-center text-white opacity-50">
                  <Bot size={18} />
                </div>
                <div className="max-w-[85%] bg-gray-50 rounded-2xl px-4 py-2.5 text-sm text-gray-400 flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin" />
                  Thinking...
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-4 bg-white border-t border-gray-100">
        <form
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto relative group"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Message Chatbot..."
            className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-3.5 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-gray-200 focus:bg-white transition-all"
            disabled={isStreaming}
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className={`absolute right-2 top-2 p-2 rounded-lg transition-all ${!input.trim() || isStreaming
              ? 'text-gray-300'
              : 'text-white bg-gray-900 hover:bg-black shadow-sm'
              }`}
          >
            <Send size={18} />
          </button>
        </form>
        <p className="text-[10px] text-center text-gray-400 mt-2">
          Streaming via {mode}. Responses are generated in real-time.
        </p>
      </div>
    </div>
  );
};

export default ChatWindow;
