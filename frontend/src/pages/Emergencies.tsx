import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { emergencyApi } from '../api/services';
import { Emergency, EmergencyEvent } from '../types';
import { useAuth } from '../context/AuthContext';
import { useRealtime } from '../context/RealtimeContext';
import { StatusBadge } from '../components/common/StatusBadge';
import { EmptyState } from '../components/common/EmptyState';
import { Modal } from '../components/common/Modal';
import { CreateEmergencyModal } from '../components/emergencies/CreateEmergencyModal';
import {
  AlertCircle,
  Search,
  Filter,
  CheckCircle2,
  XCircle,
  Clock,
  MapPin,
  Calendar,
  Building2,
  Plus,
} from 'lucide-react';

export const Emergencies: React.FC = () => {
  const { isDoctor, isStaff, isAdmin } = useAuth();
  const { showToast } = useRealtime();
  const [searchParams] = useSearchParams();

  const [emergencies, setEmergencies] = useState<Emergency[]>([]);
  const [selectedEmergency, setSelectedEmergency] = useState<Emergency | null>(null);
  const [timeline, setTimeline] = useState<EmergencyEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Filters
  const [typeFilter, setTypeFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals
  const [resolveModalOpen, setResolveModalOpen] = useState(false);
  const [cancelModalOpen, setCancelModalOpen] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [notes, setNotes] = useState('');
  const [isActionLoading, setIsActionLoading] = useState(false);

  const fetchEmergencies = async () => {
    setIsLoading(true);
    try {
      const data = await emergencyApi.getEmergencies();
      setEmergencies(data);

      const targetId = searchParams.get('id') || searchParams.get('highlight');
      if (targetId) {
        const found = data.find((e) => e.id === targetId);
        if (found) {
          handleSelectEmergency(found);
        }
      }
    } catch (err: any) {
      showToast({ type: 'error', title: 'Error Loading Emergencies', message: err.message });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchEmergencies();
  }, []);

  const handleSelectEmergency = async (e: Emergency) => {
    setSelectedEmergency(e);
    try {
      const events = await emergencyApi.getActivityTimeline(e.id);
      setTimeline(events);
    } catch {
      setTimeline([]);
    }
  };

  const handleResolve = async () => {
    if (!selectedEmergency) return;
    setIsActionLoading(true);
    try {
      const updated = await emergencyApi.resolveEmergency(selectedEmergency.id, notes);
      setEmergencies((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      setSelectedEmergency(updated);
      setResolveModalOpen(false);
      setNotes('');
      showToast({ type: 'success', title: 'Emergency Resolved', message: `Emergency #${updated.id} marked as resolved.` });
    } catch (err: any) {
      showToast({ type: 'error', title: 'Action Failed', message: err.message });
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!selectedEmergency) return;
    setIsActionLoading(true);
    try {
      const updated = await emergencyApi.cancelEmergency(selectedEmergency.id, notes);
      setEmergencies((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      setSelectedEmergency(updated);
      setCancelModalOpen(false);
      setNotes('');
      showToast({ type: 'info', title: 'Emergency Cancelled', message: `Emergency #${updated.id} was cancelled.` });
    } catch (err: any) {
      showToast({ type: 'error', title: 'Action Failed', message: err.message });
    } finally {
      setIsActionLoading(false);
    }
  };

  const filteredEmergencies = emergencies.filter((e) => {
    if (typeFilter !== 'all' && e.type !== typeFilter) return false;
    if (priorityFilter !== 'all' && e.priority !== priorityFilter) return false;
    if (statusFilter !== 'all' && e.status !== statusFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        e.id.toLowerCase().includes(q) ||
        (e.description && e.description.toLowerCase().includes(q)) ||
        (e.hospitalName && e.hospitalName.toLowerCase().includes(q))
      );
    }
    return true;
  });

  return (
    <div className="page-container">
      {/* Title & Filter Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--color-primary-navy)' }}>
            Emergency Coordination Center
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
            Real-time emergency triage, donor mobilization, and live dispatch cases.
          </p>
        </div>
        {(isDoctor || isStaff || isAdmin) && (
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="btn btn-danger"
            style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <Plus size={18} />
            <span>Broadcast Emergency SOS</span>
          </button>
        )}
      </div>

      {/* Filter Controls Bar */}
      <div
        className="clinical-card"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '1rem',
          alignItems: 'center',
          marginBottom: '1.5rem',
          padding: '1rem',
        }}
      >
        <div style={{ flex: '1 1 240px', position: 'relative' }}>
          <Search size={16} color="var(--color-text-muted)" style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)' }} />
          <input
            type="text"
            className="form-input"
            placeholder="Search by ID, hospital, or case notes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ paddingLeft: '2.25rem' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <select className="form-select" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} style={{ width: 'auto' }}>
            <option value="all">All Types</option>
            <option value="blood">Blood SOS</option>
            <option value="organ">Organ Alert</option>
            <option value="ambulance">Ambulance</option>
          </select>

          <select className="form-select" value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)} style={{ width: 'auto' }}>
            <option value="all">All Priorities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="moderate">Moderate</option>
          </select>

          <select className="form-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ width: 'auto' }}>
            <option value="all">All Statuses</option>
            <option value="created">Created</option>
            <option value="resource_search">Searching</option>
            <option value="coordinating">Coordinating</option>
            <option value="resolved">Resolved</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </div>

      {/* Main Split Layout: List & Selected Detail Drawer */}
      <div style={{ display: 'grid', gridTemplateColumns: selectedEmergency ? '1.4fr 1fr' : '1fr', gap: '1.5rem' }}>
        {/* Emergencies Table */}
        <div className="clinical-card" style={{ padding: 0, overflow: 'hidden' }}>
          {filteredEmergencies.length > 0 ? (
            <div className="clinical-table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table className="clinical-table">
                <thead>
                  <tr>
                    <th>Emergency ID</th>
                    <th>Type</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Hospital</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEmergencies.map((e) => {
                    const isSelected = selectedEmergency?.id === e.id;
                    return (
                      <tr
                        key={e.id}
                        onClick={() => handleSelectEmergency(e)}
                        style={{
                          cursor: 'pointer',
                          backgroundColor: isSelected ? 'var(--color-bg-card-subtle)' : undefined,
                        }}
                      >
                        <td style={{ fontWeight: 600, color: 'var(--color-primary-navy)' }}>
                          #{e.id}
                        </td>
                        <td style={{ textTransform: 'capitalize' }}>{e.type}</td>
                        <td><StatusBadge status={e.priority} /></td>
                        <td><StatusBadge status={e.status} /></td>
                        <td>{e.hospitalName || 'Coimbatore Hospital'}</td>
                        <td style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                          {new Date(e.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ padding: '2rem' }}>
              <EmptyState
                title="No Emergencies Match Filter"
                description="Try clearing your search query or adjusting the type and priority filters."
              />
            </div>
          )}
        </div>

        {/* Selected Emergency Detail Card */}
        {selectedEmergency && (
          <div className="clinical-card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
                  Case File
                </span>
                <h3 style={{ fontSize: '1.35rem', fontWeight: 700, color: 'var(--color-primary-navy)' }}>
                  Emergency #{selectedEmergency.id}
                </h3>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <StatusBadge status={selectedEmergency.priority} />
                <StatusBadge status={selectedEmergency.status} />
              </div>
            </div>

            <p style={{ fontSize: '0.9375rem', color: 'var(--color-text-primary)', lineHeight: 1.5, backgroundColor: 'var(--color-bg-card-subtle)', padding: '0.875rem', borderRadius: 'var(--radius-md)' }}>
              {selectedEmergency.description}
            </p>

            {/* Quick Metadata Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', fontSize: '0.8125rem' }}>
              <div>
                <span style={{ color: 'var(--color-text-muted)' }}>Hospital Facility:</span>
                <div style={{ fontWeight: 600 }}>{selectedEmergency.hospitalName || selectedEmergency.hospitalId}</div>
              </div>
              <div>
                <span style={{ color: 'var(--color-text-muted)' }}>Required Resources:</span>
                <div style={{ fontWeight: 600 }}>
                  {selectedEmergency.bloodGroup ? `${selectedEmergency.bloodGroup} (${selectedEmergency.unitsRequired || 2} units)` : selectedEmergency.organType || 'General Ambulance'}
                </div>
              </div>
              <div>
                <span style={{ color: 'var(--color-text-muted)' }}>Location Lat/Lng:</span>
                <div style={{ fontWeight: 600 }}>
                  {selectedEmergency.locationLat ?? 11.0168}, {selectedEmergency.locationLng ?? 76.9558}
                </div>
              </div>
              <div>
                <span style={{ color: 'var(--color-text-muted)' }}>Mobilization ETA:</span>
                <div style={{ fontWeight: 600, color: 'var(--color-emerald-green)' }}>
                  {selectedEmergency.eta ? `${selectedEmergency.eta} Minutes` : 'Under Triage'}
                </div>
              </div>
            </div>

            {/* Clinical Actions (Doctor / Staff / Admin) */}
            {(isDoctor || isStaff || isAdmin) && selectedEmergency.status !== 'resolved' && selectedEmergency.status !== 'cancelled' && (
              <div style={{ display: 'flex', gap: '0.75rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
                <button onClick={() => setResolveModalOpen(true)} className="btn btn-primary btn-sm" style={{ flex: 1 }}>
                  <CheckCircle2 size={16} />
                  <span>Mark Resolved</span>
                </button>
                <button onClick={() => setCancelModalOpen(true)} className="btn btn-secondary btn-sm" style={{ color: 'var(--color-emergency-red)' }}>
                  <XCircle size={16} />
                  <span>Cancel Case</span>
                </button>
              </div>
            )}

            {/* Activity History Timeline */}
            <div style={{ marginTop: '0.5rem' }}>
              <h4 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--color-primary-navy)', marginBottom: '0.75rem' }}>
                Case Activity Timeline
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '200px', overflowY: 'auto' }}>
                {timeline.map((ev) => (
                  <div
                    key={ev.id}
                    style={{
                      fontSize: '0.75rem',
                      padding: '0.5rem',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: 'var(--color-bg-card-subtle)',
                      borderLeft: '3px solid var(--color-emerald-green)',
                    }}
                  >
                    <div style={{ fontWeight: 600, color: 'var(--color-primary-navy)' }}>{ev.eventType}</div>
                    <div style={{ color: 'var(--color-text-secondary)', marginTop: '0.1rem' }}>{ev.description}</div>
                    <div style={{ color: 'var(--color-text-muted)', fontSize: '0.6875rem', marginTop: '0.2rem' }}>
                      {ev.actor} ({ev.actorRole}) • {new Date(ev.timestamp).toLocaleTimeString()}
                    </div>
                  </div>
                ))}
                {timeline.length === 0 && (
                  <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
                    No activity records logged yet.
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Resolve Modal */}
      <Modal
        isOpen={resolveModalOpen}
        onClose={() => setResolveModalOpen(false)}
        title="Resolve Emergency Case"
        subtitle="Confirm patient stabilization or transfusion completion."
      >
        <div className="form-group">
          <label className="form-label">Clinical Resolution Notes</label>
          <textarea
            className="form-textarea"
            rows={3}
            placeholder="e.g. 2 units of O- successfully transfused in trauma OT #2. Patient vitals stabilized."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
          <button onClick={() => setResolveModalOpen(false)} className="btn btn-secondary" disabled={isActionLoading}>
            Cancel
          </button>
          <button onClick={handleResolve} className="btn btn-primary" disabled={isActionLoading}>
            {isActionLoading ? 'Updating...' : 'Confirm Resolution'}
          </button>
        </div>
      </Modal>

      {/* Cancel Modal */}
      <Modal
        isOpen={cancelModalOpen}
        onClose={() => setCancelModalOpen(false)}
        title="Cancel Emergency Case"
        subtitle="Provide reason for terminating this emergency response."
      >
        <div className="form-group">
          <label className="form-label">Cancellation Reason</label>
          <textarea
            className="form-textarea"
            rows={3}
            placeholder="e.g. Patient transferred to Apollo Specialty or duplicate SOS created."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
          <button onClick={() => setCancelModalOpen(false)} className="btn btn-secondary" disabled={isActionLoading}>
            Back
          </button>
          <button onClick={handleCancel} className="btn btn-danger" disabled={isActionLoading}>
            {isActionLoading ? 'Cancelling...' : 'Confirm Cancellation'}
          </button>
        </div>
      </Modal>

      {/* Broadcast Emergency SOS Modal */}
      <CreateEmergencyModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSuccess={(id) => {
          fetchEmergencies();
          showToast({
            type: 'success',
            title: 'Emergency SOS Broadcasted',
            message: `Emergency #${id} successfully initiated.`,
          });
        }}
      />
    </div>
  );
};

export default Emergencies;
