from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Form, File, UploadFile, Query
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
from uuid import UUID, uuid4
from datetime import datetime

import os
import shutil
import models
import schemas
import auth
import json
from database import engine, get_db

# Création des tables dans PostgreSQL (à lancer une fois)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="API Trouve toi un job", version="1.0")

origins = [
    "http://localhost:5173", # On garde ça pour que ça marche toujours quand tu codes sur ta machine
    "https://trouve-toi-un-job-frontend.vercel.app", # <-- AJOUTE CETTE LIGNE EXACTEMENT (sans le / à la fin)
]

# Configuration des CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # Le port par défaut de Vite/React
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        # Dictionnaire pour stocker les connexions actives : {user_id: websocket}
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: str):
        if user_id in self.active_connections:
            websocket = self.active_connections[user_id]
            await websocket.send_text(json.dumps(message))

manager = ConnectionManager()

# --- ROUTES CRUD POUR LES CATÉGORIES ---
@app.post("/categories/", response_model=schemas.CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(category: schemas.CategoryCreate, db: Session = Depends(get_db)):
    """Créer une nouvelle catégorie."""
    db_category = models.Category(**category.model_dump())
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

@app.get("/categories/", response_model=List[schemas.CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    """Lister toutes les catégories."""
    return db.query(models.Category).all()

@app.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: UUID, db: Session = Depends(get_db)):
    """Supprimer une catégorie."""
    db_category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not db_category:
        raise HTTPException(status_code=404, detail="Catégorie non trouvée")
    
    db.delete(db_category)
    db.commit()
    return None

# --- ROUTES CRUD POUR LES JOBS ---

@app.post("/jobs/", response_model=schemas.JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    job: schemas.JobCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user) # <- MAGIE ICI !
):
    """Créer une annonce de job (Réservé aux utilisateurs connectés)"""
    
    # Plus besoin de demander le client_id, on l'associe à l'utilisateur connecté
    db_job = models.Job(
        **job.model_dump(exclude={"client_id"}), # Assure-toi de retirer client_id de JobCreate dans schemas.py
        client_id=current_user.id 
    )
    
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

@app.get("/jobs/", response_model=List[schemas.JobOut])
def list_jobs(
    skip: int = 0, 
    limit: int = 50, 
    status: str = "open",
    location: Optional[str] = None,
    category: Optional[str] = None,
    job_type: Optional[str] = None,
    min_salary: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Récupérer la liste des jobs (avec pagination, filtre de statut et recherche multicritères)."""
    
    # On commence par la requête de base avec le filtre de statut
    query = db.query(models.Job).filter(models.Job.status == status)
    
    # On applique les filtres dynamiques s'ils sont renseignés
    if location:
        # ilike est parfait avec PostgreSQL pour ignorer les majuscules/minuscules
        query = query.filter(models.Job.location.ilike(f"%{location}%"))
    if category:
        query = query.filter(models.Job.category == category)
    if job_type:
        query = query.filter(models.Job.job_type == job_type)
    if min_salary is not None:
        query = query.filter(models.Job.salary >= min_salary)

    # On termine par la pagination et l'exécution
    jobs = query.offset(skip).limit(limit).all()
    return jobs

@app.get("/jobs/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    """Récupérer les détails d'un job spécifique."""
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    return job

@app.patch("/jobs/{job_id}", response_model=schemas.JobOut)
def update_job(job_id: UUID, job_update: schemas.JobUpdate, db: Session = Depends(get_db)):
    """Mettre à jour partiellement un job existant."""
    db_job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    
    # Mise à jour uniquement des champs fournis
    update_data = job_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_job, key, value)
        
    db.commit()
    db.refresh(db_job)
    return db_job

@app.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: UUID, db: Session = Depends(get_db)):
    """Supprimer un job."""
    db_job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    
    db.delete(db_job)
    db.commit()
    return None

