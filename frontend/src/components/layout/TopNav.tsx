import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { LogOut, Bell, Plus, Shield, User } from 'lucide-react';

interface TopNavProps {
  onOpenNewEmergency: () => void;
}

export const TopNav: React.FC<TopNavProps> = ({ onOpenNewEmergency }) => {
  const { user, logout, isPatient, isDoctor, isStaff } = useAuth();

  const getRoleBadgeStyle = (role?: string) => {
    switch (role) {
      case 'doctor':
        return { bg: 'var(--color-emerald-green-light)', color: 'var(--color-emerald-green)', label: 'Doctor' };
      case 'hospital_staff':
        return { bg: 'var(--color-blue-info-light)', color: 'var(--color-blue-info)', label: 'Hospital Staff' };
      case 'ambulance_driver':
      case 'ambulance_operator':
        return { bg: 'var(--color-orange-accent-light)', color: 'var(--color-orange-accent)', label: 'Ambulance' };
      case 'donor':
        return { bg: 'var(--color-emergency-red-light)', color: 'var(--color-emergency-red)', label: 'Donor' };
      case 'patient':
        return { bg: 'var(--color-amber-warning-light)', color: 'var(--color-amber-warning)', label: 'Patient' };
      case 'admin':
        return { bg: 'var(--color-primary-navy)', color: '#ffffff', label: 'Admin' };
      default:
        return { bg: 'var(--color-bg-card-subtle)', color: 'var(--color-text-secondary)', label: role || 'User' };
    }
  };

  const roleStyle = getRoleBadgeStyle(user?.role);

  return (
    <header
      style={{
        height: 'var(--header-height)',
        backgroundColor: '#ffffff',
        borderBottom: '1px solid var(--color-border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 2rem',
        boxShadow: 'var(--shadow-xs)',
        position: 'sticky',
        top: 0,
        zIndex: 40,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--color-primary-navy)' }}>
          Clinical Command & Coordination
        </h2>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
        {/* Fast Emergency Trigger Button (Doctor, Hospital Staff, Patient, Admin) */}
        {(isDoctor || isStaff || isPatient || user?.role === 'admin') && (
          <button
            onClick={onOpenNewEmergency}
            className="btn btn-danger btn-sm"
            style={{ fontWeight: 600 }}
          >
            <Plus size={16} />
            <span>Create Emergency SOS</span>
          </button>
        )}

        {/* User Identity Pill */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '0.35rem 0.75rem',
            borderRadius: 'var(--radius-full)',
            backgroundColor: 'var(--color-bg-card-subtle)',
            border: '1px solid var(--color-border)',
          }}
        >
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: '50%',
              backgroundColor: 'var(--color-primary-navy)',
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '0.75rem',
              fontWeight: 600,
            }}
          >
            {user?.name ? user.name.charAt(0).toUpperCase() : <User size={14} />}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
            <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--color-primary-navy)' }}>
              {user?.name || 'User'}
            </span>
            <span style={{ fontSize: '0.6875rem', color: 'var(--color-text-muted)' }}>
              {user?.hospitalName || user?.roleTitle || user?.role}
            </span>
          </div>

          <span
            style={{
              fontSize: '0.6875rem',
              fontWeight: 700,
              padding: '0.15rem 0.5rem',
              borderRadius: 'var(--radius-full)',
              backgroundColor: roleStyle.bg,
              color: roleStyle.color,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            {roleStyle.label}
          </span>
        </div>

        {/* Logout Action */}
        <button
          onClick={logout}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-secondary)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
            padding: '0.4rem 0.6rem',
            cursor: 'pointer',
            borderRadius: 'var(--radius-md)',
            fontSize: '0.8125rem',
            fontWeight: 500,
          }}
          title="Sign out"
        >
          <LogOut size={16} />
          <span>Logout</span>
        </button>
      </div>
    </header>
  );
};
