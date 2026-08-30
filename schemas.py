from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from models import JobStatusEnum
import enum

# --- SCHEMAS POUR USER ---
class UserBase(BaseModel):
    last_name: str = Field(..., example="Kouassi")
    first_name: str = Field(..., example="Jean")
    age: int = Field(..., ge=16, example=25)
    location: str = Field(..., example="Abidjan")
    phone_number: str = Field(..., example="+2250700000000")
    specialty: Optional[str] = None
    role: Optional[str] = "client"
    profile_photo: Optional[str] = None
    company_photo: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=6, example="MotDePasseSecurise123")

class UserOut(UserBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- SCHEMAS POUR JOB ---
class JobBase(BaseModel):
    title: str = Field(..., example="Développeur Frontend React")
    description: str = Field(..., example="Besoin d'aide pour intégrer une maquette avec Tailwind V4.")
    budget: float = Field(..., gt=0, example=250.00)
    location: str = Field(..., example="Abidjan ou Remote")
    availability: Optional[str] = None

class JobCreate(JobBase):
    category_id: UUID

class JobUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    budget: Optional[float] = None
    status: Optional[JobStatusEnum] = None

class JobOut(JobBase):
    id: UUID
    client_id: UUID
    category_id: Optional[UUID] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- SCHEMAS POUR CATEGORY ---
class CategoryBase(BaseModel):
    name: str = Field(..., example="Développement Web")
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryOut(CategoryBase):
    id: UUID
    
    model_config = ConfigDict(from_attributes=True)

# --- SCHEMAS POUR APPLICATION ---
class ApplicationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"

class ApplicationCreate(BaseModel):
    job_id: UUID
    cover_message: str = Field(..., min_length=10)
    proposed_price: float = Field(..., gt=0)

class ApplicationOut(BaseModel):
    id: UUID
    job_id: UUID
    provider_id: UUID
    cover_message: str
    proposed_price: float
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- SCHEMAS POUR REVIEW ---
class ReviewCreate(BaseModel):
    job_id: UUID
    reviewee_id: UUID
    rating: int = Field(..., ge=1, le=5, description="La note doit être entre 1 et 5")
    comment: Optional[str] = None

class ReviewOut(BaseModel):
    id: UUID
    job_id: UUID
    reviewer_id: UUID
    reviewee_id: UUID
    rating: float
    comment: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- SCHÉMA POUR LE PROFIL UTILISATEUR COMPLET ---

class UserProfileOut(BaseModel):
    id: UUID
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    role: str
    profile_photo: Optional[str] = None
    company_photo: Optional[str] = None
    created_at: Optional[datetime] = None
    reviews: List[ReviewOut] = []
    average_rating: float = 0.0

    class Config:
        from_attributes = True  # (Si tu es sur Pydantic v2) ou orm_mode = True (sur Pydantic v1)

class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_photo: Optional[str] = None
    company_photo: Optional[str] = None

# 1. Ajoute ce mini-schéma pour filtrer les infos publiques du profil
class UserMessageInfo(BaseModel):
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_photo: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# --- SCHEMAS POUR LA MESSAGERIE ---
class MessageBase(BaseModel):
    content: str = Field(..., example="Bonjour, je suis très intéressé par votre mission.")

class MessageCreate(MessageBase):
    pass

class MessageOut(MessageBase):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    created_at: datetime
    is_read: bool
    
    # 2. Ajoute la relation ici. Pydantic lira automatiquement "message.sender" depuis SQLAlchemy
    sender: UserMessageInfo

    model_config = ConfigDict(from_attributes=True)

class ConversationCreate(BaseModel):
    job_id: UUID
    provider_id: UUID

class ConversationOut(BaseModel):
    id: UUID
    job_id: UUID
    client_id: UUID
    provider_id: UUID
    created_at: datetime
    messages: List[MessageOut] = []
    client: Optional[UserMessageInfo] = None
    provider: Optional[UserMessageInfo] = None

    model_config = ConfigDict(from_attributes=True)