# Créer le dossier d'upload s'il n'existe pas
os.makedirs("uploads", exist_ok=True)

# Monter le dossier statique pour servir les images
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone_number: str = Form(...),
    age: int = Form(...),
    location: str = Form(...),
    password: str = Form(...),
    role: str = Form("client"),
    specialty: str = Form(None),  # <-- NOUVEAU CHAMP ICI
    profile_photo: UploadFile = File(None),
    company_photo: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # 1. Vérification si le téléphone existe déjà
    db_user = db.query(models.User).filter(models.User.phone_number == phone_number).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Ce numéro de téléphone est déjà utilisé.")
    
    # 2. RÈGLE MÉTIER : La photo de profil est obligatoire pour les prestataires
    if role == "provider" and not profile_photo:
        raise HTTPException(
            status_code=400, 
            detail="La photo de profil est obligatoire pour s'inscrire en tant que prestataire."
        )

    # Fonction utilitaire pour sauvegarder le fichier
    def save_image(file: UploadFile) -> str:
        file_location = f"uploads/{datetime.now().timestamp()}_{file.filename}"
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return f"/{file_location}"

    profile_photo_path = save_image(profile_photo) if profile_photo else None
    company_photo_path = save_image(company_photo) if company_photo and role == "client" else None

    # 3. Enregistrement
    hashed_password = auth.get_password_hash(password)
    
    new_user = models.User(
        phone_number=phone_number,
        password_hash=hashed_password,
        first_name=first_name,
        last_name=last_name,
        age=age,
        location=location,
        role=role,
        specialty=specialty if role == "provider" else None,  # <-- ENREGISTREMENT ICI
        profile_photo=profile_photo_path,
        company_photo=company_photo_path
    )
    db.add(new_user)
    db.commit()
    return {"message": "Utilisateur créé avec succès"}

@app.post("/login")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Chercher l'utilisateur par son numéro de téléphone (via form_data.username)
    user = db.query(models.User).filter(models.User.phone_number == form_data.username).first()
    
    # Vérifier le mot de passe
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Numéro de téléphone ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Générer le token JWT en utilisant le numéro de téléphone comme identifiant
    access_token = auth.create_access_token(data={"sub": user.phone_number})
    return {"access_token": access_token, "token_type": "bearer"}

# --- ROUTES POUR LES CANDIDATURES (APPLICATIONS) ---

