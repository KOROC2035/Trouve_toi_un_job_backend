from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from models import JobStatusEnum
import enum

# Base commune pour éviter la répétition
class JobBase(BaseModel):
    title: str = Field(..., example="Développeur Frontend React")
    description: str = Field(..., example="Besoin d'aide pour intégrer une maquette avec Tailwind V4.")
    budget: float = Field(..., gt=0, example=250.00)
    location: str = Field(..., example="Paris ou Remote")

# Schema pour la création (données attendues en POST)
class JobCreate(JobBase):
    category_id: UUID

# Schema pour la mise à jour (PATCH)
class JobUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    budget: Optional[float] = None
    status: Optional[JobStatusEnum] = None

# Schema pour la réponse de l'API (données renvoyées en GET/POST)
class JobOut(JobBase):
    id: UUID
    client_id: UUID
    category_id: UUID
    status: str
    created_at: datetime

    # Permet à Pydantic de lire les objets SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

# Schema pour l'authentification
class UserCreate(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    role: str = "client"
    
# --- SCHEMAS POUR CATEGORY ---
class CategoryBase(BaseModel):
    name: str = Field(..., example="Développement Web")
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryOut(CategoryBase):
    id: UUID
    
    model_config = ConfigDict(from_attributes=True)
    
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

    class Config:
        from_attributes = True
        
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