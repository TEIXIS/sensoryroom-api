from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db

app = FastAPI(title="Sensory Room API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Helpers
# ============================================================

def rows_to_dicts(result):
    return [dict(row) for row in result.mappings().all()]


def one_row_or_404(result, message: str):
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=message)
    return dict(row)

def model_to_dict(model, **kwargs):
    # Compatible con Pydantic v1 y v2
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


def get_table_columns(db: Session, table_name: str):
    result = db.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table_name
        """),
        {"table_name": table_name},
    )
    return {row[0] for row in result.fetchall()}


def existing_fields(data: dict, columns: set, allowed_fields: List[str]):
    return {
        field: data[field]
        for field in allowed_fields
        if field in columns and field in data and data[field] is not None
    }


def update_optional_fields(db: Session, table_name: str, id_column: str, row_id: int, fields: dict):
    if not fields:
        return

    assignments = ", ".join(f"{field} = :{field}" for field in fields)
    params = dict(fields)
    params["row_id"] = row_id
    db.execute(
        text(f"""
            UPDATE {table_name}
            SET {assignments}
            WHERE {id_column} = :row_id
        """),
        params,
    )


def get_latest_session_config_event(db: Session, session_id: int):
    columns = get_table_columns(db, "sessio_configuracio_event")
    if not {"id_sessio", "moment"}.issubset(columns):
        return None

    result = db.execute(
        text("""
            SELECT id_event, id_sessio, moment,
                   postura_actual, menu_mans_actiu, particules_mans_actives
            FROM sessio_configuracio_event
            WHERE id_sessio = :session_id
            ORDER BY moment DESC, id_event DESC
            LIMIT 1
        """),
        {"session_id": session_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


def insert_session_config_event(
    db: Session,
    session_id: int,
    postura_actual=None,
    menu_mans_actiu=None,
    particules_mans_actives=None,
):
    columns = get_table_columns(db, "sessio_configuracio_event")
    if "id_sessio" not in columns:
        return None

    fields = ["id_sessio"]
    params = {"id_sessio": session_id}
    optional_values = {
        "postura_actual": postura_actual,
        "menu_mans_actiu": menu_mans_actiu,
        "particules_mans_actives": particules_mans_actives,
    }
    for field, value in optional_values.items():
        if field in columns and value is not None:
            fields.append(field)
            params[field] = value

    field_sql = ", ".join(fields)
    value_sql = ", ".join(f":{field}" for field in fields)
    returning_fields = [
        field
        for field in ["id_event", "id_sessio", "moment", "postura_actual", "menu_mans_actiu", "particules_mans_actives"]
        if field in columns
    ]
    returning_sql = ", ".join(returning_fields) if returning_fields else "id_sessio"

    result = db.execute(
        text(f"""
            INSERT INTO sessio_configuracio_event ({field_sql})
            VALUES ({value_sql})
            RETURNING {returning_sql}
        """),
        params,
    )
    row = result.mappings().first()
    return dict(row) if row else None


def first_not_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


def get_final_vr_elements(db: Session, session_id: int):
    result = db.execute(
        text("""
            SELECT id_vr_element, id_sessio, id_element, numero_posicio,
                   inici, fi, durada_segons, valoracio_professional, comentari
            FROM (
                SELECT DISTINCT ON (numero_posicio)
                       id_vr_element, id_sessio, id_element, numero_posicio,
                       inici, fi, durada_segons, valoracio_professional, comentari
                FROM sessio_vr_element
                WHERE id_sessio = :session_id
                  AND numero_posicio BETWEEN 1 AND 6
                ORDER BY numero_posicio, id_vr_element DESC
            ) ultims_slots
            ORDER BY numero_posicio
        """),
        {"session_id": session_id},
    )
    return rows_to_dicts(result)



# ============================================================
# Schemas / Models
# ============================================================

class UserCreate(BaseModel):
    nom: str = Field(..., min_length=1, max_length=100)
    independent: bool = False
    entorn_adult: bool = False
    menu_mans_actiu: bool = True
    particules_mans_actives: bool = True


class UserUpdate(BaseModel):
    nom: Optional[str] = Field(None, min_length=1, max_length=100)
    independent: Optional[bool] = None
    entorn_adult: Optional[bool] = None
    menu_mans_actiu: Optional[bool] = None
    particules_mans_actives: Optional[bool] = None
    actiu: Optional[bool] = None


class ConfiguracioPredeterminadaIn(BaseModel):
    nom_configuracio: str = "Configuració per defecte"
    intensitat_llum: Optional[float] = None
    color_llum_r: Optional[int] = Field(None, ge=0, le=255)
    color_llum_g: Optional[int] = Field(None, ge=0, le=255)
    color_llum_b: Optional[int] = Field(None, ge=0, le=255)
    intensitat_so: Optional[float] = None
    menu_mans_actiu: bool = True
    particules_mans_actives: bool = True


class SessionCreate(BaseModel):
    id_usuari: int
    postura_inicial: Optional[str] = None
    menu_mans_actiu: Optional[bool] = None
    particules_mans_actives: Optional[bool] = None
    observacions: Optional[str] = None


class SessionUpdate(BaseModel):
    durada_total_segons: Optional[float] = None
    durada_tutorial_segons: Optional[float] = None
    durada_preparacio_segons: Optional[float] = None
    durada_vr_segons: Optional[float] = None
    ha_entrat_tutorial: Optional[bool] = None
    ha_entrat_preparacio: Optional[bool] = None
    ha_entrat_vr: Optional[bool] = None
    postura_inicial: Optional[str] = None
    postura_final: Optional[str] = None
    postura_actual: Optional[str] = None
    menu_mans_actiu: Optional[bool] = None
    particules_mans_actives: Optional[bool] = None
    observacions: Optional[str] = None


class SessionFinish(BaseModel):
    durada_total_segons: float = 0
    durada_tutorial_segons: float = 0
    durada_preparacio_segons: float = 0
    durada_vr_segons: float = 0
    ha_entrat_tutorial: bool = False
    ha_entrat_preparacio: bool = False
    ha_entrat_vr: bool = False
    postura_final: Optional[str] = None
    observacions: Optional[str] = None


class SessionSettingsUpdate(BaseModel):
    postura_actual: Optional[str] = None
    menu_mans_actiu: Optional[bool] = None
    particules_mans_actives: Optional[bool] = None


class FaseCreate(BaseModel):
    fase: str = Field(..., min_length=1, max_length=30)  # tutorial, preparacio, vr, etc.
    durada_segons: float = 0


class EndDurationIn(BaseModel):
    durada_segons: float = 0


class ElementPoseIn(BaseModel):
    posicio_x: Optional[float] = None
    posicio_y: Optional[float] = None
    posicio_z: Optional[float] = None
    rotacio_y: Optional[float] = None


class TutorialElementIn(BaseModel):
    id_element: str = Field(..., min_length=1, max_length=100)
    durada_segons: float = 0
    valoracio_professional: Optional[int] = None
    comentari: Optional[str] = None


class PreparacioElementIn(BaseModel):
    id_element: str = Field(..., min_length=1, max_length=100)
    seleccionat: bool = True
    durada_segons: float = 0
    valoracio_professional: Optional[int] = None
    comentari: Optional[str] = None


class VRElementIn(BaseModel):
    id_element: str = Field(..., min_length=1, max_length=100)
    numero_posicio: int = Field(..., ge=1, le=6)
    durada_segons: float = 0
    valoracio_professional: Optional[int] = None
    comentari: Optional[str] = None


class CompleteSessionPayload(BaseModel):
    sessio: SessionFinish
    fases: List[FaseCreate] = []
    tutorial_elements: List[TutorialElementIn] = []
    preparacio_elements: List[PreparacioElementIn] = []
    vr_elements: List[VRElementIn] = []


# ============================================================
# Health check
# ============================================================

@app.get("/")
def root():
    return {"status": "ok", "service": "Sensory Room API"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


# ============================================================
# Users
# ============================================================

@app.get("/users")
def get_users(include_inactive: bool = False, db: Session = Depends(get_db)):
    sql = """
        SELECT id_usuari, nom, independent, entorn_adult,
               menu_mans_actiu, particules_mans_actives, actiu,
               creat_a, actualitzat_a
        FROM usuari
    """
    if not include_inactive:
        sql += " WHERE actiu = TRUE"
    sql += " ORDER BY id_usuari"

    return rows_to_dicts(db.execute(text(sql)))


@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            SELECT id_usuari, nom, independent, entorn_adult,
                   menu_mans_actiu, particules_mans_actives, actiu,
                   creat_a, actualitzat_a
            FROM usuari
            WHERE id_usuari = :user_id
        """),
        {"user_id": user_id},
    )
    return one_row_or_404(result, "Usuario no encontrado")


