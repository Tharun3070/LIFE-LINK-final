// LifeLink Real-Time Events & Live Notification Context
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { RealtimeEvent } from '../types';
import { realtimeWs } from '../api/websocket';
import { useAuth } from './AuthContext';

export interface ToastMessage {
  id: string;
  type: 'emergency' | 'blood' | 'ambulance' | 'organ' | 'info' | 'success' | 'error' | 'warning';
  title: string;
  message: string;
  timestamp: string;
  emergencyId?: string;
}

interface RealtimeContextType {
  isConnected: boolean;
  toasts: ToastMessage[];
  dismissToast: (id: string) => void;
  showToast: (toast: Omit<ToastMessage, 'id' | 'timestamp'>) => void;
  addToast: (toast: Omit<ToastMessage, 'id' | 'timestamp'>) => void;
  lastEvent: RealtimeEvent | null;
}

const RealtimeContext = createContext<RealtimeContextType | undefined>(undefined);

export const RealtimeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [lastEvent, setLastEvent] = useState<RealtimeEvent | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback((toast: Omit<ToastMessage, 'id' | 'timestamp'>) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`;
    const newToast: ToastMessage = {
      ...toast,
      id,
      timestamp: new Date().toISOString(),
    };

    setToasts((prev) => [newToast, ...prev].slice(0, 5)); // Keep max 5 active toasts

    // Auto-dismiss after 7 seconds for non-emergency toasts, 12 seconds for critical emergencies
    const duration = toast.type === 'emergency' ? 12000 : 7000;
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, duration);
  }, []);

  useEffect(() => {
    if (!user) {
      setIsConnected(false);
      return;
    }

    realtimeWs.connect();
    setIsConnected(realtimeWs.isConnected());

    const unsubscribe = realtimeWs.subscribe((event: RealtimeEvent) => {
      setLastEvent(event);
      setIsConnected(true);

      // Map event types to toast notifications
      if (event.type === 'emergency.created' || event.type === 'emergency_created') {
        showToast({
          type: 'emergency',
          title: `EMERGENCY ALERT: ${event.payload?.priority?.toUpperCase() || 'CRITICAL'}`,
          message: event.payload?.description || `Emergency #${event.payload?.emergencyId || ''} registered.`,
          emergencyId: event.payload?.emergencyId,
        });
      } else if (event.type === 'donor.responded' || event.type === 'donor_responded') {
        showToast({
          type: 'blood',
          title: 'Donor SOS Update',
          message: `Donor #${event.payload?.donorId || ''} ${event.payload?.status?.toUpperCase() || 'responded'} for Emergency #${event.payload?.emergencyId || ''}.`,
          emergencyId: event.payload?.emergencyId,
        });
      } else if (event.type === 'ambulance.location_updated') {
        // High frequency GPS updates: do not spam toasts unless status changed
        if (event.payload?.statusChange) {
          showToast({
            type: 'ambulance',
            title: 'Ambulance Status Changed',
            message: `Ambulance ${event.payload?.unitNumber || ''}: ${event.payload?.status}`,
          });
        }
      }
    });

    const checkInterval = setInterval(() => {
      setIsConnected(realtimeWs.isConnected());
    }, 5000);

    return () => {
      unsubscribe();
      clearInterval(checkInterval);
    };
  }, [user, showToast]);

  return (
    <RealtimeContext.Provider
      value={{
        isConnected,
        toasts,
        dismissToast,
        showToast,
        addToast: showToast,
        lastEvent,
      }}
    >
      {children}
    </RealtimeContext.Provider>
  );
};

export const useRealtime = () => {
  const context = useContext(RealtimeContext);
  if (!context) {
    throw new Error('useRealtime must be used within a RealtimeProvider');
  }
  return context;
};
