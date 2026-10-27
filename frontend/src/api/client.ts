// LifeLink Centralized HTTP API Client

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export interface ApiError {
  code?: string;
  message: string;
  status: number;
  details?: any;
  retryAfter?: number;
}

class ApiClient {
  private baseUrl: string;
  private isRefreshing = false;
  private refreshSubscribers: ((token: string) => void)[] = [];

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  private getToken(): string | null {
    return localStorage.getItem('lifelink_token');
  }

  private getRefreshToken(): string | null {
    return localStorage.getItem('lifelink_refresh_token');
  }

  public setTokens(token: string, refreshToken?: string) {
    localStorage.setItem('lifelink_token', token);
    if (refreshToken) {
      localStorage.setItem('lifelink_refresh_token', refreshToken);
    }
  }

  public clearTokens() {
    localStorage.removeItem('lifelink_token');
    localStorage.removeItem('lifelink_refresh_token');
    localStorage.removeItem('lifelink_user');
  }

  private onRefreshed(token: string) {
    this.refreshSubscribers.forEach((cb) => cb(token));
    this.refreshSubscribers = [];
  }

  private async refreshAccessToken(): Promise<string | null> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) return null;

    try {
      const response = await fetch(`${this.baseUrl}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        this.clearTokens();
        return null;
      }

      const data = await response.json();
      const newToken = data.access_token || data.token;
      const newRefresh = data.refresh_token || data.refreshToken;
      this.setTokens(newToken, newRefresh);
      return newToken;
    } catch {
      this.clearTokens();
      return null;
    }
  }

  public async request<T = any>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = path.startsWith('http') ? path : `${this.baseUrl}${path.startsWith('/') ? '' : '/'}${path}`;
    const token = this.getToken();

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    let response: Response;
    try {
      response = await fetch(url, { ...options, headers });
    } catch (err: any) {
      throw {
        message: 'Network connection failed. Ensure the LifeLink backend is online.',
        status: 0,
        details: err.message,
      } as ApiError;
    }

    // Handle 401 Unauthorized by attempting token refresh once
    if (response.status === 401 && this.getRefreshToken() && !path.includes('/auth/login') && !path.includes('/auth/refresh')) {
      if (!this.isRefreshing) {
        this.isRefreshing = true;
        const newToken = await this.refreshAccessToken();
        this.isRefreshing = false;

        if (newToken) {
          this.onRefreshed(newToken);
          headers['Authorization'] = `Bearer ${newToken}`;
          return this.request<T>(path, { ...options, headers });
        }
      } else {
        // Wait for active refresh
        return new Promise((resolve) => {
          this.refreshSubscribers.push((newToken: string) => {
            headers['Authorization'] = `Bearer ${newToken}`;
            resolve(this.request<T>(path, { ...options, headers }));
          });
        });
      }
    }

    if (!response.ok) {
      let errorData: any = {};
      try {
        errorData = await response.json();
      } catch {
        errorData = { message: response.statusText };
      }

      const retryAfterHeader = response.headers.get('Retry-After');
      const retryAfter = retryAfterHeader ? parseInt(retryAfterHeader, 10) : undefined;

      const apiError: ApiError = {
        code: errorData.code || `HTTP_${response.status}`,
        message: errorData.message || errorData.detail || 'An unexpected error occurred',
        status: response.status,
        details: errorData.details || errorData,
        retryAfter,
      };

      throw apiError;
    }

    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  public get<T = any>(path: string, options?: RequestInit): Promise<T> {
    return this.request<T>(path, { ...options, method: 'GET' });
  }

  public post<T = any>(path: string, body?: any, options?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  public patch<T = any>(path: string, body?: any, options?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  public put<T = any>(path: string, body?: any, options?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  public delete<T = any>(path: string, options?: RequestInit): Promise<T> {
    return this.request<T>(path, { ...options, method: 'DELETE' });
  }
}

export const api = new ApiClient(API_BASE_URL);