@app.post("/users")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            INSERT INTO usuari (
                nom, independent, entorn_adult,
                menu_mans_actiu, particules_mans_actives
            )
            VALUES (
                :nom, :independent, :entorn_adult,
                :menu_mans_actiu, :particules_mans_actives
            )
            RETURNING id_usuari, nom, independent, entorn_adult,
                      menu_mans_actiu, particules_mans_actives, actiu,
                      creat_a, actualitzat_a
        """),
        model_to_dict(user),
    )
    row = one_row_or_404(result, "No se ha podido crear el usuario")
    db.commit()
    return row


@app.patch("/users/{user_id}")
def update_user(user_id: int, user: UserUpdate, db: Session = Depends(get_db)):
    current = get_user(user_id, db)
    data = model_to_dict(user, exclude_unset=True)

    if not data:
        return current

    updated = {
        "nom": data.get("nom", current["nom"]),
        "independent": data.get("independent", current["independent"]),
        "entorn_adult": data.get("entorn_adult", current["entorn_adult"]),
        "menu_mans_actiu": data.get("menu_mans_actiu", current["menu_mans_actiu"]),
        "particules_mans_actives": data.get("particules_mans_actives", current["particules_mans_actives"]),
        "actiu": data.get("actiu", current["actiu"]),
        "user_id": user_id,
    }

    result = db.execute(
        text("""
            UPDATE usuari
            SET nom = :nom,
                independent = :independent,
                entorn_adult = :entorn_adult,
                menu_mans_actiu = :menu_mans_actiu,
                particules_mans_actives = :particules_mans_actives,
                actiu = :actiu,
                actualitzat_a = CURRENT_TIMESTAMP
            WHERE id_usuari = :user_id
            RETURNING id_usuari, nom, independent, entorn_adult,
                      menu_mans_actiu, particules_mans_actives, actiu,
                      creat_a, actualitzat_a
        """),
        updated,
    )
    row = one_row_or_404(result, "Usuario no encontrado")
    db.commit()
    return row


@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    # Baja lógica: no borramos sesiones ni historial.
    result = db.execute(
        text("""
            UPDATE usuari
            SET actiu = FALSE,
                actualitzat_a = CURRENT_TIMESTAMP
            WHERE id_usuari = :user_id
            RETURNING id_usuari, nom, actiu
        """),
        {"user_id": user_id},
    )
    row = one_row_or_404(result, "Usuario no encontrado")
    db.commit()
    return {"status": "deactivated", "user": row}


# ============================================================
# Configuración predeterminada / última configuración del usuario
# ============================================================

@app.get("/users/{user_id}/config")
def get_current_config(user_id: int, db: Session = Depends(get_db)):
    get_user(user_id, db)
    result = db.execute(
        text("""
            SELECT id_configuracio, id_usuari, nom_configuracio,
                   intensitat_llum, color_llum_r, color_llum_g, color_llum_b,
                   intensitat_so, menu_mans_actiu, particules_mans_actives,
                   es_actual, creat_a
            FROM configuracio_predeterminada
            WHERE id_usuari = :user_id AND es_actual = TRUE
            ORDER BY id_configuracio DESC
            LIMIT 1
        """),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    return dict(row)


@app.post("/users/{user_id}/config")
def create_current_config(user_id: int, config: ConfiguracioPredeterminadaIn, db: Session = Depends(get_db)):
    get_user(user_id, db)

    db.execute(
        text("""
            UPDATE configuracio_predeterminada
            SET es_actual = FALSE
            WHERE id_usuari = :user_id
        """),
        {"user_id": user_id},
    )

    params = model_to_dict(config)
    params["user_id"] = user_id

    result = db.execute(
        text("""
            INSERT INTO configuracio_predeterminada (
                id_usuari, nom_configuracio,
                intensitat_llum, color_llum_r, color_llum_g, color_llum_b,
                intensitat_so, menu_mans_actiu, particules_mans_actives,
                es_actual
            )
            VALUES (
                :user_id, :nom_configuracio,
                :intensitat_llum, :color_llum_r, :color_llum_g, :color_llum_b,
                :intensitat_so, :menu_mans_actiu, :particules_mans_actives,
                TRUE
            )
            RETURNING id_configuracio, id_usuari, nom_configuracio,
                      intensitat_llum, color_llum_r, color_llum_g, color_llum_b,
                      intensitat_so, menu_mans_actiu, particules_mans_actives,
                      es_actual, creat_a
        """),
        params,
    )
    row = one_row_or_404(result, "No se ha podido crear la configuración")
    db.commit()
    return row


# ============================================================
# Sessions
# ============================================================

@app.post("/sessions")
def create_session(session: SessionCreate, db: Session = Depends(get_db)):
    user = get_user(session.id_usuari, db)
    config = get_current_config(session.id_usuari, db)
    columns = get_table_columns(db, "sessio")
    insert_fields = ["id_usuari", "observacions"]
    params = {"id_usuari": session.id_usuari, "observacions": session.observacions}

    postura_inicial = session.postura_inicial
    menu_mans_inicial = first_not_none(
        session.menu_mans_actiu,
        config["menu_mans_actiu"] if config else None,
        user["menu_mans_actiu"],
    )
    particules_mans_inicial = first_not_none(
        session.particules_mans_actives,
        config["particules_mans_actives"] if config else None,
        user["particules_mans_actives"],
    )

    mapped_fields = {
        "postura_inicial": postura_inicial,
        "menu_mans_inicial": menu_mans_inicial,
        "particules_mans_inicial": particules_mans_inicial,
    }
    for field, value in mapped_fields.items():
        if field in columns and value is not None:
            insert_fields.append(field)
            params[field] = value

    field_sql = ", ".join(insert_fields)
    value_sql = ", ".join(f":{field}" for field in insert_fields)

    result = db.execute(
        text(f"""
            INSERT INTO sessio ({field_sql})
            VALUES ({value_sql})
            RETURNING id_sessio, id_usuari, inici, fi,
                      durada_total_segons, durada_tutorial_segons,
                      durada_preparacio_segons, durada_vr_segons,
                      ha_entrat_tutorial, ha_entrat_preparacio, ha_entrat_vr,
                      observacions
        """),
        params,
    )
    row = one_row_or_404(result, "No se ha podido crear la sesión")
    insert_session_config_event(
        db,
        row["id_sessio"],
        postura_actual=postura_inicial,
        menu_mans_actiu=menu_mans_inicial,
        particules_mans_actives=particules_mans_inicial,
    )
    db.commit()
    return row


@app.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            SELECT id_sessio, id_usuari, inici, fi,
                   durada_total_segons, durada_tutorial_segons,
                   durada_preparacio_segons, durada_vr_segons,
                   ha_entrat_tutorial, ha_entrat_preparacio, ha_entrat_vr,
                   observacions
            FROM sessio
            WHERE id_sessio = :session_id
        """),
        {"session_id": session_id},
    )
    return one_row_or_404(result, "Sesión no encontrada")


