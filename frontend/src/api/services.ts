// LifeLink Modular API Domain Services
import { api } from './client';
import {
  UserProfile,
  LoginResponse,
  Emergency,
  EmergencyEvent,
  KPIData,
  Donor,
  RankedDonorsResponse,
  Hospital,
  BloodBank,
  BloodInventoryItem,
  Ambulance,
  RouteOption,
  Organ,
  AuditLog,
  AuditVerificationResult,
  ConsentSettings,
  ClinicalGuidanceResponse,
} from '../types';

// ==========================================
// 1. Authentication & Users
// ==========================================
export const authApi = {
  login: (credentials: { identifier: string; password: string; rememberMe?: boolean }): Promise<LoginResponse> =>
    api.post('/api/v1/auth/login', credentials),

  register: (data: {
    email: string;
    password: string;
    name: string;
    role: string;
    phone?: string;
    organization?: string;
    licenseNumber?: string;
    roleTitle?: string;
  }): Promise<LoginResponse> =>
    api.post('/api/v1/auth/register', data),

  getMe: (): Promise<UserProfile> =>
    api.get('/api/v1/auth/me'),

  logout: (): Promise<{ message: string }> =>
    api.post('/api/v1/auth/logout'),

  getUsers: (params?: { role?: string; is_verified?: boolean }): Promise<UserProfile[]> => {
    const q = new URLSearchParams();
    if (params?.role) q.append('role', params.role);
    if (params?.is_verified !== undefined) q.append('is_verified', String(params.is_verified));
    return api.get(`/api/v1/users?${q.toString()}`);
  },

  getPendingVerifications: (): Promise<UserProfile[]> =>
    api.get('/api/v1/users/pending-verification'),

  verifyUser: (userId: string): Promise<UserProfile> =>
    api.post(`/api/v1/users/${userId}/verify`),
};

// ==========================================
// 2. Emergencies & Command Center
// ==========================================
export const emergencyApi = {
  getEmergencies: (params?: {
    status?: string;
    type?: string;
    priority?: string;
    hospitalId?: string;
    patientId?: string;
  }): Promise<Emergency[]> => {
    const q = new URLSearchParams();
    if (params?.status) q.append('status', params.status);
    if (params?.type) q.append('type', params.type);
    if (params?.priority) q.append('priority', params.priority);
    if (params?.hospitalId) q.append('hospitalId', params.hospitalId);
    if (params?.patientId) q.append('patientId', params.patientId);
    return api.get(`/api/v1/emergencies?${q.toString()}`);
  },

  getEmergency: (id: string): Promise<Emergency> =>
    api.get(`/api/v1/emergencies/${id}`),

  createEmergency: (data: {
    type: string;
    priority: string;
    hospitalId: string;
    description: string;
    patientId?: string | null;
    bloodGroup?: string;
    unitsRequired?: number;
    organType?: string;
    locationLat?: number;
    locationLng?: number;
  }): Promise<Emergency> =>
    api.post('/api/v1/emergencies', data),

  updateEmergency: (id: string, data: { priority?: string; description?: string; status?: string }): Promise<Emergency> =>
    api.patch(`/api/v1/emergencies/${id}`, data),

  resolveEmergency: (id: string, notes?: string): Promise<Emergency> =>
    api.post(`/api/v1/emergencies/${id}/resolve`, { notes }),

  cancelEmergency: (id: string, reason?: string): Promise<Emergency> =>
    api.post(`/api/v1/emergencies/${id}/cancel`, { reason }),

  getPatientEmergency: (): Promise<Emergency | null> =>
    api.get('/api/v1/emergencies/patient/active'),

  getKPIs: (): Promise<KPIData> =>
    api.get('/api/v1/dashboard/kpis'),

  getActivityTimeline: (emergencyId?: string): Promise<EmergencyEvent[]> => {
    const path = emergencyId ? `/api/v1/activity?emergencyId=${emergencyId}` : '/api/v1/activity';
    return api.get(path);
  },
};

