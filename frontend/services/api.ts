import { AUTH_ENDPOINTS } from '../constants';
import { User } from '../types';

// Helper to get CSRF token from cookies
export function getCSRFToken(): string | null {
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  return match ? match[1] : null;
}

/**
 * Variable to store the promise of an ongoing refresh request.
 * This prevents multiple concurrent 401s from triggering multiple /refresh calls.
 */
let refreshingPromise: Promise<boolean> | null = null;

/**
 * Core API Client that handles:
 * 1. CSRF Protection
 * 2. Credentials (cookies)
 * 3. Automatic Token Refresh on 401
 * 4. Concurrent Refresh Handling
 */
export async function apiClient(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const csrfToken = getCSRFToken();
  const defaultOptions: RequestInit = {
    ...options,
    credentials: 'include',
    headers: {
      ...options.headers,
      'X-CSRF-Token': csrfToken || '',
    },
  };

  try {
    let response = await fetch(url, defaultOptions);

    // If 401 and not already a login/refresh attempt, try to refresh
    if (response.status === 401 && url !== AUTH_ENDPOINTS.REFRESH && url !== AUTH_ENDPOINTS.LOGIN) {
      console.info(`[API] 401 Unauthorized detected for ${url}. Attempting token refresh...`);

      // If a refresh is already in progress, wait for it
      if (!refreshingPromise) {
        refreshingPromise = (async () => {
          try {
            console.info('[API] Calling /refresh endpoint...');
            const refreshRes = await fetch(AUTH_ENDPOINTS.REFRESH, {
              method: 'POST',
              credentials: 'include',
              headers: { 'X-CSRF-Token': csrfToken || '' }
            });

            if (refreshRes.ok) {
              console.info('[API] Token refresh successful!');
              return true;
            } else {
              console.warn('[API] Token refresh failed (refresh token might be expired).');
              return false;
            }
          } catch (error) {
            console.error('[API] Error during refresh call:', error);
            return false;
          } finally {
            refreshingPromise = null;
          }
        })();
      }

      const isRefreshed = await refreshingPromise;

      if (isRefreshed) {
        console.info(`[API] Retrying original request: ${url}`);
        // Retry the original request with the new tokens (automatically handled by browser cookies)
        return await fetch(url, defaultOptions);
      } else {
        // Refresh failed, probably need to re-login
        console.error('[API] Refresh failed. Redirecting to login/home.');
        if (window.location.pathname !== '/') {
          window.location.href = '/';
        }
      }
    }

    return response;
  } catch (error) {
    console.error(`[API] Fetch error for ${url}:`, error);
    throw error;
  }
}

/**
 * Legacy wrapper for CSRF - now calls the robust apiClient
 */
export async function fetchWithCSRF(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  return apiClient(url, options);
}

export async function fetchMe(): Promise<User | null> {
  try {
    const response = await apiClient(AUTH_ENDPOINTS.ME);
    if (!response.ok) {
      if (response.status === 401) return null; // Silent fail if still 401 after refresh
      throw new Error('Unauthorized');
    }
    return await response.json();
  } catch (error) {
    console.error('Fetch user failed:', error);
    return null;
  }
}

export async function logoutApi() {
  try {
    console.info('[API] Logging out...');
    await apiClient(AUTH_ENDPOINTS.LOGOUT, {
      method: 'POST',
    });
  } catch (e) {
    console.error('Logout error', e);
  } finally {
    window.location.href = '/';
  }
}

// Conversation API
import { CHAT_ENDPOINTS } from '../constants';
import { Conversation, Message } from '../types';

export interface ConversationListResponse {
  items: Conversation[];
  total: number;
  skip: number;
  limit: number;
}

export async function getConversations(skip: number = 0, limit: number = 20): Promise<ConversationListResponse> {
  const response = await apiClient(`${CHAT_ENDPOINTS.CONVERSATIONS}?skip=${skip}&limit=${limit}`);
  if (!response.ok) throw new Error('Failed to fetch conversations');
  return response.json();
}

export async function getConversation(id: string): Promise<Conversation> {
  const response = await apiClient(`${CHAT_ENDPOINTS.CONVERSATIONS}/${id}`);
  if (!response.ok) throw new Error('Failed to fetch conversation');
  return response.json();
}

export async function createConversation(title?: string): Promise<Conversation> {
  const response = await apiClient(CHAT_ENDPOINTS.CONVERSATIONS, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) throw new Error('Failed to create conversation');
  return response.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const response = await apiClient(`${CHAT_ENDPOINTS.CONVERSATIONS}/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete conversation');
}

export async function updateConversationTitle(id: string, title: string): Promise<Conversation> {
  const response = await apiClient(`${CHAT_ENDPOINTS.CONVERSATIONS}/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) throw new Error('Failed to update conversation');
  return response.json();
}


export async function addFeedback(
  messageId: string,
  feedback: 'positive' | 'negative',
  comment?: string
): Promise<Message> {
  const response = await apiClient(`${CHAT_ENDPOINTS.MESSAGES}/${messageId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback, comment }),
  });
  if (!response.ok) throw new Error('Failed to submit feedback');
  return response.json();
}
