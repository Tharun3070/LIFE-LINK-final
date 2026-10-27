import React from 'react';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  variant?: 'navy' | 'emerald' | 'red' | 'orange' | 'blue';
  trend?: {
    value: string;
    isPositive?: boolean;
  };
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  icon,
  variant = 'navy',
  trend,
}) => {
  const getIconBg = () => {
    switch (variant) {
      case 'emerald':
        return { bg: 'var(--color-emerald-green-light)', color: 'var(--color-emerald-green)' };
      case 'red':
        return { bg: 'var(--color-emergency-red-light)', color: 'var(--color-emergency-red)' };
      case 'orange':
        return { bg: 'var(--color-orange-accent-light)', color: 'var(--color-orange-accent)' };
      case 'blue':
        return { bg: 'var(--color-blue-info-light)', color: 'var(--color-blue-info)' };
      default:
        return { bg: 'var(--color-bg-card-subtle)', color: 'var(--color-primary-navy)' };
    }
  };

  const style = getIconBg();

  return (
    <div className="clinical-card" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <span style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {title}
          </span>
          <div style={{ fontSize: '1.875rem', fontWeight: 700, color: 'var(--color-primary-navy)', marginTop: '0.25rem', lineHeight: 1.1 }}>
            {value}
          </div>
        </div>
        <div
          style={{
            padding: '0.625rem',
            borderRadius: 'var(--radius-lg)',
            backgroundColor: style.bg,
            color: style.color,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {icon}
        </div>
      </div>

      {(subtitle || trend) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
          {trend && (
            <span
              style={{
                color: trend.isPositive ? 'var(--color-emerald-green)' : 'var(--color-emergency-red)',
                fontWeight: 600,
              }}
            >
              {trend.value}
            </span>
          )}
          {subtitle && <span>{subtitle}</span>}
        </div>
      )}
    </div>
  );
};

export default MetricCard;