@app.get("/users/{user_id}/sessions")
def get_user_sessions(user_id: int, db: Session = Depends(get_db)):
    get_user(user_id, db)
    result = db.execute(
        text("""
            SELECT id_sessio, id_usuari, inici, fi,
                   durada_total_segons, durada_tutorial_segons,
                   durada_preparacio_segons, durada_vr_segons,
                   ha_entrat_tutorial, ha_entrat_preparacio, ha_entrat_vr,
                   observacions
            FROM sessio
            WHERE id_usuari = :user_id
            ORDER BY inici DESC
        """),
        {"user_id": user_id},
    )
    return rows_to_dicts(result)


@app.get("/users/{user_id}/last-session")
def get_last_session(user_id: int, db: Session = Depends(get_db)):
    user = get_user(user_id, db)

    result = db.execute(
        text("""
            SELECT id_sessio, id_usuari, inici, fi,
                   durada_total_segons, durada_tutorial_segons,
                   durada_preparacio_segons, durada_vr_segons,
                   ha_entrat_tutorial, ha_entrat_preparacio, ha_entrat_vr,
                   observacions,
                   postura_inicial, postura_final,
                   menu_mans_inicial, menu_mans_final,
                   particules_mans_inicial, particules_mans_final
            FROM sessio
            WHERE id_usuari = :user_id
            ORDER BY inici DESC
            LIMIT 1
        """),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="El usuario no tiene sesiones")

    session = dict(row)

    config = get_current_config(user_id, db)
    event = get_latest_session_config_event(db, session["id_sessio"])

    session["postura_inicial"] = session.get("postura_inicial") or "DE_PIE"
    session["postura_final"] = session.get("postura_final") or session["postura_inicial"]
    session["postura_actual"] = first_not_none(
        event.get("postura_actual") if event else None,
        session.get("postura_final"),
        session.get("postura_inicial"),
        "DE_PIE",
    )
    session["menu_mans_actiu"] = first_not_none(
        event.get("menu_mans_actiu") if event else None,
        session.get("menu_mans_final"),
        session.get("menu_mans_inicial"),
        config["menu_mans_actiu"] if config else None,
        user["menu_mans_actiu"],
    )
    session["particules_mans_actives"] = first_not_none(
        event.get("particules_mans_actives") if event else None,
        session.get("particules_mans_final"),
        session.get("particules_mans_inicial"),
        config["particules_mans_actives"] if config else None,
        user["particules_mans_actives"],
    )

    session["vr_elements"] = [
        {
            "id_element": element["id_element"],
            "numero_posicio": element["numero_posicio"],
        }
        for element in get_final_vr_elements(db, session["id_sessio"])
    ]
    return session


