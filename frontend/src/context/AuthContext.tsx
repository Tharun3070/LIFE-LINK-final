// LifeLink Authentication Context & Hook
import React, { createContext, useContext, useState, useEffect } from 'react';
import { UserProfile, UserRole } from '../types';
import { authApi } from '../api/services';
import { api } from '../api/client';
import { realtimeWs } from '../api/websocket';

interface AuthContextType {
  user: UserProfile | null;
  token: string | null;
  isLoading: boolean;
  login: (identifier: string, password: string, rememberMe?: boolean) => Promise<void>;
  register: (data: {
    email: string;
    password: string;
    name: string;
    role: string;
    phone?: string;
    organization?: string;
    licenseNumber?: string;
    roleTitle?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  // Role helpers
  isDoctor: boolean;
  isStaff: boolean;
  isDriver: boolean;
  isDonor: boolean;
  isPatient: boolean;
  isAdmin: boolean;
  hasRole: (roles: UserRole[]) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(() => {
    const saved = localStorage.getItem('lifelink_user');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return null;
      }
    }
    return null;
  });

  const [token, setToken] = useState<string | null>(() => localStorage.getItem('lifelink_token'));
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Restore and verify session on initial mount
  useEffect(() => {
    const restoreSession = async () => {
      const savedToken = localStorage.getItem('lifelink_token');
      if (savedToken) {
        try {
          const profile = await authApi.getMe();
          setUser(profile);
          localStorage.setItem('lifelink_user', JSON.stringify(profile));
          realtimeWs.connect();
        } catch {
          // Token expired or invalid
          api.clearTokens();
          setUser(null);
          setToken(null);
        }
      }
      setIsLoading(false);
    };

    restoreSession();
  }, []);

  const login = async (identifier: string, password: string, rememberMe = true) => {
    setIsLoading(true);
    try {
      const res = await authApi.login({ identifier, password, rememberMe });
      api.setTokens(res.token, res.refreshToken);
      setToken(res.token);
      setUser(res.user);
      localStorage.setItem('lifelink_user', JSON.stringify(res.user));
      realtimeWs.connect();
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (data: {
    email: string;
    password: string;
    name: string;
    role: string;
    phone?: string;
    organization?: string;
    licenseNumber?: string;
    roleTitle?: string;
  }) => {
    setIsLoading(true);
    try {
      const res = await authApi.register(data);
      if (res.token) {
        api.setTokens(res.token, res.refreshToken);
        setToken(res.token);
        setUser(res.user);
        localStorage.setItem('lifelink_user', JSON.stringify(res.user));
        realtimeWs.connect();
      }
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } catch {
      // Ignore network errors on logout
    } finally {
      api.clearTokens();
      setUser(null);
      setToken(null);
      realtimeWs.disconnect();
    }
  };

  const refreshProfile = async () => {
    try {
      const profile = await authApi.getMe();
      setUser(profile);
      localStorage.setItem('lifelink_user', JSON.stringify(profile));
    } catch {
      // Ignore
    }
  };

  const role = user?.role;
  const isDoctor = role === 'doctor';
  const isStaff = role === 'hospital_staff';
  const isDriver = role === 'ambulance_driver' || role === 'ambulance_operator';
  const isDonor = role === 'donor';
  const isPatient = role === 'patient';
  const isAdmin = role === 'admin';

  const hasRole = (roles: UserRole[]): boolean => {
    if (!user) return false;
    if (user.role === 'admin') return true;
    return roles.includes(user.role);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        login,
        register,
        logout,
        refreshProfile,
        isDoctor,
        isStaff,
        isDriver,
        isDonor,
        isPatient,
        isAdmin,
        hasRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
