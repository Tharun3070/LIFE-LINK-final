import React, { useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopNav } from './TopNav';
import { ToastContainer } from '../common/ToastContainer';
import { CreateEmergencyModal } from '../emergencies/CreateEmergencyModal';

export const AppLayout: React.FC = () => {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isEmergencyModalOpen, setIsEmergencyModalOpen] = useState(false);
  const navigate = useNavigate();

  const handleEmergencySuccess = (emergencyId: string) => {
    navigate(`/emergencies?highlight=${emergencyId}`);
  };

  return (
    <div className="app-container">
      <Sidebar
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed((prev) => !prev)}
      />

      <div className="main-content">
        <TopNav onOpenNewEmergency={() => setIsEmergencyModalOpen(true)} />

        <main style={{ flex: 1, backgroundColor: 'var(--color-bg-main)', overflowY: 'auto' }}>
          <Outlet />
        </main>

        <ToastContainer />

        <CreateEmergencyModal
          isOpen={isEmergencyModalOpen}
          onClose={() => setIsEmergencyModalOpen(false)}
          onSuccess={handleEmergencySuccess}
        />
      </div>
    </div>
  );
};