@app.patch("/sessions/{session_id}")
def update_session(session_id: int, session: SessionUpdate, db: Session = Depends(get_db)):
    current = get_session(session_id, db)
    data = model_to_dict(session, exclude_unset=True)
    if not data:
        return current

    columns = get_table_columns(db, "sessio")
    update_fields = existing_fields(
        data,
        columns,
        [
            "durada_total_segons", "durada_tutorial_segons", "durada_preparacio_segons",
            "durada_vr_segons", "ha_entrat_tutorial", "ha_entrat_preparacio",
            "ha_entrat_vr", "observacions", "postura_inicial", "postura_final",
            "postura_actual", "menu_mans_actiu", "particules_mans_actives",
        ],
    )

    if not update_fields:
        return current

    assignments = ", ".join(f"{field} = :{field}" for field in update_fields)
    params = dict(update_fields)
    params["session_id"] = session_id

    result = db.execute(
        text(f"""
            UPDATE sessio
            SET {assignments}
            WHERE id_sessio = :session_id
            RETURNING id_sessio, id_usuari, inici, fi,
                      durada_total_segons, durada_tutorial_segons,
                      durada_preparacio_segons, durada_vr_segons,
                      ha_entrat_tutorial, ha_entrat_preparacio, ha_entrat_vr,
                      observacions
        """),
        params,
    )
    row = one_row_or_404(result, "Sesión no encontrada")
    db.commit()
    return row


