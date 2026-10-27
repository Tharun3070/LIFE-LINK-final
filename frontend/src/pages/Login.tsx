import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Activity, ShieldCheck, Eye, EyeOff, AlertCircle, UserCheck } from 'lucide-react';

export const Login: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [identifier, setIdentifier] = useState('doctor@lifelink.demo');
  const [password, setPassword] = useState('doctor123');
  const [rememberMe, setRememberMe] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const demoAccounts = [
    { label: 'Doctor', id: 'doctor@lifelink.demo', pass: 'doctor123', color: 'var(--color-emerald-green)' },
    { label: 'Hospital Staff', id: 'staff@lifelink.demo', pass: 'staff123', color: 'var(--color-blue-info)' },
    { label: 'Ambulance', id: 'driver@lifelink.demo', pass: 'driver123', color: 'var(--color-orange-accent)' },
    { label: 'Donor', id: 'donor@lifelink.demo', pass: 'donor123', color: 'var(--color-emergency-red)' },
    { label: 'Patient', id: 'patient@lifelink.demo', pass: 'patient123', color: 'var(--color-amber-warning)' },
    { label: 'Admin', id: 'admin@lifelink.demo', pass: 'admin123', color: 'var(--color-primary-navy)' },
  ];

  const handleSelectDemo = (id: string, pass: string) => {
    setIdentifier(id);
    setPassword(pass);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier.trim() || !password) {
      setError('Please provide your identifier and password.');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      await login(identifier.trim(), password, rememberMe);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Login failed. Please verify credentials.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#0E1F29',
        backgroundImage: 'radial-gradient(circle at 50% 20%, #1A3644 0%, #0E1F29 100%)',
        padding: '1.5rem',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '460px',
          backgroundColor: '#ffffff',
          borderRadius: 'var(--radius-xl)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.45)',
          overflow: 'hidden',
          border: '1px solid rgba(255, 255, 255, 0.1)',
        }}
      >
        {/* Brand Banner Header */}
        <div
          style={{
            backgroundColor: 'var(--color-primary-navy)',
            padding: '2.5rem 2rem 2rem',
            textAlign: 'center',
            color: '#ffffff',
            borderBottom: '3px solid var(--color-emerald-green)',
          }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: 'var(--radius-lg)',
              backgroundColor: 'var(--color-emergency-red)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 20px rgba(217, 45, 53, 0.6)',
              marginBottom: '1rem',
            }}
          >
            <Activity size={32} color="#ffffff" />
          </div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, color: '#ffffff', letterSpacing: '-0.02em' }}>
            LifeLink
          </h1>
          <p style={{ fontSize: '0.875rem', color: '#94A3B8', marginTop: '0.35rem' }}>
            AI-Powered Healthcare Emergency Intelligence & Response
          </p>
        </div>

        {/* Form Body */}
        <div style={{ padding: '2rem' }}>
          {error && (
            <div
              style={{
                padding: '0.75rem 1rem',
                backgroundColor: 'var(--color-emergency-red-light)',
                color: 'var(--color-emergency-red)',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.875rem',
                marginBottom: '1.25rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              <AlertCircle size={18} />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Email or Username</label>
              <input
                type="text"
                className="form-input"
                placeholder="name@hospital.org"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                required
                autoComplete="username"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  className="form-input"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  style={{ paddingRight: '2.5rem' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  style={{
                    position: 'absolute',
                    right: '0.75rem',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--color-text-muted)',
                    cursor: 'pointer',
                  }}
                  title={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', fontSize: '0.8125rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', color: 'var(--color-text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                />
                <span>Remember me on this workstation</span>
              </label>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', padding: '0.75rem', fontSize: '1rem', fontWeight: 600 }}
              disabled={isLoading}
            >
              {isLoading ? 'Authenticating...' : 'Sign In to Clinical Portal'}
            </button>
          </form>

          {/* Quick Demo Role Selector */}
          <div style={{ marginTop: '2rem', paddingTop: '1.5rem', borderTop: '1px solid var(--color-border)' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: '0.75rem', textAlign: 'center' }}>
              Demo Evaluation Accounts (1-Click Fill)
            </span>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem' }}>
              {demoAccounts.map((acc) => (
                <button
                  key={acc.label}
                  type="button"
                  onClick={() => handleSelectDemo(acc.id, acc.pass)}
                  style={{
                    padding: '0.45rem',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--color-border)',
                    backgroundColor: identifier === acc.id ? acc.color : 'var(--color-bg-card-subtle)',
                    color: identifier === acc.id ? '#ffffff' : 'var(--color-primary-navy)',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {acc.label}
                </button>
              ))}
            </div>
          </div>

          <div style={{ marginTop: '1.5rem', textAlign: 'center', fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
            Need an account?{' '}
            <Link to="/register" style={{ fontWeight: 600 }}>
              Register for LifeLink
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
