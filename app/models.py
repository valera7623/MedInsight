from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="doctor")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    patients: Mapped[list["Patient"]] = relationship("Patient", back_populates="owner")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="owner")
    predictions: Mapped[list["Prediction"]] = relationship("Prediction", back_populates="owner")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship("AnalysisJob", back_populates="owner")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str] = mapped_column(String(1), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    owner: Mapped["User"] = relationship("User", back_populates="patients")
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="patient", cascade="all, delete-orphan"
    )
    predictions: Mapped[list["Prediction"]] = relationship(
        "Prediction", back_populates="patient", cascade="all, delete-orphan"
    )
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob", back_populates="patient", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, default="discharge")
    parsed_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    patient: Mapped["Patient"] = relationship("Patient", back_populates="documents")
    owner: Mapped["User"] = relationship("User", back_populates="documents")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship("AnalysisJob", back_populates="document")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("documents.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    patient: Mapped["Patient"] = relationship("Patient", back_populates="analysis_jobs")
    owner: Mapped["User"] = relationship("User", back_populates="analysis_jobs")
    document: Mapped["Document | None"] = relationship("Document", back_populates="analysis_jobs")
    predictions: Mapped[list["Prediction"]] = relationship("Prediction", back_populates="analysis_job")


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    analysis_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("analysis_jobs.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="readmission")
    features: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prediction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    probabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    patient: Mapped["Patient"] = relationship("Patient", back_populates="predictions")
    owner: Mapped["User"] = relationship("User", back_populates="predictions")
    analysis_job: Mapped["AnalysisJob | None"] = relationship("AnalysisJob", back_populates="predictions")