@app.post("/sessions/{session_id}/finish")
@app.patch("/sessions/{session_id}/end")
def finish_session(session_id: int, payload: SessionFinish, db: Session = Depends(get_db)):
    get_session(session_id, db)
    params = model_to_dict(payload)
    params["session_id"] = session_id
    columns = get_table_columns(db, "sessio")
    event = get_latest_session_config_event(db, session_id)

    optional_updates = {}
    if "postura_final" in columns and payload.postura_final is not None:
        optional_updates["postura_final"] = payload.postura_final
    if "menu_mans_final" in columns:
        menu_mans_final = event.get("menu_mans_actiu") if event else None
        if menu_mans_final is None and "menu_mans_inicial" in columns:
            session_row = db.execute(
                text("SELECT menu_mans_inicial FROM sessio WHERE id_sessio = :session_id"),
                {"session_id": session_id},
            ).mappings().first()
            menu_mans_final = session_row["menu_mans_inicial"] if session_row else None
        if menu_mans_final is not None:
            optional_updates["menu_mans_final"] = menu_mans_final
    if "particules_mans_final" in columns:
        particules_mans_final = event.get("particules_mans_actives") if event else None
        if particules_mans_final is None and "particules_mans_inicial" in columns:
            session_row = db.execute(
                text("SELECT particules_mans_inicial FROM sessio WHERE id_sessio = :session_id"),
                {"session_id": session_id},
            ).mappings().first()
            particules_mans_final = session_row["particules_mans_inicial"] if session_row else None
        if particules_mans_final is not None:
            optional_updates["particules_mans_final"] = particules_mans_final

    params.update(optional_updates)
    optional_sql = ""
    if optional_updates:
        optional_sql = ",\n                " + ",\n                ".join(f"{field} = :{field}" for field in optional_updates)

    result = db.execute(
        text(f"""
            UPDATE sessio
            SET fi = CURRENT_TIMESTAMP,
                durada_total_segons = :durada_total_segons,
                durada_tutorial_segons = :durada_tutorial_segons,
                durada_preparacio_segons = :durada_preparacio_segons,
                durada_vr_segons = :durada_vr_segons,
                ha_entrat_tutorial = :ha_entrat_tutorial,
                ha_entrat_preparacio = :ha_entrat_preparacio,
                ha_entrat_vr = :ha_entrat_vr,
                observacions = :observacions
                {optional_sql}
            WHERE id_sessio = :session_id
            RETURNING id_sessio, id_usuari, inici, fi,
                      durada_total_segons, durada_tutorial_segons,
                      durada_preparacio_segons, durada_vr_segons,
                      ha_entrat_tutorial, ha_entrat_preparacio, ha_entrat_vr,
                      observacions
        """),
        params,
    )
    row = one_row_or_404(result, "Sesión no encontrada")
    db.commit()
    return row


@app.patch("/sessions/{session_id}/settings")
def update_session_settings(session_id: int, payload: SessionSettingsUpdate, db: Session = Depends(get_db)):
    get_session(session_id, db)
    data = model_to_dict(payload, exclude_unset=True)
    event = insert_session_config_event(
        db,
        session_id,
        postura_actual=data.get("postura_actual"),
        menu_mans_actiu=data.get("menu_mans_actiu"),
        particules_mans_actives=data.get("particules_mans_actives"),
    )
    db.commit()
    return {"status": "saved", "event": event, "session": get_session(session_id, db)}


# ============================================================
# Session phase history
# ============================================================

@app.post("/sessions/{session_id}/phases")
def add_session_phase(session_id: int, fase: FaseCreate, db: Session = Depends(get_db)):
    get_session(session_id, db)
    params = model_to_dict(fase)
    params["session_id"] = session_id

    result = db.execute(
        text("""
            INSERT INTO sessio_fase (id_sessio, fase, durada_segons, fi)
            VALUES (:session_id, :fase, :durada_segons, CURRENT_TIMESTAMP)
            RETURNING id_sessio_fase, id_sessio, fase, inici, fi, durada_segons
        """),
        params,
    )
    row = one_row_or_404(result, "No se ha podido guardar la fase")
    db.commit()
    return row


@app.get("/sessions/{session_id}/phases")
def get_session_phases(session_id: int, db: Session = Depends(get_db)):
    get_session(session_id, db)
    result = db.execute(
        text("""
            SELECT id_sessio_fase, id_sessio, fase, inici, fi, durada_segons
            FROM sessio_fase
            WHERE id_sessio = :session_id
            ORDER BY id_sessio_fase
        """),
        {"session_id": session_id},
    )
    return rows_to_dicts(result)


