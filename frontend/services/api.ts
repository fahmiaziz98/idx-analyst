import { AUTH_ENDPOINTS } from '../constants';
import { User } from '../types';


export function getCSRFToken(): string | null {
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  return match ? match[1] : null;
}

/**
 * Fetch with CSRF protection
 * Use this for POST, PUT, DELETE, PATCH requests
 */
export async function fetchWithCSRF(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const csrfToken = getCSRFToken();

  return fetch(url, {
    ...options,
    credentials: 'include',
    headers: {
      ...options.headers,
      'X-CSRF-Token': csrfToken || '',
    },
  });
}

export async function fetchMe(): Promise<User | null> {

  try {
    const response = await fetch(AUTH_ENDPOINTS.ME, {
      credentials: 'include',
    });
    if (!response.ok) throw new Error('Unauthorized');
    return await response.json();
  } catch (error) {
    console.error('Fetch user failed:', error);
    return null;
  }
}

export async function logoutApi() {
  try {
    await fetchWithCSRF(AUTH_ENDPOINTS.LOGOUT, {
      method: 'POST',
    });
  } catch (e) {
    console.error('Logout error', e);
  } finally {
    window.location.href = '/';
  }
}
