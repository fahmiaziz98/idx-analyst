
import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Sparkles, Loader2, ThumbsUp, ThumbsDown } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message } from '../types';

interface ChatWindowProps {
  messages: Message[];
  onSendMessage: (content: string) => void;
  isStreaming: boolean;
  onFeedbackSubmit: (messageId: string, feedback: 'positive' | 'negative', comment?: string) => Promise<void>;
}

const ChatWindow: React.FC<ChatWindowProps> = ({ messages, onSendMessage, isStreaming, onFeedbackSubmit }) => {
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
          {/* Header Actions */}
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
              This chat uses WebSockets for real-time interaction.
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
                {msg.role === 'assistant' ? (
                  <div className="flex flex-col gap-1 max-w-[85%]">
                    <div className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed bg-white text-gray-800`}>
                      <div className="prose prose-sm prose-slate max-w-none prose-headings:font-bold prose-headings:text-gray-900 prose-p:text-gray-800 prose-a:text-blue-600 prose-strong:text-gray-900 prose-code:text-emerald-700 prose-pre:bg-gray-50 prose-pre:border prose-pre:border-gray-200 prose-table:border prose-table:border-collapse prose-th:bg-gray-50 prose-th:px-4 prose-th:py-2 prose-td:border prose-td:px-4 prose-td:py-2">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    </div>
                    {!isStreaming && (
                      <FeedbackComponent
                        messageId={msg.id}
                        existingFeedback={msg.feedback}
                        onSubmit={onFeedbackSubmit}
                      />
                    )}
                  </div>
                ) : (
                  <div className="max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed bg-gray-100 text-gray-900 border border-gray-200">
                    {msg.content}
                  </div>
                )}
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
          Streaming via WebSockets. Responses are generated in real-time.
        </p>
      </div>
    </div>
  );
};


interface FeedbackComponentProps {
  messageId: string;
  existingFeedback?: 'positive' | 'negative' | null;
  onSubmit: (messageId: string, feedback: 'positive' | 'negative', comment?: string) => Promise<void>;
}

const FeedbackComponent: React.FC<FeedbackComponentProps> = ({ messageId, existingFeedback, onSubmit }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedFeedback, setSelectedFeedback] = useState<'positive' | 'negative' | null>(existingFeedback || null);
  const [comment, setComment] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(!!existingFeedback);

  const handleFeedbackClick = (type: 'positive' | 'negative') => {
    if (isSubmitted && selectedFeedback === type) return; // Prevent re-clicking if already submitted same type
    setSelectedFeedback(type);
    setIsExpanded(true);
  };

  const handleSubmit = async () => {
    if (!selectedFeedback) return;
    setIsSubmitting(true);
    try {
      await onSubmit(messageId, selectedFeedback, comment);
      setIsSubmitted(true);
      setIsExpanded(false); // Collapse after submitting
    } catch (error) {
      console.error('Failed to submit feedback', error);
      // Optional: show error toast
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isSubmitted && !isExpanded) {
    return (
      <div className="mt-2 flex items-center gap-2 text-gray-400 text-xs">
        <span className="flex items-center gap-1">
          {selectedFeedback === 'positive' ? (
            <>
              <ThumbsUp size={14} className="text-emerald-500 fill-emerald-500" />
              <span className="text-emerald-600">Helpful</span>
            </>
          ) : (
            <>
              <ThumbsDown size={14} className="text-red-500 fill-red-500" />
              <span className="text-red-600">Not Helpful</span>
            </>
          )}
        </span>
        <button
          onClick={() => setIsExpanded(true)}
          className="hover:underline ml-2"
        >
          Edit
        </button>
      </div>
    )
  }

  return (
    <div className={`mt-2 flex flex-col gap-3 transition-all duration-300 ease-in-out ${isExpanded ? 'bg-gray-50 p-3 rounded-lg border border-gray-200' : ''}`}>
      <div className="flex items-center gap-2">
        <button
          onClick={() => handleFeedbackClick('positive')}
          className={`p-1.5 rounded-full transition-colors flex items-center gap-1 ${selectedFeedback === 'positive'
            ? 'bg-emerald-100 text-emerald-600'
            : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'
            }`}
          title="Helpful"
        >
          <ThumbsUp size={16} className={selectedFeedback === 'positive' ? 'fill-current' : ''} />
          {isExpanded && <span className="text-xs font-medium">Helpful</span>}
        </button>
        <button
          onClick={() => handleFeedbackClick('negative')}
          className={`p-1.5 rounded-full transition-colors flex items-center gap-1 ${selectedFeedback === 'negative'
            ? 'bg-red-100 text-red-600'
            : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'
            }`}
          title="Not Helpful"
        >
          <ThumbsDown size={16} className={selectedFeedback === 'negative' ? 'fill-current' : ''} />
          {isExpanded && <span className="text-xs font-medium">Not Helpful</span>}
        </button>
      </div>

      {isExpanded && (
        <div className="space-y-3 animate-in fade-in slide-in-from-top-2">
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Tell us more (optional)..."
            className="w-full text-sm p-2 border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            rows={2}
          />
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setIsExpanded(false)}
              className="text-xs text-gray-500 hover:text-gray-700 font-medium px-3 py-1.5"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="text-xs bg-gray-900 text-white px-3 py-1.5 rounded-md hover:bg-black disabled:opacity-50 transition-colors flex items-center gap-1"
            >
              {isSubmitting ? <Loader2 size={12} className="animate-spin" /> : null}
              Submit Feedback
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ChatWindow;