@app.post("/applications/", response_model=schemas.ApplicationOut)
def apply_to_job(
    application: schemas.ApplicationCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # 1. Vérifier si le job existe et est ouvert
    job = db.query(models.Job).filter(models.Job.id == application.job_id).first()
    if not job or job.status != "open":
        raise HTTPException(status_code=400, detail="Ce job n'est plus disponible.")
    
    # 2. Vérifier si l'utilisateur est bien un prestataire (optionnel selon ta logique)
    if current_user.role != "provider" and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Seuls les prestataires peuvent postuler.")

    # 3. Empêcher de postuler deux fois au même job
    existing_app = db.query(models.Application).filter(
        models.Application.job_id == application.job_id,
        models.Application.provider_id == current_user.id
    ).first()
    if existing_app:
        raise HTTPException(status_code=400, detail="Vous avez déjà postulé à ce job.")

    new_app = models.Application(
        **application.model_dump(),
        provider_id=current_user.id
    )
    db.add(new_app)
    db.commit()
    db.refresh(new_app)
    return new_app

@app.get("/jobs/{job_id}/applications", response_model=List[schemas.ApplicationOut])
def get_job_applications(
    job_id: UUID, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Permet au client de voir qui a postulé à son job."""
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    
    # Sécurité : Seul le créateur du job peut voir les candidatures
    if job.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès refusé.")
    
    return job.applications

@app.patch("/applications/{app_id}/accept")
def accept_application(
    app_id: UUID, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Accepter une candidature et passer le job en 'in_progress'."""
    application = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Candidature non trouvée")
    
    # Vérifier que l'utilisateur est bien le propriétaire du job lié
    if application.job.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Action non autorisée.")

    # Mettre à jour la candidature
    application.status = "accepted"
    # Mettre à jour le statut du job automatiquement
    application.job.status = "in_progress"
    
    # Rejeter automatiquement les autres candidatures pour ce job (Optionnel)
    other_apps = db.query(models.Application).filter(
        models.Application.job_id == application.job_id,
        models.Application.id != app_id
    ).all()
    for other in other_apps:
        other.status = "rejected"

    db.commit()
    return {"message": "Candidature acceptée, le job est maintenant en cours."}

# --- ROUTES POUR LES AVIS (REVIEWS) ---

@app.post("/reviews/", response_model=schemas.ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    review: schemas.ReviewCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Laisser un avis à la fin d'une mission."""
    
    # 1. Vérifier que le job existe
    job = db.query(models.Job).filter(models.Job.id == review.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé.")

    # 2. On ne peut évaluer qu'une fois la mission terminée
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Vous ne pouvez évaluer qu'une mission terminée.")

    # 3. Interdiction de s'auto-évaluer
    if current_user.id == review.reviewee_id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas vous évaluer vous-même.")

    # 4. Vérifier qui a le droit de laisser un avis (Client ou Prestataire validé)
    accepted_app = db.query(models.Application).filter(
        models.Application.job_id == job.id,
        models.Application.status == "accepted"
    ).first()

    if not accepted_app:
        raise HTTPException(status_code=400, detail="Personne n'a été validé pour cette mission.")

    participants_valides = [job.client_id, accepted_app.provider_id]

    if current_user.id not in participants_valides:
        raise HTTPException(status_code=403, detail="Vous n'avez pas participé à cette mission.")
        
    if review.reviewee_id not in participants_valides:
        raise HTTPException(status_code=400, detail="L'utilisateur évalué ne fait pas partie de cette mission.")

    # 5. Bloquer les avis multiples
    existing_review = db.query(models.Review).filter(
        models.Review.job_id == review.job_id,
        models.Review.reviewer_id == current_user.id
    ).first()

    if existing_review:
        raise HTTPException(status_code=400, detail="Vous avez déjà laissé un avis pour cette mission.")

    # Si tout est bon, on sauvegarde !
    new_review = models.Review(
        **review.model_dump(),
        reviewer_id=current_user.id
    )
    db.add(new_review)
    db.commit()
    db.refresh(new_review)
    return new_review

@app.get("/users/{user_id}/reviews", response_model=List[schemas.ReviewOut])
def get_user_reviews(user_id: UUID, db: Session = Depends(get_db)):
    """Consulter tous les avis reçus par un utilisateur spécifique (pour afficher sur son profil)."""
    reviews = db.query(models.Review).filter(models.Review.reviewee_id == user_id).all()
    return reviews

@app.get("/users/me")
def read_users_me(current_user = Depends(auth.get_current_user)):
    """
    Retourne les informations de l'utilisateur actuellement connecté
    grâce à son token JWT.
    """
    return current_user

@app.get("/users/me/jobs")
def get_my_jobs(current_user = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    # Ici, on récupère TOUS les jobs du client, sans filtrer par statut "open"
    return db.query(models.Job).filter(models.Job.client_id == current_user.id).all()


@app.get("/users/me/applications")
def get_my_applications(current_user = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """
    Retourne toutes les candidatures envoyées par le prestataire connecté.
    """
    # Assure-toi d'utiliser le bon nom de modèle (ex: models.Application)
    return db.query(models.Application).filter(models.Application.provider_id == current_user.id).all()

@app.get("/users/me/profile", response_model=schemas.UserProfileOut)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Récupère le profil complet de l'utilisateur connecté avec ses avis reçus."""
    reviews = db.query(models.Review).filter(models.Review.reviewee_id == current_user.id).all()
    
    # Calcul de la moyenne des notes
    avg_rating = sum(r.rating for r in reviews) / len(reviews) if reviews else 0.0

    return {
        "id": current_user.id,
        "first_name": getattr(current_user, "first_name", ""),
        "last_name": getattr(current_user, "last_name", ""),
        "role": current_user.role,
        "profile_photo": getattr(current_user, "profile_photo", None),
        "company_photo": getattr(current_user, "company_photo", None),
        "created_at": current_user.created_at,
        "reviews": reviews,
        "average_rating": round(avg_rating, 1)
    }

@app.put("/users/me/profile")
async def update_profile(
    profile_data: schemas.UserProfileUpdate, # Assure-toi que c'est le bon schéma
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Mise à jour des champs
    if profile_data.first_name is not None:
        current_user.first_name = profile_data.first_name
    if profile_data.last_name is not None:
        current_user.last_name = profile_data.last_name
        
    # Les nouveaux champs d'image
    if profile_data.profile_photo is not None:
        current_user.profile_photo = profile_data.profile_photo
    if profile_data.company_photo is not None:
        current_user.company_photo = profile_data.company_photo

    db.commit()
    db.refresh(current_user)
    return current_user

# 1. Créer le dossier 'uploads' s'il n'existe pas
os.makedirs("uploads", exist_ok=True)

# 2. Rendre le dossier 'uploads' accessible publiquement via HTTP
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# 3. Route pour téléverser une image (avatar ou couverture)
@app.post("/users/me/upload-image")
async def upload_user_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Reçoit un fichier image, le sauvegarde localement et retourne son URL."""
    # Extrait l'extension du fichier original (.jpg, .png, etc.)
    file_extension = os.path.splitext(file.filename)[1]
    
    # Génère un nom de fichier unique pour éviter les conflits
    unique_filename = f"{uuid4().hex}{file_extension}"
    file_path = os.path.join("uploads", unique_filename)
    
    # Sauvegarde du fichier sur le disque
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Retourne l'URL publique de l'image
    image_url = f"http://127.0.0.1:8000/uploads/{unique_filename}"
    return {"url": image_url}
    
@app.get("/providers", response_model=List[schemas.UserOut])
def search_providers(
    specialty: Optional[str] = Query(None, description="Filtrer par spécialité"),
    location: Optional[str] = Query(None, description="Filtrer par ville/localisation"),
    min_age: Optional[int] = Query(None, description="Âge minimum"),
    max_age: Optional[int] = Query(None, description="Âge maximum"),
    db: Session = Depends(get_db)
):
    # On ne récupère que les utilisateurs ayant le rôle "provider"
    query = db.query(models.User).filter(models.User.role == "provider")

    # Application des filtres de manière dynamique (insensible à la casse)
    if specialty:
        query = query.filter(models.User.specialty.ilike(f"%{specialty}%"))
        
    if location:
        query = query.filter(models.User.location.ilike(f"%{location}%"))
        
    if min_age is not None:
        query = query.filter(models.User.age >= min_age)
        
    if max_age is not None:
        query = query.filter(models.User.age <= max_age)

    return query.all()

# 1. Créer ou récupérer une conversation existante
@app.post("/conversations/", response_model=schemas.ConversationOut)
def create_conversation(conv: schemas.ConversationCreate, db: Session = Depends(get_db), current_user = Depends(auth.get_current_user)):
    # Vérifier si une conversation existe déjà pour ce duo sur ce job
    existing_conv = db.query(models.Conversation).filter(
        models.Conversation.job_id == conv.job_id,
        models.Conversation.provider_id == conv.provider_id,
        models.Conversation.client_id == current_user.id
    ).first()

    if existing_conv:
        return existing_conv

    # Sinon, on la crée
    new_conv = models.Conversation(
        job_id=conv.job_id,
        client_id=current_user.id,
        provider_id=conv.provider_id
    )
    db.add(new_conv)
    db.commit()
    db.refresh(new_conv)
    return new_conv

# 2. Lister les conversations de l'utilisateur connecté
@app.get("/conversations/", response_model=list[schemas.ConversationOut])
def get_user_conversations(db: Session = Depends(get_db), current_user = Depends(auth.get_current_user)):
    conversations = db.query(models.Conversation).filter(
        or_(
            models.Conversation.client_id == current_user.id,
            models.Conversation.provider_id == current_user.id
        )
    ).all()

    # NOUVEAU : On ajoute le compteur de non lus pour chaque conversation
    for conv in conversations:
        conv.unread_count = db.query(models.Message).filter(
            models.Message.conversation_id == conv.id,
            models.Message.sender_id != current_user.id, # Message envoyé par l'autre
            models.Message.is_read == False              # Message non lu
        ).count()

    return conversations

# 3. Récupérer les messages d'une conversation précise ET les marquer comme lus
@app.get("/conversations/{conversation_id}/messages", response_model=list[schemas.MessageOut])
def get_messages(conversation_id: str, db: Session = Depends(get_db), current_user = Depends(auth.get_current_user)):
    
    # 1. On récupère tous les messages pour l'affichage
    messages = db.query(models.Message).filter(
        models.Message.conversation_id == conversation_id
    ).order_by(models.Message.created_at.asc()).all()

    # 2. On cible les messages non lus envoyés par l'autre personne
    unread_messages = db.query(models.Message).filter(
        models.Message.conversation_id == conversation_id,
        models.Message.sender_id != current_user.id,
        models.Message.is_read == False
    ).all()

    # 3. S'il y a des messages non lus, on les passe à True et on sauvegarde
    if unread_messages:
        for msg in unread_messages:
            msg.is_read = True
        db.commit()

    return messages

@app.websocket("/ws/chat/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str, db: Session = Depends(get_db)):
    # 1. L'utilisateur se connecte
    await manager.connect(websocket, user_id)
    try:
        while True:
            # 2. On attend de recevoir un message depuis le Frontend React
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            conversation_id = message_data.get("conversation_id")
            receiver_id = message_data.get("receiver_id")
            content = message_data.get("content")

            # 3. On sauvegarde le message dans la base de données PostgreSQL
            new_message = models.Message(
                conversation_id=conversation_id,
                sender_id=user_id,
                content=content
            )
            db.add(new_message)
            db.commit()
            db.refresh(new_message)

            # 4. On prépare le message à renvoyer (pour l'affichage)
            msg_to_send = {
                "id": str(new_message.id),
                "conversation_id": str(new_message.conversation_id),
                "sender_id": str(new_message.sender_id),
                "content": new_message.content,
                "created_at": new_message.created_at.isoformat()
            }

            # 5. On envoie le message en direct au destinataire (s'il est connecté en ce moment)
            await manager.send_personal_message(msg_to_send, receiver_id)
            
            # Et on le renvoie aussi à l'expéditeur pour qu'il s'affiche dans son interface
            await manager.send_personal_message(msg_to_send, user_id)

    except WebSocketDisconnect:
        # Si l'utilisateur quitte la page, on le déconnecte du manager
        manager.disconnect(user_id)

# 4. Compter les messages non lus pour l'utilisateur connecté
@app.get("/conversations/unread-count")
def get_unread_messages_count(db: Session = Depends(get_db), current_user = Depends(auth.get_current_user)):
    unread_count = db.query(models.Message).join(models.Conversation).filter(
        # L'utilisateur fait partie de la conversation
        or_(
            models.Conversation.client_id == current_user.id,
            models.Conversation.provider_id == current_user.id
        ),
        # Le message n'a pas été envoyé par l'utilisateur connecté
        models.Message.sender_id != current_user.id,
        # Le message n'est pas encore lu
        models.Message.is_read == False
    ).count()

    return {"count": unread_count}