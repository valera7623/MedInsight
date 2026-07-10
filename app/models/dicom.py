"""ORM models — dicom."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.db.types import PortableJSON, PortableTSVector, PortableUUID, uuid_default
from app.models._time import utc_now


class DicomStudy(Base):
    """DICOM study metadata (Phase 12)."""

    __tablename__ = "dicom_studies"
    __table_args__ = (
        Index("ix_dicom_studies_patient_modality", "patient_id", "modality"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    study_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    study_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    study_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    body_part: Mapped[str | None] = mapped_column(String(128), nullable=True)
    patient_name_dicom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    patient_id_dicom: Mapped[str | None] = mapped_column(String(128), nullable=True)
    num_series: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_instances: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_path_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_vector: Mapped[str | None] = mapped_column(PortableTSVector, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    zip_original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    zip_size_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    radiology_findings: Mapped[list | None] = mapped_column(PortableJSON, nullable=True)
    radiology_impression: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_measurements: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    clinical_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    clinical_context_processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    patient: Mapped["Patient"] = relationship("Patient", foreign_keys=[patient_id])
    series: Mapped[list["DicomSeries"]] = relationship(
        "DicomSeries", back_populates="study", cascade="all, delete-orphan"
    )

class DicomSeries(Base):
    __tablename__ = "dicom_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    study_id: Mapped[int] = mapped_column(Integer, ForeignKey("dicom_studies.id"), nullable=False, index=True)
    series_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    series_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    series_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    num_instances: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    study: Mapped["DicomStudy"] = relationship("DicomStudy", back_populates="series")
    frames: Mapped[list["DicomFrame"]] = relationship(
        "DicomFrame", back_populates="series", cascade="all, delete-orphan"
    )

class DicomFrame(Base):
    __tablename__ = "dicom_frames"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    series_id: Mapped[int] = mapped_column(Integer, ForeignKey("dicom_series.id"), nullable=False, index=True)
    instance_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    frame_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bit_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pixel_spacing: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    series: Mapped["DicomSeries"] = relationship("DicomSeries", back_populates="frames")
    annotations: Mapped[list["DicomAnnotation"]] = relationship(
        "DicomAnnotation", back_populates="frame", cascade="all, delete-orphan"
    )

class DicomAnnotation(Base):
    """User-drawn markup on a DICOM frame (Phase 12c)."""

    __tablename__ = "dicom_annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    frame_id: Mapped[int] = mapped_column(Integer, ForeignKey("dicom_frames.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    coordinates: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#FF0000")
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    measurement_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    frame: Mapped["DicomFrame"] = relationship("DicomFrame", back_populates="annotations")

class DicomAnnotationSession(Base):
    """Tracks which frame a user last annotated (Phase 12c)."""

    __tablename__ = "dicom_annotation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    study_uid: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    series_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    frame_instance_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class AnnotationHistory(Base):
    """Undo/audit trail for annotation edits (Phase 12d)."""

    __tablename__ = "annotation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    annotation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dicom_annotations.id"), nullable=True, index=True
    )
    frame_id: Mapped[int] = mapped_column(Integer, ForeignKey("dicom_frames.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    before_state: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
