
export const API_BASE_URL = 'http://localhost:7860/api/v1'; // Base URL for FastAPI

export const AUTH_ENDPOINTS = {
  LOGIN: `${API_BASE_URL}/auth/login`,
  LOGOUT: `${API_BASE_URL}/auth/logout`,
  ME: `${API_BASE_URL}/auth/me`,
  REFRESH: `${API_BASE_URL}/auth/refresh`,
};

export const CHAT_ENDPOINTS = {
  STREAM: `${API_BASE_URL}/chat/stream`,
  WEBSOCKET: `ws://localhost:7860/api/v1/ws/chat`,
};

export const STORAGE_KEYS = {
  ACCESS_TOKEN: 'chat_access_token',
  REFRESH_TOKEN: 'chat_refresh_token',
  CONVERSATIONS: 'chat_history',
};
