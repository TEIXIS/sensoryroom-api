# Sensory Room API

API REST para guardar usuarios, configuraciones y sesiones de la sala multisensorial VR/tablet.

Base URL de produccion:

```text
https://moving.cs.upc.edu/sensory_room_api/api
```

Los clientes Unity construyen las URLs con `baseUrl.TrimEnd('/') + path`, por lo que pueden usar la base con o sin `/` final.

## Arquitectura

La API esta implementada con FastAPI en `server.py` y usa PostgreSQL mediante SQLAlchemy. La conexion se configura en `database.py` con la variable de entorno `DATABASE_URL`.

Conceptualmente la base de datos guarda:

- `usuari`: pacientes/usuarios. Incluye si son independientes, si usan entorno adulto, si estan activos y los permisos por defecto de menu de manos y particulas.
- `configuracio_predeterminada`: configuracion actual del usuario. Solo una configuracion queda marcada como `es_actual = TRUE`.
- `sessio`: sesion principal de un usuario. Guarda tiempos totales, fases visitadas, postura inicial/final, permisos iniciales/finales y observaciones.
- `sessio_configuracio_event`: cambios durante la sesion de postura, menu de manos y particulas. La ultima entrada representa el estado actual.
- `sessio_fase`: historial de fases visitadas: `tutorial`, `preparacio`, `vr`, etc.
- `sessio_tutorial_element`: elementos mostrados en tutorial, con duracion, posicion opcional y comentario/valoracion.
- `sessio_preparacio_element`: elementos seleccionados durante preparacion.
- `sessio_vr_element`: elementos finales en VR. Usa `numero_posicio` del 1 al 6. Para recuperar el estado final se toma el ultimo elemento guardado por cada posicion.

## Flujo Habitual

1. Crear o seleccionar usuario desde tablet.
2. Crear sesion con `POST /sessions`.
3. Guardar fases con `POST /sessions/{session_id}/phases`.
4. Guardar elementos de tutorial/preparacion/VR segun avanza la experiencia.
5. Actualizar configuracion viva con `PATCH /sessions/{session_id}/settings` cuando cambie postura, menu de manos o particulas.
6. Cerrar elementos/fases cuando termina su tiempo.
7. Cerrar sesion con `POST /sessions/{session_id}/finish` o `PATCH /sessions/{session_id}/end`.

Para recuperar una experiencia anterior:

```http
GET /users/{user_id}/last-session
```

Devuelve la ultima sesion del usuario, la configuracion actual calculada y los elementos VR finales. Si el usuario no tiene sesiones devuelve `404`.

## Endpoints

### General

#### `GET /`

Informacion basica de la API.

#### `GET /health`

Comprueba que la API y la base de datos estan disponibles.

Respuesta:

```json
{
  "status": "ok",
  "database": "connected"
}
```

### Usuarios

#### `GET /users`

Lista usuarios activos.

Query params:

- `include_inactive`: `false` por defecto. Si es `true`, tambien devuelve usuarios desactivados.

#### `GET /users/{user_id}`

Devuelve un usuario concreto.

#### `POST /users`

Crea un usuario.

Body:

```json
{
  "nom": "Marc",
  "independent": false,
  "entorn_adult": false,
  "menu_mans_actiu": true,
  "particules_mans_actives": true
}
```

#### `PATCH /users/{user_id}`

Actualiza parcialmente un usuario.

Body, todos los campos son opcionales:

```json
{
  "nom": "Marc",
  "independent": false,
  "entorn_adult": true,
  "menu_mans_actiu": true,
  "particules_mans_actives": false,
  "actiu": true
}
```

#### `DELETE /users/{user_id}`

Baja logica del usuario. No borra sesiones ni historial; marca `actiu = FALSE`.

### Configuracion Del Usuario

#### `GET /users/{user_id}/config`

Devuelve la configuracion actual del usuario o `null` si no hay ninguna.

#### `POST /users/{user_id}/config`

Crea una nueva configuracion actual. Antes desmarca las configuraciones anteriores del usuario.

Body:

```json
{
  "nom_configuracio": "Configuracion por defecto",
  "intensitat_llum": 0.8,
  "color_llum_r": 255,
  "color_llum_g": 255,
  "color_llum_b": 255,
  "intensitat_so": 0.5,
  "menu_mans_actiu": true,
  "particules_mans_actives": true
}
```

