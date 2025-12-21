
import React from 'react';
import { Plus, MessageSquare, Trash2, LogOut, Settings, User as UserIcon, Zap, Globe } from 'lucide-react';
import { Conversation, User, ChatMode } from '../types';
import { logoutApi } from '../services/api';

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete: (id: string) => void;
  user: User | null;
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
}

const Sidebar: React.FC<SidebarProps> = ({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onDelete,
  user,
  mode,
  onModeChange
}) => {
  return (
    <div className="w-64 bg-gray-50 h-full border-r border-gray-200 flex flex-col">
      {/* New Chat Button */}
      <div className="p-4">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-3 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors shadow-sm"
        >
          <Plus size={16} />
          New chat
        </button>
      </div>

      {/* Mode Switcher */}
      <div className="px-4 mb-2">
        <div className="bg-gray-200 p-1 rounded-lg flex gap-1">
          <button
            onClick={() => onModeChange('SSE')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 text-xs font-medium rounded-md transition-all ${
              mode === 'SSE' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Zap size={12} />
            SSE
          </button>
          <button
            onClick={() => onModeChange('WS')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 text-xs font-medium rounded-md transition-all ${
              mode === 'WS' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Globe size={12} />
            WS
          </button>
        </div>
      </div>

      {/* Chat History */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-2 space-y-1">
        {conversations.length === 0 ? (
          <div className="px-3 py-10 text-center text-xs text-gray-400">
            No history yet
          </div>
        ) : (
          conversations.sort((a, b) => b.updatedAt - a.updatedAt).map((chat) => (
            <div
              key={chat.id}
              className={`group flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors ${
                activeId === chat.id ? 'bg-gray-200 text-gray-900' : 'text-gray-600 hover:bg-gray-100'
              }`}
              onClick={() => onSelect(chat.id)}
            >
              <MessageSquare size={14} className="shrink-0" />
              <span className="truncate flex-1">{chat.title || 'Untitled Chat'}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(chat.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-500 transition-all"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* User Profile */}
      <div className="mt-auto border-t border-gray-200 p-4 space-y-2">
        {user ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-gray-200 overflow-hidden flex items-center justify-center border border-gray-300">
                {user.avatar_url ? (
                  <img src={user.avatar_url} alt={user.name} className="w-full h-full object-cover" />
                ) : (
                  <UserIcon size={16} className="text-gray-500" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{user.name}</p>
                <p className="text-xs text-gray-500 truncate">{user.email}</p>
              </div>
            </div>
            <button
              onClick={logoutApi}
              className="flex items-center gap-2 w-full text-left text-sm text-gray-600 hover:text-red-600 transition-colors py-1 px-1"
            >
              <LogOut size={14} />
              Log out
            </button>
          </div>
        ) : (
          <div className="animate-pulse flex items-center gap-3">
            <div className="w-8 h-8 bg-gray-200 rounded-full" />
            <div className="flex-1 space-y-2">
              <div className="h-3 bg-gray-200 rounded w-2/3" />
              <div className="h-2 bg-gray-200 rounded w-1/2" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Sidebar;
