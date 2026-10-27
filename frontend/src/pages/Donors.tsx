import React, { useState, useEffect } from 'react';
import {
  Users,
  Search,
  Filter,
  Shield,
  Heart,
  MapPin,
  Calendar,
  CheckCircle,
  XCircle,
  RefreshCw,
  AlertCircle,
  Sliders,
  Phone,
  Eye,
  Award,
} from 'lucide-react';
import { bloodApi } from '../api/services';
import { Donor } from '../types';
import { useAuth } from '../context/AuthContext';
import { useRealtime } from '../context/RealtimeContext';
import StatusBadge from '../components/common/StatusBadge';
import EmptyState from '../components/common/EmptyState';
import Modal from '../components/common/Modal';

export const Donors: React.FC = () => {
  const { user, isDonor } = useAuth();
  const { addToast } = useRealtime();

  const [donors, setDonors] = useState<Donor[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedBloodGroup, setSelectedBloodGroup] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [selectedCity, setSelectedCity] = useState<string>('all');

  // Personal donor profile state if user is a donor
  const [myDonorProfile, setMyDonorProfile] = useState<Donor | null>(null);
  const [updatingAvailability, setUpdatingAvailability] = useState<boolean>(false);

  // Selected donor for details modal
  const [viewingDonor, setViewingDonor] = useState<Donor | null>(null);

  const fetchDonors = async () => {
    try {
      setLoading(true);
      setError(null);
      const params: any = { limit: 100 };
      if (selectedBloodGroup !== 'all') params.blood_group = selectedBloodGroup;
      if (selectedStatus !== 'all') params.status = selectedStatus;
      if (selectedCity !== 'all') params.city = selectedCity;

      const data = await bloodApi.getDonors(params);
      setDonors(data);

      if (isDonor) {
        try {
          const me = await bloodApi.getDonorMe();
          setMyDonorProfile(me);
        } catch {
          // non-blocking
        }
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to retrieve donors.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDonors();
  }, [selectedBloodGroup, selectedStatus, selectedCity]);

  // Handle donor availability toggle
  const handleToggleMyAvailability = async (isAvailable: boolean) => {
    try {
      setUpdatingAvailability(true);
      await bloodApi.updateAvailability(isAvailable);
      if (myDonorProfile) {
        setMyDonorProfile({ ...myDonorProfile, isAvailable });
      }
      addToast({
        title: isAvailable ? 'Active for Emergency Dispatch' : 'Emergency Dispatch Paused',
        message: isAvailable
          ? 'You are now visible to hospitals for urgent blood matches.'
          : 'You will not receive emergency outreach alerts until resumed.',
        type: isAvailable ? 'success' : 'info',
      });
      fetchDonors();
    } catch (err: any) {
      addToast({
        title: 'Update Failed',
        message: err?.message || 'Unable to update availability.',
        type: 'error',
      });
    } finally {
      setUpdatingAvailability(false);
    }
  };

  const filteredDonors = donors.filter((d) => {
    const matchesSearch =
      d.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.city?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.id.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSearch;
  });

  // Extract unique cities
  const uniqueCities = Array.from(new Set(donors.map((d) => d.city).filter(Boolean)));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-lg bg-emerald-100 text-emerald-700">
              <Users className="w-5 h-5 text-emerald-600" />
            </span>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Verified Blood Donor Registry</h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Privacy-preserving donor network with differential GPS privacy and automated compatibility triage.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchDonors()}
            className="btn btn-secondary flex items-center gap-2 text-xs"
            title="Refresh Donor Registry"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* If current user is a Donor, display personal emergency readiness card */}
      {isDonor && myDonorProfile && (
        <div className="bg-gradient-to-r from-emerald-900 to-slate-900 text-white rounded-2xl p-5 shadow-sm border border-emerald-800">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-2xl bg-white/10 flex flex-col items-center justify-center font-bold border border-white/20">
                <span className="text-lg leading-none text-emerald-400">{myDonorProfile.bloodGroup}</span>
                <span className="text-[10px] text-slate-300 font-normal mt-0.5">My Group</span>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-white">{myDonorProfile.name}</h3>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                    Verified Donor
                  </span>
                </div>
                <p className="text-xs text-slate-300 mt-0.5 flex items-center gap-2">
                  <span>Total Donations: <strong>{myDonorProfile.totalDonations || 0}</strong></span>
                  <span>•</span>
                  <span>Last: {myDonorProfile.lastDonationDate ? new Date(myDonorProfile.lastDonationDate).toLocaleDateString() : 'None recorded'}</span>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-300">
                Status: <strong className={myDonorProfile.isAvailable ? 'text-emerald-400' : 'text-amber-400'}>
                  {myDonorProfile.isAvailable ? 'Available for Emergencies' : 'Standby / Paused'}
                </strong>
              </span>
              <button
                onClick={() => handleToggleMyAvailability(!myDonorProfile.isAvailable)}
                disabled={updatingAvailability}
                className={`btn btn-sm text-xs font-semibold px-4 py-2 ${
                  myDonorProfile.isAvailable
                    ? 'bg-amber-500 hover:bg-amber-600 text-slate-950'
                    : 'bg-emerald-500 hover:bg-emerald-600 text-white'
                }`}
              >
                {myDonorProfile.isAvailable ? 'Pause Availability' : 'Go Available'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search by name, city, ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input input-sm pl-9 text-xs w-full"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 w-full md:w-auto">
          <select
            value={selectedBloodGroup}
            onChange={(e) => setSelectedBloodGroup(e.target.value)}
            className="input input-sm text-xs bg-slate-50"
          >
            <option value="all">All Groups</option>
            <option value="O+">O+</option>
            <option value="O-">O-</option>
            <option value="A+">A+</option>
            <option value="A-">A-</option>
            <option value="B+">B+</option>
            <option value="B-">B-</option>
            <option value="AB+">AB+</option>
            <option value="AB-">AB-</option>
          </select>

          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="input input-sm text-xs bg-slate-50"
          >
            <option value="all">All Statuses</option>
            <option value="available">Available</option>
            <option value="paused">Paused</option>
            <option value="unavailable">Unavailable</option>
          </select>

          <select
            value={selectedCity}
            onChange={(e) => setSelectedCity(e.target.value)}
            className="input input-sm text-xs bg-slate-50"
          >
            <option value="all">All Cities</option>
            {uniqueCities.map((city) => (
              <option key={city} value={city}>
                {city}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Donors Grid */}
      {loading ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200">
          <RefreshCw className="w-6 h-6 animate-spin text-emerald-600 mx-auto mb-2" />
          <p className="text-xs text-slate-500 font-medium">Loading verified donors...</p>
        </div>
      ) : error ? (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : filteredDonors.length === 0 ? (
        <EmptyState
          title="No Registered Donors Found"
          description="No donors match the selected filters or search terms. Try adjusting the filter criteria."
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredDonors.map((donor) => (
            <div
              key={donor.id}
              className="bg-white rounded-xl border border-slate-200 p-4 hover:border-slate-300 hover:shadow-xs transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="w-12 h-12 rounded-xl bg-red-50 text-red-700 border border-red-200 flex flex-col items-center justify-center font-bold text-sm shadow-xs">
                      <span>{donor.bloodGroup}</span>
                      <span className="text-[9px] font-normal text-slate-500 uppercase">ABO/Rh</span>
                    </span>
                    <div>
                      <h3 className="font-semibold text-sm text-slate-900">{donor.name}</h3>
                      <p className="text-xs text-slate-500 mt-0.5 flex items-center gap-1">
                        <MapPin className="w-3 h-3 text-slate-400" />
                        {donor.city || 'Regional Area'}
                      </p>
                    </div>
                  </div>
                  <StatusBadge status={donor.isAvailable ? 'available' : 'unavailable'} size="sm" />
                </div>

                <div className="mt-4 pt-3 border-t border-slate-100 grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-slate-400 block text-[11px]">Donations</span>
                    <span className="font-semibold text-slate-800 flex items-center gap-1 mt-0.5">
                      <Award className="w-3.5 h-3.5 text-amber-500" />
                      {donor.totalDonations || 0} times
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Last Donation</span>
                    <span className="font-semibold text-slate-800 flex items-center gap-1 mt-0.5">
                      <Calendar className="w-3.5 h-3.5 text-slate-400" />
                      {donor.lastDonationDate
                        ? new Date(donor.lastDonationDate).toLocaleDateString()
                        : 'Never'}
                    </span>
                  </div>
                </div>

                {/* Privacy Badge */}
                <div className="mt-3 py-1.5 px-2.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
                  <span className="flex items-center gap-1">
                    <Shield className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Differential Privacy (SEC-05)</span>
                  </span>
                  <span className="text-slate-400">
                    {donor.coordinatesObfuscated ? '500m Obfuscated' : 'Protected'}
                  </span>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                <span className="text-[11px] text-slate-400 font-mono">#{donor.id.slice(0, 8)}</span>
                <button
                  onClick={() => setViewingDonor(donor)}
                  className="btn btn-secondary btn-sm text-xs flex items-center gap-1 text-slate-700"
                >
                  <Eye className="w-3.5 h-3.5" />
                  View Details
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Donor Details Modal */}
      {viewingDonor && (
        <Modal
          isOpen={true}
          onClose={() => setViewingDonor(null)}
          title={`Donor Profile: ${viewingDonor.name}`}
          size="md"
        >
          <div className="space-y-4 text-xs">
            <div className="flex items-center gap-4 p-4 rounded-xl bg-slate-50 border border-slate-200">
              <div className="w-14 h-14 rounded-xl bg-red-600 text-white flex flex-col items-center justify-center font-bold text-base shadow-xs">
                <span>{viewingDonor.bloodGroup}</span>
                <span className="text-[10px] font-normal text-red-200">ABO/Rh</span>
              </div>
              <div>
                <h4 className="text-sm font-bold text-slate-900">{viewingDonor.name}</h4>
                <p className="text-slate-500 mt-0.5">
                  Registered ID: <span className="font-mono">{viewingDonor.id}</span>
                </p>
                <div className="mt-1 flex items-center gap-2">
                  <StatusBadge status={viewingDonor.isAvailable ? 'available' : 'unavailable'} size="sm" />
                  {viewingDonor.isSynthetic && (
                    <span className="badge badge-outline text-[10px]">Synthetic Demo Record</span>
                  )}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 rounded-lg border border-slate-200">
                <span className="text-slate-400 block text-[11px]">Geographic Jurisdiction</span>
                <p className="font-semibold text-slate-800 mt-1">
                  {viewingDonor.city || 'Not specified'} {viewingDonor.district ? `(${viewingDonor.district})` : ''}
                </p>
                <span className="text-[11px] text-slate-400">Pincode: {viewingDonor.pincode || '641001'}</span>
              </div>

              <div className="p-3 rounded-lg border border-slate-200">
                <span className="text-slate-400 block text-[11px]">Clinical Donation Record</span>
                <p className="font-semibold text-slate-800 mt-1">
                  {viewingDonor.totalDonations || 0} Lifesaving Donations
                </p>
                <span className="text-[11px] text-slate-400">
                  Last: {viewingDonor.lastDonationDate ? new Date(viewingDonor.lastDonationDate).toLocaleDateString() : 'N/A'}
                </span>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-900 space-y-1">
              <div className="flex items-center gap-1.5 font-semibold text-emerald-800">
                <Shield className="w-4 h-4 text-emerald-600" />
                Donor Location Privacy Enforcement
              </div>
              <p className="text-[11px] text-emerald-800">
                Per HIPAA & LifeLink SEC-05 privacy protocols, exact donor residential GPS coordinates are never exposed over public endpoints. Coordinates are dynamically perturbed by a 500-meter Gaussian obfuscation radius.
              </p>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setViewingDonor(null)}
                className="btn btn-secondary text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

export default Donors;
