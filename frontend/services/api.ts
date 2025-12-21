
import { STORAGE_KEYS, AUTH_ENDPOINTS } from '../constants';
import { User } from '../types';

export const getAccessToken = () => localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
export const setTokens = (access: string, refresh: string) => {
  localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access);
  localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refresh);
};
export const clearTokens = () => {
  localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
  localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
};

export async function fetchMe(): Promise<User | null> {
  const token = getAccessToken();
  // if (!token) return null; // Allow fetching with cookies

  try {
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(AUTH_ENDPOINTS.ME, {
      headers,
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
  const token = getAccessToken();
  try {
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    await fetch(AUTH_ENDPOINTS.LOGOUT, {
      method: 'POST',
      headers,
      credentials: 'include',
    });
  } catch (e) {
    console.error('Logout error', e);
  } finally {
    clearTokens();
    window.location.href = '/';
  }
}
