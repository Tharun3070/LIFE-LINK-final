import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useRealtime } from '../../context/RealtimeContext';
import {
  Activity,
  AlertCircle,
  Droplet,
  Users,
  Building2,
  Ambulance,
  Heart,
  BookOpen,
  ShieldCheck,
  UserCheck,
  ChevronLeft,
  ChevronRight,
  Radio,
  Clock,
} from 'lucide-react';

interface SidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isCollapsed, onToggleCollapse }) => {
  const { user, isDoctor, isStaff, isAdmin } = useAuth();
  const { isConnected } = useRealtime();

  const navItems = [
    { to: '/dashboard', label: 'Command Center', icon: Activity, exact: true },
    { to: '/emergencies', label: 'Emergencies', icon: AlertCircle },
    { to: '/blood-requests', label: 'Blood Coordination', icon: Droplet },
    { to: '/donors', label: 'Blood Donors', icon: Users },
    { to: '/hospitals', label: 'Hospitals & Banks', icon: Building2 },
    { to: '/ambulances', label: 'Ambulance Fleet', icon: Ambulance },
    { to: '/organs', label: 'Organ Viability', icon: Heart },
    { to: '/clinical-guidance', label: 'Clinical Guidance', icon: BookOpen },
    // Restricted to clinical staff / admin
    ...((isDoctor || isStaff || isAdmin)
      ? [
          { to: '/audit-logs', label: 'Audit & Integrity', icon: ShieldCheck },
        ]
      : []),
    { to: '/profile', label: 'Profile & Consent', icon: UserCheck },
  ];

  return (
    <aside
      style={{
        width: isCollapsed ? 'var(--sidebar-collapsed-width)' : 'var(--sidebar-width)',
        backgroundColor: 'var(--color-bg-sidebar)',
        color: 'var(--color-text-sidebar)',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.2s ease-in-out',
        zIndex: 50,
        boxShadow: 'var(--shadow-md)',
        flexShrink: 0,
      }}
    >
      {/* Brand Header */}
      <div
        style={{
          height: 'var(--header-height)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: isCollapsed ? 'center' : 'space-between',
          padding: isCollapsed ? '0' : '0 1.25rem',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'var(--color-emergency-red)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#ffffff',
              boxShadow: '0 0 12px rgba(217, 45, 53, 0.45)',
            }}
          >
            <Activity size={20} />
          </div>
          {!isCollapsed && (
            <div>
              <span
                style={{
                  fontSize: '1.125rem',
                  fontWeight: 700,
                  color: '#ffffff',
                  letterSpacing: '0.02em',
                  display: 'block',
                  lineHeight: 1.1,
                }}
              >
                LifeLink
              </span>
              <span
                style={{
                  fontSize: '0.6875rem',
                  color: 'var(--color-emerald-green)',
                  fontWeight: 600,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                }}
              >
                Emergency Net
              </span>
            </div>
          )}
        </div>

        {!isCollapsed && (
          <button
            onClick={onToggleCollapse}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--color-text-sidebar)',
              padding: '0.25rem',
              cursor: 'pointer',
              borderRadius: 'var(--radius-sm)',
            }}
            title="Collapse sidebar"
          >
            <ChevronLeft size={18} />
          </button>
        )}
      </div>

      {/* Navigation Menu */}
      <nav
        style={{
          flex: 1,
          padding: '1rem 0.5rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.25rem',
          overflowY: 'auto',
        }}
      >
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.exact}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: '0.875rem',
                padding: isCollapsed ? '0.75rem 0' : '0.75rem 1rem',
                justifyContent: isCollapsed ? 'center' : 'flex-start',
                borderRadius: 'var(--radius-md)',
                color: isActive ? '#ffffff' : 'var(--color-text-sidebar)',
                backgroundColor: isActive ? 'var(--color-emerald-green)' : 'transparent',
                fontWeight: isActive ? 600 : 500,
                fontSize: '0.875rem',
                textDecoration: 'none',
                transition: 'background-color 0.15s ease',
              })}
              title={isCollapsed ? item.label : undefined}
            >
              <Icon size={19} />
              {!isCollapsed && <span>{item.label}</span>}
            </NavLink>
          );
        })}
      </nav>

      {/* Live System Status / Collapse Button */}
      <div
        style={{
          padding: isCollapsed ? '1rem 0' : '1rem 1.25rem',
          borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: isCollapsed ? 'center' : 'stretch',
          gap: '0.75rem',
        }}
      >
        {!isCollapsed && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              fontSize: '0.75rem',
              color: isConnected ? 'var(--color-emerald-green)' : 'var(--color-amber-warning)',
              backgroundColor: 'rgba(255, 255, 255, 0.04)',
              padding: '0.4rem 0.6rem',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            <Radio size={14} className={isConnected ? '' : 'pulse-critical'} />
            <span style={{ fontWeight: 500 }}>
              {isConnected ? 'Real-time Connected' : 'Reconnecting...'}
            </span>
          </div>
        )}

        {isCollapsed && (
          <button
            onClick={onToggleCollapse}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--color-text-sidebar)',
              padding: '0.5rem',
              cursor: 'pointer',
            }}
            title="Expand sidebar"
          >
            <ChevronRight size={18} />
          </button>
        )}
      </div>
    </aside>
  );
};
