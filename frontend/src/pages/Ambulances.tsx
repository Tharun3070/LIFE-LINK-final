import React, { useState, useEffect } from 'react';
import {
  Truck,
  MapPin,
  Navigation,
  Compass,
  Activity,
  Phone,
  RefreshCw,
  AlertCircle,
  Clock,
  Radio,
  Sliders,
  Sparkles,
  CheckCircle2,
  Share2,
} from 'lucide-react';
import { ambulanceApi } from '../api/services';
import { Ambulance, RouteOption } from '../types';
import { useAuth } from '../context/AuthContext';
import { useRealtime } from '../context/RealtimeContext';
import StatusBadge from '../components/common/StatusBadge';
import EmptyState from '../components/common/EmptyState';
import Modal from '../components/common/Modal';

export const Ambulances: React.FC = () => {
  const { user } = useAuth();
  const { addToast } = useRealtime();

  const [ambulances, setAmbulances] = useState<Ambulance[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Route Comparison Modal
  const [routeAmbulance, setRouteAmbulance] = useState<Ambulance | null>(null);
  const [routes, setRoutes] = useState<RouteOption[]>([]);
  const [routesLoading, setRoutesLoading] = useState<boolean>(false);
  const [routesError, setRoutesError] = useState<string | null>(null);

  // Status Update State
  const [updatingAmbulance, setUpdatingAmbulance] = useState<Ambulance | null>(null);
  const [newStatus, setNewStatus] = useState<string>('');
  const [isUpdatingStatus, setIsUpdatingStatus] = useState<boolean>(false);

  // Live Telemetry Ingestion Simulator State
  const [pingingAmbulanceId, setPingingAmbulanceId] = useState<string | null>(null);

  const fetchAmbulances = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await ambulanceApi.getAmbulances();
      setAmbulances(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to retrieve ambulance fleet.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAmbulances();
  }, []);

  // Fetch Multi-Route Comparison
  const handleOpenRoutes = async (amb: Ambulance) => {
    setRouteAmbulance(amb);
    setRoutesLoading(true);
    setRoutesError(null);
    setRoutes([]);

    try {
      const data = await ambulanceApi.getRoutes(amb.id);
      setRoutes(data);
    } catch (err: any) {
      setRoutesError(err?.message || 'Failed to retrieve route alternatives.');
    } finally {
      setRoutesLoading(false);
    }
  };

  // Live Telemetry Ping Simulation
  const handleSimulateTelemetry = async (amb: Ambulance) => {
    try {
      setPingingAmbulanceId(amb.id);
      // Generate slight GPS movement (+0.002 deg)
      const lat = (amb.currentLat || 11.0168) + (Math.random() - 0.5) * 0.004;
      const lng = (amb.currentLng || 76.9558) + (Math.random() - 0.5) * 0.004;
      const speed = Math.floor(Math.random() * 40) + 30; // 30-70 km/h

      const res = await ambulanceApi.ingestTelemetry({
        ambulanceId: amb.id,
        lat,
        lng,
        speedKmh: speed,
        heading: Math.floor(Math.random() * 360),
        telemetrySource: 'mobile_app_gps',
      });

      addToast({
        title: 'Telemetry Ingested',
        message: `Unit ${amb.unitNumber}: Coordinates updated to ${lat.toFixed(4)}, ${lng.toFixed(4)} at ${speed} km/h.`,
        type: 'info',
      });

      await fetchAmbulances();
    } catch (err: any) {
      addToast({
        title: 'Telemetry Ingestion Failed',
        message: err?.message || 'Could not ingest telemetry ping.',
        type: 'error',
      });
    } finally {
      setPingingAmbulanceId(null);
    }
  };

  // Handle Status Update
  const handleUpdateStatus = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!updatingAmbulance || !newStatus) return;

    try {
      setIsUpdatingStatus(true);
      await ambulanceApi.updateStatus(updatingAmbulance.id, newStatus);
      addToast({
        title: 'Dispatch Status Updated',
        message: `Unit ${updatingAmbulance.unitNumber} transitioned to ${newStatus.replace('_', ' ')}.`,
        type: 'success',
      });
      setUpdatingAmbulance(null);
      await fetchAmbulances();
    } catch (err: any) {
      addToast({
        title: 'Status Update Failed',
        message: err?.message || 'Could not update dispatch status.',
        type: 'error',
      });
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const filteredAmbulances = ambulances.filter((amb) => {
    const matchesSearch =
      amb.unitNumber.toLowerCase().includes(searchQuery.toLowerCase()) ||
      amb.hospitalName?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      amb.driverName?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = filterStatus === 'all' || amb.status === filterStatus;
    return matchesSearch && matchesStatus;
  });

  const availableCount = ambulances.filter((a) => a.status === 'available').length;
  const inTransitCount = ambulances.filter((a) => ['dispatched', 'en_route_pickup', 'transporting'].includes(a.status)).length;
  const atSceneCount = ambulances.filter((a) => ['at_scene', 'at_hospital'].includes(a.status)).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-lg bg-orange-100 text-orange-700">
              <Truck className="w-5 h-5 text-orange-600" />
            </span>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Ambulance Fleet & Dispatch Coordination</h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Real-time GPS telemetry, multi-route traffic intelligence (Route A/B/C), and emergency trauma bay routing.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchAmbulances()}
            className="btn btn-secondary flex items-center gap-2 text-xs"
            title="Refresh Fleet"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh Fleet
          </button>
        </div>
      </div>

      {/* Fleet KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs">
          <span className="text-slate-400 text-xs font-semibold block">Total Active Fleet</span>
          <span className="text-2xl font-bold text-slate-900 mt-1 block">{ambulances.length}</span>
          <span className="text-[11px] text-slate-500 mt-0.5 block">Instrumented units</span>
        </div>

        <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs">
          <span className="text-slate-400 text-xs font-semibold block">Available for Dispatch</span>
          <span className="text-2xl font-bold text-emerald-600 mt-1 block">{availableCount}</span>
          <span className="text-[11px] text-emerald-700 mt-0.5 block">Ready on station</span>
        </div>

        <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs">
          <span className="text-slate-400 text-xs font-semibold block">In Transit / En Route</span>
          <span className="text-2xl font-bold text-orange-600 mt-1 block">{inTransitCount}</span>
          <span className="text-[11px] text-orange-700 mt-0.5 block">Active emergency runs</span>
        </div>

        <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs">
          <span className="text-slate-400 text-xs font-semibold block">At Scene / Hospital</span>
          <span className="text-2xl font-bold text-blue-600 mt-1 block">{atSceneCount}</span>
          <span className="text-[11px] text-blue-700 mt-0.5 block">Patient handover</span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative w-full md:w-80">
          <Navigation className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search unit, hospital, driver..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input input-sm pl-9 text-xs w-full"
          />
        </div>

        <div className="flex items-center gap-2 w-full md:w-auto">
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="input input-sm text-xs bg-slate-50"
          >
            <option value="all">All Dispatch Statuses</option>
            <option value="available">Available</option>
            <option value="dispatched">Dispatched</option>
            <option value="en_route_pickup">En Route to Scene</option>
            <option value="at_scene">At Scene</option>
            <option value="transporting">Transporting Patient</option>
            <option value="at_hospital">At Hospital Trauma Bay</option>
            <option value="maintenance">Maintenance</option>
          </select>
        </div>
      </div>

      {/* Fleet Table */}
      {loading ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200">
          <RefreshCw className="w-6 h-6 animate-spin text-emerald-600 mx-auto mb-2" />
          <p className="text-xs text-slate-500 font-medium">Tracking fleet telemetry...</p>
        </div>
      ) : error ? (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : filteredAmbulances.length === 0 ? (
        <EmptyState
          title="No Ambulances Found"
          description="No ambulance units match your filter criteria."
        />
      ) : (
        <div className="overflow-x-auto border border-slate-200 rounded-xl bg-white shadow-xs">
          <table className="table-clinical w-full text-left text-xs">
            <thead>
              <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                <th className="py-3 px-4 font-semibold">Unit Number</th>
                <th className="py-3 px-4 font-semibold">Hospital Base</th>
                <th className="py-3 px-4 font-semibold">Status</th>
                <th className="py-3 px-4 font-semibold">Driver / Crew</th>
                <th className="py-3 px-4 font-semibold">Speed & Heading</th>
                <th className="py-3 px-4 font-semibold">Assigned Case</th>
                <th className="py-3 px-4 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredAmbulances.map((amb) => {
                const isPinging = pingingAmbulanceId === amb.id;

                return (
                  <tr key={amb.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2.5">
                        <div className="w-9 h-9 rounded-lg bg-orange-100 text-orange-700 flex items-center justify-center font-bold text-xs shrink-0">
                          <Truck className="w-4 h-4" />
                        </div>
                        <div>
                          <span className="font-bold text-slate-900 block">{amb.unitNumber}</span>
                          <span className="text-[10px] text-slate-400 font-mono">
                            {amb.currentLat?.toFixed(4)}, {amb.currentLng?.toFixed(4)}
                          </span>
                        </div>
                      </div>
                    </td>

                    <td className="py-3 px-4">
                      <span className="font-medium text-slate-800 block">{amb.hospitalName || 'Coimbatore Medical'}</span>
                      <span className="text-[11px] text-slate-400">{amb.hospitalId}</span>
                    </td>

                    <td className="py-3 px-4">
                      <StatusBadge status={amb.status} size="sm" />
                    </td>

                    <td className="py-3 px-4">
                      <span className="font-medium text-slate-800 block">{amb.driverName || 'Designated Driver'}</span>
                      <span className="text-[11px] text-slate-400 flex items-center gap-1">
                        <Phone className="w-3 h-3 text-slate-400" />
                        {amb.driverPhone || '+91 98401 23456'}
                      </span>
                    </td>

                    <td className="py-3 px-4">
                      <div className="font-semibold text-slate-900">{amb.speedKmh ? `${amb.speedKmh} km/h` : 'Stationary'}</div>
                      <div className="text-[11px] text-slate-400 flex items-center gap-1">
                        <Compass className="w-3 h-3 text-slate-400" />
                        {amb.heading ? `${amb.heading}°` : 'North'}
                      </div>
                    </td>

                    <td className="py-3 px-4">
                      {amb.assignedEmergencyId ? (
                        <span className="badge badge-emergency text-[11px] font-mono">
                          #{amb.assignedEmergencyId.slice(0, 8)}
                        </span>
                      ) : (
                        <span className="text-slate-400 text-xs">None (Unassigned)</span>
                      )}
                    </td>

                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => handleSimulateTelemetry(amb)}
                          disabled={isPinging}
                          className="btn btn-secondary btn-sm text-[11px] px-2 py-1 flex items-center gap-1 text-slate-700"
                          title="Simulate Real-Time GPS Telemetry Ping"
                        >
                          <Radio className={`w-3 h-3 text-emerald-600 ${isPinging ? 'animate-ping' : ''}`} />
                          Ping GPS
                        </button>

                        <button
                          onClick={() => handleOpenRoutes(amb)}
                          className="btn btn-secondary btn-sm text-[11px] px-2 py-1 flex items-center gap-1 text-blue-700 border-blue-200 hover:bg-blue-50"
                          title="Compare Multi-Route Options (A/B/C)"
                        >
                          <Navigation className="w-3 h-3 text-blue-600" />
                          Routes
                        </button>

                        <button
                          onClick={() => {
                            setUpdatingAmbulance(amb);
                            setNewStatus(amb.status);
                          }}
                          className="btn btn-primary btn-sm text-[11px] px-2.5 py-1"
                        >
                          Update Status
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Multi-Route Intelligence Modal (A / B / C) */}
      {routeAmbulance && (
        <Modal
          isOpen={true}
          onClose={() => setRouteAmbulance(null)}
          title={`Route Intelligence: Unit ${routeAmbulance.unitNumber}`}
          size="lg"
        >
          <div className="space-y-4">
            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-900 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Navigation className="w-4 h-4 text-blue-600 shrink-0" />
                <span>
                  Dynamic route optimization evaluated against live traffic, road closures, and trauma bay distance.
                </span>
              </div>
            </div>

            {routesLoading ? (
              <div className="py-8 text-center">
                <RefreshCw className="w-5 h-5 animate-spin text-emerald-600 mx-auto mb-2" />
                <p className="text-xs text-slate-500">Calculating route telemetry...</p>
              </div>
            ) : routesError ? (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                {routesError}
              </div>
            ) : routes.length === 0 ? (
              <div className="p-6 text-center border border-dashed border-slate-200 rounded-xl text-xs text-slate-500">
                No route alternatives generated for this vehicle.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {routes.map((rt) => (
                  <div
                    key={rt.routeId}
                    className={`p-4 rounded-xl border flex flex-col justify-between transition-all ${
                      rt.isRecommended
                        ? 'bg-emerald-50/40 border-emerald-300 ring-1 ring-emerald-400'
                        : 'bg-white border-slate-200'
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-sm text-slate-900">{rt.routeName}</span>
                        {rt.isRecommended && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-600 text-white flex items-center gap-1">
                            <Sparkles className="w-3 h-3" />
                            AI Recommended
                          </span>
                        )}
                      </div>

                      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="text-slate-400 block text-[11px]">Distance</span>
                          <span className="font-bold text-slate-800 text-sm">{rt.distanceKm} km</span>
                        </div>
                        <div>
                          <span className="text-slate-400 block text-[11px]">Estimated ETA</span>
                          <span className="font-bold text-emerald-600 text-sm">~{rt.etaMinutes} mins</span>
                        </div>
                      </div>

                      <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
                        <span className="text-slate-500">Traffic Condition:</span>
                        <span className={`font-semibold capitalize ${
                          rt.trafficCondition === 'light'
                            ? 'text-emerald-600'
                            : rt.trafficCondition === 'moderate'
                            ? 'text-amber-600'
                            : 'text-red-600'
                        }`}>
                          {rt.trafficCondition}
                        </span>
                      </div>

                      {rt.rationale && (
                        <p className="text-[11px] text-slate-500 mt-2 italic bg-slate-50 p-2 rounded">
                          "{rt.rationale}"
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setRouteAmbulance(null)}
                className="btn btn-secondary text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Update Dispatch Status Modal */}
      {updatingAmbulance && (
        <Modal
          isOpen={true}
          onClose={() => setUpdatingAmbulance(null)}
          title={`Update Status: Unit ${updatingAmbulance.unitNumber}`}
          size="sm"
        >
          <form onSubmit={handleUpdateStatus} className="space-y-4">
            <div>
              <label className="label">Dispatch Lifecycle Status *</label>
              <select
                value={newStatus}
                onChange={(e) => setNewStatus(e.target.value)}
                className="input text-sm w-full font-semibold"
                required
              >
                <option value="available">Available (Stationary at Base)</option>
                <option value="dispatched">Dispatched (Alert Acknowledged)</option>
                <option value="en_route_pickup">En Route to Scene</option>
                <option value="at_scene">At Scene (First Aid / Stabilization)</option>
                <option value="transporting">Transporting Patient to Trauma Center</option>
                <option value="at_hospital">At Hospital Trauma Bay (Handover)</option>
                <option value="maintenance">Maintenance / Sanitization</option>
              </select>
            </div>

            <p className="text-xs text-slate-500">
              Updating this state triggers instant real-time telemetry updates to coordinating doctors and hospital staff.
            </p>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setUpdatingAmbulance(null)}
                className="btn btn-secondary text-xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isUpdatingStatus}
                className="btn btn-primary text-xs font-semibold"
              >
                {isUpdatingStatus ? 'Saving...' : 'Confirm Status'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};

export default Ambulances;