@app.patch("/session-phases/{session_phase_id}/end")
def end_session_phase(session_phase_id: int, payload: EndDurationIn, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            UPDATE sessio_fase
            SET fi = CURRENT_TIMESTAMP,
                durada_segons = :durada_segons
            WHERE id_sessio_fase = :session_phase_id
            RETURNING id_sessio_fase, id_sessio, fase, inici, fi, durada_segons
        """),
        {"session_phase_id": session_phase_id, "durada_segons": payload.durada_segons},
    )
    row = one_row_or_404(result, "Fase de sesión no encontrada")
    db.commit()
    return row


# ============================================================
# Tutorial elements
# ============================================================

@app.post("/sessions/{session_id}/tutorial-elements")
def add_tutorial_element(session_id: int, element: TutorialElementIn, db: Session = Depends(get_db)):
    get_session(session_id, db)
    params = model_to_dict(element)
    params["session_id"] = session_id

    result = db.execute(
        text("""
            INSERT INTO sessio_tutorial_element (
                id_sessio, id_element, inici, fi, durada_segons,
                valoracio_professional, comentari
            )
            VALUES (
                :session_id, :id_element, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :durada_segons,
                :valoracio_professional, :comentari
            )
            RETURNING id_tutorial_element, id_sessio, id_element,
                      inici, fi, durada_segons, valoracio_professional, comentari
        """),
        params,
    )
    row = one_row_or_404(result, "No se ha podido guardar el elemento de tutorial")
    db.commit()
    return row


@app.put("/sessions/{session_id}/tutorial-elements")
def replace_tutorial_elements(session_id: int, elements: List[TutorialElementIn], db: Session = Depends(get_db)):
    get_session(session_id, db)
    db.execute(text("DELETE FROM sessio_tutorial_element WHERE id_sessio = :session_id"), {"session_id": session_id})

    inserted = []
    for element in elements:
        params = model_to_dict(element)
        params["session_id"] = session_id
        result = db.execute(
            text("""
                INSERT INTO sessio_tutorial_element (
                    id_sessio, id_element, inici, fi, durada_segons,
                    valoracio_professional, comentari
                )
                VALUES (
                    :session_id, :id_element, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :durada_segons,
                    :valoracio_professional, :comentari
                )
                RETURNING id_tutorial_element, id_sessio, id_element,
                          inici, fi, durada_segons, valoracio_professional, comentari
            """),
            params,
        )
        inserted.append(one_row_or_404(result, "No se ha podido guardar un elemento de tutorial"))

    db.commit()
    return inserted


@app.get("/sessions/{session_id}/tutorial-elements")
def get_tutorial_elements(session_id: int, db: Session = Depends(get_db)):
    get_session(session_id, db)
    result = db.execute(
        text("""
            SELECT id_tutorial_element, id_sessio, id_element,
                   inici, fi, durada_segons, valoracio_professional, comentari
            FROM sessio_tutorial_element
            WHERE id_sessio = :session_id
            ORDER BY id_tutorial_element
        """),
        {"session_id": session_id},
    )
    return rows_to_dicts(result)


@app.patch("/tutorial-elements/{tutorial_element_id}/end")
def end_tutorial_element(tutorial_element_id: int, payload: EndDurationIn, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            UPDATE sessio_tutorial_element
            SET fi = CURRENT_TIMESTAMP,
                durada_segons = :durada_segons
            WHERE id_tutorial_element = :tutorial_element_id
            RETURNING id_tutorial_element, id_sessio, id_element,
                      inici, fi, durada_segons, valoracio_professional, comentari
        """),
        {"tutorial_element_id": tutorial_element_id, "durada_segons": payload.durada_segons},
    )
    row = one_row_or_404(result, "Elemento de tutorial no encontrado")
    db.commit()
    return row


@app.patch("/tutorial-elements/{tutorial_element_id}/pose")
def update_tutorial_element_pose(tutorial_element_id: int, payload: ElementPoseIn, db: Session = Depends(get_db)):
    columns = get_table_columns(db, "sessio_tutorial_element")
    fields = existing_fields(
        model_to_dict(payload, exclude_unset=True),
        columns,
        ["posicio_x", "posicio_y", "posicio_z", "rotacio_y"],
    )
    update_optional_fields(db, "sessio_tutorial_element", "id_tutorial_element", tutorial_element_id, fields)
    db.commit()

    result = db.execute(
        text("""
            SELECT id_tutorial_element, id_sessio, id_element,
                   inici, fi, durada_segons, valoracio_professional, comentari
            FROM sessio_tutorial_element
            WHERE id_tutorial_element = :tutorial_element_id
        """),
        {"tutorial_element_id": tutorial_element_id},
    )
    return one_row_or_404(result, "Elemento de tutorial no encontrado")


# ============================================================
# Preparation elements
# ============================================================

@app.post("/sessions/{session_id}/preparation-elements")
def add_preparation_element(session_id: int, element: PreparacioElementIn, db: Session = Depends(get_db)):
    get_session(session_id, db)
    params = model_to_dict(element)
    params["session_id"] = session_id

    columns = get_table_columns(db, "sessio_preparacio_element")
    optional_fields = existing_fields(
        params,
        columns,
        ["durada_segons", "valoracio_professional", "comentari"],
    )

    insert_fields = ["id_sessio", "id_element", "seleccionat"]
    insert_params = {
        "id_sessio": session_id,
        "id_element": element.id_element,
        "seleccionat": element.seleccionat,
    }
    insert_fields.extend(optional_fields.keys())
    insert_params.update(optional_fields)

    field_sql = ", ".join(insert_fields)
    value_sql = ", ".join(f":{field}" for field in insert_fields)

    result = db.execute(
        text(f"""
            INSERT INTO sessio_preparacio_element ({field_sql})
            VALUES ({value_sql})
            RETURNING id_preparacio_element, id_sessio, id_element, seleccionat
        """),
        insert_params,
    )
    row = one_row_or_404(result, "No se ha podido guardar el elemento de preparación")
    db.commit()
    return row


