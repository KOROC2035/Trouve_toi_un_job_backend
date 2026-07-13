from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from uuid import UUID

import models
import schemas
import auth
from database import engine, get_db

# Création des tables dans PostgreSQL (à lancer une fois)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="API Trouve toi un job", version="1.0")

# Configuration des CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], # Le port par défaut de Vite/React
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
def list_jobs(skip: int = 0, limit: int = 50, status: str = "open", db: Session = Depends(get_db)):
    """Récupérer la liste des jobs (avec pagination et filtre de statut)."""
    jobs = db.query(models.Job).filter(models.Job.status == status).offset(skip).limit(limit).all()
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

@app.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Vérifier si l'email existe déjà
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé.")
    
    # Hasher le mot de passe avant de sauvegarder
    hashed_password = auth.get_password_hash(user.password)
    
    new_user = models.User(
        email=user.email,
        password_hash=hashed_password,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role
    )
    db.add(new_user)
    db.commit()
    return {"message": "Utilisateur créé avec succès"}

@app.post("/login")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Chercher l'utilisateur
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    
    # Vérifier le mot de passe
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Générer le token JWT
    access_token = auth.create_access_token(data={"sub": user.email})
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