### Sesiones

#### `POST /sessions`

Crea una sesion para un usuario.

Body:

```json
{
  "id_usuari": 1,
  "postura_inicial": "DE_PIE",
  "menu_mans_actiu": true,
  "particules_mans_actives": true,
  "observacions": null
}
```

Si no se envian permisos, se heredan de la configuracion actual del usuario y despues del propio usuario.

#### `GET /sessions/{session_id}`

Devuelve una sesion.

#### `GET /users/{user_id}/sessions`

Lista sesiones de un usuario, ordenadas de mas reciente a mas antigua.

#### `GET /users/{user_id}/last-session`

Devuelve la ultima sesion del usuario con datos calculados para reanudar:

- `postura_actual`: ultima postura registrada, o postura final/inicial.
- `menu_mans_actiu`: ultimo estado registrado, o final/inicial/configuracion/usuario.
- `particules_mans_actives`: mismo criterio que menu.
- `vr_elements`: elementos VR finales, ordenados por `numero_posicio`.

Ejemplo de respuesta:

```json
{
  "id_sessio": 12,
  "id_usuari": 1,
  "postura_inicial": "DE_PIE",
  "postura_final": "SENTADO",
  "postura_actual": "SENTADO",
  "menu_mans_actiu": true,
  "particules_mans_actives": false,
  "vr_elements": [
    { "id_element": "blau_cel", "numero_posicio": 1 },
    { "id_element": "groc", "numero_posicio": 2 }
  ]
}
```

#### `PATCH /sessions/{session_id}`

Actualiza parcialmente una sesion.

Body, todos los campos son opcionales:

```json
{
  "durada_total_segons": 300,
  "durada_tutorial_segons": 60,
  "durada_preparacio_segons": 90,
  "durada_vr_segons": 150,
  "ha_entrat_tutorial": true,
  "ha_entrat_preparacio": true,
  "ha_entrat_vr": true,
  "postura_inicial": "DE_PIE",
  "postura_final": "SENTADO",
  "postura_actual": "SENTADO",
  "menu_mans_actiu": true,
  "particules_mans_actives": false,
  "observacions": "Sesion completada"
}
```

#### `POST /sessions/{session_id}/finish`

Alias:

```http
PATCH /sessions/{session_id}/end
```

Cierra la sesion, guarda duraciones finales y marca `fi = CURRENT_TIMESTAMP`.

Body:

```json
{
  "durada_total_segons": 300,
  "durada_tutorial_segons": 60,
  "durada_preparacio_segons": 90,
  "durada_vr_segons": 150,
  "ha_entrat_tutorial": true,
  "ha_entrat_preparacio": true,
  "ha_entrat_vr": true,
  "postura_final": "SENTADO",
  "observacions": "Sesion finalizada"
}
```

#### `PATCH /sessions/{session_id}/settings`

Guarda un evento de configuracion durante la sesion.

Body:

```json
{
  "postura_actual": "SENTADO",
  "menu_mans_actiu": true,
  "particules_mans_actives": false
}
```

### Fases

#### `POST /sessions/{session_id}/phases`

Guarda una fase de sesion.

Body:

```json
{
  "fase": "tutorial",
  "durada_segons": 30
}
```

#### `GET /sessions/{session_id}/phases`

Lista fases de la sesion.

#### `PATCH /session-phases/{session_phase_id}/end`

Cierra una fase y actualiza su duracion.

Body:

```json
{
  "durada_segons": 45
}
```

### Elementos De Tutorial

#### `POST /sessions/{session_id}/tutorial-elements`

Guarda un elemento mostrado en tutorial.

Body:

```json
{
  "id_element": "blau_cel",
  "durada_segons": 10,
  "valoracio_professional": 4,
  "comentari": "Buena respuesta"
}
```

#### `PUT /sessions/{session_id}/tutorial-elements`

Reemplaza todos los elementos de tutorial de una sesion.

Body:

```json
[
  {
    "id_element": "blau_cel",
    "durada_segons": 10,
    "valoracio_professional": 4,
    "comentari": "Buena respuesta"
  }
]
```

#### `GET /sessions/{session_id}/tutorial-elements`

