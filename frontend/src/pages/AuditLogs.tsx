import React, { useState, useEffect } from 'react';
import {
  Shield,
  CheckCircle2,
  XCircle,
  Search,
  Filter,
  Lock,
  Link as LinkIcon,
  RefreshCw,
  AlertCircle,
  Clock,
  Eye,
  FileCode,
  Fingerprint,
} from 'lucide-react';
import { auditApi } from '../api/services';
import { AuditLog, AuditVerificationResult } from '../types';
import StatusBadge from '../components/common/StatusBadge';
import EmptyState from '../components/common/EmptyState';
import Modal from '../components/common/Modal';

export const AuditLogs: React.FC = () => {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [filterModule, setFilterModule] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Cryptographic Verification State
  const [verifying, setVerifying] = useState<boolean>(false);
  const [verificationResult, setVerificationResult] = useState<AuditVerificationResult | null>(null);
  const [isVerifyModalOpen, setIsVerifyModalOpen] = useState<boolean>(false);

  // Selected Log Detail Modal
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  const fetchLogs = async () => {
    try {
      setLoading(true);
      setError(null);
      const params: any = {};
      if (filterModule !== 'all') params.module = filterModule;
      if (filterStatus !== 'all') params.status = filterStatus;
      if (searchQuery.trim()) params.search = searchQuery.trim();

      const data = await auditApi.getLogs(params);
      setLogs(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to retrieve immutable audit logs.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [filterModule, filterStatus]);

  const handleVerifyChain = async () => {
    try {
      setVerifying(true);
      const res = await auditApi.verifyChain();
      setVerificationResult(res);
      setIsVerifyModalOpen(true);
    } catch (err: any) {
      setVerificationResult({
        isValid: false,
        verifiedCount: 0,
        error: err?.message || 'Verification endpoint error.',
      });
      setIsVerifyModalOpen(true);
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-lg bg-indigo-100 text-indigo-700">
              <Shield className="w-5 h-5 text-indigo-600" />
            </span>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Tamper-Evident Audit Trail</h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Cryptographically sealed SHA-256 hash-chained log stream verifying system actions and clinical data integrity (SEC-10).
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchLogs()}
            className="btn btn-secondary flex items-center gap-2 text-xs"
            title="Refresh Audit Logs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={handleVerifyChain}
            disabled={verifying}
            className="btn btn-primary flex items-center gap-2 text-xs font-semibold shadow-xs"
          >
            <Lock className={`w-3.5 h-3.5 ${verifying ? 'animate-spin' : ''}`} />
            {verifying ? 'Verifying Chain...' : 'Verify Hash Chain'}
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search actor, action, resource, hash..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && fetchLogs()}
            className="input input-sm pl-9 text-xs w-full"
          />
        </div>

        <div className="flex items-center gap-2 w-full md:w-auto">
          <select
            value={filterModule}
            onChange={(e) => setFilterModule(e.target.value)}
            className="input input-sm text-xs bg-slate-50"
          >
            <option value="all">All Modules</option>
            <option value="blood">Blood Management</option>
            <option value="organ">Organ Coordination</option>
            <option value="ambulance">Ambulance Fleet</option>
            <option value="system">System / Database</option>
            <option value="auth">Authentication & RBAC</option>
          </select>

          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="input input-sm text-xs bg-slate-50"
          >
            <option value="all">All Statuses</option>
            <option value="success">Success</option>
            <option value="failed">Failed</option>
            <option value="pending">Pending</option>
          </select>
        </div>
      </div>

      {/* Audit Log Table */}
      {loading ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200">
          <RefreshCw className="w-6 h-6 animate-spin text-emerald-600 mx-auto mb-2" />
          <p className="text-xs text-slate-500 font-medium">Loading immutable audit stream...</p>
        </div>
      ) : error ? (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : logs.length === 0 ? (
        <EmptyState
          title="No Audit Records Found"
          description="No audit logs match your search or filter parameters."
        />
      ) : (
        <div className="overflow-x-auto border border-slate-200 rounded-xl bg-white shadow-xs">
          <table className="table-clinical w-full text-left text-xs">
            <thead>
              <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                <th className="py-3 px-4 font-semibold">Timestamp</th>
                <th className="py-3 px-4 font-semibold">Actor & Role</th>
                <th className="py-3 px-4 font-semibold">Action</th>
                <th className="py-3 px-4 font-semibold">Module & Target</th>
                <th className="py-3 px-4 font-semibold">Status</th>
                <th className="py-3 px-4 font-semibold">Cryptographic Hash</th>
                <th className="py-3 px-4 font-semibold text-right">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-slate-50/70 transition-colors">
                  <td className="py-3 px-4 whitespace-nowrap">
                    <div className="font-semibold text-slate-900">
                      {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </div>
                    <div className="text-[11px] text-slate-400">
                      {new Date(log.timestamp).toLocaleDateString()}
                    </div>
                  </td>

                  <td className="py-3 px-4">
                    <span className="font-bold text-slate-900 block">{log.actor}</span>
                    <span className="text-[10px] uppercase font-semibold text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">
                      {log.actorType}
                    </span>
                  </td>

                  <td className="py-3 px-4">
                    <span className="font-semibold text-slate-800 block">{log.action}</span>
                    <span className="text-[11px] text-slate-400 font-mono">ID: #{log.id.slice(0, 8)}</span>
                  </td>

                  <td className="py-3 px-4">
                    <span className="badge badge-neutral text-[10px] font-bold uppercase">{log.module}</span>
                    <span className="text-slate-600 text-xs block mt-0.5 truncate max-w-xs">{log.resource}</span>
                  </td>

                  <td className="py-3 px-4">
                    <StatusBadge status={log.status} size="sm" />
                  </td>

                  <td className="py-3 px-4">
                    <div className="flex items-center gap-1.5 font-mono text-[11px] text-slate-600 bg-slate-50 px-2 py-1 rounded border border-slate-200 w-fit">
                      <Fingerprint className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                      <span>{log.recordHash ? `${log.recordHash.slice(0, 10)}...` : 'Unsealed'}</span>
                    </div>
                  </td>

                  <td className="py-3 px-4 text-right">
                    <button
                      onClick={() => setSelectedLog(log)}
                      className="btn btn-secondary btn-sm text-[11px] px-2 py-1 text-slate-700"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      Inspect
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Hash Chain Verification Modal */}
      <Modal
        isOpen={isVerifyModalOpen}
        onClose={() => setIsVerifyModalOpen(false)}
        title="Audit Trail Cryptographic Integrity Seal"
        size="md"
      >
        {verificationResult && (
          <div className="space-y-4">
            <div
              className={`p-5 rounded-2xl border text-center ${
                verificationResult.isValid
                  ? 'bg-emerald-50 border-emerald-300 text-emerald-900'
                  : 'bg-rose-50 border-rose-300 text-rose-900'
              }`}
            >
              <div className="w-12 h-12 rounded-full mx-auto flex items-center justify-center mb-3">
                {verificationResult.isValid ? (
                  <CheckCircle2 className="w-12 h-12 text-emerald-600" />
                ) : (
                  <XCircle className="w-12 h-12 text-rose-600" />
                )}
              </div>
              <h3 className="text-lg font-bold">
                {verificationResult.isValid
                  ? 'Hash Chain Sealed & Continuous'
                  : 'Hash Chain Broken / Tamper Detected'}
              </h3>
              <p className="text-xs mt-1 text-slate-600 max-w-sm mx-auto">
                {verificationResult.isValid
                  ? `Successfully validated continuity across ${verificationResult.verifiedCount} consecutive records. No record modifications, insertions, or unauthorized deletions detected.`
                  : `Tampering detected at record ID: ${verificationResult.tamperedId || 'Unknown'}. Continuity compromised.`}
              </p>
            </div>

            <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Records Verified:</span>
                <span className="font-bold text-slate-900">{verificationResult.verifiedCount} entries</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Hash Algorithm:</span>
                <span className="font-mono text-slate-800">SHA-256 Chained</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Compliance Standard:</span>
                <span className="font-semibold text-emerald-700">LifeLink SEC-10 / HIPAA Audit</span>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setIsVerifyModalOpen(false)}
                className="btn btn-secondary text-xs"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* Selected Log Record Modal */}
      {selectedLog && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedLog(null)}
          title={`Audit Record: #${selectedLog.id}`}
          size="lg"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3 p-4 bg-slate-50 rounded-xl border border-slate-200">
              <div>
                <span className="text-slate-400 block text-[11px]">Actor Identity</span>
                <p className="font-bold text-slate-900 mt-0.5">{selectedLog.actor} ({selectedLog.actorType})</p>
                <span className="text-slate-500 text-[11px]">IP: {selectedLog.ipAddress || '127.0.0.1'}</span>
              </div>

              <div>
                <span className="text-slate-400 block text-[11px]">Action Executed</span>
                <p className="font-bold text-slate-900 mt-0.5">{selectedLog.action}</p>
                <span className="text-slate-500 text-[11px]">Module: {selectedLog.module}</span>
              </div>
            </div>

            <div className="space-y-2">
              <span className="text-slate-400 font-semibold block">Cryptographic Hash Signatures</span>
              <div className="p-3 bg-slate-900 text-slate-200 rounded-xl font-mono text-[11px] space-y-1.5 overflow-x-auto">
                <div>
                  <span className="text-emerald-400">Previous Record Hash:</span>{' '}
                  {selectedLog.previousHash || 'GENESIS_BLOCK_0000000000000000'}
                </div>
                <div>
                  <span className="text-indigo-400">Current Record Hash:&nbsp;</span>{' '}
                  {selectedLog.recordHash || 'N/A'}
                </div>
              </div>
            </div>

            {selectedLog.metadata && (
              <div className="space-y-2">
                <span className="text-slate-400 font-semibold block">Context Metadata Payload</span>
                <pre className="p-3 bg-slate-100 rounded-xl font-mono text-[11px] overflow-x-auto">
                  {JSON.stringify(selectedLog.metadata, null, 2)}
                </pre>
              </div>
            )}

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedLog(null)}
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

export default AuditLogs;
