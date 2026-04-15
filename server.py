from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db

app = FastAPI()


class UserCreate(BaseModel):
    nom: str
    edat: int
    independent: bool = True


@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT id_usuari, nom, edat, independent
        FROM usuari
        ORDER BY id_usuari
    """))

    users = []
    for row in result:
        users.append({
            "id_usuari": row.id_usuari,
            "nom": row.nom,
            "edat": row.edat,
            "independent": row.independent
        })

    return users


@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            SELECT id_usuari, nom, edat, independent
            FROM usuari
            WHERE id_usuari = :user_id
        """),
        {"user_id": user_id}
    )

    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return {
        "id_usuari": row.id_usuari,
        "nom": row.nom,
        "edat": row.edat,
        "independent": row.independent
    }


@app.post("/users")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            INSERT INTO usuari (nom, edat, independent)
            VALUES (:nom, :edat, :independent)
            RETURNING id_usuari, nom, edat, independent
        """),
        {
            "nom": user.nom,
            "edat": user.edat,
            "independent": user.independent
        }
    )

    row = result.fetchone()
    db.commit()

    return {
        "id_usuari": row.id_usuari,
        "nom": row.nom,
        "edat": row.edat,
        "independent": row.independent
    }


@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            DELETE FROM usuari
            WHERE id_usuari = :user_id
        """),
        {"user_id": user_id}
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return {"status": "deleted"}