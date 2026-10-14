/**
 * Authentication and User Service for AI Data Intelligence Cloud
 */

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  slug: string;
  description?: string;
  owner_id: string;
  created_at: string;
  role: string;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  workspaces: WorkspaceSummary[];
}

const TOKEN_KEY = 'aidata_access_token';
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function getAuthHeaders(): Record<string, string> {
  const token = getStoredToken();
  if (token) {
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
  }
  return {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
}

export async function registerUser(email: string, fullName: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, full_name: fullName, password }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Registration failed (HTTP ${res.status})`);
  }
  const data: TokenResponse = await res.json();
  setStoredToken(data.access_token);
  return data;
}

export async function loginUser(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Login failed (HTTP ${res.status})`);
  }
  const data: TokenResponse = await res.json();
  setStoredToken(data.access_token);
  return data;
}

export async function getCurrentUserProfile(): Promise<UserProfile | null> {
  const token = getStoredToken();
  if (!token) return null;

  const res = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    if (res.status === 401) {
      clearStoredToken();
    }
    return null;
  }
  return await res.json();
}
