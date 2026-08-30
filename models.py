from sqlalchemy import Column, String, Text, Numeric, ForeignKey, Enum as SQLEnum, DateTime, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from database import Base
from sqlalchemy import CheckConstraint
import enum

class RoleEnum(str, enum.Enum):
    client = "client"
    provider = "provider"
    admin = "admin"

class JobStatusEnum(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number = Column(String, unique=True, index=True, nullable=False) # Remplace l'email
    password_hash = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    age = Column(Integer, nullable=False) # Nouveau champ
    location = Column(String, nullable=False) # Nouveau champ
    role = Column(SQLEnum(RoleEnum), default=RoleEnum.client)
    bio = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    profile_photo = Column(String, nullable=True)
    company_photo = Column(String, nullable=True)
    specialty = Column(String, nullable=True)

    # Relation : Un utilisateur peut poster plusieurs jobs
    jobs = relationship("Job", back_populates="owner")

class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)

    # Relation : Une catégorie peut avoir plusieurs jobs
    jobs = relationship("Job", backref="category")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id")) # Assure-toi d'avoir le modèle Category
    title = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=False)
    budget = Column(Numeric(10, 2), nullable=False)
    location = Column(String, nullable=False)
    status = Column(SQLEnum(JobStatusEnum), default=JobStatusEnum.open)
    created_at = Column(DateTime, default=datetime.utcnow)
    availability = Column(String)

    # Relation : Le job appartient à un utilisateur
    owner = relationship("User", back_populates="jobs")
    
class ApplicationStatusEnum(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"

class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    cover_message = Column(Text, nullable=False)
    proposed_price = Column(Numeric(10, 2), nullable=False)
    status = Column(SQLEnum(ApplicationStatusEnum), default=ApplicationStatusEnum.pending)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    job = relationship("Job", backref="applications")
    provider = relationship("User")
    
class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reviewee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # La note doit être un entier (ou Numeric si tu veux des demi-étoiles)
    rating = Column(Numeric(2, 1), nullable=False) 
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Contrainte au niveau de la base de données : la note doit être entre 1 et 5
    __table_args__ = (
        CheckConstraint('rating >= 1 AND rating <= 5', name='check_rating_range'),
    )

    # Relations pour naviguer facilement d'un objet à l'autre
    job = relationship("Job")
    # Comme on a deux clés étrangères vers la même table User, il faut le préciser à SQLAlchemy
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    reviewee = relationship("User", foreign_keys=[reviewee_id])
    
class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    job = relationship("Job")
    client = relationship("User", foreign_keys=[client_id])
    provider = relationship("User", foreign_keys=[provider_id])
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)

    # Relations
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User")