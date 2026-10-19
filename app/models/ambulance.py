from sqlalchemy import String, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Ambulance(Base):
    __tablename__ = "ambulances"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    unit_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False) # AMB-042
    status: Mapped[str] = mapped_column(String(30), default="idle", index=True) # idle, dispatched, en_route, on_scene, transporting, at_hospital, returning, offline
    driver_name: Mapped[str] = mapped_column(String(100), nullable=True)
    origin: Mapped[str] = mapped_column(String(150), nullable=True)
    destination: Mapped[str] = mapped_column(String(150), nullable=True)
    
    lat: Mapped[float] = mapped_column(Float, nullable=True)
    lng: Mapped[float] = mapped_column(Float, nullable=True)
    heading: Mapped[float] = mapped_column(Float, nullable=True)
    
    speed_kmh: Mapped[float] = mapped_column(Float, nullable=True)
    eta_minutes: Mapped[int] = mapped_column(Integer, nullable=True)
    
    routes_json: Mapped[str] = mapped_column(Text, nullable=True)
    selected_route_id: Mapped[str] = mapped_column(String(50), nullable=True)
    
    hospital_id: Mapped[str] = mapped_column(String(50), ForeignKey("hospitals.id", ondelete="RESTRICT"), nullable=False, index=True)
    emergency_id: Mapped[str] = mapped_column(String(50), ForeignKey("emergencies.id", ondelete="SET NULL"), nullable=True, index=True)
    
    dispatched_at: Mapped[str] = mapped_column(String(50), nullable=True)
    arrived_at: Mapped[str] = mapped_column(String(50), nullable=True)
    telemetry_source: Mapped[str] = mapped_column(String(30), default="operator_manual", nullable=True) # live_gps, simulated, operator_manual
    last_telemetry_at: Mapped[str] = mapped_column(String(50), nullable=True)
    device_id: Mapped[str] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(50), nullable=False)