// ==========================================
// 3. Blood & Donor Intelligence
// ==========================================
export const bloodApi = {
  createRequest: (data: {
    bloodGroup: string;
    unitsRequired: number;
    priority: string;
    hospitalId: string;
    notes?: string;
  }): Promise<Emergency> =>
    api.post('/api/v1/blood/requests', data),

  getRankedDonors: (emergencyId: string, options?: { minCandidates?: number; demoMode?: boolean }): Promise<RankedDonorsResponse> => {
    const q = new URLSearchParams({ emergencyId });
    if (options?.minCandidates) q.append('min_candidates', String(options.minCandidates));
    if (options?.demoMode) q.append('demo_mode', 'true');
    return api.get(`/api/v1/blood/donors/ranked?${q.toString()}`);
  },

  contactDonor: (donorId: string, emergencyId: string): Promise<{ status: string; donorId: string; contactedAt: string }> =>
    api.post(`/api/v1/blood/donors/${donorId}/contact`, { emergencyId }),

  submitDonorResponse: (donorId: string, data: { status: 'accepted' | 'declined' | 'timeout'; shareLocation?: boolean; emergencyId?: string }): Promise<any> =>
    api.post(`/api/v1/blood/donors/${donorId}/response`, data),

  dispatchBatch: (emergencyId: string, batchSize = 5): Promise<any> =>
    api.post(`/api/v1/blood/emergencies/${emergencyId}/dispatch-batch?batch_size=${batchSize}`),

  getWorkflowStatus: (emergencyId: string): Promise<any> =>
    api.get(`/api/v1/blood/emergencies/${emergencyId}/workflow-status`),

  getDonors: (params?: { blood_group?: string; status?: string; city?: string; limit?: number; skip?: number }): Promise<Donor[]> => {
    const q = new URLSearchParams();
    if (params?.blood_group) q.append('blood_group', params.blood_group);
    if (params?.status) q.append('status', params.status);
    if (params?.city) q.append('city', params.city);
    if (params?.limit) q.append('limit', String(params.limit));
    if (params?.skip) q.append('skip', String(params.skip));
    return api.get(`/api/v1/donors?${q.toString()}`);
  },

  getDonorMe: (): Promise<Donor> =>
    api.get('/api/v1/donors/me'),

  updateAvailability: (isAvailable: boolean): Promise<{ isAvailable: boolean }> =>
    api.post('/api/v1/donors/me/availability', { isAvailable }),

  getDonorConsent: (): Promise<any> =>
    api.get('/api/v1/donors/me/consent'),

  updateDonorConsent: (data: any): Promise<any> =>
    api.patch('/api/v1/donors/me/consent', data),
};

// ==========================================
// 4. Hospitals & Blood Banks
// ==========================================
export const hospitalApi = {
  getHospitals: (params?: { city?: string; district?: string }): Promise<Hospital[]> => {
    const q = new URLSearchParams();
    if (params?.city) q.append('city', params.city);
    if (params?.district) q.append('district', params.district);
    return api.get(`/api/v1/hospitals?${q.toString()}`);
  },

  getHospital: (id: string): Promise<Hospital> =>
    api.get(`/api/v1/hospitals/${id}`),

  getHospitalInventory: (id: string): Promise<{ bloodInventory: BloodInventoryItem[]; traumaBaysAvailable: number; totalTraumaBays: number }> =>
    api.get(`/api/v1/hospitals/${id}/inventory`),

  getBloodBanks: (params?: { city?: string; district?: string }): Promise<BloodBank[]> => {
    const q = new URLSearchParams();
    if (params?.city) q.append('city', params.city);
    if (params?.district) q.append('district', params.district);
    return api.get(`/api/v1/blood-banks?${q.toString()}`);
  },

  getBloodBank: (id: string): Promise<BloodBank> =>
    api.get(`/api/v1/blood-banks/${id}`),

  getBloodBankInventory: (id: string): Promise<{ inventory: BloodInventoryItem[]; bloodBankId: string; lastUpdated: string }> =>
    api.get(`/api/v1/blood-banks/${id}/inventory`),
};

