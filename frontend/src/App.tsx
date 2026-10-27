import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { RealtimeProvider } from './context/RealtimeContext';
import { AppLayout } from './components/layout/AppLayout';

// Pages
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Emergencies from './pages/Emergencies';
import BloodRequests from './pages/BloodRequests';
import Donors from './pages/Donors';
import Hospitals from './pages/Hospitals';
import Ambulances from './pages/Ambulances';
import OrganCoordination from './pages/OrganCoordination';
import ClinicalGuidance from './pages/ClinicalGuidance';
import AuditLogs from './pages/AuditLogs';
import Profile from './pages/Profile';

// Protected Route Guard
const ProtectedRoute: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const { user, token, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#0f172a',
        color: '#f8fafc',
      }}>
        <div style={{
          width: '48px',
          height: '48px',
          border: '3px solid rgba(22, 132, 81, 0.2)',
          borderTopColor: '#168451',
          borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
          marginBottom: '1rem',
        }} />
        <h2 style={{ fontSize: '1rem', fontWeight: 600, letterSpacing: '0.02em' }}>
          LifeLink Intelligence Platform
        </h2>
        <p style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '0.25rem' }}>
          Verifying cryptographic authentication token & active session...
        </p>
      </div>
    );
  }

  if (!user && !token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
};

// Public Route Guard (Redirects to dashboard if already authenticated)
const PublicRoute: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const { user, token, isLoading } = useAuth();

  if (isLoading) {
    return null;
  }

  if (user && token) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <RealtimeProvider>
          <Routes>
            {/* Public Authentication Pages */}
            <Route
              path="/login"
              element={
                <PublicRoute>
                  <Login />
                </PublicRoute>
              }
            />
            <Route
              path="/register"
              element={
                <PublicRoute>
                  <Register />
                </PublicRoute>
              }
            />

            {/* Authenticated Clinical Command Center */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <AppLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="emergencies" element={<Emergencies />} />
              <Route path="blood-requests" element={<BloodRequests />} />
              <Route path="donors" element={<Donors />} />
              <Route path="hospitals" element={<Hospitals />} />
              <Route path="ambulances" element={<Ambulances />} />
              <Route path="organs" element={<OrganCoordination />} />
              <Route path="clinical-guidance" element={<ClinicalGuidance />} />
              <Route path="audit-logs" element={<AuditLogs />} />
              <Route path="audit" element={<AuditLogs />} />
              <Route path="profile" element={<Profile />} />
            </Route>

            {/* Fallback Catch-All */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </RealtimeProvider>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
