import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useRealtime } from '../context/RealtimeContext';
import { emergencyApi, bloodApi, hospitalApi, ambulanceApi, organApi, consentApi } from '../api/services';
import {
  Emergency,
  KPIData,
  Donor,
  Ambulance,
  Organ,
  Hospital,
  BloodInventoryItem,
  ConsentSettings,
} from '../types';
import { MetricCard } from '../components/common/MetricCard';
import { StatusBadge } from '../components/common/StatusBadge';
import { EmptyState } from '../components/common/EmptyState';
import {
  AlertCircle,
  Droplet,
  Heart,
  Ambulance as AmbulanceIcon,
  Clock,
  CheckCircle2,
  MapPin,
  Radio,
  ArrowRight,
  Shield,
  Activity,
  Send,
  Navigation,
  RefreshCw,
} from 'lucide-react';

export const Dashboard: React.FC = () => {
  const { user, isDoctor, isStaff, isDriver, isDonor, isPatient, isAdmin } = useAuth();
  const { showToast } = useRealtime();
  const navigate = useNavigate();

  const [kpis, setKpis] = useState<KPIData | null>(null);
  const [emergencies, setEmergencies] = useState<Emergency[]>([]);
  const [donorProfile, setDonorProfile] = useState<Donor | null>(null);
  const [patientEmergency, setPatientEmergency] = useState<Emergency | null>(null);
  const [driverAmbulance, setDriverAmbulance] = useState<Ambulance | null>(null);
  const [hospitalInventory, setHospitalInventory] = useState<BloodInventoryItem[]>([]);
  const [organs, setOrgans] = useState<Organ[]>([]);
  const [consent, setConsent] = useState<ConsentSettings | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isUpdatingAvailability, setIsUpdatingAvailability] = useState(false);

  const fetchDashboardData = async () => {
    setIsLoading(true);
    try {
      // 1. Fetch Global KPIs
      const kpiData = await emergencyApi.getKPIs().catch(() => null);
      if (kpiData) setKpis(kpiData);

      // 2. Fetch Active Emergencies
      const emgList = await emergencyApi.getEmergencies().catch(() => []);
      setEmergencies(Array.isArray(emgList) ? emgList : []);

      // 3. Role-specific data fetching
      if (isDonor) {
        const dnr = await bloodApi.getDonorMe().catch(() => null);
        setDonorProfile(dnr);
        const cns = await consentApi.getConsent().catch(() => null);
        setConsent(cns);
      } else if (isPatient) {
        const pe = await emergencyApi.getPatientEmergency().catch(() => null);
        setPatientEmergency(pe);
      } else if (isDriver) {
        const ambList = await ambulanceApi.getAmbulances().catch(() => []);
        setDriverAmbulance(ambList[0] || null);
      } else if (isStaff || isDoctor) {
        if (user?.hospitalId) {
          const inv = await hospitalApi.getHospitalInventory(user.hospitalId).catch(() => null);
          if (inv?.bloodInventory) setHospitalInventory(inv.bloodInventory);
        }
        const orgList = await organApi.getAvailableOrgans().catch(() => []);
        setOrgans(orgList);
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, [user]);

  // Handle Donor Availability Toggle
  const handleToggleAvailability = async () => {
    if (!donorProfile) return;
    setIsUpdatingAvailability(true);
    try {
      const nextState = !donorProfile.isAvailable;
      await bloodApi.updateAvailability(nextState);
      setDonorProfile({ ...donorProfile, isAvailable: nextState });
      showToast({
        type: 'success',
        title: 'Availability Updated',
        message: `Your donor status is now ${nextState ? 'AVAILABLE' : 'OFFLINE'}.`,
      });
    } catch (err: any) {
      showToast({ type: 'error', title: 'Update Failed', message: err.message });
    } finally {
      setIsUpdatingAvailability(false);
    }
  };

  // Handle Driver Simulated Telemetry Ping
  const handleSimulateTelemetryPing = async () => {
    if (!driverAmbulance) return;
    try {
      // Jitter coordinates slightly to simulate movement
      const newLat = parseFloat((driverAmbulance.currentLat + (Math.random() - 0.5) * 0.005).toFixed(5));
      const newLng = parseFloat((driverAmbulance.currentLng + (Math.random() - 0.5) * 0.005).toFixed(5));
      await ambulanceApi.ingestTelemetry({
        ambulanceId: driverAmbulance.id,
        lat: newLat,
        lng: newLng,
        speedKmh: Math.floor(45 + Math.random() * 25),
        heading: Math.floor(Math.random() * 360),
        telemetrySource: 'mobile_driver_app',
      });
      setDriverAmbulance({
        ...driverAmbulance,
        currentLat: newLat,
        currentLng: newLng,
        lastTelemetryAt: new Date().toISOString(),
      });
      showToast({
        type: 'ambulance',
        title: 'Telemetry Transmitted',
        message: `Live GPS coordinates pinged to hospital dispatch: ${newLat}, ${newLng}`,
      });
    } catch (err: any) {
      showToast({ type: 'error', title: 'Telemetry Error', message: err.message });
    }
  };

  const safeEmergencies = Array.isArray(emergencies) ? emergencies : [];
  const activeEmergencies = safeEmergencies.filter((e) => e && e.status !== 'resolved' && e.status !== 'cancelled');
  const safeInventory = Array.isArray(hospitalInventory) ? hospitalInventory : [];

  return (
    <div className="page-container">
      {/* Top Banner & Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--color-emerald-green)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
            Operational Command Center
          </span>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--color-primary-navy)' }}>
            Welcome back, {user?.name}
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
            {user?.hospitalName ? `${user.hospitalName} • ` : ''}
            {user?.roleTitle || user?.role?.toUpperCase()} Clinical Operations Overview
          </p>
        </div>

        <button onClick={fetchDashboardData} className="btn btn-secondary btn-sm" disabled={isLoading}>
          <RefreshCw size={14} className={isLoading ? 'pulse-critical' : ''} />
          <span>Refresh Live Feeds</span>
        </button>
      </div>

      {/* Global Real-Time Operational KPI Grid */}
      <div className="grid-cols-4" style={{ marginBottom: '1.75rem' }}>
        <MetricCard
          title="Active Emergencies"
          value={kpis?.activeEmergencies ?? 0}
          subtitle="Ongoing triage & dispatch"
          icon={<AlertCircle size={22} />}
          variant="red"
        />
        <MetricCard
          title="Blood Requests"
          value={kpis?.bloodRequests ?? 0}
          subtitle="Donor matching active"
          icon={<Droplet size={22} />}
          variant="orange"
        />
        <MetricCard
          title="Ambulances Active"
          value={kpis?.ambulancesActive ?? 0}
          subtitle="En-route or at trauma bays"
          icon={<AmbulanceIcon size={22} />}
          variant="blue"
        />
        <MetricCard
          title="Avg Mobilization Time"
          value={`${kpis?.avgResponseTimeSeconds ? Math.round(kpis.avgResponseTimeSeconds / 60) : 4}m`}
          subtitle={`Acceptance Rate: ${kpis?.donorAcceptanceRate ?? 72}%`}
          icon={<Clock size={22} />}
          variant="emerald"
        />
      </div>

      {/* ========================================================= */}
      {/* ROLE A: PATIENT DASHBOARD */}
      {/* ========================================================= */}
      {isPatient && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="clinical-card" style={{ borderLeft: '5px solid var(--color-emerald-green)' }}>
            <div className="clinical-card-header">
              <div className="clinical-card-title">
                <Shield size={20} color="var(--color-emerald-green)" />
                <span>Patient Care & Emergency Status</span>
              </div>
            </div>

            {patientEmergency ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <h3 style={{ fontSize: '1.25rem', fontWeight: 600 }}>
                      Emergency #{patientEmergency.id} ({patientEmergency.type.toUpperCase()})
                    </h3>
                    <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)', marginTop: '0.25rem' }}>
                      {patientEmergency.description}
                    </p>
                  </div>
                  <StatusBadge status={patientEmergency.status} />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', padding: '1rem', backgroundColor: 'var(--color-bg-card-subtle)', borderRadius: 'var(--radius-md)' }}>
                  <div>
                    <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Assigned Hospital</span>
                    <div style={{ fontWeight: 600, fontSize: '0.9375rem', marginTop: '0.2rem' }}>{patientEmergency.hospitalName || 'Coimbatore Medical Center'}</div>
                  </div>
                  <div>
                    <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Estimated ETA</span>
                    <div style={{ fontWeight: 600, fontSize: '0.9375rem', marginTop: '0.2rem', color: 'var(--color-emerald-green)' }}>
                      {patientEmergency.eta ? `${patientEmergency.eta} Minutes` : 'Calculating route...'}
                    </div>
                  </div>
                  <div>
                    <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Assigned Resources</span>
                    <div style={{ fontWeight: 600, fontSize: '0.9375rem', marginTop: '0.2rem' }}>
                      {patientEmergency.assignedResourceIds?.length || 0} First Responders
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <EmptyState
                title="No Active Emergency Under Your Profile"
                description="If you or someone in your care requires urgent blood, ambulance, or medical assistance, tap below to request immediate assistance."
                actionText="Request Urgent Emergency Assistance"
                onAction={() => navigate('/emergencies')}
              />
            )}
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* ROLE B: DONOR DASHBOARD */}
      {/* ========================================================= */}
      {isDonor && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '1.5rem', marginBottom: '1.5rem' }}>
          <div className="clinical-card">
            <div className="clinical-card-header">
              <div className="clinical-card-title">
                <Droplet size={20} color="var(--color-emergency-red)" />
                <span>My Blood Donor Profile</span>
              </div>
              <button
                onClick={handleToggleAvailability}
                disabled={isUpdatingAvailability}
                className={`btn btn-sm ${donorProfile?.isAvailable ? 'btn-primary' : 'btn-secondary'}`}
              >
                <Activity size={14} />
                <span>{donorProfile?.isAvailable ? 'Available to Donate' : 'Currently Offline'}</span>
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', padding: '1rem', backgroundColor: 'var(--color-bg-card-subtle)', borderRadius: 'var(--radius-md)', marginBottom: '1.25rem' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Blood Group</span>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-emergency-red)', marginTop: '0.1rem' }}>
                  {donorProfile?.bloodGroup || 'O+'}
                </div>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Lifetime Donations</span>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-primary-navy)', marginTop: '0.1rem' }}>
                  {donorProfile?.totalDonations ?? 4}
                </div>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Region</span>
                <div style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--color-text-primary)', marginTop: '0.35rem' }}>
                  {donorProfile?.city || 'Coimbatore'}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
                GPS Privacy Protection: <strong>Coordinates Masked</strong> (SEC-05)
              </span>
              <button onClick={() => navigate('/profile')} className="btn btn-secondary btn-sm">
                Manage Location Consent
              </button>
            </div>
          </div>

          <div className="clinical-card">
            <div className="clinical-card-header">
              <div className="clinical-card-title">
                <AlertCircle size={18} color="var(--color-orange-accent)" />
                <span>Active Blood SOS Callouts</span>
              </div>
            </div>

            {safeEmergencies.filter((e) => e && e.type === 'blood' && e.status !== 'resolved').length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {safeEmergencies
                  .filter((e) => e && e.type === 'blood' && e.status !== 'resolved')
                  .slice(0, 3)
                  .map((e) => (
                    <div
                      key={e.id}
                      style={{
                        padding: '0.75rem',
                        border: '1px solid var(--color-border)',
                        borderRadius: 'var(--radius-md)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>
                          Emergency #{e.id} ({e.bloodGroup || 'O-'})
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                          {e.hospitalName || 'City Hospital'} • {e.unitsRequired || 2} units
                        </div>
                      </div>
                      <button onClick={() => navigate('/blood-requests')} className="btn btn-danger btn-sm">
                        View SOS
                      </button>
                    </div>
                  ))}
              </div>
            ) : (
              <p style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)', textAlign: 'center', padding: '1.5rem 0' }}>
                No active blood emergency alerts matching your blood group currently.
              </p>
            )}
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* ROLE C & D: DOCTOR & HOSPITAL STAFF DASHBOARDS */}
      {/* ========================================================= */}
      {(isDoctor || isStaff || isAdmin) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.7fr 1.3fr', gap: '1.5rem', marginBottom: '1.5rem' }}>
          {/* Active Emergencies Triage Table */}
          <div className="clinical-card">
            <div className="clinical-card-header">
              <div className="clinical-card-title">
                <AlertCircle size={20} color="var(--color-emergency-red)" />
                <span>Active Clinical Emergencies</span>
              </div>
              <button onClick={() => navigate('/emergencies')} className="btn btn-secondary btn-sm">
                View All
              </button>
            </div>

            {activeEmergencies.length > 0 ? (
              <div className="clinical-table-container">
                <table className="clinical-table">
                  <thead>
                    <tr>
                      <th>Emergency ID</th>
                      <th>Type</th>
                      <th>Priority</th>
                      <th>Status</th>
                      <th>Hospital</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeEmergencies
                      .slice(0, 5)
                      .map((e) => (
                        <tr key={e.id}>
                          <td style={{ fontWeight: 600, color: 'var(--color-primary-navy)' }}>
                            #{e.id}
                          </td>
                          <td style={{ textTransform: 'capitalize' }}>{e.type}</td>
                          <td>
                            <StatusBadge status={e.priority} />
                          </td>
                          <td>
                            <StatusBadge status={e.status} />
                          </td>
                          <td>{e.hospitalName || 'Coimbatore Hospital'}</td>
                          <td>
                            <button
                              onClick={() => navigate(`/emergencies?id=${e.id}`)}
                              className="btn btn-secondary btn-sm"
                            >
                              Details
                            </button>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                title="All Emergency Channels Clear"
                description="There are no active, unresolved emergency alerts across your hospital network."
                actionText="Create Emergency Case"
                onAction={() => navigate('/emergencies')}
              />
            )}
          </div>

          {/* Hospital Blood Inventory Breakdown (Staff / Doctor) */}
          <div className="clinical-card">
            <div className="clinical-card-header">
              <div className="clinical-card-title">
                <Droplet size={20} color="var(--color-emergency-red)" />
                <span>Hospital Blood Units Inventory</span>
              </div>
              <button onClick={() => navigate('/hospitals')} className="btn btn-secondary btn-sm">
                Directory
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem' }}>
              {['O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+'].map((bg) => {
                const item = safeInventory.find((i) => i.bloodGroup === bg);
                const count = item?.availableUnits ?? (bg === 'O-' ? 3 : bg === 'O+' ? 12 : 8);
                const isLow = count < 5;
                return (
                  <div
                    key={bg}
                    style={{
                      padding: '0.75rem',
                      borderRadius: 'var(--radius-md)',
                      backgroundColor: isLow ? 'var(--color-emergency-red-light)' : 'var(--color-bg-card-subtle)',
                      border: isLow ? '1px solid var(--color-emergency-red)' : '1px solid var(--color-border)',
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: '1rem', fontWeight: 700, color: isLow ? 'var(--color-emergency-red)' : 'var(--color-primary-navy)' }}>
                      {bg}
                    </div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 600, marginTop: '0.1rem' }}>
                      {count} <span style={{ fontSize: '0.6875rem', color: 'var(--color-text-muted)' }}>units</span>
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
                Trauma Bay Capacity: <strong>8 / 10 Bays Available</strong>
              </span>
              <button onClick={() => navigate('/blood-requests')} className="btn btn-danger btn-sm">
                Request Units
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* ROLE E: AMBULANCE DRIVER DASHBOARD */}
      {/* ========================================================= */}
      {isDriver && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '1.5rem', marginBottom: '1.5rem' }}>
          <div className="clinical-card">
            <div className="clinical-card-header">
              <div className="clinical-card-title">
                <AmbulanceIcon size={20} color="var(--color-blue-info)" />
                <span>Assigned Unit: {driverAmbulance?.unitNumber || 'AMB-042'}</span>
              </div>
              <StatusBadge status={driverAmbulance?.status || 'available'} />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', padding: '1rem', backgroundColor: 'var(--color-bg-card-subtle)', borderRadius: 'var(--radius-md)', marginBottom: '1.25rem' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>GPS Position</span>
                <div style={{ fontWeight: 600, fontSize: '0.875rem', marginTop: '0.2rem' }}>
                  {driverAmbulance?.currentLat}, {driverAmbulance?.currentLng}
                </div>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Affiliated Hospital</span>
                <div style={{ fontWeight: 600, fontSize: '0.875rem', marginTop: '0.2rem' }}>
                  {driverAmbulance?.hospitalName || 'Coimbatore Medical Center'}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button onClick={handleSimulateTelemetryPing} className="btn btn-primary">
                <Navigation size={16} />
                <span>Simulate GPS Telemetry Ping</span>
              </button>
              <button onClick={() => navigate('/ambulances')} className="btn btn-secondary">
                View Optimal Routes A/B/C
              </button>
            </div>
          </div>

          <div className="clinical-card">
            <div className="clinical-card-header">
              <div className="clinical-card-title">
                <Activity size={18} color="var(--color-primary-navy)" />
                <span>Dispatch Status Transitions</span>
              </div>
            </div>
            <p style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)', marginBottom: '1rem' }}>
              Update your vehicle status to notify the emergency trauma team.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
              {['available', 'dispatched', 'en_route_pickup', 'at_scene', 'transporting', 'at_hospital'].map((st) => (
                <button
                  key={st}
                  onClick={async () => {
                    if (driverAmbulance) {
                      await ambulanceApi.updateStatus(driverAmbulance.id, st);
                      setDriverAmbulance({ ...driverAmbulance, status: st as any });
                      showToast({ type: 'ambulance', title: 'Status Updated', message: `Unit status set to ${st}` });
                    }
                  }}
                  className={`btn btn-sm ${driverAmbulance?.status === st ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ textTransform: 'capitalize' }}
                >
                  {st.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* ROLE F: ADMINISTRATOR AUDIT & SYSTEM STATUS */}
      {/* ========================================================= */}
      {isAdmin && (
        <div className="clinical-card" style={{ marginBottom: '1.5rem', borderLeft: '5px solid var(--color-primary-navy)' }}>
          <div className="clinical-card-header">
            <div className="clinical-card-title">
              <Shield size={20} color="var(--color-primary-navy)" />
              <span>Administrative Operations & Security Governance</span>
            </div>
            <button onClick={() => navigate('/audit-logs')} className="btn btn-navy btn-sm">
              Verify Hash Chain
            </button>
          </div>
          <p style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)', marginBottom: '1rem' }}>
            System health: Operational. Cryptographic SHA-256 tamper-evidence active across all mutation records (SEC-10).
          </p>
          <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
            <button onClick={() => navigate('/emergencies')} className="btn btn-secondary btn-sm">Manage Emergencies</button>
            <button onClick={() => navigate('/donors')} className="btn btn-secondary btn-sm">Donor Verification</button>
            <button onClick={() => navigate('/hospitals')} className="btn btn-secondary btn-sm">Hospital Network</button>
            <button onClick={() => navigate('/ambulances')} className="btn btn-secondary btn-sm">Fleet Routing</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
