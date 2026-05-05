import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Preferimos leer la conexión desde variable de entorno.
# En local puedes usar tu usuario/password. En el servidor pon la URL real de PostgreSQL.
# Ejemplo:
# export DATABASE_URL="postgresql+psycopg2://USUARIO:PASSWORD@localhost:5432/NOMBRE_BD"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:virvig@localhost:5432/tea_vr"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
