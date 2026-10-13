"""Configuración de SQLite, conexiones y esquema de Dominotion.

La aplicación usa una sola base de datos SQLite. En desarrollo vive junto a
este módulo; en una versión empaquetada se guarda en el directorio persistente
del usuario para que reinstalar o actualizar el programa no borre los torneos.
Cada conexión activa claves foráneas, WAL y un tiempo de espera para escrituras
concurrentes breves. ``inicializar_bd`` crea el esquema y agrega las columnas
que falten en bases de datos existentes, incluidas las tablas de clasificaciones
capturadas al archivar un torneo.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

# Límite de espera por bloqueos breves de otro escritor. Se configura tanto
# en sqlite3.connect como en busy_timeout para mantener el mismo límite en SQLite.
TIMEOUT_ESPERA_BLOQUEO_SEGUNDOS = 30.0

NOMBRE_ARCHIVO_BD = "torneos.db"
NOMBRE_CARPETA_DATOS = "Dominotion"


def _esta_empaquetado() -> bool:
    """Indica si PyInstaller inició la aplicación en modo onefile u onedir."""
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def _carpeta_datos_usuario() -> Path:
    """Ruta de datos del usuario, fuera de la carpeta de instalación.

    Así los instaladores pueden actualizar el programa sin reemplazar los datos
    del torneo y la aplicación puede escribir sin permisos de administrador.
    """
    override = os.environ.get("DOMINOTION_DATA_DIR")
    if override:
        return Path(override)

    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")

    return Path(base) / NOMBRE_CARPETA_DATOS


def resolver_ruta_bd() -> Path:
    """Calcula dónde debe vivir ``torneos.db``.

    - Variable de entorno ``DOMINOTION_DB_PATH``: ruta explícita (útil para
      pruebas automatizadas o para forzar una ubicación concreta).
    - Ejecutable empaquetado: carpeta de datos del usuario.
    - Ejecución desde código fuente: junto a este módulo.
    """
    override = os.environ.get("DOMINOTION_DB_PATH")
    if override:
        return Path(override)

    if _esta_empaquetado():
        carpeta = _carpeta_datos_usuario()
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta / NOMBRE_ARCHIVO_BD

    return Path(__file__).parent / NOMBRE_ARCHIVO_BD


# Se resuelve al importar. La variable pública permite que las pruebas apunten
# a una base temporal antes de abrir conexiones.
RUTA_BD = resolver_ruta_bd()


def obtener_conexion() -> sqlite3.Connection:
    conexion = sqlite3.connect(RUTA_BD, timeout=TIMEOUT_ESPERA_BLOQUEO_SEGUNDOS)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA journal_mode = WAL")
    # Con WAL, NORMAL mantiene la recuperación ante el cierre inesperado de la
    # aplicación y evita sincronizar a disco en cada commit como haría FULL.
    conexion.execute("PRAGMA synchronous = NORMAL")
    conexion.execute(f"PRAGMA busy_timeout = {int(TIMEOUT_ESPERA_BLOQUEO_SEGUNDOS * 1000)}")
    conexion.row_factory = sqlite3.Row
    return conexion


def checkpoint_wal(modo: str = "PASSIVE") -> None:
    """Fuerza un checkpoint de WAL hacia el archivo principal.

    En uso normal SQLite hace checkpoints automáticos, pero en sesiones muy
    largas (un torneo de varias horas con guardados frecuentes) conviene
    forzar uno de vez en cuando para que ``torneos.db-wal`` no crezca sin
    límite. ``PASSIVE`` nunca bloquea a otros lectores/escritores; es
    seguro llamarlo, por ejemplo, al cerrar la aplicación. (No lo toques Alan. NO)
    """
    conexion = obtener_conexion()
    try:
        conexion.execute(f"PRAGMA wal_checkpoint({modo})")
    finally:
        conexion.close()


def inicializar_bd() -> None:
    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.executescript(
                """
                CREATE TABLE IF NOT EXISTS jugadores (
                    cedula TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    sexo   TEXT NOT NULL CHECK (sexo IN ('M', 'F'))
                );

                CREATE TABLE IF NOT EXISTS jugadores_vetados (
                    cedula      TEXT PRIMARY KEY REFERENCES jugadores(cedula) ON DELETE CASCADE ON UPDATE CASCADE,
                    fecha_hora  TEXT NOT NULL,
                    motivo      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clubes (
                    id     INTEGER PRIMARY KEY,
                    nombre TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS club_jugadores (
                    club_id INTEGER NOT NULL REFERENCES clubes(id) ON DELETE CASCADE,
                    cedula  TEXT NOT NULL REFERENCES jugadores(cedula) ON DELETE CASCADE ON UPDATE CASCADE,
                    PRIMARY KEY (club_id, cedula)
                );

                CREATE TABLE IF NOT EXISTS torneos (
                    id               INTEGER PRIMARY KEY,
                    nombre           TEXT NOT NULL,
                    duracion_minutos INTEGER NOT NULL,
                    tipo             TEXT NOT NULL CHECK (tipo IN ('mixto', 'hombres', 'mujeres')),
                    puntaje_meta     INTEGER NOT NULL,
                    num_rondas       INTEGER NOT NULL,
                    estado           TEXT NOT NULL DEFAULT 'inscripcion',
                    modalidad        TEXT NOT NULL DEFAULT 'intercalado',
                    jugadores_por_mesa INTEGER NOT NULL DEFAULT 4,
                    permite_retiros  INTEGER NOT NULL DEFAULT 1,
                    fecha_finalizacion TEXT,
                    edicion_historico INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS torneo_ranking_archivado (
                    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                    posicion INTEGER NOT NULL,
                    cedula TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    pg INTEGER NOT NULL,
                    pp INTEGER NOT NULL,
                    ef INTEGER NOT NULL,
                    pf INTEGER NOT NULL,
                    PRIMARY KEY (torneo_id, cedula),
                    UNIQUE (torneo_id, posicion)
                );

                CREATE TABLE IF NOT EXISTS torneo_jugadores_archivados (
                    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                    cedula TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    sexo TEXT NOT NULL,
                    PRIMARY KEY (torneo_id, cedula)
                );

                CREATE TABLE IF NOT EXISTS torneo_ranking_club_archivado (
                    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                    club_nombre TEXT NOT NULL,
                    posicion INTEGER NOT NULL,
                    cedula TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    pg INTEGER NOT NULL,
                    pp INTEGER NOT NULL,
                    ef INTEGER NOT NULL,
                    pf INTEGER NOT NULL,
                    PRIMARY KEY (torneo_id, club_nombre, cedula)
                );

                CREATE TABLE IF NOT EXISTS historial_jugadores (
                    id             INTEGER PRIMARY KEY,
                    cedula_jugador TEXT NOT NULL,
                    fecha_hora     TEXT NOT NULL,
                    accion         TEXT NOT NULL,
                    detalle        TEXT NOT NULL,
                    FOREIGN KEY (cedula_jugador) REFERENCES jugadores(cedula) ON DELETE CASCADE ON UPDATE CASCADE
                );

                CREATE TABLE IF NOT EXISTS torneo_jugadores (
                    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                    cedula    TEXT NOT NULL REFERENCES jugadores(cedula) ON DELETE CASCADE ON UPDATE CASCADE,
                    PRIMARY KEY (torneo_id, cedula)
                );

                CREATE TABLE IF NOT EXISTS torneo_jugadores_retirados (
                    torneo_id   INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                    cedula      TEXT NOT NULL REFERENCES jugadores(cedula) ON DELETE CASCADE ON UPDATE CASCADE,
                    fecha_hora  TEXT NOT NULL,
                    motivo      TEXT NOT NULL,
                    PRIMARY KEY (torneo_id, cedula)
                );

                CREATE TABLE IF NOT EXISTS penalizaciones (
                    id INTEGER PRIMARY KEY,
                    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                    cedula TEXT NOT NULL REFERENCES jugadores(cedula) ON DELETE CASCADE,
                    numero_falta INTEGER NOT NULL,
                    tipo TEXT NOT NULL CHECK (tipo IN ('tarjeta_amarilla', 'tarjeta_roja')),
                    motivo TEXT,
                    fecha_hora TEXT NOT NULL,
                    aplicada INTEGER NOT NULL DEFAULT 0,
                    mesa_id INTEGER REFERENCES mesas(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS rondas (
                    id            INTEGER PRIMARY KEY,
                    torneo_id     INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                    numero_ronda  INTEGER NOT NULL,
                    estado        TEXT NOT NULL CHECK (estado IN ('pendiente', 'en_curso', 'finalizada')),
                    modalidad     TEXT NOT NULL DEFAULT 'intercalado',
                    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(torneo_id, numero_ronda)
                );

               CREATE TABLE IF NOT EXISTS mesas (
                    id           INTEGER PRIMARY KEY,
                    ronda_id     INTEGER NOT NULL REFERENCES rondas(id) ON DELETE CASCADE,
                    numero_mesa  INTEGER NOT NULL,
                    j1_cedula    TEXT NOT NULL REFERENCES jugadores(cedula),
                    j2_cedula    TEXT NOT NULL REFERENCES jugadores(cedula),
                    j3_cedula    TEXT NOT NULL REFERENCES jugadores(cedula),
                    j4_cedula    TEXT NOT NULL REFERENCES jugadores(cedula),
                    puntos_p1    INTEGER DEFAULT 0,
                    puntos_p2    INTEGER DEFAULT 0,
                    puntos_base_p1 INTEGER DEFAULT 0,
                    puntos_base_p2 INTEGER DEFAULT 0,
                    descuento_p1 INTEGER DEFAULT 0,
                    descuento_p2 INTEGER DEFAULT 0,
                    motivo_penalizacion TEXT,
                    estado       TEXT NOT NULL CHECK (estado IN ('pendiente', 'finalizada'))
                );

                CREATE TABLE IF NOT EXISTS byes (
                    id         INTEGER PRIMARY KEY,
                    cedula     TEXT NOT NULL REFERENCES jugadores(cedula) ON DELETE CASCADE,
                    ronda_id   INTEGER NOT NULL REFERENCES rondas(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS auditoria_resultados (
                    id INTEGER PRIMARY KEY,
                    mesa_id INTEGER NOT NULL REFERENCES mesas(id) ON DELETE CASCADE,
                    fecha_hora TEXT NOT NULL,
                    puntos_base_p1 INTEGER NOT NULL,
                    puntos_base_p2 INTEGER NOT NULL,
                    descuento_p1 INTEGER NOT NULL,
                    descuento_p2 INTEGER NOT NULL,
                    puntos_final_p1 INTEGER NOT NULL,
                    puntos_final_p2 INTEGER NOT NULL,
                    motivo TEXT
                );

                CREATE TABLE IF NOT EXISTS historial_emparejamientos (
                    id INTEGER PRIMARY KEY,
                    torneo_id INTEGER NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
                    ronda_id INTEGER REFERENCES rondas(id) ON DELETE CASCADE,
                    numero_ronda INTEGER NOT NULL,
                    tipo_cambio TEXT NOT NULL,
                    mesa_a INTEGER NOT NULL,
                    mesa_b INTEGER,
                    detalle TEXT NOT NULL,
                    fecha_hora TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS history_auth (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    pin_salt BLOB NOT NULL,
                    pin_hash BLOB NOT NULL,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until REAL NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS history_security_answers (
                    question_id TEXT PRIMARY KEY,
                    answer_salt BLOB NOT NULL,
                    answer_hash BLOB NOT NULL
                );

                CREATE TABLE IF NOT EXISTS migraciones_datos (
                    id TEXT PRIMARY KEY,
                    aplicada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_torneo_jugadores_torneo
                    ON torneo_jugadores(torneo_id);
                CREATE INDEX IF NOT EXISTS idx_rondas_torneo_numero
                    ON rondas(torneo_id, numero_ronda);
                CREATE INDEX IF NOT EXISTS idx_mesas_ronda
                    ON mesas(ronda_id);
                CREATE INDEX IF NOT EXISTS idx_byes_ronda
                    ON byes(ronda_id);
                CREATE INDEX IF NOT EXISTS idx_historial_jugadores_cedula
                    ON historial_jugadores(cedula_jugador);
                CREATE INDEX IF NOT EXISTS idx_jugadores_vetados_fecha
                    ON jugadores_vetados(fecha_hora);
                CREATE INDEX IF NOT EXISTS idx_penalizaciones_torneo_jugador
                    ON penalizaciones(torneo_id, cedula);
                CREATE INDEX IF NOT EXISTS idx_historial_emparejamientos_torneo
                    ON historial_emparejamientos(torneo_id, numero_ronda);

                -- Estos índices aceleran el ranking por jugador y la búsqueda
                -- de penalizaciones por mesa sin recorrer todas las filas.
                CREATE INDEX IF NOT EXISTS idx_mesas_j1 ON mesas(j1_cedula);
                CREATE INDEX IF NOT EXISTS idx_mesas_j2 ON mesas(j2_cedula);
                CREATE INDEX IF NOT EXISTS idx_mesas_j3 ON mesas(j3_cedula);
                CREATE INDEX IF NOT EXISTS idx_mesas_j4 ON mesas(j4_cedula);
                CREATE INDEX IF NOT EXISTS idx_penalizaciones_mesa
                    ON penalizaciones(mesa_id, tipo);
                CREATE INDEX IF NOT EXISTS idx_club_jugadores_cedula
                    ON club_jugadores(cedula);
                """
            )
            columnas = {
                "torneos": {
                    "estado": "TEXT NOT NULL DEFAULT 'inscripcion'",
                    "modalidad": "TEXT NOT NULL DEFAULT 'intercalado'",
                    "jugadores_por_mesa": "INTEGER NOT NULL DEFAULT 4",
                    "permite_retiros": "INTEGER NOT NULL DEFAULT 1",
                    "fecha_finalizacion": "TEXT",
                    "edicion_historico": "INTEGER NOT NULL DEFAULT 0",
                },
                "rondas": {
                    "modalidad": "TEXT NOT NULL DEFAULT 'intercalado'",
                    "fecha_creacion": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
                },
                "mesas": {
                    "puntos_base_p1": "INTEGER DEFAULT 0",
                    "puntos_base_p2": "INTEGER DEFAULT 0",
                    "descuento_p1": "INTEGER DEFAULT 0",
                    "descuento_p2": "INTEGER DEFAULT 0",
                    "motivo_penalizacion": "TEXT",
                },
                "penalizaciones": {
                    "aplicada": "INTEGER NOT NULL DEFAULT 0",
                    "mesa_id": "INTEGER REFERENCES mesas(id) ON DELETE SET NULL",
                },
            }
            for tabla, definiciones in columnas.items():
                existentes = {
                    fila["name"]
                    for fila in conexion.execute(f"PRAGMA table_info({tabla})").fetchall()
                }
                for nombre, definicion in definiciones.items():
                    if nombre not in existentes:
                        conexion.execute(
                            f"ALTER TABLE {tabla} ADD COLUMN {nombre} {definicion}"
                        )
    finally:
        conexion.close()
