import React, { useState, useEffect } from 'react';
import {
  Heart,
  Activity,
  Clock,
  ShieldAlert,
  Search,
  Filter,
  CheckCircle2,
  XCircle,
  Building2,
  MapPin,
  RefreshCw,
  AlertCircle,
  Sparkles,
  UserCheck,
  TrendingUp,
} from 'lucide-react';
import { organApi } from '../api/services';
import { Organ } from '../types';
import { useAuth } from '../context/AuthContext';
import { useRealtime } from '../context/RealtimeContext';
import StatusBadge from '../components/common/StatusBadge';
import EmptyState from '../components/common/EmptyState';
import Modal from '../components/common/Modal';

export const OrganCoordination: React.FC = () => {
  const { user, isDoctor, isStaff, isAdmin } = useAuth();
  const { addToast } = useRealtime();

  const [organs, setOrgans] = useState<Organ[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState<string>('');
  const [filterType, setFilterType] = useState<string>('all');
  const [filterViability, setFilterViability] = useState<string>('all');

  // Clinical Review Modal
  const [reviewingOrgan, setReviewingOrgan] = useState<Organ | null>(null);
  const [reviewDecision, setReviewDecision] = useState<'approved' | 'rejected'>('approved');
  const [reviewNotes, setReviewNotes] = useState<string>('');
  const [submittingReview, setSubmittingReview] = useState<boolean>(false);

  // Create Organ Request Modal
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [formOrganType, setFormOrganType] = useState<string>('Kidney');
  const [formPriority, setFormPriority] = useState<string>('critical');
  const [formHospitalId, setFormHospitalId] = useState<string>(user?.hospitalId || 'hosp-001');
  const [formNotes, setFormNotes] = useState<string>('');
  const [creatingRequest, setCreatingRequest] = useState<boolean>(false);

  const fetchOrgans = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await organApi.getOrgans();
      setOrgans(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to retrieve organ coordination catalog.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrgans();
  }, []);

  // Format remaining seconds into HH:MM:SS
  const formatTime = (seconds: number) => {
    if (seconds <= 0) return '00:00:00';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Submit Clinical Review Decision
  const handleSubmitReview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reviewingOrgan) return;

    try {
      setSubmittingReview(true);
      await organApi.submitClinicalReview(reviewingOrgan.id, {
        decision: reviewDecision,
        notes: reviewNotes || undefined,
      });

      addToast({
        title: `Clinical Review ${reviewDecision === 'approved' ? 'Approved' : 'Rejected'}`,
        message: `Organ ${reviewingOrgan.organType} allocation decision recorded by ${user?.name}.`,
        type: reviewDecision === 'approved' ? 'success' : 'warning',
      });

      setReviewingOrgan(null);
      setReviewNotes('');
      await fetchOrgans();
    } catch (err: any) {
      addToast({
        title: 'Review Submission Failed',
        message: err?.message || 'Could not record clinical review.',
        type: 'error',
      });
    } finally {
      setSubmittingReview(false);
    }
  };

  // Create Organ Request Submission
  const handleCreateRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setCreatingRequest(true);
      await organApi.createOrganRequest({
        organType: formOrganType,
        priority: formPriority,
        hospitalId: formHospitalId,
        notes: formNotes || undefined,
      });

      addToast({
        title: 'Organ Search Alert Created',
        message: `Alert broadcast for ${formOrganType}. Evaluating regional donor network.`,
        type: 'emergency',
      });

      setIsCreateModalOpen(false);
      setFormNotes('');
      await fetchOrgans();
    } catch (err: any) {
      addToast({
        title: 'Request Failed',
        message: err?.message || 'Unable to submit organ alert.',
        type: 'error',
      });
    } finally {
      setCreatingRequest(false);
    }
  };

  const filteredOrgans = organs.filter((organ) => {
    const matchesSearch =
      organ.organType.toLowerCase().includes(searchQuery.toLowerCase()) ||
      organ.sourceHospitalName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      organ.donorBloodGroup?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = filterType === 'all' || organ.organType.toLowerCase() === filterType.toLowerCase();
    const matchesViability = filterViability === 'all' || organ.viabilityLevel === filterViability;
    return matchesSearch && matchesType && matchesViability;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-lg bg-rose-100 text-rose-700">
              <Heart className="w-5 h-5 text-rose-600" />
            </span>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Organ Viability & Allocation Intelligence</h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Real-time cold ischemia time (CIT) countdown tickers, AI reachability assessment, and mandatory human clinical review.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchOrgans()}
            className="btn btn-secondary flex items-center gap-2 text-xs"
            title="Refresh Organ Catalog"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          {(isDoctor || isStaff || isAdmin) && (
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="btn btn-emergency flex items-center gap-2 text-xs font-semibold"
            >
              <Heart className="w-4 h-4" />
              Broadcast Organ Alert
            </button>
          )}
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search organ, source hospital, ABO/Rh..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input input-sm pl-9 text-xs w-full"
          />
        </div>

        <div className="flex items-center gap-2 w-full md:w-auto">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="input input-sm text-xs bg-slate-50"
          >
            <option value="all">All Organ Types</option>
            <option value="heart">Heart (CIT: 4-6 hrs)</option>
            <option value="liver">Liver (CIT: 8-12 hrs)</option>
            <option value="kidney">Kidney (CIT: 24-36 hrs)</option>
            <option value="lung">Lung (CIT: 6-8 hrs)</option>
            <option value="pancreas">Pancreas (CIT: 12-18 hrs)</option>
          </select>

          <select
            value={filterViability}
            onChange={(e) => setFilterViability(e.target.value)}
            className="input input-sm text-xs bg-slate-50"
          >
            <option value="all">All Viability Levels</option>
            <option value="normal">Normal (Stable CIT)</option>
            <option value="warning">Warning (Half Life Exceeded)</option>
            <option value="critical">Critical (&lt; 2 hrs Remaining)</option>
            <option value="expired">Expired</option>
          </select>
        </div>
      </div>

      {/* Organs Grid */}
      {loading ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200">
          <RefreshCw className="w-6 h-6 animate-spin text-emerald-600 mx-auto mb-2" />
          <p className="text-xs text-slate-500 font-medium">Tracking cold ischemia clocks...</p>
        </div>
      ) : error ? (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : filteredOrgans.length === 0 ? (
        <EmptyState
          title="No Organs in Active Transit or Search"
          description="There are currently no active organ donations in transit matching your filters."
          actionLabel="Broadcast Alert"
          onAction={() => setIsCreateModalOpen(true)}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {filteredOrgans.map((organ) => {
            const viabilityPct = Math.max(
              0,
              Math.min(
                100,
                Math.round(
                  (organ.viabilityRemainingSeconds / (organ.viabilityTotalSeconds || 14400)) * 100
                )
              )
            );

            const isApproved = organ.clinicalReviewStatus === 'approved';
            const isPendingReview = organ.clinicalReviewStatus === 'pending';

            return (
              <div
                key={organ.id}
                className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs hover:border-slate-300 transition-all flex flex-col justify-between"
              >
                <div className="space-y-4">
                  {/* Top Bar: Organ Type & Status */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center font-bold shrink-0 border border-rose-200">
                        <Heart className="w-6 h-6" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-lg font-bold text-slate-900">{organ.organType}</h3>
                          {organ.donorBloodGroup && (
                            <span className="badge badge-emergency text-[10px] font-bold">
                              {organ.donorBloodGroup}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-500 mt-0.5">
                          Donor Age: <strong>{organ.donorAge || '34'} yrs</strong> • ID: #{organ.id.slice(0, 8)}
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-col items-end gap-1">
                      <StatusBadge status={organ.status} size="sm" />
                      <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded ${
                        isApproved
                          ? 'bg-emerald-100 text-emerald-800'
                          : isPendingReview
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-rose-100 text-rose-800'
                      }`}>
                        Review: {organ.clinicalReviewStatus}
                      </span>
                    </div>
                  </div>

                  {/* Cold Ischemia Countdown Meter */}
                  <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                        <Clock className={`w-4 h-4 ${
                          organ.viabilityLevel === 'critical' ? 'text-red-600 animate-pulse' : 'text-slate-500'
                        }`} />
                        <span>Cold Ischemia Time (CIT) Clock</span>
                      </div>
                      <span className={`font-mono font-bold text-sm ${
                        organ.viabilityLevel === 'critical'
                          ? 'text-red-600'
                          : organ.viabilityLevel === 'warning'
                          ? 'text-amber-600'
                          : 'text-emerald-700'
                      }`}>
                        {formatTime(organ.viabilityRemainingSeconds)}
                      </span>
                    </div>

                    <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          organ.viabilityLevel === 'critical'
                            ? 'bg-red-600'
                            : organ.viabilityLevel === 'warning'
                            ? 'bg-amber-500'
                            : 'bg-emerald-500'
                        }`}
                        style={{ width: `${viabilityPct}%` }}
                      />
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
                      <span>Viability Health: {viabilityPct}%</span>
                      <StatusBadge status={organ.viabilityLevel} size="sm" />
                    </div>
                  </div>

                  {/* Logistics: Source -> Target & Reachability */}
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div className="p-3 rounded-lg border border-slate-200">
                      <span className="text-slate-400 block text-[11px]">Source Hospital</span>
                      <p className="font-semibold text-slate-800 mt-1 flex items-center gap-1">
                        <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="truncate">{organ.sourceHospitalName}</span>
                      </p>
                      <span className="text-[11px] text-slate-400">Distance: {organ.distanceKm} km</span>
                    </div>

                    <div className="p-3 rounded-lg border border-slate-200">
                      <span className="text-slate-400 block text-[11px]">AI Reachability Score</span>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-base font-bold text-slate-900">{organ.reachabilityScore}%</span>
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                          organ.aiRecommendation === 'proceed'
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-amber-100 text-amber-800'
                        }`}>
                          {organ.aiRecommendation}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-400">ETA: ~{organ.etaMinutes} mins</span>
                    </div>
                  </div>

                  {/* AI Clinical Rationale */}
                  {organ.aiRationale && (
                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-600 flex items-start gap-2">
                      <Sparkles className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                      <div>
                        <strong className="text-slate-800">AI Viability Assessment:</strong> {organ.aiRationale}
                      </div>
                    </div>
                  )}
                </div>

                {/* Footer Actions */}
                <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between gap-3">
                  <div className="text-[11px] text-slate-400">
                    {organ.clinicalReviewNotes && (
                      <span className="truncate max-w-xs block">
                        Note: "{organ.clinicalReviewNotes}"
                      </span>
                    )}
                  </div>

                  {(isDoctor || isStaff || isAdmin) && (
                    <button
                      onClick={() => {
                        setReviewingOrgan(organ);
                        setReviewDecision('approved');
                        setReviewNotes(organ.clinicalReviewNotes || '');
                      }}
                      className="btn btn-primary btn-sm text-xs flex items-center gap-1.5"
                    >
                      <UserCheck className="w-3.5 h-3.5" />
                      {isPendingReview ? 'Conduct Clinical Review' : 'Modify Review'}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Clinical Review Decision Modal */}
      {reviewingOrgan && (
        <Modal
          isOpen={true}
          onClose={() => setReviewingOrgan(null)}
          title={`Clinical Review: ${reviewingOrgan.organType} Allocation`}
          size="md"
        >
          <form onSubmit={handleSubmitReview} className="space-y-4">
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0" />
              <span>
                <strong>Mandatory Verification:</strong> Human clinician sign-off is legally required before initiating organ transport.
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs p-3 bg-slate-50 rounded-lg border border-slate-200">
              <div>
                <span className="text-slate-400 block">Organ & Group</span>
                <span className="font-bold text-slate-800">{reviewingOrgan.organType} ({reviewingOrgan.donorBloodGroup || 'N/A'})</span>
              </div>
              <div>
                <span className="text-slate-400 block">Remaining CIT</span>
                <span className="font-bold text-emerald-600">{formatTime(reviewingOrgan.viabilityRemainingSeconds)}</span>
              </div>
            </div>

            <div>
              <label className="label">Clinical Decision *</label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setReviewDecision('approved')}
                  className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
                    reviewDecision === 'approved'
                      ? 'bg-emerald-50 border-emerald-500 text-emerald-800 ring-2 ring-emerald-400'
                      : 'bg-white border-slate-200 text-slate-700'
                  }`}
                >
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  Approve Allocation
                </button>
                <button
                  type="button"
                  onClick={() => setReviewDecision('rejected')}
                  className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
                    reviewDecision === 'rejected'
                      ? 'bg-rose-50 border-rose-500 text-rose-800 ring-2 ring-rose-400'
                      : 'bg-white border-slate-200 text-slate-700'
                  }`}
                >
                  <XCircle className="w-4 h-4 text-rose-600" />
                  Reject Allocation
                </button>
              </div>
            </div>

            <div>
              <label className="label">Clinician Rationale / Crossmatch Notes</label>
              <textarea
                value={reviewNotes}
                onChange={(e) => setReviewNotes(e.target.value)}
                placeholder="e.g. HLA crossmatch negative, ischemia within safety thresholds, recipient prep ongoing..."
                rows={3}
                className="input text-xs w-full"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setReviewingOrgan(null)}
                className="btn btn-secondary text-xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submittingReview}
                className="btn btn-primary text-xs font-semibold"
              >
                {submittingReview ? 'Recording...' : 'Submit Decision'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Create Organ Alert Modal */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title="Broadcast Organ Alert Search"
        size="md"
      >
        <form onSubmit={handleCreateRequest} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Organ Required *</label>
              <select
                value={formOrganType}
                onChange={(e) => setFormOrganType(e.target.value)}
                className="input text-sm w-full font-bold"
                required
              >
                <option value="Kidney">Kidney (Renal)</option>
                <option value="Liver">Liver (Hepatic)</option>
                <option value="Heart">Heart (Cardiac)</option>
                <option value="Lung">Lung (Pulmonary)</option>
                <option value="Pancreas">Pancreas</option>
                <option value="Cornea">Cornea (Ocular)</option>
              </select>
            </div>

            <div>
              <label className="label">Priority Level *</label>
              <select
                value={formPriority}
                onChange={(e) => setFormPriority(e.target.value)}
                className="input text-sm w-full"
                required
              >
                <option value="critical">Status 1A (Urgent Life-Threat)</option>
                <option value="high">Status 1B (High Urgency)</option>
                <option value="moderate">Status 2 (Standard Allocation)</option>
              </select>
            </div>
          </div>

          <div>
            <label className="label">Receiving Hospital ID *</label>
            <input
              type="text"
              value={formHospitalId}
              onChange={(e) => setFormHospitalId(e.target.value)}
              className="input text-sm w-full"
              required
            />
          </div>

          <div>
            <label className="label">Recipient Clinical Notes</label>
            <textarea
              value={formNotes}
              onChange={(e) => setFormNotes(e.target.value)}
              placeholder="e.g. End-stage hepatic failure, blood type A+, ready in OT 4..."
              rows={3}
              className="input text-sm w-full"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
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
              className="btn btn-emergency text-xs font-semibold"
            >
              {creatingRequest ? 'Broadcasting...' : 'Broadcast Alert'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default OrganCoordination;
