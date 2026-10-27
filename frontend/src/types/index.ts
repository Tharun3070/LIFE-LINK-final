// LifeLink Unified Frontend & Backend Type Definitions

export type UserRole =
  | 'patient'
  | 'donor'
  | 'doctor'
  | 'hospital_staff'
  | 'ambulance_driver'
  | 'ambulance_operator'
  | 'transplant_coordinator'
  | 'admin';

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  roleTitle?: string;
  hospitalId?: string | null;
  hospitalName?: string | null;
  organization?: string | null;
  phone?: string | null;
  licenseNumber?: string | null;
  isVerified?: boolean;
  avatar?: string | null;
  permissions?: string[];
  lastLogin?: string | null;
  sessionStatus?: string;
}

export interface LoginResponse {
  user: UserProfile;
  token: string;
  refreshToken?: string;
  expiresAt?: number;
}

export type EmergencyType = 'blood' | 'organ' | 'ambulance' | 'general';
export type EmergencyPriority = 'critical' | 'high' | 'moderate' | 'low';
export type EmergencyStatus =
  | 'created'
  | 'resource_search'
  | 'coordinating'
  | 'in_transit'
  | 'arrived'
  | 'resolved'
  | 'cancelled';

export interface Emergency {
  id: string;
  type: EmergencyType;
  priority: EmergencyPriority;
  status: EmergencyStatus;
  hospitalId: string;
  hospitalName?: string;
  patientId?: string | null;
  createdAt: string;
  updatedAt: string;
  description: string;
  eta?: number | null;
  assignedResourceIds?: string[];
  bloodGroup?: string | null;
  unitsRequired?: number | null;
  organType?: string | null;
  locationLat?: number | null;
  locationLng?: number | null;
  isSimulated?: boolean;
}

export interface EmergencyEvent {
  id: string;
  emergencyId: string;
  timestamp: string;
  eventType: string;
  actor: string;
  actorRole: string;
  description: string;
  metadata?: Record<string, any>;
}

export interface KPIData {
  activeEmergencies: number;
  bloodRequests: number;
  organAlerts: number;
  ambulancesActive: number;
  avgResponseTimeSeconds: number;
  donorAcceptanceRate: number;
}

export interface Donor {
  id: string;
  name: string;
  bloodGroup: string;
  city?: string;
  district?: string;
  taluk?: string;
  pincode?: string;
  phone?: string | null;
  isAvailable: boolean;
  totalDonations?: number;
  lastDonationDate?: string | null;
  coordinates?: { lat: number; lng: number } | null;
  coordinatesObfuscated?: boolean;
  locationConsentGranted?: boolean;
  isSynthetic?: boolean;
  dataProvenance?: string;
}

export interface RankedDonorCandidate {
  id: string;
  name?: string;
  bloodGroup: string;
  distanceKm: number;
  etaMinutes: number;
  eligibility: string;
  responseProbability: number;
  reliabilityScore: number;
  reachabilityScore?: number;
  aiRank: number;
  status: string;
  locationConsentGranted: boolean;
  historicalAcceptanceRate?: number;
  coordinates?: { lat: number; lng: number } | null;
}

export interface RankedDonorsResponse {
  donors: RankedDonorCandidate[];
  searchConfig?: {
    initialRadiusKm: number;
    currentRadiusKm: number;
    maxRadiusKm: number;
    expansionCount: number;
    expansionReason?: string;
  };
  aiRecommendation?: string;
  emergencyId?: string;
}

export interface Hospital {
  id: string;
  name: string;
  category?: string;
  type?: string;
  address?: string;
  city?: string;
  district?: string;
  state?: string;
  pincode?: string;
  contactNumber?: string;
  emergencyHelpline?: string;
  lat?: number;
  lng?: number;
  traumaBayCount?: number;
  bloodBankAvailable?: boolean;
  organTransplantCenter?: boolean;
}

export interface BloodBank {
  id: string;
  name: string;
  category?: string;
  address?: string;
  city?: string;
  district?: string;
  contactNumber?: string;
  helpline?: string;
  lat?: number;
  lng?: number;
  hospitalId?: string | null;
}

export interface BloodInventoryItem {
  bloodGroup: string;
  availableUnits: number;
  component?: string;
  lastUpdated?: string;
}

export interface RouteOption {
  routeId: string;
  routeName: string;
  distanceKm: number;
  etaMinutes: number;
  trafficCondition: 'light' | 'moderate' | 'heavy' | 'congested';
  isRecommended: boolean;
  rationale?: string;
  waypoints?: [number, number][];
}

export interface Ambulance {
  id: string;
  unitNumber: string;
  hospitalId: string;
  hospitalName?: string;
  status: 'available' | 'dispatched' | 'en_route_pickup' | 'at_scene' | 'transporting' | 'at_hospital' | 'maintenance';
  currentLat: number;
  currentLng: number;
  speedKmh?: number;
  heading?: number;
  assignedEmergencyId?: string | null;
  driverName?: string | null;
  driverPhone?: string | null;
  deviceSource?: string;
  lastTelemetryAt?: string;
  recommendedRoute?: RouteOption | null;
}

export interface Organ {
  id: string;
  organType: string;
  sourceHospitalId: string;
  sourceHospitalName: string;
  targetHospitalId?: string | null;
  targetHospitalName?: string | null;
  donorId?: string | null;
  donorAge?: number | null;
  donorBloodGroup?: string;
  distanceKm: number;
  etaMinutes: number;
  viabilityRemainingSeconds: number;
  viabilityTotalSeconds: number;
  viabilityLevel: 'normal' | 'warning' | 'critical' | 'expired';
  reachabilityScore: number;
  aiRecommendation: 'proceed' | 'caution' | 'infeasible';
  aiRationale?: string;
  status: 'available' | 'clinical_review' | 'in_transit' | 'delivered' | 'expired';
  clinicalReviewStatus: 'pending' | 'approved' | 'rejected';
  clinicalReviewNotes?: string | null;
  availableAt: string;
  updatedAt: string;
}

export interface AuditLog {
  id: string;
  timestamp: string;
  actor: string;
  actorType: 'user' | 'system' | 'ai' | 'donor';
  action: string;
  resource: string;
  resourceId?: string | null;
  authorization?: string | null;
  status: 'success' | 'failed' | 'pending';
  module: 'blood' | 'organ' | 'ambulance' | 'system' | 'auth';
  ipAddress?: string | null;
  sessionId?: string | null;
  previousHash?: string | null;
  recordHash?: string | null;
  metadata?: Record<string, any>;
}

export interface AuditVerificationResult {
  isValid: boolean;
  verifiedCount: number;
  tamperedId?: string | null;
  error?: string | null;
}

export interface ConsentSettings {
  id?: string;
  userId: string;
  liveLocation: boolean;
  emergencyCommunication: boolean;
  donationRequests: boolean;
  healthDataSharing: boolean;
  updatedAt?: string;
}

export interface ClinicalGuidanceResponse {
  answer: string;
  citations: {
    docId: string;
    title: string;
    organization: string;
    section?: string;
    url?: string;
  }[];
  confidenceScore?: number;
}

export interface RealtimeEvent {
  type: string;
  payload: Record<string, any>;
  timestamp: string;
}