// ==========================================
// 5. Ambulance Intelligence & Routing
// ==========================================
export const ambulanceApi = {
  getAmbulances: (): Promise<Ambulance[]> =>
    api.get('/api/v1/ambulances'),

  getAmbulance: (id: string): Promise<Ambulance> =>
    api.get(`/api/v1/ambulances/${id}`),

  getRoutes: (id: string): Promise<RouteOption[]> =>
    api.get(`/api/v1/ambulances/${id}/routes`),

  ingestTelemetry: (data: {
    ambulanceId: string;
    lat: number;
    lng: number;
    speedKmh?: number;
    heading?: number;
    telemetrySource?: string;
  }): Promise<{ status: string; ambulanceId: string; updatedAt: string }> =>
    api.post('/api/v1/ambulances/telemetry/ingest', data),

  updateStatus: (id: string, status: string): Promise<Ambulance> =>
    api.post(`/api/v1/ambulances/${id}/status`, { status }),

  assignAmbulance: (id: string, emergencyId: string): Promise<Ambulance> =>
    api.post(`/api/v1/ambulances/${id}/assign`, { emergencyId }),
};

// ==========================================
// 6. Organ Viability & Clinical Review
// ==========================================
export const organApi = {
  getOrgans: (): Promise<Organ[]> =>
    api.get('/api/v1/organs'),

  getAvailableOrgans: (): Promise<Organ[]> =>
    api.get('/api/v1/organs/available'),

  getOrgan: (id: string): Promise<Organ> =>
    api.get(`/api/v1/organs/${id}`),

  submitClinicalReview: (id: string, data: { decision: 'approved' | 'rejected'; notes?: string }): Promise<Organ> =>
    api.post(`/api/v1/organs/${id}/clinical-review`, data),

  createOrganRequest: (data: { organType: string; priority: string; hospitalId: string; notes?: string }): Promise<any> =>
    api.post('/api/v1/organs/requests', data),
};

// ==========================================
// 7. Privacy & Consent
// ==========================================
export const consentApi = {
  getConsent: (): Promise<ConsentSettings> =>
    api.get('/api/v1/consent'),

  updateConsent: (data: Partial<ConsentSettings>): Promise<ConsentSettings> =>
    api.patch('/api/v1/consent', data),
};

// ==========================================
// 8. Clinical Guidance RAG
// ==========================================
export const clinicalGuidanceApi = {
  query: (query: string, domain?: string): Promise<ClinicalGuidanceResponse> =>
    api.post('/api/v1/clinical-guidance/query', { query, domain }),

  getTrustedDocuments: (): Promise<any[]> =>
    api.get('/api/v1/clinical-guidance/documents'),

  getMLReadiness: (): Promise<any> =>
    api.get('/api/v1/ml/readiness'),

  parseIntent: (text: string): Promise<any> =>
    api.post('/api/v1/clinical-guidance/parse-intent', { text }),
};

// ==========================================
// 9. Audit Log & Cryptographic Verification
// ==========================================
export const auditApi = {
  getLogs: (params?: { module?: string; status?: string; search?: string }): Promise<AuditLog[]> => {
    const q = new URLSearchParams();
    if (params?.module) q.append('module', params.module);
    if (params?.status) q.append('status', params.status);
    if (params?.search) q.append('search', params.search);
    return api.get(`/api/v1/audit?${q.toString()}`);
  },

  verifyChain: (): Promise<AuditVerificationResult> =>
    api.get('/api/v1/audit/verify'),
};

// ==========================================
// 10. Notifications
// ==========================================
export const notificationApi = {
  getProviderStatus: (): Promise<{
    provider: string;
    mockNotificationsOnly: boolean;
    liveEnabled: boolean;
    rateLimitPerHour: number;
    spendCeilingUsd: number;
    configuredChannels: string[];
  }> => api.get('/api/v1/notifications/provider-status'),
};
