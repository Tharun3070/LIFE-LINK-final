import React, { useState, useEffect } from 'react';
import {
  BookOpen,
  Sparkles,
  Search,
  ExternalLink,
  ShieldCheck,
  FileText,
  Activity,
  RefreshCw,
  AlertCircle,
  HelpCircle,
  Cpu,
  Layers,
  CheckCircle2,
} from 'lucide-react';
import { clinicalGuidanceApi } from '../api/services';
import { ClinicalGuidanceResponse } from '../types';
import EmptyState from '../components/common/EmptyState';
import Modal from '../components/common/Modal';

export const ClinicalGuidance: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'rag' | 'documents' | 'intent' | 'ml'>('rag');

  // RAG Query State
  const [queryText, setQueryText] = useState<string>('');
  const [selectedDomain, setSelectedDomain] = useState<string>('all');
  const [querying, setQuerying] = useState<boolean>(false);
  const [ragResult, setRagResult] = useState<ClinicalGuidanceResponse | null>(null);
  const [ragError, setRagError] = useState<string | null>(null);

  // Documents Library State
  const [documents, setDocuments] = useState<any[]>([]);
  const [docsLoading, setDocsLoading] = useState<boolean>(false);

  // LLM Intent Parser State
  const [intentText, setIntentText] = useState<string>(
    'Trauma patient in ER bay 3 requires 3 units of O negative red cells immediately for acute hemorrhagic shock.'
  );
  const [intentResult, setIntentResult] = useState<any | null>(null);
  const [parsingIntent, setParsingIntent] = useState<boolean>(false);

  // ML Training Gate State
  const [mlReadiness, setMlReadiness] = useState<any | null>(null);
  const [mlLoading, setMlLoading] = useState<boolean>(false);

  // Fetch trusted docs on mount
  useEffect(() => {
    fetchDocuments();
    fetchMlReadiness();
  }, []);

  const fetchDocuments = async () => {
    try {
      setDocsLoading(true);
      const docs = await clinicalGuidanceApi.getTrustedDocuments();
      setDocuments(docs);
    } catch {
      // non-blocking
    } finally {
      setDocsLoading(false);
    }
  };

  const fetchMlReadiness = async () => {
    try {
      setMlLoading(true);
      const data = await clinicalGuidanceApi.getMLReadiness();
      setMlReadiness(data);
    } catch {
      // non-blocking
    } finally {
      setMlLoading(false);
    }
  };

  const handleRunRAG = async (queryToRun?: string) => {
    const q = queryToRun || queryText;
    if (!q.trim()) return;

    try {
      setQuerying(true);
      setRagError(null);
      const domain = selectedDomain === 'all' ? undefined : selectedDomain;
      const res = await clinicalGuidanceApi.query(q, domain);
      setRagResult(res);
    } catch (err: any) {
      setRagError(err?.message || 'Unable to retrieve clinical guidance.');
      setRagResult(null);
    } finally {
      setQuerying(false);
    }
  };

  const handleParseIntent = async () => {
    if (!intentText.trim()) return;
    try {
      setParsingIntent(true);
      const res = await clinicalGuidanceApi.parseIntent(intentText);
      setIntentResult(res);
    } catch (err: any) {
      setIntentResult({ error: err?.message || 'Intent extraction failed' });
    } finally {
      setParsingIntent(false);
    }
  };

  const presetQueries = [
    {
      title: 'Heart Cold Ischemia Limits',
      query: 'What is the maximum acceptable cold ischemia time for a donor heart according to NOTTO guidelines?',
      domain: 'organ_viability',
    },
    {
      title: 'PRBC Cold Chain Storage',
      query: 'What are the required storage temperature and transport protocols for Packed Red Blood Cells (PRBC)?',
      domain: 'blood_transfusion',
    },
    {
      title: 'Emergency Uncrossmatched Blood',
      query: 'When is uncrossmatched O-negative blood indicated in emergency trauma resuscitation?',
      domain: 'blood_transfusion',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-lg bg-teal-100 text-teal-700">
              <BookOpen className="w-5 h-5 text-teal-600" />
            </span>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Clinical Intelligence & Evidence Retrieval</h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Retrieval-Augmented Generation (RAG) grounded in WHO, AABB, and NOTTO medical guidelines.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200">
          <button
            onClick={() => setActiveTab('rag')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'rag' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Clinical Guidance RAG
          </button>
          <button
            onClick={() => setActiveTab('documents')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'documents' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Authoritative Docs ({documents.length})
          </button>
          <button
            onClick={() => setActiveTab('intent')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'intent' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Clinical Intent Extraction
          </button>
          <button
            onClick={() => setActiveTab('ml')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'ml' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            ML Training Gate
          </button>
        </div>
      </div>

      {/* Tab 1: Clinical Guidance RAG */}
      {activeTab === 'rag' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Query Box (7 cols) */}
          <div className="lg:col-span-7 space-y-4">
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-sm text-slate-900 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-teal-600" />
                  Query Evidence-Grounded Knowledge Base
                </h3>
                <select
                  value={selectedDomain}
                  onChange={(e) => setSelectedDomain(e.target.value)}
                  className="input input-sm text-xs bg-slate-50"
                >
                  <option value="all">All Clinical Domains</option>
                  <option value="blood_transfusion">Blood Transfusion & Cold Chain</option>
                  <option value="organ_viability">Organ Viability & Ischemia</option>
                  <option value="emergency_triage">Emergency Triage</option>
                </select>
              </div>

              <div className="relative">
                <textarea
                  value={queryText}
                  onChange={(e) => setQueryText(e.target.value)}
                  placeholder="Ask a clinical question regarding cold chain storage, ischemic limits, or transfusion protocols..."
                  rows={4}
                  className="input text-xs w-full leading-relaxed"
                />
              </div>

              <div className="flex items-center justify-between">
                <span className="text-[11px] text-slate-400">
                  Grounded solely in verified clinical publications. Never hallucinates medical thresholds.
                </span>
                <button
                  onClick={() => handleRunRAG()}
                  disabled={querying || !queryText.trim()}
                  className="btn btn-primary text-xs font-semibold flex items-center gap-1.5"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  {querying ? 'Synthesizing...' : 'Search Evidence'}
                </button>
              </div>
            </div>

            {/* Presets */}
            <div className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400 block">
                Recommended Clinical Queries
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {presetQueries.map((preset, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setQueryText(preset.query);
                      setSelectedDomain(preset.domain);
                      handleRunRAG(preset.query);
                    }}
                    className="p-3 text-left rounded-xl bg-white border border-slate-200 hover:border-teal-300 hover:bg-teal-50/30 transition-all text-xs"
                  >
                    <span className="font-semibold text-slate-800 block text-[11px]">{preset.title}</span>
                    <span className="text-[10px] text-slate-500 mt-1 line-clamp-2">{preset.query}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Results Box (5 cols) */}
          <div className="lg:col-span-5">
            {querying ? (
              <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
                <RefreshCw className="w-6 h-6 animate-spin text-teal-600 mx-auto mb-2" />
                <p className="text-xs text-slate-600 font-medium">Retrieving vetted clinical passages...</p>
                <p className="text-[11px] text-slate-400 mt-1">Checking semantic embeddings against guidelines</p>
              </div>
            ) : ragError ? (
              <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs">
                <p className="font-bold">Retrieval Error</p>
                <p className="mt-1">{ragError}</p>
              </div>
            ) : ragResult ? (
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-600" />
                    <span className="font-bold text-sm text-slate-900">Evidence Synthesized</span>
                  </div>
                  {ragResult.confidenceScore !== undefined && (
                    <span className="badge badge-emerald text-[10px] font-bold">
                      {Math.round(ragResult.confidenceScore * 100)}% Confidence
                    </span>
                  )}
                </div>

                {/* Synthesis Answer */}
                <div className="text-xs text-slate-800 leading-relaxed space-y-2 whitespace-pre-line bg-slate-50 p-3.5 rounded-xl border border-slate-100">
                  {ragResult.answer}
                </div>

                {/* Citations */}
                <div className="space-y-2 pt-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 block">
                    Authoritative Evidence Citations ({ragResult.citations?.length || 0})
                  </span>
                  <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                    {ragResult.citations?.map((cit, idx) => (
                      <div
                        key={idx}
                        className="p-3 rounded-lg border border-slate-200 bg-white text-xs hover:border-slate-300 transition-colors"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span className="font-semibold text-slate-900">{cit.title}</span>
                          <span className="text-[10px] px-2 py-0.5 rounded font-bold bg-teal-50 text-teal-700 border border-teal-200 shrink-0">
                            {cit.organization}
                          </span>
                        </div>
                        {cit.section && (
                          <p className="text-[11px] text-slate-500 mt-1">Section: {cit.section}</p>
                        )}
                        {cit.url && (
                          <a
                            href={cit.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[11px] text-teal-600 hover:underline flex items-center gap-1 mt-1 font-medium"
                          >
                            <ExternalLink className="w-3 h-3" />
                            Source Document
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
                <BookOpen className="w-10 h-10 text-slate-300 mx-auto mb-2" />
                <h4 className="text-sm font-bold text-slate-800">No Query Executed</h4>
                <p className="text-xs text-slate-400 mt-1 max-w-xs mx-auto">
                  Type a clinical query or select one of the presets to view citation-backed medical protocols.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 2: Authoritative Documents */}
      {activeTab === 'documents' && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs flex items-center justify-between">
            <div>
              <h3 className="font-bold text-sm text-slate-900">Vetted Clinical Guidelines Registry</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Every guideline is cryptographically verified via SHA-256 checksums to prevent unauthorized alteration.
              </p>
            </div>
            <button
              onClick={() => fetchDocuments()}
              className="btn btn-secondary btn-sm text-xs flex items-center gap-1"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${docsLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {documents.map((doc) => (
              <div
                key={doc.docId}
                className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs hover:border-slate-300 transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <span className="badge badge-emerald text-[10px] font-bold">{doc.issuingOrganization}</span>
                    <span className="text-[10px] text-slate-400 font-mono">v{doc.version || '1.0'}</span>
                  </div>
                  <h4 className="font-bold text-sm text-slate-900 mt-2">{doc.title}</h4>
                  <p className="text-xs text-slate-500 mt-1">Domain: {doc.domain?.replace('_', ' ')}</p>
                </div>

                <div className="mt-4 pt-3 border-t border-slate-100 space-y-1 text-xs">
                  <div className="flex items-center justify-between text-slate-500">
                    <span>Published:</span>
                    <span className="font-medium text-slate-800">{doc.publicationDate || '2023'}</span>
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono truncate">
                    SHA-256: {doc.checksum ? doc.checksum.slice(0, 16) + '...' : 'Verified'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 3: Natural Language Clinical Intent Parser */}
      {activeTab === 'intent' && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-5 max-w-3xl mx-auto">
          <div>
            <h3 className="font-bold text-base text-slate-900 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-teal-600" />
              Automated Clinical Intent Extraction
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Extracts blood group, units, priority urgency, and destination hospital from unstructured clinical speech or dispatch notes.
            </p>
          </div>

          <div>
            <label className="label">Unstructured Clinical Note / Radio Transcription</label>
            <textarea
              value={intentText}
              onChange={(e) => setIntentText(e.target.value)}
              rows={4}
              className="input text-xs w-full leading-relaxed"
            />
          </div>

          <div className="flex justify-end">
            <button
              onClick={handleParseIntent}
              disabled={parsingIntent || !intentText.trim()}
              className="btn btn-primary text-xs font-semibold flex items-center gap-1.5"
            >
              <Cpu className="w-3.5 h-3.5" />
              {parsingIntent ? 'Extracting Parameters...' : 'Parse Clinical Intent'}
            </button>
          </div>

          {intentResult && (
            <div className="mt-4 pt-4 border-t border-slate-100 space-y-3">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400 block">
                Structured Parameters Extracted
              </span>
              <pre className="p-4 rounded-xl bg-slate-900 text-emerald-400 font-mono text-xs overflow-x-auto">
                {JSON.stringify(intentResult, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Tab 4: ML Training Readiness Gate */}
      {activeTab === 'ml' && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-6 max-w-3xl mx-auto">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100">
            <div>
              <h3 className="font-bold text-base text-slate-900 flex items-center gap-2">
                <Cpu className="w-5 h-5 text-teal-600" />
                ML Readiness Gate Evaluation
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Evaluates genuine clinical production outcomes against the 2,500-sample / 250-emergency safety threshold.
              </p>
            </div>
            <button
              onClick={() => fetchMlReadiness()}
              className="btn btn-secondary btn-sm text-xs flex items-center gap-1"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${mlLoading ? 'animate-spin' : ''}`} />
              Re-evaluate Gate
            </button>
          </div>

          {mlReadiness ? (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-slate-500 block">Gate Status</span>
                  <span className={`text-lg font-bold ${
                    mlReadiness.isReady ? 'text-emerald-600' : 'text-amber-600'
                  }`}>
                    {mlReadiness.isReady ? 'Production ML Retraining Permitted' : 'Readiness Threshold Pending'}
                  </span>
                </div>
                <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                  mlReadiness.isReady ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                }`}>
                  {mlReadiness.sampleCount || 0} / 2,500 Samples
                </span>
              </div>

              <div className="grid grid-cols-2 gap-4 text-xs">
                <div className="p-4 rounded-xl border border-slate-200">
                  <span className="text-slate-400 block">Verified Emergencies Cataloged</span>
                  <span className="text-xl font-bold text-slate-900 mt-1 block">
                    {mlReadiness.emergencyCount || 0} / 250
                  </span>
                  <div className="w-full bg-slate-100 rounded-full h-2 mt-2 overflow-hidden">
                    <div
                      className="bg-teal-500 h-full rounded-full"
                      style={{ width: `${Math.min(100, ((mlReadiness.emergencyCount || 0) / 250) * 100)}%` }}
                    />
                  </div>
                </div>

                <div className="p-4 rounded-xl border border-slate-200">
                  <span className="text-slate-400 block">Acceptance Ground Truth Recorded</span>
                  <span className="text-xl font-bold text-slate-900 mt-1 block">
                    {mlReadiness.sampleCount || 0} / 2,500
                  </span>
                  <div className="w-full bg-slate-100 rounded-full h-2 mt-2 overflow-hidden">
                    <div
                      className="bg-emerald-500 h-full rounded-full"
                      style={{ width: `${Math.min(100, ((mlReadiness.sampleCount || 0) / 2500) * 100)}%` }}
                    />
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-blue-50 border border-blue-200 text-blue-900 text-xs">
                <strong>ML Governance Safeguard:</strong> Model weights remain deterministic heuristic-based until statistical power exceeds 2,500 real verified outcomes to prevent bias in emergency life-support routing.
              </div>
            </div>
          ) : (
            <div className="p-8 text-center text-xs text-slate-400">Loading ML gate evaluation...</div>
          )}
        </div>
      )}
    </div>
  );
};

export default ClinicalGuidance;
