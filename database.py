from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

# Remplace par tes identifiants PostgreSQL (ex: postgresql://user:password@localhost/dbname)
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("L'URL de la base de données (DATABASE_URL) n'est pas configurée dans le fichier .env")

# Ajout des paramètres pour éviter les erreurs "SSL SYSCALL error: EOF detected" sur Render
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dépendance pour obtenir la session de la base de données dans nos routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()