@app.put("/sessions/{session_id}/preparation-elements")
def replace_preparation_elements(session_id: int, elements: List[PreparacioElementIn], db: Session = Depends(get_db)):
    get_session(session_id, db)
    db.execute(text("DELETE FROM sessio_preparacio_element WHERE id_sessio = :session_id"), {"session_id": session_id})

    inserted = []
    for element in elements:
        params = model_to_dict(element)
        params["session_id"] = session_id
        result = db.execute(
            text("""
                INSERT INTO sessio_preparacio_element (id_sessio, id_element, seleccionat)
                VALUES (:session_id, :id_element, :seleccionat)
                RETURNING id_preparacio_element, id_sessio, id_element, seleccionat
            """),
            params,
        )
        inserted.append(one_row_or_404(result, "No se ha podido guardar un elemento de preparación"))

    db.commit()
    return inserted


@app.get("/sessions/{session_id}/preparation-elements")
def get_preparation_elements(session_id: int, db: Session = Depends(get_db)):
    get_session(session_id, db)
    result = db.execute(
        text("""
            SELECT id_preparacio_element, id_sessio, id_element, seleccionat
            FROM sessio_preparacio_element
            WHERE id_sessio = :session_id
            ORDER BY id_preparacio_element
        """),
        {"session_id": session_id},
    )
    return rows_to_dicts(result)


# ============================================================
# VR elements / positions
# ============================================================

@app.post("/sessions/{session_id}/vr-elements")
def add_vr_element(session_id: int, element: VRElementIn, db: Session = Depends(get_db)):
    get_session(session_id, db)
    params = model_to_dict(element)
    params["session_id"] = session_id

    db.execute(
        text("""
            DELETE FROM sessio_vr_element
            WHERE id_sessio = :session_id
              AND numero_posicio = :numero_posicio
        """),
        params,
    )

    result = db.execute(
        text("""
            INSERT INTO sessio_vr_element (
                id_sessio, id_element, numero_posicio,
                inici, fi, durada_segons,
                valoracio_professional, comentari
            )
            VALUES (
                :session_id, :id_element, :numero_posicio,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :durada_segons,
                :valoracio_professional, :comentari
            )
            RETURNING id_vr_element, id_sessio, id_element, numero_posicio,
                      inici, fi, durada_segons, valoracio_professional, comentari
        """),
        params,
    )
    row = one_row_or_404(result, "No se ha podido guardar el elemento de VR")
    db.commit()
    return row


@app.put("/sessions/{session_id}/vr-elements")
def replace_vr_elements(session_id: int, elements: List[VRElementIn], db: Session = Depends(get_db)):
    get_session(session_id, db)
    db.execute(text("DELETE FROM sessio_vr_element WHERE id_sessio = :session_id"), {"session_id": session_id})

    inserted = []
    used_positions = set()
    for element in elements:
        if element.numero_posicio in used_positions or len(inserted) >= 6:
            continue

        used_positions.add(element.numero_posicio)
        params = model_to_dict(element)
        params["session_id"] = session_id
        result = db.execute(
            text("""
                INSERT INTO sessio_vr_element (
                    id_sessio, id_element, numero_posicio,
                    inici, fi, durada_segons,
                    valoracio_professional, comentari
                )
                VALUES (
                    :session_id, :id_element, :numero_posicio,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :durada_segons,
                    :valoracio_professional, :comentari
                )
                RETURNING id_vr_element, id_sessio, id_element, numero_posicio,
                          inici, fi, durada_segons, valoracio_professional, comentari
            """),
            params,
        )
        inserted.append(one_row_or_404(result, "No se ha podido guardar un elemento de VR"))

    db.commit()
    return inserted


@app.get("/sessions/{session_id}/vr-elements")
def get_vr_elements(session_id: int, db: Session = Depends(get_db)):
    get_session(session_id, db)
    return get_final_vr_elements(db, session_id)


