import React from 'react';

interface StatusBadgeProps {
  status: string;
  type?: 'priority' | 'status' | 'viability';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'md', className = '' }) => {
  const norm = (status || '').toLowerCase().trim();

  let badgeClass = 'badge-neutral';
  let dotColor = '#64748B';

  if (norm === 'critical' || norm === 'expired' || norm === 'failed') {
    badgeClass = 'badge-critical';
    dotColor = 'var(--color-emergency-red)';
  } else if (norm === 'high' || norm === 'warning' || norm === 'coordinating' || norm === 'in_transit') {
    badgeClass = 'badge-high';
    dotColor = 'var(--color-orange-accent)';
  } else if (norm === 'moderate' || norm === 'pending' || norm === 'resource_search') {
    badgeClass = 'badge-moderate';
    dotColor = 'var(--color-amber-warning)';
  } else if (norm === 'low' || norm === 'normal' || norm === 'resolved' || norm === 'delivered' || norm === 'available' || norm === 'eligible' || norm === 'approved' || norm === 'success') {
    badgeClass = 'badge-success';
    dotColor = 'var(--color-emerald-green)';
  } else if (norm === 'created' || norm === 'dispatched' || norm === 'at_scene') {
    badgeClass = 'badge-info';
    dotColor = 'var(--color-blue-info)';
  }

  // Format label text
  const label = norm.replace(/_/g, ' ');

  const sizeStyle = size === 'sm' ? { fontSize: '0.6875rem', padding: '0.125rem 0.5rem' } : {};

  return (
    <span className={`badge ${badgeClass} ${className}`} style={sizeStyle}>
      <span
        style={{
          width: size === 'sm' ? '5px' : '6px',
          height: size === 'sm' ? '5px' : '6px',
          borderRadius: '50%',
          backgroundColor: dotColor,
          display: 'inline-block',
        }}
      />
      {label}
    </span>
  );
};

export default StatusBadge;
