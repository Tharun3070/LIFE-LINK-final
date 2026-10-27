import React, { useState, useEffect } from 'react';
import { Modal } from '../common/Modal';
import { emergencyApi, hospitalApi } from '../../api/services';
import { Hospital, EmergencyType, EmergencyPriority } from '../../types';
import { useAuth } from '../../context/AuthContext';
import { useRealtime } from '../../context/RealtimeContext';
import { AlertCircle, Droplet, Heart, Ambulance } from 'lucide-react';

interface CreateEmergencyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (emergencyId: string) => void;
}

export const CreateEmergencyModal: React.FC<CreateEmergencyModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const { user } = useAuth();
  const { showToast } = useRealtime();

  const [type, setType] = useState<EmergencyType>('blood');
  const [priority, setPriority] = useState<EmergencyPriority>('critical');
  const [hospitalId, setHospitalId] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [bloodGroup, setBloodGroup] = useState<string>('O-');
  const [unitsRequired, setUnitsRequired] = useState<number>(2);
  const [organType, setOrganType] = useState<string>('kidney');
  const [locationLat, setLocationLat] = useState<number>(11.0168);
  const [locationLng, setLocationLng] = useState<number>(76.9558);

  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      hospitalApi.getHospitals().then((data) => {
        setHospitals(data);
        if (data.length > 0 && !hospitalId) {
          setHospitalId(user?.hospitalId || data[0].id);
        }
      }).catch(() => {
        // Fallback default hospital
        setHospitalId('city-hospital-001');
      });

      // Request geolocation if available
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            setLocationLat(parseFloat(pos.coords.latitude.toFixed(5)));
            setLocationLng(parseFloat(pos.coords.longitude.toFixed(5)));
          },
          () => {} // Safe fallback if denied
        );
      }
    }
  }, [isOpen, user?.hospitalId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim()) {
      setError('Please provide an emergency description.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const payload: any = {
        type,
        priority,
        hospitalId: hospitalId || 'city-hospital-001',
        description: description.trim(),
        locationLat,
        locationLng,
      };

      if (type === 'blood') {
        payload.bloodGroup = bloodGroup;
        payload.unitsRequired = unitsRequired;
      } else if (type === 'organ') {
        payload.organType = organType;
      }

      const res = await emergencyApi.createEmergency(payload);
      showToast({
        type: 'success',
        title: 'Emergency SOS Broadcasted',
        message: `Emergency #${res.id} has been registered and coordination initiated.`,
      });
      onSuccess(res.id);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to register emergency SOS.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create Clinical Emergency SOS"
      subtitle="Broadcast urgent resource search across hospitals, ambulances, and donor networks."
      maxWidth="600px"
    >
      <form onSubmit={handleSubmit}>
        {error && (
          <div
            style={{
              padding: '0.75rem',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'var(--color-emergency-red-light)',
              color: 'var(--color-emergency-red)',
              fontSize: '0.875rem',
              marginBottom: '1rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {/* Emergency Type Selector */}
        <div className="form-group">
          <label className="form-label">Emergency Category</label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
            {[
              { id: 'blood', label: 'Blood SOS', icon: Droplet, color: 'var(--color-emergency-red)' },
              { id: 'organ', label: 'Organ Alert', icon: Heart, color: 'var(--color-orange-accent)' },
              { id: 'ambulance', label: 'Ambulance Dispatch', icon: Ambulance, color: 'var(--color-blue-info)' },
            ].map((cat) => {
              const Icon = cat.icon;
              const isSelected = type === cat.id;
              return (
                <button
                  type="button"
                  key={cat.id}
                  onClick={() => setType(cat.id as EmergencyType)}
                  style={{
                    padding: '0.75rem',
                    borderRadius: 'var(--radius-md)',
                    border: isSelected ? `2px solid ${cat.color}` : '1px solid var(--color-border)',
                    backgroundColor: isSelected ? '#ffffff' : 'var(--color-bg-card-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '0.35rem',
                    cursor: 'pointer',
                  }}
                >
                  <Icon size={20} color={cat.color} />
                  <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--color-primary-navy)' }}>
                    {cat.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Priority & Target Hospital */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="form-group">
            <label className="form-label">Priority Level</label>
            <select
              className="form-select"
              value={priority}
              onChange={(e) => setPriority(e.target.value as EmergencyPriority)}
            >
              <option value="critical">Critical (Life Threatening)</option>
              <option value="high">High (Urgent Intervention)</option>
              <option value="moderate">Moderate (Stabilized)</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Receiving Hospital</label>
            <select
              className="form-select"
              value={hospitalId}
              onChange={(e) => setHospitalId(e.target.value)}
            >
              {hospitals.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name} ({h.city || 'Tamil Nadu'})
                </option>
              ))}
              {hospitals.length === 0 && <option value="city-hospital-001">City General Hospital</option>}
            </select>
          </div>
        </div>

        {/* Dynamic Fields for Blood Emergency */}
        {type === 'blood' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', padding: '1rem', backgroundColor: 'var(--color-emergency-red-light)', borderRadius: 'var(--radius-md)', marginBottom: '1rem' }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" style={{ color: 'var(--color-emergency-red-dark)' }}>
                Required Blood Group
              </label>
              <select
                className="form-select"
                value={bloodGroup}
                onChange={(e) => setBloodGroup(e.target.value)}
              >
                {['O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+'].map((bg) => (
                  <option key={bg} value={bg}>{bg}</option>
                ))}
              </select>
            </div>

            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" style={{ color: 'var(--color-emergency-red-dark)' }}>
                Units Required
              </label>
              <input
                type="number"
                min="1"
                max="20"
                className="form-input"
                value={unitsRequired}
                onChange={(e) => setUnitsRequired(parseInt(e.target.value, 10) || 1)}
              />
            </div>
          </div>
        )}

        {/* Dynamic Fields for Organ Emergency */}
        {type === 'organ' && (
          <div style={{ padding: '1rem', backgroundColor: 'var(--color-orange-accent-light)', borderRadius: 'var(--radius-md)', marginBottom: '1rem' }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" style={{ color: 'var(--color-orange-accent)' }}>
                Target Organ Type
              </label>
              <select
                className="form-select"
                value={organType}
                onChange={(e) => setOrganType(e.target.value)}
              >
                <option value="kidney">Kidney (Cold Ischemic Max: 36h)</option>
                <option value="liver">Liver (Cold Ischemic Max: 12h)</option>
                <option value="heart">Heart (Cold Ischemic Max: 6h)</option>
                <option value="lungs">Lungs (Cold Ischemic Max: 8h)</option>
                <option value="pancreas">Pancreas (Cold Ischemic Max: 18h)</option>
              </select>
            </div>
          </div>
        )}

        {/* Clinical Case Description */}
        <div className="form-group">
          <label className="form-label">Clinical Description & Case Notes</label>
          <textarea
            className="form-textarea"
            rows={3}
            placeholder="e.g. Acute hemorrhagic trauma patient admitted to Emergency Bay #3. Immediate crossmatched units required."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
          />
        </div>

        {/* Manual GPS Verification */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="form-group">
            <label className="form-label" style={{ fontSize: '0.75rem' }}>Latitude Coordinates</label>
            <input
              type="number"
              step="any"
              className="form-input"
              value={locationLat}
              onChange={(e) => setLocationLat(parseFloat(e.target.value))}
            />
          </div>
          <div className="form-group">
            <label className="form-label" style={{ fontSize: '0.75rem' }}>Longitude Coordinates</label>
            <input
              type="number"
              step="any"
              className="form-input"
              value={locationLng}
              onChange={(e) => setLocationLng(parseFloat(e.target.value))}
            />
          </div>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.5rem' }}>
          <button type="button" onClick={onClose} className="btn btn-secondary" disabled={isSubmitting}>
            Cancel
          </button>
          <button type="submit" className="btn btn-danger" disabled={isSubmitting}>
            {isSubmitting ? 'Registering SOS...' : 'Broadcast Emergency SOS'}
          </button>
        </div>
      </form>
    </Modal>
  );
};