Lista elementos de tutorial.

#### `PATCH /tutorial-elements/{tutorial_element_id}/end`

Cierra un elemento de tutorial y actualiza duracion.

Body:

```json
{
  "durada_segons": 12
}
```

#### `PATCH /tutorial-elements/{tutorial_element_id}/pose`

Actualiza posicion/rotacion guardada para el elemento.

Body:

```json
{
  "posicio_x": 1.2,
  "posicio_y": 0.5,
  "posicio_z": -0.8,
  "rotacio_y": 90
}
```

### Elementos De Preparacion

#### `POST /sessions/{session_id}/preparation-elements`

Guarda un elemento seleccionado en preparacion.

Body:

```json
{
  "id_element": "groc",
  "seleccionat": true,
  "durada_segons": 5,
  "valoracio_professional": null,
  "comentari": null
}
```

#### `PUT /sessions/{session_id}/preparation-elements`

Reemplaza todos los elementos de preparacion de una sesion.

Body:

```json
[
  { "id_element": "groc", "seleccionat": true },
  { "id_element": "rosa", "seleccionat": true }
]
```

#### `GET /sessions/{session_id}/preparation-elements`

Lista elementos de preparacion.

### Elementos VR

#### `POST /sessions/{session_id}/vr-elements`

Guarda un elemento final de VR en una posicion. Antes borra el elemento anterior de esa misma posicion.

Body:

```json
{
  "id_element": "groc",
  "numero_posicio": 1,
  "durada_segons": 20,
  "valoracio_professional": 5,
  "comentari": "Elemento principal"
}
```

`numero_posicio` debe estar entre 1 y 6.

#### `PUT /sessions/{session_id}/vr-elements`

Reemplaza todos los elementos VR de una sesion. Solo guarda hasta 6 posiciones unicas.

Body:

```json
[
  { "id_element": "groc", "numero_posicio": 1 },
  { "id_element": "rosa", "numero_posicio": 2 }
]
```

#### `GET /sessions/{session_id}/vr-elements`

Devuelve los elementos VR finales de la sesion, ordenados por `numero_posicio`.

#### `PATCH /vr-elements/{vr_element_id}/end`

Cierra un elemento VR y actualiza duracion.

Body:

```json
{
  "durada_segons": 30
}
```

#### `PATCH /vr-elements/{vr_element_id}/pose`

Actualiza posicion/rotacion guardada para un elemento VR.

Body:

```json
{
  "posicio_x": 1.2,
  "posicio_y": 0.5,
  "posicio_z": -0.8,
  "rotacio_y": 90
}
```

### Guardado Completo

#### `POST /sessions/{session_id}/complete`

Endpoint pensado para guardar una sesion completa desde Unity al final. Actualiza/cierra la sesion y reemplaza fases, elementos de tutorial, preparacion y VR.

Body:

```json
{
  "sessio": {
    "durada_total_segons": 300,
    "durada_tutorial_segons": 60,
    "durada_preparacio_segons": 90,
    "durada_vr_segons": 150,
    "ha_entrat_tutorial": true,
    "ha_entrat_preparacio": true,
    "ha_entrat_vr": true,
    "postura_final": "SENTADO",
    "observacions": "Sesion completa"
  },
  "fases": [
    { "fase": "tutorial", "durada_segons": 60 },
    { "fase": "preparacio", "durada_segons": 90 },
    { "fase": "vr", "durada_segons": 150 }
  ],
  "tutorial_elements": [
    { "id_element": "blau_cel", "durada_segons": 10 }
  ],
  "preparation_elements": [
    { "id_element": "groc", "seleccionat": true }
  ],
  "vr_elements": [
    { "id_element": "groc", "numero_posicio": 1 }
  ]
}
```

## Notas Para Unity

- Tablet y VR deben usar la misma base URL:

```text
https://moving.cs.upc.edu/sensory_room_api/api/
```

- En multidispositivo, la tablet indica el usuario seleccionado al casco con el mensaje socket `USER:<id_usuari>`.
- El casco consulta `GET /users/{user_id}/last-session`.
- Si la ultima sesion tiene `vr_elements`, el casco restaura configuracion y entra en VR.
- Si no hay sesion o no hay elementos VR, se mantiene el flujo normal: tutorial, preparacion y VR.

