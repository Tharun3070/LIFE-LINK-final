import React from 'react';
import { useRealtime, ToastMessage } from '../../context/RealtimeContext';
import { AlertCircle, AlertTriangle, Droplet, Ambulance, Heart, CheckCircle2, Info, X } from 'lucide-react';

export const ToastContainer: React.FC = () => {
  const { toasts, dismissToast } = useRealtime();

  if (toasts.length === 0) return null;

  const getToastIcon = (type: ToastMessage['type']) => {
    switch (type) {
      case 'emergency':
        return <AlertCircle size={20} color="var(--color-emergency-red)" />;
      case 'blood':
        return <Droplet size={20} color="var(--color-orange-accent)" />;
      case 'ambulance':
        return <Ambulance size={20} color="var(--color-blue-info)" />;
      case 'organ':
        return <Heart size={20} color="var(--color-emergency-red)" />;
      case 'success':
        return <CheckCircle2 size={20} color="var(--color-emerald-green)" />;
      case 'warning':
        return <AlertTriangle size={20} color="var(--color-orange-accent)" />;
      case 'error':
        return <AlertTriangle size={20} color="var(--color-emergency-red)" />;
      default:
        return <Info size={20} color="var(--color-blue-info)" />;
    }
  };

  const getBorderColor = (type: ToastMessage['type']) => {
    switch (type) {
      case 'emergency':
        return 'var(--color-emergency-red)';
      case 'blood':
        return 'var(--color-orange-accent)';
      case 'ambulance':
        return 'var(--color-blue-info)';
      case 'organ':
        return 'var(--color-emergency-red)';
      case 'success':
        return 'var(--color-emerald-green)';
      default:
        return 'var(--color-border)';
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '1.5rem',
        right: '1.5rem',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        maxWidth: '420px',
        width: 'calc(100vw - 3rem)',
      }}
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          style={{
            backgroundColor: '#ffffff',
            border: `1px solid ${getBorderColor(toast.type)}`,
            borderLeft: `5px solid ${getBorderColor(toast.type)}`,
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-xl)',
            padding: '1rem',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '0.75rem',
            animation: 'toastSlideIn 0.25s ease-out',
          }}
        >
          <div style={{ marginTop: '0.1rem' }}>{getToastIcon(toast.type)}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h4
              style={{
                fontSize: '0.875rem',
                fontWeight: 600,
                color: 'var(--color-primary-navy)',
                marginBottom: '0.2rem',
              }}
            >
              {toast.title}
            </h4>
            <p
              style={{
                fontSize: '0.8125rem',
                color: 'var(--color-text-secondary)',
                lineHeight: 1.4,
                wordBreak: 'break-word',
              }}
            >
              {toast.message}
            </p>
          </div>
          <button
            onClick={() => dismissToast(toast.id)}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--color-text-muted)',
              cursor: 'pointer',
              padding: '0.2rem',
            }}
            title="Dismiss"
          >
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  );
};
