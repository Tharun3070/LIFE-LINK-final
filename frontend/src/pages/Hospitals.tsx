import React, { useState, useEffect } from 'react';
import {
  Building2,
  Droplet,
  Search,
  Filter,
  Phone,
  MapPin,
  Activity,
  Heart,
  RefreshCw,
  AlertCircle,
  Eye,
  CheckCircle2,
  XCircle,
  ExternalLink,
  ShieldCheck,
} from 'lucide-react';
import { hospitalApi } from '../api/services';
import { Hospital, BloodBank, BloodInventoryItem, Emergency } from '../types';
import StatusBadge from '../components/common/StatusBadge';
import EmptyState from '../components/common/EmptyState';
import Modal from '../components/common/Modal';

export const Hospitals: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'hospitals' | 'bloodbanks'>('hospitals');

  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [bloodBanks, setBloodBanks] = useState<BloodBank[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCity, setSelectedCity] = useState<string>('all');
  const [filterOrganCenter, setFilterOrganCenter] = useState<boolean>(false);
  const [filterBloodBank, setFilterBloodBank] = useState<boolean>(false);

  // Selected Hospital / Blood Bank Inventory Modal
  const [viewingFacility, setViewingFacility] = useState<{
    id: string;
    name: string;
    type: 'hospital' | 'bloodbank';
  } | null>(null);
  const [inventory, setInventory] = useState<BloodInventoryItem[]>([]);
  const [traumaBays, setTraumaBays] = useState<{ available: number; total: number } | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState<boolean>(false);
  const [inventoryError, setInventoryError] = useState<string | null>(null);

  // Hospital Emergencies Modal
  const [viewingEmergenciesHospital, setViewingEmergenciesHospital] = useState<Hospital | null>(null);
  const [hospitalEmergencies, setHospitalEmergencies] = useState<Emergency[]>([]);
  const [emergenciesLoading, setEmergenciesLoading] = useState<boolean>(false);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      if (activeTab === 'hospitals') {
        const data = await hospitalApi.getHospitals();
        setHospitals(data);
      } else {
        const data = await hospitalApi.getBloodBanks();
        setBloodBanks(data);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to retrieve facilities directory.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [activeTab]);

  const handleOpenInventory = async (facility: { id: string; name: string; type: 'hospital' | 'bloodbank' }) => {
    setViewingFacility(facility);
    setInventoryLoading(true);
    setInventoryError(null);
    setInventory([]);
    setTraumaBays(null);

    try {
      if (facility.type === 'hospital') {
        const data = await hospitalApi.getHospitalInventory(facility.id);
        setInventory(data.bloodInventory || []);
        setTraumaBays({
          available: data.traumaBaysAvailable ?? 4,
          total: data.totalTraumaBays ?? 6,
        });
      } else {
        const data = await hospitalApi.getBloodBankInventory(facility.id);
        setInventory(data.inventory || []);
      }
    } catch (err: any) {
      setInventoryError(err?.message || 'Failed to load live blood inventory.');
    } finally {
      setInventoryLoading(false);
    }
  };

  const handleOpenEmergencies = async (hospital: Hospital) => {
    setViewingEmergenciesHospital(hospital);
    setEmergenciesLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/hospitals/${hospital.id}/emergencies`);
      if (res.ok) {
        const data = await res.json();
        setHospitalEmergencies(data);
      } else {
        setHospitalEmergencies([]);
      }
    } catch {
      setHospitalEmergencies([]);
    } finally {
      setEmergenciesLoading(false);
    }
  };

  const filteredHospitals = hospitals.filter((h) => {
    const matchesSearch =
      h.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      h.city?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      h.district?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCity = selectedCity === 'all' || h.city === selectedCity;
    const matchesOrgan = !filterOrganCenter || h.organTransplantCenter;
    const matchesBlood = !filterBloodBank || h.bloodBankAvailable;
    return matchesSearch && matchesCity && matchesOrgan && matchesBlood;
  });

  const filteredBloodBanks = bloodBanks.filter((b) => {
    const matchesSearch =
      b.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      b.city?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      b.district?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCity = selectedCity === 'all' || b.city === selectedCity;
    return matchesSearch && matchesCity;
  });

  const cities = Array.from(
    new Set(
      (activeTab === 'hospitals' ? hospitals : bloodBanks)
        .map((f) => f.city)
        .filter(Boolean)
    )
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-lg bg-blue-100 text-blue-700">
              <Building2 className="w-5 h-5 text-blue-600" />
            </span>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Partner Healthcare Network</h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Trauma centers, authorized blood banks, and verified organ retrieval hospitals.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200">
          <button
            onClick={() => setActiveTab('hospitals')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'hospitals'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Partner Hospitals ({hospitals.length})
          </button>
          <button
            onClick={() => setActiveTab('bloodbanks')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'bloodbanks'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Regional Blood Banks ({bloodBanks.length})
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder={`Search ${activeTab === 'hospitals' ? 'hospitals' : 'blood banks'}, city...`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input input-sm pl-9 text-xs w-full"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 w-full md:w-auto">
          <select
            value={selectedCity}
            onChange={(e) => setSelectedCity(e.target.value)}
            className="input input-sm text-xs bg-slate-50"
          >
            <option value="all">All Locations</option>
            {cities.map((city) => (
              <option key={city} value={city}>
                {city}
              </option>
            ))}
          </select>

          {activeTab === 'hospitals' && (
            <>
              <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none px-2 py-1 bg-slate-50 rounded-lg border border-slate-200">
                <input
                  type="checkbox"
                  checked={filterOrganCenter}
                  onChange={(e) => setFilterOrganCenter(e.target.checked)}
                  className="rounded border-slate-300 text-emerald-600"
                />
                <span>Organ Centers Only</span>
              </label>

              <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none px-2 py-1 bg-slate-50 rounded-lg border border-slate-200">
                <input
                  type="checkbox"
                  checked={filterBloodBank}
                  onChange={(e) => setFilterBloodBank(e.target.checked)}
                  className="rounded border-slate-300 text-emerald-600"
                />
                <span>On-Site Blood Bank</span>
              </label>
            </>
          )}

          <button
            onClick={() => fetchData()}
            className="btn btn-secondary btn-sm text-xs flex items-center gap-1"
            title="Refresh List"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Facilities Grid */}
      {loading ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200">
          <RefreshCw className="w-6 h-6 animate-spin text-emerald-600 mx-auto mb-2" />
          <p className="text-xs text-slate-500 font-medium">Loading medical facility registry...</p>
        </div>
      ) : error ? (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : activeTab === 'hospitals' && filteredHospitals.length === 0 ? (
        <EmptyState
          title="No Hospitals Found"
          description="No partner hospitals match your search criteria. Try removing some filters."
        />
      ) : activeTab === 'bloodbanks' && filteredBloodBanks.length === 0 ? (
        <EmptyState
          title="No Blood Banks Found"
          description="No regional blood banks match your search criteria. Try removing some filters."
        />
      ) : activeTab === 'hospitals' ? (
        /* Hospitals Cards */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredHospitals.map((hospital) => (
            <div
              key={hospital.id}
              className="bg-white rounded-xl border border-slate-200 p-5 hover:border-slate-300 hover:shadow-xs transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      {hospital.type || hospital.category || 'Tertiary Care'}
                    </span>
                    <h3 className="text-base font-bold text-slate-900 mt-2">{hospital.name}</h3>
                    <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>{hospital.address || `${hospital.city}, ${hospital.district}`}</span>
                    </p>
                  </div>
                  <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-600 shrink-0">
                    <Building2 className="w-5 h-5" />
                  </div>
                </div>

                {/* Capabilities Pills */}
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {hospital.organTransplantCenter && (
                    <span className="badge badge-emerald flex items-center gap-1 text-[11px]">
                      <Heart className="w-3 h-3" />
                      Organ Center
                    </span>
                  )}
                  {hospital.bloodBankAvailable && (
                    <span className="badge badge-blue flex items-center gap-1 text-[11px]">
                      <Droplet className="w-3 h-3" />
                      Blood Bank
                    </span>
                  )}
                  <span className="badge badge-neutral text-[11px]">
                    {hospital.traumaBayCount || 6} Trauma Bays
                  </span>
                </div>

                {/* Helplines */}
                <div className="mt-4 pt-3 border-t border-slate-100 text-xs space-y-1 text-slate-600">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Emergency Line:</span>
                    <a
                      href={`tel:${hospital.emergencyHelpline || '108'}`}
                      className="font-semibold text-red-600 hover:underline flex items-center gap-1"
                    >
                      <Phone className="w-3 h-3" />
                      {hospital.emergencyHelpline || hospital.contactNumber || '108'}
                    </a>
                  </div>
                </div>
              </div>

              {/* Actions Footer */}
              <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between gap-2">
                <button
                  onClick={() => handleOpenEmergencies(hospital)}
                  className="btn btn-secondary btn-sm text-xs flex-1 flex items-center justify-center gap-1"
                >
                  <Activity className="w-3.5 h-3.5 text-slate-500" />
                  Cases
                </button>
                <button
                  onClick={() =>
                    handleOpenInventory({
                      id: hospital.id,
                      name: hospital.name,
                      type: 'hospital',
                    })
                  }
                  className="btn btn-primary btn-sm text-xs flex-1 flex items-center justify-center gap-1"
                >
                  <Droplet className="w-3.5 h-3.5" />
                  Live Blood Stock
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Blood Banks Cards */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredBloodBanks.map((bank) => (
            <div
              key={bank.id}
              className="bg-white rounded-xl border border-slate-200 p-5 hover:border-slate-300 hover:shadow-xs transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-red-700 bg-red-50 px-2 py-0.5 rounded border border-red-200">
                      {bank.category || 'Regional Blood Storage Center'}
                    </span>
                    <h3 className="text-base font-bold text-slate-900 mt-2">{bank.name}</h3>
                    <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>{bank.address || `${bank.city}, ${bank.district}`}</span>
                    </p>
                  </div>
                  <div className="w-10 h-10 rounded-xl bg-red-50 text-red-600 flex items-center justify-center shrink-0">
                    <Droplet className="w-5 h-5" />
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-slate-100 text-xs space-y-1 text-slate-600">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Direct Helpline:</span>
                    <a
                      href={`tel:${bank.helpline || bank.contactNumber || '108'}`}
                      className="font-semibold text-slate-800 hover:underline flex items-center gap-1"
                    >
                      <Phone className="w-3 h-3 text-emerald-600" />
                      {bank.helpline || bank.contactNumber || '108'}
                    </a>
                  </div>
                </div>
              </div>

              <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-end">
                <button
                  onClick={() =>
                    handleOpenInventory({
                      id: bank.id,
                      name: bank.name,
                      type: 'bloodbank',
                    })
                  }
                  className="btn btn-primary btn-sm text-xs w-full flex items-center justify-center gap-1.5"
                >
                  <Droplet className="w-3.5 h-3.5" />
                  Inspect Cold Storage Inventory
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Live Blood Stock / Resource Inventory Modal */}
      {viewingFacility && (
        <Modal
          isOpen={true}
          onClose={() => setViewingFacility(null)}
          title={`Resource Inventory: ${viewingFacility.name}`}
          size="lg"
        >
          <div className="space-y-4">
            {/* Trauma Bays Indicator if Hospital */}
            {traumaBays && (
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center">
                    <Activity className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-slate-900">Trauma Bay Emergency Capacity</h4>
                    <p className="text-xs text-slate-500">Live resuscitation beds monitored by operations dispatch</p>
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-2xl font-bold text-emerald-600">{traumaBays.available}</span>
                  <span className="text-slate-400 text-xs font-semibold"> / {traumaBays.total} available</span>
                </div>
              </div>
            )}

            {/* Inventory Units Grid */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <Droplet className="w-3.5 h-3.5 text-red-600" />
                Verified Cold Storage Units by Blood Group (ABO/Rh)
              </h4>

              {inventoryLoading ? (
                <div className="py-8 text-center">
                  <RefreshCw className="w-5 h-5 animate-spin text-emerald-600 mx-auto mb-2" />
                  <p className="text-xs text-slate-500">Verifying cold storage sensors...</p>
                </div>
              ) : inventoryError ? (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  {inventoryError}
                </div>
              ) : inventory.length === 0 ? (
                <div className="p-6 text-center border border-dashed border-slate-200 rounded-xl text-xs text-slate-500">
                  No verified blood inventory units currently cataloged for this facility.
                </div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {inventory.map((item) => {
                    const isLow = item.availableUnits < 3;
                    return (
                      <div
                        key={item.bloodGroup}
                        className={`p-3.5 rounded-xl border text-center ${
                          isLow
                            ? 'bg-amber-50/50 border-amber-200'
                            : 'bg-white border-slate-200'
                        }`}
                      >
                        <span className="text-sm font-bold text-slate-900 block">{item.bloodGroup}</span>
                        <span className={`text-2xl font-black block my-1 ${
                          isLow ? 'text-amber-600' : 'text-slate-800'
                        }`}>
                          {item.availableUnits}
                        </span>
                        <span className="text-[10px] text-slate-400 uppercase font-semibold">
                          {item.component || 'Whole Blood'}
                        </span>
                        {isLow && (
                          <span className="block mt-1 text-[9px] font-bold text-amber-700 bg-amber-100 rounded py-0.5">
                            Critically Low
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setViewingFacility(null)}
                className="btn btn-secondary text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Hospital Active Emergencies Modal */}
      {viewingEmergenciesHospital && (
        <Modal
          isOpen={true}
          onClose={() => setViewingEmergenciesHospital(null)}
          title={`Active Emergencies: ${viewingEmergenciesHospital.name}`}
          size="md"
        >
          <div className="space-y-3">
            {emergenciesLoading ? (
              <div className="py-8 text-center">
                <RefreshCw className="w-5 h-5 animate-spin text-emerald-600 mx-auto mb-2" />
                <p className="text-xs text-slate-500">Loading cases...</p>
              </div>
            ) : hospitalEmergencies.length === 0 ? (
              <div className="p-6 text-center border border-dashed border-slate-200 rounded-xl text-xs text-slate-500">
                No active emergencies currently assigned to this hospital.
              </div>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {hospitalEmergencies.map((e) => (
                  <div key={e.id} className="p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-slate-900">{e.description}</div>
                      <span className="text-[11px] text-slate-400">ID: #{e.id.slice(0, 8)}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={e.priority} size="sm" />
                      <StatusBadge status={e.status} size="sm" />
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="flex justify-end pt-2">
              <button
                onClick={() => setViewingEmergenciesHospital(null)}
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

export default Hospitals;
