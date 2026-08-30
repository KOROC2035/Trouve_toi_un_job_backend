# auth.py
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
import models

# /!\ À stocker dans un fichier .env en production !
SECRET_KEY = "ta_cle_secrete_ultra_complexe_ici" 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # Token valide 7 jours

# Configuration du hachage des mots de passe
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Indique à FastAPI où se trouve la route de connexion (pour la doc Swagger)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- DÉPENDANCE CENTRALE ---
# Cette fonction sera injectée dans nos routes pour vérifier si l'utilisateur est connecté
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Identifiants invalides",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Décoder le token pour récupérer le numéro de téléphone
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        phone_number: str = payload.get("sub")
        if phone_number is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    # Chercher l'utilisateur dans la base de données via son numéro
    user = db.query(models.User).filter(models.User.phone_number == phone_number).first()
    if user is None:
        raise credentials_exception
    return user