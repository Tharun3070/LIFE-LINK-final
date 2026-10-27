import React, { useState, useEffect } from 'react';
import {
  Droplet,
  Users,
  Search,
  Filter,
  Send,
  CheckCircle2,
  XCircle,
  Clock,
  Sparkles,
  Phone,
  Shield,
  RefreshCw,
  AlertCircle,
  MapPin,
  ChevronRight,
  TrendingUp,
} from 'lucide-react';
import { bloodApi, emergencyApi } from '../api/services';
import { Emergency, RankedDonorsResponse, RankedDonorCandidate } from '../types';
import { useAuth } from '../context/AuthContext';
import { useRealtime } from '../context/RealtimeContext';
import StatusBadge from '../components/common/StatusBadge';
import EmptyState from '../components/common/EmptyState';
import Modal from '../components/common/Modal';

export const BloodRequests: React.FC = () => {
  const { user } = useAuth();
  const { addToast } = useRealtime();

  const [requests, setRequests] = useState<Emergency[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedBloodGroup, setSelectedBloodGroup] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');

  // Active selected request for donor triage
  const [selectedRequest, setSelectedRequest] = useState<Emergency | null>(null);
  const [rankedData, setRankedData] = useState<RankedDonorsResponse | null>(null);
  const [rankedLoading, setRankedLoading] = useState<boolean>(false);
  const [rankedError, setRankedError] = useState<string | null>(null);
  const [includeDemoDonors, setIncludeDemoDonors] = useState<boolean>(true);

  // Outreach batch dispatch state
  const [dispatchingBatch, setDispatchingBatch] = useState<boolean>(false);
  const [workflowStatus, setWorkflowStatus] = useState<any | null>(null);

  // Contact Donor Action State
  const [contactingDonorId, setContactingDonorId] = useState<string | null>(null);
  const [simulatingStatusDonorId, setSimulatingStatusDonorId] = useState<string | null>(null);

  // New Request Modal
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [formBloodGroup, setFormBloodGroup] = useState<string>('O+');
  const [formUnits, setFormUnits] = useState<number>(2);
  const [formPriority, setFormPriority] = useState<string>('critical');
  const [formHospitalId, setFormHospitalId] = useState<string>(user?.hospitalId || 'hosp-001');
  const [formNotes, setFormNotes] = useState<string>('');
  const [creatingRequest, setCreatingRequest] = useState<boolean>(false);

  const fetchBloodRequests = async () => {
    try {
      setLoading(true);
      setError(null);
      // Fetch emergencies with type=blood
      const data = await emergencyApi.getEmergencies({ type: 'blood' });
      setRequests(data);
      if (data.length > 0 && !selectedRequest) {
        setSelectedRequest(data[0]);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load blood requests.');
    } finally {
      setLoading(false);
    }
  };

  const fetchRankedDonors = async (emergencyId: string) => {
    try {
      setRankedLoading(true);
      setRankedError(null);
      const res = await bloodApi.getRankedDonors(emergencyId, { demoMode: includeDemoDonors });
      setRankedData(res);
      // Also fetch workflow outreach status
      try {
        const wf = await bloodApi.getWorkflowStatus(emergencyId);
        setWorkflowStatus(wf);
      } catch {
        // non-blocking
      }
    } catch (err: any) {
      setRankedError(err?.message || 'Unable to rank donors. Ensure emergency has a valid blood group.');
      setRankedData(null);
    } finally {
      setRankedLoading(false);
    }
  };

  useEffect(() => {
    fetchBloodRequests();
  }, []);

  useEffect(() => {
    if (selectedRequest) {
      fetchRankedDonors(selectedRequest.id);
    }
  }, [selectedRequest, includeDemoDonors]);

  // Handle Contacting a Donor
  const handleContactDonor = async (donor: RankedDonorCandidate) => {
    if (!selectedRequest) return;
    try {
      setContactingDonorId(donor.id);
      await bloodApi.contactDonor(donor.id, selectedRequest.id);
      addToast({
        title: 'Donor Alert Dispatched',
        message: `High-priority dispatch sent to ${donor.name || 'Donor'} (${donor.bloodGroup}).`,
        type: 'info',
      });
      // Refresh rankings and workflow status
      fetchRankedDonors(selectedRequest.id);
    } catch (err: any) {
      addToast({
        title: 'Dispatch Failed',
        message: err?.message || 'Could not send donor notification.',
        type: 'error',
      });
    } finally {
      setContactingDonorId(null);
    }
  };

  // Simulate Donor Response
  const handleSimulateResponse = async (donorId: string, status: 'accepted' | 'declined') => {
    if (!selectedRequest) return;
    try {
      setSimulatingStatusDonorId(donorId);
      await bloodApi.submitDonorResponse(donorId, {
        status,
        emergencyId: selectedRequest.id,
        shareLocation: status === 'accepted',
      });
      addToast({
        title: `Donor ${status.toUpperCase()}`,
        message: `Simulated ${status} response recorded for donor ${donorId}.`,
        type: status === 'accepted' ? 'success' : 'warning',
      });
      fetchRankedDonors(selectedRequest.id);
    } catch (err: any) {
      addToast({
        title: 'Simulation Error',
        message: err?.message || 'Failed to record response.',
        type: 'error',
      });
    } finally {
      setSimulatingStatusDonorId(null);
    }
  };

  // Handle Batch Outreach Dispatch
  const handleDispatchBatch = async () => {
    if (!selectedRequest) return;
    try {
      setDispatchingBatch(true);
      const res = await bloodApi.dispatchBatch(selectedRequest.id, 5);
      addToast({
        title: 'Batch Outreach Initiated',
        message: `Dispatched alerts to ${res?.dispatchedCount || 5} nearest donors within ${res?.searchRadiusKm || 15}km.`,
        type: 'success',
      });
      fetchRankedDonors(selectedRequest.id);
    } catch (err: any) {
      addToast({
        title: 'Outreach Dispatch Error',
        message: err?.message || 'Failed to dispatch batch.',
        type: 'error',
      });
    } finally {
      setDispatchingBatch(false);
    }
  };

  // Handle Create Blood Request Form Submission
  const handleCreateRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setCreatingRequest(true);
      const newReq = await bloodApi.createRequest({
        bloodGroup: formBloodGroup,
        unitsRequired: Number(formUnits),
        priority: formPriority,
        hospitalId: formHospitalId,
        notes: formNotes || undefined,
      });
      addToast({
        title: 'Blood SOS Initiated',
        message: `Request created for ${formUnits} units of ${formBloodGroup}. AI intent parsing activated.`,
        type: 'emergency',
      });
      setIsCreateModalOpen(false);
      setFormNotes('');
      await fetchBloodRequests();
      setSelectedRequest(newReq);
    } catch (err: any) {
      addToast({
        title: 'Creation Failed',
        message: err?.message || 'Unable to submit blood request. Ensure you have Doctor or Staff permissions.',
        type: 'error',
      });
    } finally {
      setCreatingRequest(false);
    }
  };

  const filteredRequests = requests.filter((r) => {
    const matchesSearch =
      r.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.hospitalName?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesGroup = selectedBloodGroup === 'all' || r.bloodGroup === selectedBloodGroup;
    const matchesStatus = selectedStatus === 'all' || r.status === selectedStatus;
    return matchesSearch && matchesGroup && matchesStatus;
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-lg bg-red-100 text-red-700">
              <Droplet className="w-5 h-5 fill-red-600 text-red-600" />
            </span>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Blood Emergency Coordination</h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Real-time ABO/Rh compatibility triage, dynamic radius expansion, and AI-ranked donor outreach.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchBloodRequests()}
            className="btn btn-secondary flex items-center gap-2 text-xs"
            title="Refresh Blood Requests"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="btn btn-emergency flex items-center gap-2 text-xs font-semibold shadow-sm"
          >
            <Droplet className="w-4 h-4" />
            Request Blood Units
          </button>
        </div>
      </div>

      {/* Main Grid: Left List + Right AI Donor Intelligence Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Requests List (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          {/* Search & Filter Toolbar */}
          <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-xs space-y-3">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search requests, ID, hospital..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="input input-sm pl-9 text-xs w-full"
              />
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <select
                  value={selectedBloodGroup}
                  onChange={(e) => setSelectedBloodGroup(e.target.value)}
                  className="input input-sm text-xs w-full bg-slate-50"
                >
                  <option value="all">All Blood Groups</option>
                  <option value="O+">O+ (Universal RBC Recipient O-)</option>
                  <option value="O-">O- (Universal Donor)</option>
                  <option value="A+">A+</option>
                  <option value="A-">A-</option>
                  <option value="B+">B+</option>
                  <option value="B-">B-</option>
                  <option value="AB+">AB+ (Universal Plasma Donor)</option>
                  <option value="AB-">AB-</option>
                </select>
              </div>
              <div className="flex-1">
                <select
                  value={selectedStatus}
                  onChange={(e) => setSelectedStatus(e.target.value)}
                  className="input input-sm text-xs w-full bg-slate-50"
                >
                  <option value="all">All Statuses</option>
                  <option value="created">Created</option>
                  <option value="resource_search">Searching Donors</option>
                  <option value="coordinating">Coordinating</option>
                  <option value="resolved">Resolved</option>
                </select>
              </div>
            </div>
          </div>

          {/* List Content */}
          {loading && requests.length === 0 ? (
            <div className="p-8 text-center bg-white rounded-xl border border-slate-200">
              <RefreshCw className="w-6 h-6 animate-spin text-emerald-600 mx-auto mb-2" />
              <p className="text-xs text-slate-500 font-medium">Loading active blood requests...</p>
            </div>
          ) : error ? (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : filteredRequests.length === 0 ? (
            <EmptyState
              title="No Blood Requests Found"
              description="No active blood requests match your current filters. Create a new request to trigger automated donor intelligence."
              actionLabel="Create Request"
              onAction={() => setIsCreateModalOpen(true)}
            />
          ) : (
            <div className="space-y-2.5 max-h-[calc(100vh-280px)] overflow-y-auto pr-1">
              {filteredRequests.map((req) => {
                const isSelected = selectedRequest?.id === req.id;
                return (
                  <div
                    key={req.id}
                    onClick={() => setSelectedRequest(req)}
                    className={`p-3.5 rounded-xl border transition-all cursor-pointer ${
                      isSelected
                        ? 'border-red-500 bg-red-50/40 shadow-sm ring-1 ring-red-400'
                        : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <span className="w-10 h-10 rounded-lg bg-red-600 text-white font-bold flex items-center justify-center text-sm shadow-xs">
                          {req.bloodGroup || 'UNK'}
                        </span>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm text-slate-900">
                              {req.unitsRequired ? `${req.unitsRequired} Units` : 'Blood Unit Alert'}
                            </span>
                            <StatusBadge status={req.priority} size="sm" />
                          </div>
                          <p className="text-xs text-slate-500 mt-0.5 flex items-center gap-1">
                            <MapPin className="w-3 h-3 text-slate-400" />
                            {req.hospitalName || 'Regional Hospital'}
                          </p>
                        </div>
                      </div>
                      <StatusBadge status={req.status} size="sm" />
                    </div>

                    <div className="mt-2.5 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
                      <span>ID: #{req.id.slice(0, 8)}</span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(req.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: AI Donor Matching & Outreach Intelligence (7 cols) */}
        <div className="lg:col-span-7">
          {selectedRequest ? (
            <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-5 space-y-5">
              {/* Request Banner & Outreach Summary */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-red-100 text-red-700 flex flex-col items-center justify-center font-bold">
                    <span className="text-base leading-none">{selectedRequest.bloodGroup}</span>
                    <span className="text-[10px] font-normal uppercase mt-0.5">ABO/Rh</span>
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                      Emergency Donor Matching
                      <span className="badge badge-outline text-[11px] font-mono">#{selectedRequest.id.slice(0, 8)}</span>
                    </h2>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Units Required: <strong className="text-slate-800">{selectedRequest.unitsRequired || 1} units</strong> • Priority:{' '}
                      <strong className="capitalize text-red-600">{selectedRequest.priority}</strong>
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={includeDemoDonors}
                      onChange={(e) => setIncludeDemoDonors(e.target.checked)}
                      className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    <span>Include Demo Pool</span>
                  </label>
                  <button
                    onClick={handleDispatchBatch}
                    disabled={dispatchingBatch}
                    className="btn btn-primary btn-sm flex items-center gap-1.5 text-xs"
                    title="Dispatch alerts to next 5 eligible donors"
                  >
                    <Send className={`w-3.5 h-3.5 ${dispatchingBatch ? 'animate-pulse' : ''}`} />
                    {dispatchingBatch ? 'Dispatching...' : 'Dispatch Batch'}
                  </button>
                </div>
              </div>

              {/* Progressive Radius Expansion Status Banner */}
              {rankedData?.searchConfig && (
                <div className="bg-slate-50 rounded-lg p-3 border border-slate-200 text-xs flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-emerald-600 shrink-0" />
                    <div>
                      <span className="font-semibold text-slate-800">Dynamic Search Radius:</span>{' '}
                      <span className="text-emerald-700 font-bold">{rankedData.searchConfig.currentRadiusKm} km</span>{' '}
                      <span className="text-slate-500">(Initial: {rankedData.searchConfig.initialRadiusKm} km, Max: {rankedData.searchConfig.maxRadiusKm} km)</span>
                    </div>
                  </div>
                  {rankedData.searchConfig.expansionCount > 0 && (
                    <span className="bg-amber-100 text-amber-800 px-2 py-0.5 rounded text-[11px] font-medium">
                      Expanded {rankedData.searchConfig.expansionCount}× ({rankedData.searchConfig.expansionReason || 'insufficient candidate density'})
                    </span>
                  )}
                </div>
              )}

              {/* AI Recommendation Quote */}
              {rankedData?.aiRecommendation && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-900 flex items-start gap-2">
                  <TrendingUp className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-semibold">AI Allocation Rationale:</span> {rankedData.aiRecommendation}
                  </div>
                </div>
              )}

              {/* Candidates Table */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <Users className="w-3.5 h-3.5" />
                    Ranked Candidates ({rankedData?.donors?.length || 0})
                  </h3>
                  <span className="text-[11px] text-slate-400">Ranked by Reachability, ETA, & Historical Response Rate</span>
                </div>

                {rankedLoading ? (
                  <div className="py-12 text-center">
                    <RefreshCw className="w-6 h-6 animate-spin text-emerald-600 mx-auto mb-2" />
                    <p className="text-xs text-slate-500 font-medium">Calculating multi-factor reachability scores...</p>
                  </div>
                ) : rankedError ? (
                  <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs">
                    <p className="font-semibold">Unable to Rank Donors</p>
                    <p className="mt-1">{rankedError}</p>
                  </div>
                ) : !rankedData?.donors || rankedData.donors.length === 0 ? (
                  <div className="p-6 text-center border border-dashed border-slate-300 rounded-xl">
                    <Users className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                    <p className="text-sm font-semibold text-slate-700">No Eligible Donors within Radius</p>
                    <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                      All donors within {rankedData?.searchConfig?.currentRadiusKm || 15}km have either already been contacted or do not meet compatibility criteria.
                    </p>
                    <button
                      onClick={handleDispatchBatch}
                      className="btn btn-secondary btn-sm mt-3 text-xs"
                    >
                      Expand Radius Search
                    </button>
                  </div>
                ) : (
                  <div className="overflow-x-auto border border-slate-200 rounded-xl">
                    <table className="table-clinical w-full text-left text-xs">
                      <thead>
                        <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                          <th className="py-2.5 px-3 font-semibold">Rank</th>
                          <th className="py-2.5 px-3 font-semibold">Candidate</th>
                          <th className="py-2.5 px-3 font-semibold">Group</th>
                          <th className="py-2.5 px-3 font-semibold">Distance & ETA</th>
                          <th className="py-2.5 px-3 font-semibold">Reachability</th>
                          <th className="py-2.5 px-3 font-semibold">Status</th>
                          <th className="py-2.5 px-3 font-semibold text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {rankedData.donors.map((candidate, idx) => {
                          const isContacting = contactingDonorId === candidate.id;
                          const isSimulating = simulatingStatusDonorId === candidate.id;

                          return (
                            <tr key={candidate.id} className="hover:bg-slate-50/70 transition-colors">
                              <td className="py-3 px-3 font-bold text-slate-700">
                                <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                                  idx === 0 ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-600'
                                }`}>
                                  {candidate.aiRank || idx + 1}
                                </span>
                              </td>
                              <td className="py-3 px-3">
                                <div className="font-semibold text-slate-900">{candidate.name || `Donor #${candidate.id.slice(0, 6)}`}</div>
                                <div className="text-[11px] text-slate-400 flex items-center gap-1 mt-0.5">
                                  <Shield className="w-3 h-3 text-emerald-600" />
                                  {candidate.locationConsentGranted ? 'GPS Obfuscated (500m)' : 'City Geocoded'}
                                </div>
                              </td>
                              <td className="py-3 px-3">
                                <span className="inline-block px-2 py-0.5 font-bold rounded bg-red-50 text-red-700 border border-red-200 text-xs">
                                  {candidate.bloodGroup}
                                </span>
                              </td>
                              <td className="py-3 px-3">
                                <div className="font-medium text-slate-800">{candidate.distanceKm} km</div>
                                <div className="text-[11px] text-slate-400">~{candidate.etaMinutes} mins ETA</div>
                              </td>
                              <td className="py-3 px-3">
                                <div className="flex items-center gap-2">
                                  <div className="w-16 bg-slate-100 rounded-full h-2 overflow-hidden">
                                    <div
                                      className={`h-full rounded-full ${
                                        candidate.reachabilityScore && candidate.reachabilityScore >= 80
                                          ? 'bg-emerald-500'
                                          : candidate.reachabilityScore && candidate.reachabilityScore >= 60
                                          ? 'bg-blue-500'
                                          : 'bg-amber-500'
                                      }`}
                                      style={{ width: `${candidate.reachabilityScore || 75}%` }}
                                    />
                                  </div>
                                  <span className="font-semibold text-xs text-slate-700">
                                    {candidate.reachabilityScore || Math.round(candidate.responseProbability * 100)}%
                                  </span>
                                </div>
                              </td>
                              <td className="py-3 px-3">
                                <StatusBadge status={candidate.status} size="sm" />
                              </td>
                              <td className="py-3 px-3 text-right">
                                <div className="flex items-center justify-end gap-1.5">
                                  {candidate.status === 'contacted' ? (
                                    <>
                                      <button
                                        onClick={() => handleSimulateResponse(candidate.id, 'accepted')}
                                        disabled={isSimulating}
                                        className="btn btn-secondary btn-sm text-[11px] text-emerald-700 hover:bg-emerald-50 border-emerald-200 px-2 py-1 flex items-center gap-1"
                                        title="Simulate Accept Response"
                                      >
                                        <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                                        Accept
                                      </button>
                                      <button
                                        onClick={() => handleSimulateResponse(candidate.id, 'declined')}
                                        disabled={isSimulating}
                                        className="btn btn-secondary btn-sm text-[11px] text-rose-700 hover:bg-rose-50 border-rose-200 px-2 py-1 flex items-center gap-1"
                                        title="Simulate Decline Response"
                                      >
                                        <XCircle className="w-3 h-3 text-rose-600" />
                                        Decline
                                      </button>
                                    </>
                                  ) : (
                                    <button
                                      onClick={() => handleContactDonor(candidate)}
                                      disabled={isContacting || candidate.status === 'accepted'}
                                      className="btn btn-primary btn-sm text-[11px] px-2.5 py-1 flex items-center gap-1"
                                    >
                                      <Send className="w-3 h-3" />
                                      {isContacting ? 'Sending...' : 'Contact'}
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
              <Droplet className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-bold text-slate-800">Select a Blood Request</h3>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                Choose an emergency from the left list to review real-time donor reachability, compatibility, and progressive outreach.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Create Blood Request Modal */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title="Initiate Blood Emergency Request"
        size="md"
      >
        <form onSubmit={handleCreateRequest} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Blood Group Required *</label>
              <select
                value={formBloodGroup}
                onChange={(e) => setFormBloodGroup(e.target.value)}
                className="input text-sm w-full font-bold"
                required
              >
                <option value="O+">O+ (Positive)</option>
                <option value="O-">O- (Universal RBC)</option>
                <option value="A+">A+ (Positive)</option>
                <option value="A-">A- (Negative)</option>
                <option value="B+">B+ (Positive)</option>
                <option value="B-">B- (Negative)</option>
                <option value="AB+">AB+ (Positive)</option>
                <option value="AB-">AB- (Negative)</option>
              </select>
            </div>
            <div>
              <label className="label">Units Required (Pints) *</label>
              <input
                type="number"
                min="1"
                max="20"
                value={formUnits}
                onChange={(e) => setFormUnits(Math.max(1, parseInt(e.target.value) || 1))}
                className="input text-sm w-full font-bold"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Urgency Priority *</label>
              <select
                value={formPriority}
                onChange={(e) => setFormPriority(e.target.value)}
                className="input text-sm w-full"
                required
              >
                <option value="critical">Critical (Immediate Life-Threat)</option>
                <option value="high">High (Surgery / Massive Bleed)</option>
                <option value="moderate">Moderate (Scheduled Transfusion)</option>
                <option value="low">Low (Standby / Routine)</option>
              </select>
            </div>
            <div>
              <label className="label">Receiving Hospital ID *</label>
              <input
                type="text"
                value={formHospitalId}
                onChange={(e) => setFormHospitalId(e.target.value)}
                className="input text-sm w-full"
                placeholder="e.g. hosp-001"
                required
              />
            </div>
          </div>

          <div>
            <label className="label">Clinical Notes / Indication</label>
            <textarea
              value={formNotes}
              onChange={(e) => setFormNotes(e.target.value)}
              placeholder="e.g. Trauma bay resuscitation, acute hemorrhage, crossmatch pending..."
              rows={3}
              className="input text-sm w-full"
            />
          </div>

          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800">
            <strong>Emergency Protocol:</strong> Submitting this request will automatically query the registered donor pool, initiate progressive geographic radius expansion, and queue outreach dispatches according to clinical RBAC policy.
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setIsCreateModalOpen(false)}
              className="btn btn-secondary text-xs"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={creatingRequest}
              className="btn btn-emergency text-xs font-semibold flex items-center gap-1.5"
            >
              <Droplet className="w-4 h-4" />
              {creatingRequest ? 'Dispatching...' : 'Create Blood SOS'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default BloodRequests;
