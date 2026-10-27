import React, { useState, useEffect } from 'react';
import {
  User,
  Shield,
  Key,
  Bell,
  MapPin,
  CheckCircle2,
  Save,
  RefreshCw,
  Phone,
  Building2,
  Lock,
  Radio,
  Sliders,
  AlertCircle,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useRealtime } from '../context/RealtimeContext';
import { consentApi, notificationApi } from '../api/services';
import { ConsentSettings } from '../types';

export const Profile: React.FC = () => {
  const { user } = useAuth();
  const { addToast } = useRealtime();

  // Privacy & Consent State
  const [consent, setConsent] = useState<ConsentSettings>({
    userId: user?.id || '',
    liveLocation: true,
    emergencyCommunication: true,
    donationRequests: true,
    healthDataSharing: false,
  });
  const [consentLoading, setConsentLoading] = useState<boolean>(true);
  const [consentSaving, setConsentSaving] = useState<boolean>(false);

  // Notification Provider Status
  const [providerStatus, setProviderStatus] = useState<any | null>(null);
  const [providerLoading, setProviderLoading] = useState<boolean>(false);

  useEffect(() => {
    fetchConsent();
    fetchProviderStatus();
  }, []);

  const fetchConsent = async () => {
    try {
      setConsentLoading(true);
      const data = await consentApi.getConsent();
      setConsent(data);
    } catch {
      // Fallback to default state if user has no consent record yet
    } finally {
      setConsentLoading(false);
    }
  };

  const fetchProviderStatus = async () => {
    try {
      setProviderLoading(true);
      const data = await notificationApi.getProviderStatus();
      setProviderStatus(data);
    } catch {
      // non-blocking
    } finally {
      setProviderLoading(false);
    }
  };

  const handleSaveConsent = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setConsentSaving(true);
      const updated = await consentApi.updateConsent(consent);
      setConsent(updated);
      addToast({
        title: 'Privacy Preferences Saved',
        message: 'Your consent preferences have been updated in the cryptographic audit trail.',
        type: 'success',
      });
    } catch (err: any) {
      addToast({
        title: 'Save Failed',
        message: err?.message || 'Unable to update consent preferences.',
        type: 'error',
      });
    } finally {
      setConsentSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="border-b border-slate-200 pb-5">
        <div className="flex items-center gap-2">
          <span className="p-2 rounded-lg bg-slate-100 text-slate-700">
            <User className="w-5 h-5 text-slate-700" />
          </span>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">User Account & Privacy Governance</h1>
        </div>
        <p className="text-sm text-slate-500 mt-1">
          Manage clinical identity credentials, authorized RBAC permissions, and granular HIPAA consent toggles.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Left Column: Identity & Permissions (5 cols) */}
        <div className="md:col-span-5 space-y-5">
          {/* Identity Card */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-4">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-2xl bg-emerald-600 text-white font-bold text-xl flex items-center justify-center shadow-xs">
                {user?.name?.slice(0, 2).toUpperCase() || 'LL'}
              </div>
              <div>
                <h3 className="font-bold text-base text-slate-900">{user?.name}</h3>
                <p className="text-xs text-slate-500">{user?.email}</p>
                <div className="mt-1 flex items-center gap-1.5">
                  <span className="badge badge-emerald text-[11px] font-bold capitalize">
                    {user?.role?.replace('_', ' ')}
                  </span>
                  {user?.isVerified && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3 text-blue-600" />
                      Verified
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">User Identifier:</span>
                <span className="font-mono text-slate-800 text-[11px]">#{user?.id}</span>
              </div>
              {user?.hospitalName && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Affiliated Hospital:</span>
                  <span className="font-semibold text-slate-800">{user.hospitalName}</span>
                </div>
              )}
              {user?.licenseNumber && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">License / Registration:</span>
                  <span className="font-mono font-semibold text-slate-800">{user.licenseNumber}</span>
                </div>
              )}
              {user?.phone && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Phone:</span>
                  <span className="text-slate-800">{user.phone}</span>
                </div>
              )}
            </div>
          </div>

          {/* Granted Permissions Card */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-3">
            <div className="flex items-center gap-2">
              <Key className="w-4 h-4 text-emerald-600" />
              <h3 className="font-bold text-sm text-slate-900">Granted Role Permissions</h3>
            </div>
            <p className="text-xs text-slate-500">
              Cryptographically validated access control policies applied to your session.
            </p>

            <div className="flex flex-wrap gap-1.5 pt-1">
              {user?.permissions && user.permissions.length > 0 ? (
                user.permissions.map((perm) => (
                  <span
                    key={perm}
                    className="px-2 py-1 rounded-md text-[10px] font-mono font-medium bg-slate-100 text-slate-700 border border-slate-200"
                  >
                    {perm}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-400">Standard user capabilities</span>
              )}
            </div>
          </div>

          {/* Notification Gateway Mode Card */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-indigo-600" />
                <h3 className="font-bold text-sm text-slate-900">Notification Infrastructure</h3>
              </div>
              <span className="badge badge-emerald text-[10px] font-bold">Safe Mode Active</span>
            </div>

            {providerStatus ? (
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Provider:</span>
                  <span className="font-semibold text-slate-800">{providerStatus.provider}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Mock Mode:</span>
                  <span className="text-emerald-700 font-bold">
                    {providerStatus.mockNotificationsOnly ? 'Simulated (Protected)' : 'Live'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Spend Ceiling:</span>
                  <span className="text-slate-800 font-mono">${providerStatus.spendCeilingUsd || 10}.00</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Hourly Limit:</span>
                  <span className="text-slate-800 font-mono">{providerStatus.rateLimitPerHour || 100} msgs/hr</span>
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400">Loading gateway status...</p>
            )}
          </div>
        </div>

        {/* Right Column: Privacy & Consent Preferences Form (7 cols) */}
        <div className="md:col-span-7">
          <form
            onSubmit={handleSaveConsent}
            className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-6"
          >
            <div>
              <div className="flex items-center gap-2">
                <Shield className="w-5 h-5 text-emerald-600" />
                <h3 className="font-bold text-base text-slate-900">Privacy & Data Governance Controls</h3>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                LifeLink complies with HIPAA and GDPR medical privacy standards. Adjust your consent preferences below.
              </p>
            </div>

            {consentLoading ? (
              <div className="py-8 text-center text-xs text-slate-400">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto text-emerald-600 mb-2" />
                Retrieving active consent records...
              </div>
            ) : (
              <div className="space-y-4">
                {/* Toggle 1: Live Location */}
                <div className="p-4 rounded-xl border border-slate-200 flex items-start justify-between gap-4">
                  <div>
                    <label className="font-semibold text-sm text-slate-900 block cursor-pointer">
                      Differential GPS Location Sharing (SEC-05)
                    </label>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Permits emergency routing algorithms to query your approximate location. Exact GPS is perturbed by 500m.
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={consent.liveLocation}
                    onChange={(e) => setConsent({ ...consent, liveLocation: e.target.checked })}
                    className="w-5 h-5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 mt-0.5"
                  />
                </div>

                {/* Toggle 2: Emergency Communication */}
                <div className="p-4 rounded-xl border border-slate-200 flex items-start justify-between gap-4">
                  <div>
                    <label className="font-semibold text-sm text-slate-900 block cursor-pointer">
                      Emergency SMS & Voice Alerts
                    </label>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Receive automated high-urgency notifications during critical blood emergencies or ambulance dispatches.
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={consent.emergencyCommunication}
                    onChange={(e) => setConsent({ ...consent, emergencyCommunication: e.target.checked })}
                    className="w-5 h-5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 mt-0.5"
                  />
                </div>

                {/* Toggle 3: Blood Donation Requests */}
                <div className="p-4 rounded-xl border border-slate-200 flex items-start justify-between gap-4">
                  <div>
                    <label className="font-semibold text-sm text-slate-900 block cursor-pointer">
                      Blood Donor Outreach Dispatch
                    </label>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Allows partner hospitals to contact you when matching emergency ABO/Rh patients require urgent units.
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={consent.donationRequests}
                    onChange={(e) => setConsent({ ...consent, donationRequests: e.target.checked })}
                    className="w-5 h-5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 mt-0.5"
                  />
                </div>

                {/* Toggle 4: Health Data Sharing */}
                <div className="p-4 rounded-xl border border-slate-200 flex items-start justify-between gap-4">
                  <div>
                    <label className="font-semibold text-sm text-slate-900 block cursor-pointer">
                      Anonymized Research & RAG Intelligence
                    </label>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Contribute de-identified clinical outcome statistics to improve emergency dispatch machine learning models.
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={consent.healthDataSharing}
                    onChange={(e) => setConsent({ ...consent, healthDataSharing: e.target.checked })}
                    className="w-5 h-5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 mt-0.5"
                  />
                </div>
              </div>
            )}

            <div className="flex items-center justify-between pt-4 border-t border-slate-100">
              <span className="text-[11px] text-slate-400">
                Changes are logged to the tamper-evident audit trail with SHA-256 verification.
              </span>
              <button
                type="submit"
                disabled={consentSaving}
                className="btn btn-primary text-xs font-semibold flex items-center gap-1.5"
              >
                <Save className="w-3.5 h-3.5" />
                {consentSaving ? 'Saving...' : 'Save Preferences'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Profile;