@app.patch("/vr-elements/{vr_element_id}/end")
def end_vr_element(vr_element_id: int, payload: EndDurationIn, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            UPDATE sessio_vr_element
            SET fi = CURRENT_TIMESTAMP,
                durada_segons = :durada_segons
            WHERE id_vr_element = :vr_element_id
            RETURNING id_vr_element, id_sessio, id_element, numero_posicio,
                      inici, fi, durada_segons, valoracio_professional, comentari
        """),
        {"vr_element_id": vr_element_id, "durada_segons": payload.durada_segons},
    )
    row = one_row_or_404(result, "Elemento de VR no encontrado")
    db.commit()
    return row


@app.patch("/vr-elements/{vr_element_id}/pose")
def update_vr_element_pose(vr_element_id: int, payload: ElementPoseIn, db: Session = Depends(get_db)):
    columns = get_table_columns(db, "sessio_vr_element")
    fields = existing_fields(
        model_to_dict(payload, exclude_unset=True),
        columns,
        ["posicio_x", "posicio_y", "posicio_z", "rotacio_y"],
    )
    update_optional_fields(db, "sessio_vr_element", "id_vr_element", vr_element_id, fields)
    db.commit()

    result = db.execute(
        text("""
            SELECT id_vr_element, id_sessio, id_element, numero_posicio,
                   inici, fi, durada_segons, valoracio_professional, comentari
            FROM sessio_vr_element
            WHERE id_vr_element = :vr_element_id
        """),
        {"vr_element_id": vr_element_id},
    )
    return one_row_or_404(result, "Elemento de VR no encontrado")


# ============================================================
# Complete save: useful from Unity at the end of a session
# ============================================================

@app.post("/sessions/{session_id}/complete")
def complete_session(session_id: int, payload: CompleteSessionPayload, db: Session = Depends(get_db)):
    get_session(session_id, db)

    # 1) Update session and mark finished
    session_params = model_to_dict(payload.sessio)
    session_params["session_id"] = session_id
    columns = get_table_columns(db, "sessio")
    event = get_latest_session_config_event(db, session_id)
    optional_updates = {}
    if "postura_final" in columns and payload.sessio.postura_final is not None:
        optional_updates["postura_final"] = payload.sessio.postura_final
    if "menu_mans_final" in columns:
        menu_mans_final = event.get("menu_mans_actiu") if event else None
        if menu_mans_final is not None:
            optional_updates["menu_mans_final"] = menu_mans_final
    if "particules_mans_final" in columns:
        particules_mans_final = event.get("particules_mans_actives") if event else None
        if particules_mans_final is not None:
            optional_updates["particules_mans_final"] = particules_mans_final

    session_params.update(optional_updates)
    optional_sql = ""
    if optional_updates:
        optional_sql = ",\n                " + ",\n                ".join(f"{field} = :{field}" for field in optional_updates)

    result = db.execute(
        text(f"""
            UPDATE sessio
            SET fi = CURRENT_TIMESTAMP,
                durada_total_segons = :durada_total_segons,
                durada_tutorial_segons = :durada_tutorial_segons,
                durada_preparacio_segons = :durada_preparacio_segons,
                durada_vr_segons = :durada_vr_segons,
                ha_entrat_tutorial = :ha_entrat_tutorial,
                ha_entrat_preparacio = :ha_entrat_preparacio,
                ha_entrat_vr = :ha_entrat_vr,
                observacions = :observacions
                {optional_sql}
            WHERE id_sessio = :session_id
            RETURNING id_sessio, id_usuari, inici, fi,
                      durada_total_segons, durada_tutorial_segons,
                      durada_preparacio_segons, durada_vr_segons,
                      ha_entrat_tutorial, ha_entrat_preparacio, ha_entrat_vr,
                      observacions
        """),
        session_params,
    )
    session_row = one_row_or_404(result, "Sesión no encontrada")

    # 2) Replace details
    db.execute(text("DELETE FROM sessio_fase WHERE id_sessio = :session_id"), {"session_id": session_id})
    db.execute(text("DELETE FROM sessio_tutorial_element WHERE id_sessio = :session_id"), {"session_id": session_id})
    db.execute(text("DELETE FROM sessio_preparacio_element WHERE id_sessio = :session_id"), {"session_id": session_id})
    db.execute(text("DELETE FROM sessio_vr_element WHERE id_sessio = :session_id"), {"session_id": session_id})

    for fase in payload.fases:
        params = model_to_dict(fase)
        params["session_id"] = session_id
        db.execute(
            text("""
                INSERT INTO sessio_fase (id_sessio, fase, durada_segons, fi)
                VALUES (:session_id, :fase, :durada_segons, CURRENT_TIMESTAMP)
            """),
            params,
        )

    for element in payload.tutorial_elements:
        params = model_to_dict(element)
        params["session_id"] = session_id
        db.execute(
            text("""
                INSERT INTO sessio_tutorial_element (
                    id_sessio, id_element, inici, fi, durada_segons,
                    valoracio_professional, comentari
                )
                VALUES (
                    :session_id, :id_element, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :durada_segons,
                    :valoracio_professional, :comentari
                )
            """),
            params,
        )

    for element in payload.preparacio_elements:
        params = model_to_dict(element)
        params["session_id"] = session_id
        db.execute(
            text("""
                INSERT INTO sessio_preparacio_element (id_sessio, id_element, seleccionat)
                VALUES (:session_id, :id_element, :seleccionat)
            """),
            params,
        )

    used_vr_positions = set()
    inserted_vr_count = 0
    for element in payload.vr_elements:
        if element.numero_posicio in used_vr_positions or inserted_vr_count >= 6:
            continue

        used_vr_positions.add(element.numero_posicio)
        inserted_vr_count += 1
        params = model_to_dict(element)
        params["session_id"] = session_id
        db.execute(
            text("""
                INSERT INTO sessio_vr_element (
                    id_sessio, id_element, numero_posicio,
                    inici, fi, durada_segons,
                    valoracio_professional, comentari
                )
                VALUES (
                    :session_id, :id_element, :numero_posicio,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :durada_segons,
                    :valoracio_professional, :comentari
                )
            """),
            params,
        )

    db.commit()
    return {"status": "completed", "session": session_row}
