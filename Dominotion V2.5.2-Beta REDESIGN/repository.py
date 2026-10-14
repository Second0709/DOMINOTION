"""Reglas de negocio y consultas de persistencia para el torneo.

Este módulo concentra el acceso a SQLite para que la interfaz no gestione
conexiones ni construya SQL. Las escrituras que abarcan varios registros usan
una transacción: si falla una validación o una operación, SQLite revierte el
cambio completo. Los errores esperables de dominio se exponen como
``ErrorDatos`` y los listados devuelven filas de SQLite.
Al completar un torneo se guardan también copias de las clasificaciones para
que los cambios posteriores de nombres o clubes no alteren el resultado archivado.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import db as _db
from db import obtener_conexion

logger = logging.getLogger("dominotion")

# Una mano no puede sumar más que todas las fichas del juego: 270 puntos con dobles
# nueve (168 con dobles seis). Un marcador por encima de la meta + este margen es un
# error de captura y se rechaza.
EXCESO_MAXIMO_SOBRE_META = 270
# Cuántas copias de seguridad previas a una migración se conservan.
CANTIDAD_RESPALDOS_MIGRACION = 5
_respaldo_migracion_intentado = False


class ErrorDatos(Exception):
    """Error de validación o regla de negocio que la interfaz puede mostrar."""


# --------------------------------------------------------------------------
# Historial de Jugadores
# --------------------------------------------------------------------------

def registrar_historial_jugador(
    cedula: str, accion: str, detalle: str, conexion: sqlite3.Connection | None = None
) -> None:
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = """
        INSERT INTO historial_jugadores (cedula_jugador, fecha_hora, accion, detalle)
        VALUES (?, ?, ?, ?)
    """
    if conexion:
        conexion.execute(sql, (cedula, fecha_hora, accion, detalle))
    else:
        conn = obtener_conexion()
        try:
            with conn:
                conn.execute(sql, (cedula, fecha_hora, accion, detalle))
        finally:
            conn.close()


def obtener_historial_jugador(cedula: str) -> list[sqlite3.Row]:
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT fecha_hora, accion, detalle
            FROM historial_jugadores
            WHERE cedula_jugador = ?
            ORDER BY id DESC
            """,
            (cedula,),
        ).fetchall()
    finally:
        conexion.close()


# --------------------------------------------------------------------------
# Jugadores
# --------------------------------------------------------------------------

def crear_jugador(cedula: str, nombre: str, sexo: str) -> None:
    cedula_limpia = cedula.strip()
    nombre_limpio = nombre.strip()
    sexo_limpio = sexo.strip().upper()

    if not cedula_limpia or not nombre_limpio:
        raise ErrorDatos("La cédula y el nombre son obligatorios.")

    if sexo_limpio not in ("M", "F"):
        raise ErrorDatos("El sexo debe ser 'M' o 'F'.")

    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute(
                "INSERT INTO jugadores (cedula, nombre, sexo) VALUES (?, ?, ?)",
                (cedula_limpia, nombre_limpio, sexo_limpio),
            )
            registrar_historial_jugador(
                cedula_limpia,
                "CREACIÓN",
                f"Jugador creado: '{nombre_limpio}', Sexo: {sexo_limpio}",
                conexion=conexion,
            )
    except sqlite3.IntegrityError:
        raise ErrorDatos(f"Ya existe un jugador con cédula {cedula_limpia}.")
    finally:
        conexion.close()


def eliminar_jugador(cedula: str) -> None:
    actual = obtener_jugador(cedula)
    if actual is None:
        raise ErrorDatos(f"No existe un jugador con cédula {cedula}.")

    conexion = obtener_conexion()
    try:
        with conexion:
            # ON DELETE CASCADE borraría también sus descansos (BYE) y sanciones, lo
            # que reescribiría el historial; por eso se protege a quien ya participó.
            partidas = conexion.execute(
                "SELECT COUNT(*) FROM mesas WHERE ? IN (j1_cedula, j2_cedula, j3_cedula, j4_cedula)",
                (cedula,),
            ).fetchone()[0]
            descansos = conexion.execute(
                "SELECT COUNT(*) FROM byes WHERE cedula = ?", (cedula,)
            ).fetchone()[0]
            sanciones = conexion.execute(
                "SELECT COUNT(*) FROM penalizaciones WHERE cedula = ?", (cedula,)
            ).fetchone()[0]
            if partidas or descansos or sanciones:
                raise ErrorDatos(
                    f"No se puede eliminar a '{actual['nombre']}' porque tiene historial en "
                    f"torneos ({partidas} mesa(s), {descansos} descanso(s), {sanciones} "
                    "sanción(es)). Si no debe volver a participar, retírelo del torneo o "
                    "agréguelo a la lista de vetados."
                )
            conexion.execute("DELETE FROM jugadores WHERE cedula = ?", (cedula,))
    except sqlite3.IntegrityError:
        raise ErrorDatos(
            f"No se puede eliminar a '{actual['nombre']}' porque otros registros dependen de él."
        )
    finally:
        conexion.close()


def listar_jugadores() -> list[sqlite3.Row]:
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            "SELECT cedula, nombre, sexo FROM jugadores ORDER BY nombre"
        ).fetchall()
    finally:
        conexion.close()


def esta_jugador_vetado(cedula: str) -> bool:
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            "SELECT 1 FROM jugadores_vetados WHERE cedula = ?", (cedula.strip(),)
        ).fetchone() is not None
    finally:
        conexion.close()


def listar_jugadores_vetados() -> list[sqlite3.Row]:
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT v.cedula, j.nombre, j.sexo, v.fecha_hora, v.motivo
            FROM jugadores_vetados v
            JOIN jugadores j ON j.cedula = v.cedula
            ORDER BY v.fecha_hora DESC, j.nombre
            """
        ).fetchall()
    finally:
        conexion.close()


def vetar_jugador(cedula: str, motivo: str) -> None:
    cedula_limpia = cedula.strip()
    motivo_limpio = motivo.strip()
    if obtener_jugador(cedula_limpia) is None:
        raise ErrorDatos(f"No existe un jugador con cédula {cedula_limpia}.")
    if not motivo_limpio:
        raise ErrorDatos("Debe indicar el motivo del veto.")

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute(
                """
                INSERT INTO jugadores_vetados (cedula, fecha_hora, motivo)
                VALUES (?, ?, ?)
                """,
                (cedula_limpia, ahora, motivo_limpio),
            )
            registrar_historial_jugador(
                cedula_limpia,
                "VETO",
                f"Jugador vetado permanentemente hasta levantamiento manual. Motivo: {motivo_limpio}",
                conexion=conexion,
            )
    except sqlite3.IntegrityError:
        raise ErrorDatos("El jugador ya se encuentra vetado.")
    finally:
        conexion.close()


def levantar_veto_jugador(cedula: str) -> None:
    cedula_limpia = cedula.strip()
    conexion = obtener_conexion()
    try:
        with conexion:
            eliminado = conexion.execute(
                "DELETE FROM jugadores_vetados WHERE cedula = ?", (cedula_limpia,)
            ).rowcount
            if not eliminado:
                raise ErrorDatos("El jugador no se encuentra vetado.")
            registrar_historial_jugador(
                cedula_limpia,
                "LEVANTAMIENTO DE VETO",
                "Veto levantado manualmente.",
                conexion=conexion,
            )
    finally:
        conexion.close()


def obtener_jugador(cedula: str) -> sqlite3.Row | None:
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            "SELECT cedula, nombre, sexo FROM jugadores WHERE cedula = ?", (cedula,)
        ).fetchone()
    finally:
        conexion.close()


def editar_jugador(
    cedula_actual: str,
    nombre: str | None = None,
    sexo: str | None = None,
    nueva_cedula: str | None = None,
) -> None:
    actual = obtener_jugador(cedula_actual)
    if actual is None:
        raise ErrorDatos(f"No existe un jugador con cédula {cedula_actual}.")

    cedula_actual_str = str(actual["cedula"]).strip()

    target_cedula = cedula_actual_str
    if nueva_cedula is not None:
        nueva_cedula_clean = str(nueva_cedula).strip()
        if nueva_cedula_clean and nueva_cedula_clean != cedula_actual_str:
            target_cedula = nueva_cedula_clean

    nuevo_nombre = nombre.strip() if nombre and nombre.strip() else str(actual["nombre"])
    nuevo_sexo = sexo.strip().upper() if sexo and sexo.strip() else str(actual["sexo"])

    if nuevo_sexo not in ("M", "F"):
        raise ErrorDatos("El sexo debe ser 'M' o 'F'.")

    if nuevo_sexo != str(actual["sexo"]):
        conexion = obtener_conexion()
        try:
            conflicto = conexion.execute(
                """
                SELECT t.nombre, t.tipo
                FROM torneo_jugadores tj
                JOIN torneos t ON t.id = tj.torneo_id
                WHERE tj.cedula = ?
                  AND t.estado NOT IN ('finalizado', 'cancelado')
                  AND ((t.tipo = 'hombres' AND ? <> 'M')
                       OR (t.tipo = 'mujeres' AND ? <> 'F'))
                LIMIT 1
                """,
                (cedula_actual_str, nuevo_sexo, nuevo_sexo),
            ).fetchone()
        finally:
            conexion.close()
        if conflicto is not None:
            raise ErrorDatos(
                f"No se puede cambiar el sexo: el jugador está inscrito en el torneo "
                f"'{conflicto['nombre']}', que es solo para {conflicto['tipo']}. "
                "Retírelo del torneo primero."
            )

    if target_cedula != cedula_actual_str:
        existente = obtener_jugador(target_cedula)
        if existente is not None:
            raise ErrorDatos(f"Ya existe otro jugador con la cédula '{target_cedula}'.")

    cambios = []
    if target_cedula != cedula_actual_str:
        cambios.append(f"Cédula: {cedula_actual_str} ➔ {target_cedula}")
    if nuevo_nombre != actual["nombre"]:
        cambios.append(f"Nombre: '{actual['nombre']}' ➔ '{nuevo_nombre}'")
    if nuevo_sexo != actual["sexo"]:
        cambios.append(f"Sexo: {actual['sexo']} ➔ {nuevo_sexo}")

    if not cambios:
        return

    conexion = obtener_conexion()
    try:
        with conexion:
            # Algunas tablas (mesas, byes, penalizaciones) no tienen ON UPDATE CASCADE.
            # Se difiere la verificación de claves foráneas hasta confirmar la
            # transacción y se actualizan a mano junto con las copias archivadas.
            conexion.execute("PRAGMA defer_foreign_keys = ON")
            conexion.execute(
                "UPDATE jugadores SET cedula = ?, nombre = ?, sexo = ? WHERE cedula = ?",
                (target_cedula, nuevo_nombre, nuevo_sexo, cedula_actual_str),
            )
            if target_cedula != cedula_actual_str:
                for columna in ("j1_cedula", "j2_cedula", "j3_cedula", "j4_cedula"):
                    conexion.execute(
                        f"UPDATE mesas SET {columna} = ? WHERE {columna} = ?",
                        (target_cedula, cedula_actual_str),
                    )
                for tabla in (
                    "byes",
                    "penalizaciones",
                    "torneo_ranking_archivado",
                    "torneo_jugadores_archivados",
                    "torneo_ranking_club_archivado",
                ):
                    conexion.execute(
                        f"UPDATE {tabla} SET cedula = ? WHERE cedula = ?",
                        (target_cedula, cedula_actual_str),
                    )

            detalle_cambio = " | ".join(cambios)
            registrar_historial_jugador(
                target_cedula,
                "EDICIÓN",
                f"Modificación: {detalle_cambio}",
                conexion=conexion,
            )
    except sqlite3.IntegrityError as error:
        if obtener_jugador(target_cedula) is not None:
            raise ErrorDatos(f"La cédula '{target_cedula}' ya pertenece a otro registro.")
        raise ErrorDatos(
            "No se pudo actualizar la cédula porque la base de datos rechazó el cambio "
            f"por una restricción de integridad ({error})."
        )
    finally:
        conexion.close()


# --------------------------------------------------------------------------
# Clubes
# --------------------------------------------------------------------------

def crear_club(nombre: str) -> int:
    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        raise ErrorDatos("El nombre del club no puede estar vacío.")

    conexion = obtener_conexion()
    try:
        with conexion:
            cursor = conexion.execute(
                "INSERT INTO clubes (nombre) VALUES (?)", (nombre_limpio,)
            )
            return cursor.lastrowid
    except sqlite3.IntegrityError:
        raise ErrorDatos(f"Ya existe un club llamado '{nombre_limpio}'.")
    finally:
        conexion.close()


def listar_clubes() -> list[sqlite3.Row]:
    conexion = obtener_conexion()
    try:
        return conexion.execute("SELECT id, nombre FROM clubes ORDER BY nombre").fetchall()
    finally:
        conexion.close()


def listar_clubes_con_jugadores() -> list[sqlite3.Row]:
    """Clubes con jugadores asignados, filtrados en una sola consulta."""
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT c.id, c.nombre
            FROM clubes c
            WHERE EXISTS (
                SELECT 1 FROM club_jugadores cj WHERE cj.club_id = c.id
            )
            ORDER BY c.nombre
            """
        ).fetchall()
    finally:
        conexion.close()


def obtener_club(club_id: int) -> sqlite3.Row | None:
    conexion = obtener_conexion()
    try:
        return conexion.execute("SELECT id, nombre FROM clubes WHERE id = ?", (club_id,)).fetchone()
    finally:
        conexion.close()


def editar_club(club_id: int, nombre: str | None = None) -> None:
    actual = obtener_club(club_id)
    if actual is None:
        raise ErrorDatos(f"No existe un club con ID {club_id}.")

    if not nombre or not nombre.strip():
        return

    nuevo_nombre = nombre.strip()
    if nuevo_nombre == actual["nombre"]:
        return

    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute(
                "UPDATE clubes SET nombre = ? WHERE id = ?",
                (nuevo_nombre, club_id),
            )
    except sqlite3.IntegrityError:
        raise ErrorDatos(f"Ya existe un club llamado '{nuevo_nombre}'.")
    finally:
        conexion.close()


def listar_jugadores_de_club(club_id: int) -> list[sqlite3.Row]:
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT j.cedula, j.nombre, j.sexo
            FROM jugadores j
            JOIN club_jugadores cj ON cj.cedula = j.cedula
            WHERE cj.club_id = ?
            ORDER BY j.nombre
            """,
            (club_id,),
        ).fetchall()
    finally:
        conexion.close()


def asignar_jugador_a_club(cedula: str, club_id: int) -> None:
    if obtener_jugador(cedula) is None:
        raise ErrorDatos(f"No existe un jugador con cédula {cedula}.")
    if obtener_club(club_id) is None:
        raise ErrorDatos(f"No existe un club con ID {club_id}.")

    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute(
                "INSERT OR IGNORE INTO club_jugadores (club_id, cedula) VALUES (?, ?)",
                (club_id, cedula),
            )
            registrar_historial_jugador(
                cedula,
                "CLUB",
                f"Asignado al club ID {club_id}",
                conexion=conexion,
            )
    finally:
        conexion.close()


def retirar_jugador_de_club(cedula: str, club_id: int) -> None:
    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute(
                "DELETE FROM club_jugadores WHERE club_id = ? AND cedula = ?",
                (club_id, cedula),
            )
            registrar_historial_jugador(
                cedula,
                "CLUB",
                f"Retirado del club ID {club_id}",
                conexion=conexion,
            )
    finally:
        conexion.close()


def eliminar_club(club_id: int) -> None:
    actual = obtener_club(club_id)
    if actual is None:
        raise ErrorDatos(f"No existe un club con ID {club_id}.")

    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute("DELETE FROM clubes WHERE id = ?", (club_id,))
    finally:
        conexion.close()


# --------------------------------------------------------------------------
# Torneos
# --------------------------------------------------------------------------

def crear_torneo(
    nombre: str,
    duracion_minutos: int,
    tipo: str,
    puntaje_meta: int,
    num_rondas: int,
    modalidad: str = "intercalado",
    jugadores_por_mesa: int = 4,
    permite_retiros: bool = True,
) -> int:
    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        raise ErrorDatos("El nombre del torneo no puede estar vacío.")

    tipo_limpio = tipo.strip().lower()
    if tipo_limpio not in ("mixto", "hombres", "mujeres"):
        raise ErrorDatos("El tipo debe ser 'mixto', 'hombres' o 'mujeres'.")
        
    if duracion_minutos <= 0 or puntaje_meta <= 0 or num_rondas <= 0:
        raise ErrorDatos("La duración, puntaje meta y rondas deben ser mayores a 0.")
    if modalidad not in ("intercalado", "suizo_puro"):
        raise ErrorDatos("La modalidad debe ser 'intercalado' o 'suizo_puro'.")
    if jugadores_por_mesa != 4:
        raise ErrorDatos("Esta versión requiere mesas de 4 jugadores.")

    conexion = obtener_conexion()
    try:
        with conexion:
            cursor = conexion.execute(
                """
                INSERT INTO torneos
                    (nombre, duracion_minutos, tipo, puntaje_meta, num_rondas,
                     modalidad, jugadores_por_mesa, permite_retiros)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    nombre_limpio, duracion_minutos, tipo_limpio, puntaje_meta,
                    num_rondas, modalidad, jugadores_por_mesa, int(permite_retiros),
                ),
            )
            return cursor.lastrowid
    finally:
        conexion.close()


def listar_torneos() -> list[sqlite3.Row]:
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            "SELECT id, nombre, duracion_minutos, tipo, puntaje_meta, num_rondas, "
            "estado, modalidad, jugadores_por_mesa, permite_retiros "
            "FROM torneos ORDER BY id DESC"
        ).fetchall()
    finally:
        conexion.close()


def listar_torneos_activos() -> list[sqlite3.Row]:
    """Lista los torneos que todavía no están archivados como finalizados."""
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT id, nombre, duracion_minutos, tipo, puntaje_meta, num_rondas,
                   estado, modalidad, jugadores_por_mesa, permite_retiros
            FROM torneos
            WHERE estado != 'finalizado'
            ORDER BY id DESC
            """
        ).fetchall()
    finally:
        conexion.close()


def listar_torneos_finalizados() -> list[sqlite3.Row]:
    """Lista los torneos archivados y captura datos históricos aún no guardados."""
    torneos = obtener_conexion()
    try:
        filas = torneos.execute(
            """
            SELECT id, nombre, duracion_minutos, tipo, puntaje_meta, num_rondas,
                   estado, modalidad, jugadores_por_mesa, permite_retiros,
                   fecha_finalizacion
            FROM torneos
            WHERE estado = 'finalizado'
            ORDER BY COALESCE(fecha_finalizacion, '') DESC, id DESC
            """
        ).fetchall()
    finally:
        torneos.close()

    for torneo in filas:
        _asegurar_clasificaciones_archivadas(torneo["id"])
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT id, nombre, duracion_minutos, tipo, puntaje_meta, num_rondas,
                   estado, modalidad, jugadores_por_mesa, permite_retiros,
                   fecha_finalizacion
            FROM torneos
            WHERE estado = 'finalizado'
            ORDER BY COALESCE(fecha_finalizacion, '') DESC, id DESC
            """
        ).fetchall()
    finally:
        conexion.close()


def listar_clasificacion_archivada(
    torneo_id: int, sexo: str | None = None
) -> list[sqlite3.Row]:
    """Lista la clasificación archivada, opcionalmente filtrada por sexo."""
    if sexo is not None:
        sexo = sexo.upper()
        if sexo not in ("M", "F"):
            raise ErrorDatos("El filtro de sexo debe ser 'M' o 'F'.")
    _asegurar_clasificaciones_archivadas(torneo_id)
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT ranking.posicion, ranking.cedula, ranking.nombre,
                   ranking.pg, ranking.pp, ranking.ef, ranking.pf
            FROM torneo_ranking_archivado ranking
            JOIN torneo_jugadores_archivados jugador
              ON jugador.torneo_id = ranking.torneo_id
             AND jugador.cedula = ranking.cedula
            WHERE ranking.torneo_id = ?
              AND (? IS NULL OR jugador.sexo = ?)
            ORDER BY ranking.posicion
            """,
            (torneo_id, sexo, sexo),
        ).fetchall()
    finally:
        conexion.close()


def listar_clasificaciones_club_archivadas(torneo_id: int) -> dict[str, list[sqlite3.Row]]:
    _asegurar_clasificaciones_archivadas(torneo_id)
    conexion = obtener_conexion()
    try:
        filas = conexion.execute(
            """
            SELECT club_nombre, posicion, cedula, nombre, pg, pp, ef, pf
            FROM torneo_ranking_club_archivado
            WHERE torneo_id = ?
            ORDER BY club_nombre COLLATE NOCASE, posicion
            """,
            (torneo_id,),
        ).fetchall()
        clasificaciones: dict[str, list[sqlite3.Row]] = {}
        for fila in filas:
            clasificaciones.setdefault(fila["club_nombre"], []).append(fila)
        return clasificaciones
    finally:
        conexion.close()


def _asegurar_clasificaciones_archivadas(torneo_id: int) -> None:
    """Conserva una copia de las clasificaciones cuando se consulta un archivo antiguo."""
    conexion = obtener_conexion()
    try:
        torneo = conexion.execute(
            """
            SELECT estado, fecha_finalizacion,
                   (SELECT COUNT(*) FROM torneo_jugadores_archivados
                    WHERE torneo_id = torneos.id) AS jugadores_archivados,
                   (SELECT COUNT(*) FROM torneo_ranking_archivado
                    WHERE torneo_id = torneos.id) AS ranking_archivado,
                   (SELECT COUNT(*) FROM torneo_ranking_club_archivado
                    WHERE torneo_id = torneos.id) AS clubes_archivados,
                   EXISTS (
                       SELECT 1
                       FROM club_jugadores cj
                       JOIN torneo_jugadores tj ON tj.cedula = cj.cedula
                       WHERE tj.torneo_id = torneos.id
                   ) AS tiene_clubes
            FROM torneos
            WHERE id = ?
            """,
            (torneo_id,),
        ).fetchone()
    finally:
        conexion.close()
    if torneo is None or torneo["estado"] != "finalizado":
        return
    if not (
        torneo["jugadores_archivados"] > 0
        and torneo["ranking_archivado"] > 0
        and (torneo["clubes_archivados"] > 0 or not torneo["tiene_clubes"])
    ):
        _completar_clasificaciones_archivadas(
            torneo_id,
            guardar_jugadores=torneo["jugadores_archivados"] == 0,
            guardar_ranking=torneo["ranking_archivado"] == 0,
            guardar_clubes=torneo["clubes_archivados"] == 0 and torneo["tiene_clubes"],
        )
    _migrar_efectividad_clasificaciones_archivadas(torneo_id)


def _respaldar_bd_antes_de_migrar() -> Path | None:
    """Copia la base de datos a ``respaldos/`` antes de reescribir datos archivados.

    Se hace una sola vez por ejecución de la aplicación. Si no se puede copiar,
    se registra el aviso y la migración continúa (no debe impedir abrir el programa).
    """
    global _respaldo_migracion_intentado
    if _respaldo_migracion_intentado:
        return None
    _respaldo_migracion_intentado = True
    try:
        ruta = Path(_db.RUTA_BD)
        carpeta = ruta.parent / "respaldos"
        carpeta.mkdir(exist_ok=True)
        destino = carpeta / f"{ruta.stem}_antes_de_migrar_{datetime.now():%Y%m%d_%H%M%S}.db"
        origen = obtener_conexion()
        copia = sqlite3.connect(destino)
        try:
            origen.backup(copia)
        finally:
            copia.close()
            origen.close()
        antiguos = sorted(carpeta.glob(f"{ruta.stem}_antes_de_migrar_*.db"))
        for viejo in antiguos[:-CANTIDAD_RESPALDOS_MIGRACION]:
            viejo.unlink(missing_ok=True)
        return destino
    except (OSError, sqlite3.Error) as error:
        logger.warning("No se pudo crear la copia de seguridad previa a la migración: %s", error)
        return None


def _migracion_aplicada(migracion: str) -> bool:
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            "SELECT 1 FROM migraciones_datos WHERE id = ?", (migracion,)
        ).fetchone() is not None
    finally:
        conexion.close()


def _migrar_efectividad_clasificaciones_archivadas(torneo_id: int) -> None:
    """Actualiza una vez la EF del snapshot de un torneo archivado."""
    migracion = f"efectividad_objetivo_menos_puntos_perdedor_v2:{torneo_id}"
    if _migracion_aplicada(migracion):
        return
    _respaldar_bd_antes_de_migrar()
    conexion = obtener_conexion()
    try:
        with conexion:
            if conexion.execute(
                "SELECT 1 FROM migraciones_datos WHERE id = ?", (migracion,)
            ).fetchone():
                return

            resultados = conexion.execute(
                """
                WITH partidas AS (
                    SELECT r.torneo_id, m.*, t.puntaje_meta,
                           (
                               SELECT p.cedula FROM penalizaciones p
                               WHERE p.mesa_id = m.id AND p.tipo = 'tarjeta_roja'
                               ORDER BY p.id DESC LIMIT 1
                           ) AS infractor
                    FROM mesas m
                    JOIN rondas r ON r.id = m.ronda_id
                    JOIN torneos t ON t.id = r.torneo_id
                    WHERE m.estado = 'finalizada' AND r.torneo_id = ?
                ),
                participaciones AS (
                    SELECT j1_cedula AS cedula, puntos_p1 AS propios, puntos_p2 AS rivales,
                           puntaje_meta, infractor FROM partidas
                    UNION ALL
                    SELECT j2_cedula, puntos_p1, puntos_p2, puntaje_meta, infractor FROM partidas
                    UNION ALL
                    SELECT j3_cedula, puntos_p2, puntos_p1, puntaje_meta, infractor FROM partidas
                    UNION ALL
                    SELECT j4_cedula, puntos_p2, puntos_p1, puntaje_meta, infractor FROM partidas
                )
                SELECT cedula,
                       SUM(CASE
                           WHEN infractor IS NOT NULL AND cedula <> infractor THEN puntaje_meta
                           WHEN infractor IS NOT NULL THEN -puntaje_meta
                           WHEN propios > rivales THEN puntaje_meta - rivales
                           WHEN propios < rivales THEN -(puntaje_meta - propios)
                           ELSE 0
                       END) AS ef,
                       SUM(CASE
                           WHEN infractor IS NOT NULL AND cedula <> infractor THEN 1
                           WHEN infractor IS NOT NULL THEN 0
                           WHEN propios > rivales THEN 1
                           ELSE 0
                       END) AS pg,
                       SUM(CASE
                           WHEN infractor IS NOT NULL AND cedula <> infractor THEN 0
                           WHEN infractor IS NOT NULL THEN 1
                           WHEN propios < rivales OR (propios = 0 AND rivales = 0) THEN 1
                           ELSE 0
                       END) AS pp,
                       SUM(CASE
                           WHEN infractor IS NOT NULL AND cedula <> infractor THEN puntaje_meta
                           WHEN infractor IS NOT NULL THEN 0
                           ELSE propios
                       END) AS pf
                FROM participaciones
                GROUP BY cedula
                """,
                (torneo_id,),
            ).fetchall()
            por_jugador = {fila["cedula"]: fila for fila in resultados}
            # Torneos dañados por el antiguo error (motivo escrito a mano que empezaba por
            # "Tarjeta roja"): ahí también se corrigen PG, PP y PF, no solo la EF.
            afectado = conexion.execute(
                """
                SELECT 1
                FROM mesas m
                JOIN rondas r ON r.id = m.ronda_id
                WHERE r.torneo_id = ? AND m.estado = 'finalizada'
                  AND m.motivo_penalizacion LIKE 'Tarjeta roja%'
                  AND NOT EXISTS (
                      SELECT 1 FROM penalizaciones p
                      WHERE p.mesa_id = m.id AND p.tipo = 'tarjeta_roja'
                  )
                LIMIT 1
                """,
                (torneo_id,),
            ).fetchone() is not None
            descansos = {
                fila["cedula"]: fila["total"]
                for fila in conexion.execute(
                    """
                    SELECT b.cedula, COUNT(*) AS total
                    FROM byes b JOIN rondas r ON r.id = b.ronda_id
                    WHERE r.torneo_id = ?
                    GROUP BY b.cedula
                    """,
                    (torneo_id,),
                )
            }
            if resultados:
                for tabla in (
                    "torneo_ranking_archivado",
                    "torneo_ranking_club_archivado",
                ):
                    filas = conexion.execute(
                        f"SELECT cedula FROM {tabla} WHERE torneo_id = ?",
                        (torneo_id,),
                    ).fetchall()
                    for fila in filas:
                        datos = por_jugador.get(fila["cedula"])
                        ef = datos["ef"] if datos else 0
                        if afectado:
                            conexion.execute(
                                f"UPDATE {tabla} SET pg = ?, pp = ?, ef = ?, pf = ? "
                                "WHERE torneo_id = ? AND cedula = ?",
                                (
                                    (datos["pg"] if datos else 0)
                                    + descansos.get(fila["cedula"], 0),
                                    datos["pp"] if datos else 0,
                                    ef,
                                    datos["pf"] if datos else 0,
                                    torneo_id,
                                    fila["cedula"],
                                ),
                            )
                        else:
                            conexion.execute(
                                f"UPDATE {tabla} SET ef = ? WHERE torneo_id = ? AND cedula = ?",
                                (ef, torneo_id, fila["cedula"]),
                            )

                for tabla in (
                    "torneo_ranking_archivado",
                    "torneo_ranking_club_archivado",
                ):
                    es_clasificacion_club = tabla == "torneo_ranking_club_archivado"
                    clubes = (
                        conexion.execute(
                            f"SELECT DISTINCT club_nombre FROM {tabla} "
                            "WHERE torneo_id = ?",
                            (torneo_id,),
                        ).fetchall()
                        if es_clasificacion_club
                        else [None]
                    )
                    for club in clubes:
                        clausula_club = (
                            " AND club_nombre = ?" if es_clasificacion_club else ""
                        )
                        parametros = (
                            (torneo_id, club["club_nombre"])
                            if es_clasificacion_club
                            else (torneo_id,)
                        )
                        filas = conexion.execute(
                            f"""
                            SELECT cedula, pg, ef, pf, nombre
                            FROM {tabla}
                            WHERE torneo_id = ?{clausula_club}
                            ORDER BY pg DESC, ef DESC, pf DESC,
                                     nombre COLLATE NOCASE, cedula
                            """,
                            parametros,
                        ).fetchall()
                        for fila in filas:
                            conexion.execute(
                                f"UPDATE {tabla} SET posicion = -posicion "
                                f"WHERE torneo_id = ?{clausula_club} AND cedula = ?",
                                (*parametros, fila["cedula"]),
                            )
                        for posicion, fila in enumerate(filas, start=1):
                            conexion.execute(
                                f"UPDATE {tabla} SET posicion = ? "
                                f"WHERE torneo_id = ?{clausula_club} AND cedula = ?",
                                (posicion, *parametros, fila["cedula"]),
                            )

            conexion.execute(
                "INSERT INTO migraciones_datos (id) VALUES (?)", (migracion,)
            )
    finally:
        conexion.close()


def _completar_clasificaciones_archivadas(
    torneo_id: int,
    *,
    guardar_jugadores: bool,
    guardar_ranking: bool,
    guardar_clubes: bool,
) -> None:
    """Completa snapshots ausentes sin sobrescribir los datos históricos existentes."""
    if not any((guardar_jugadores, guardar_ranking, guardar_clubes)):
        return

    participantes: list[sqlite3.Row] = []
    ranking_general: list[sqlite3.Row] = []
    ranking_clubes: list[tuple[str, list[sqlite3.Row]]] = []
    if guardar_jugadores:
        conexion = obtener_conexion()
        try:
            participantes = conexion.execute(
                """
                SELECT DISTINCT j.cedula, j.nombre, j.sexo
                FROM jugadores j
                JOIN (
                    SELECT torneo_id, cedula FROM torneo_jugadores
                    UNION
                    SELECT torneo_id, cedula FROM torneo_jugadores_retirados
                ) participantes
                  ON participantes.cedula = j.cedula
                 AND participantes.torneo_id = ?
                ORDER BY j.nombre COLLATE NOCASE
                """,
                (torneo_id,),
            ).fetchall()
        finally:
            conexion.close()

    if guardar_ranking:
        ranking_general = obtener_ranking_torneo(torneo_id)

    if guardar_clubes:
        conexion = obtener_conexion()
        try:
            clubes = conexion.execute(
                """
                SELECT DISTINCT c.id, c.nombre
                FROM clubes c
                JOIN club_jugadores cj ON cj.club_id = c.id
                JOIN torneo_jugadores tj ON tj.cedula = cj.cedula
                WHERE tj.torneo_id = ?
                ORDER BY c.nombre COLLATE NOCASE
                """,
                (torneo_id,),
            ).fetchall()
        finally:
            conexion.close()
        ranking_clubes = [
            (club["nombre"], obtener_ranking_torneo(torneo_id, club_id=club["id"]))
            for club in clubes
        ]

    conexion = obtener_conexion()
    try:
        with conexion:
            if guardar_jugadores:
                conexion.executemany(
                    """
                    INSERT OR IGNORE INTO torneo_jugadores_archivados
                        (torneo_id, cedula, nombre, sexo)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (torneo_id, jugador["cedula"], jugador["nombre"], jugador["sexo"])
                        for jugador in participantes
                    ],
                )
            if guardar_ranking:
                conexion.executemany(
                    """
                    INSERT OR IGNORE INTO torneo_ranking_archivado
                        (torneo_id, posicion, cedula, nombre, pg, pp, ef, pf)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            torneo_id, posicion, jugador["cedula"], jugador["nombre"],
                            jugador["pg"], jugador["pp"], jugador["ef"], jugador["pf"],
                        )
                        for posicion, jugador in enumerate(ranking_general, start=1)
                    ],
                )
            if guardar_clubes:
                conexion.executemany(
                    """
                    INSERT OR IGNORE INTO torneo_ranking_club_archivado
                        (torneo_id, club_nombre, posicion, cedula, nombre, pg, pp, ef, pf)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            torneo_id, nombre_club, posicion, jugador["cedula"],
                            jugador["nombre"], jugador["pg"], jugador["pp"],
                            jugador["ef"], jugador["pf"],
                        )
                        for nombre_club, ranking in ranking_clubes
                        for posicion, jugador in enumerate(ranking, start=1)
                    ],
                )
            conexion.execute(
                """
                UPDATE torneos
                SET fecha_finalizacion = COALESCE(fecha_finalizacion, ?)
                WHERE id = ? AND estado = 'finalizado'
                """,
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), torneo_id),
            )
    finally:
        conexion.close()


def _guardar_clasificaciones_archivadas(torneo_id: int) -> None:
    """Guarda rankings calculados y nombres de clubes tal como estaban al archivar."""
    torneo = obtener_torneo(torneo_id)
    if torneo is None:
        raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")

    ranking_general = obtener_ranking_torneo(torneo_id)
    conexion = obtener_conexion()
    try:
        clubes = conexion.execute(
            """
            SELECT DISTINCT c.id, c.nombre
            FROM clubes c
            JOIN club_jugadores cj ON cj.club_id = c.id
            JOIN torneo_jugadores tj ON tj.cedula = cj.cedula
            WHERE tj.torneo_id = ?
            ORDER BY c.nombre COLLATE NOCASE
            """,
            (torneo_id,),
        ).fetchall()
        participantes = conexion.execute(
            """
            SELECT DISTINCT j.cedula, j.nombre, j.sexo
            FROM jugadores j
            JOIN (
                SELECT torneo_id, cedula FROM torneo_jugadores
                UNION
                SELECT torneo_id, cedula FROM torneo_jugadores_retirados
            ) participantes
              ON participantes.cedula = j.cedula
             AND participantes.torneo_id = ?
            ORDER BY j.nombre COLLATE NOCASE
            """,
            (torneo_id,),
        ).fetchall()
    finally:
        conexion.close()

    ranking_clubes = [
        (club["nombre"], obtener_ranking_torneo(torneo_id, club_id=club["id"]))
        for club in clubes
    ]
    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute(
                "DELETE FROM torneo_ranking_archivado WHERE torneo_id = ?",
                (torneo_id,),
            )
            conexion.execute(
                "DELETE FROM torneo_ranking_club_archivado WHERE torneo_id = ?",
                (torneo_id,),
            )
            conexion.execute(
                "DELETE FROM torneo_jugadores_archivados WHERE torneo_id = ?",
                (torneo_id,),
            )
            conexion.executemany(
                """
                INSERT INTO torneo_ranking_archivado
                    (torneo_id, posicion, cedula, nombre, pg, pp, ef, pf)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        torneo_id, posicion, jugador["cedula"], jugador["nombre"],
                        jugador["pg"], jugador["pp"], jugador["ef"], jugador["pf"],
                    )
                    for posicion, jugador in enumerate(ranking_general, start=1)
                ],
            )
            conexion.executemany(
                """
                INSERT INTO torneo_ranking_club_archivado
                    (torneo_id, club_nombre, posicion, cedula, nombre, pg, pp, ef, pf)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        torneo_id, nombre_club, posicion, jugador["cedula"],
                        jugador["nombre"], jugador["pg"], jugador["pp"],
                        jugador["ef"], jugador["pf"],
                    )
                    for nombre_club, ranking in ranking_clubes
                    for posicion, jugador in enumerate(ranking, start=1)
                ],
            )
            conexion.executemany(
                """
                INSERT INTO torneo_jugadores_archivados
                    (torneo_id, cedula, nombre, sexo)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (torneo_id, jugador["cedula"], jugador["nombre"], jugador["sexo"])
                    for jugador in participantes
                ],
            )
            conexion.execute(
                """
                UPDATE torneos
                SET fecha_finalizacion = COALESCE(fecha_finalizacion, ?)
                WHERE id = ? AND estado = 'finalizado'
                """,
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), torneo_id),
            )
    finally:
        conexion.close()


def continuar_torneo_finalizado(torneo_id: int, rondas_adicionales: int) -> None:
    """Reabre un torneo archivado y amplía la cantidad de rondas programadas."""
    if not isinstance(rondas_adicionales, int) or rondas_adicionales <= 0:
        raise ErrorDatos("La cantidad de rondas adicionales debe ser un entero mayor que 0.")
    conexion = obtener_conexion()
    try:
        with conexion:
            torneo = conexion.execute(
                """
                SELECT estado, num_rondas,
                       (SELECT COUNT(*) FROM rondas r WHERE r.torneo_id = torneos.id) AS rondas
                FROM torneos WHERE id = ?
                """,
                (torneo_id,),
            ).fetchone()
            if torneo is None:
                raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")
            if torneo["estado"] != "finalizado":
                raise ErrorDatos("Solo se pueden continuar torneos finalizados.")
            if torneo["rondas"] < torneo["num_rondas"]:
                raise ErrorDatos("El torneo no completó todas las rondas programadas.")
            incompletas = conexion.execute(
                """
                SELECT COUNT(*) FROM mesas m
                JOIN rondas r ON r.id = m.ronda_id
                WHERE r.torneo_id = ? AND m.estado != 'finalizada'
                """,
                (torneo_id,),
            ).fetchone()[0]
            if incompletas:
                raise ErrorDatos("El torneo tiene mesas pendientes y no se puede continuar.")
            conexion.execute(
                """
                UPDATE torneos
                SET num_rondas = num_rondas + ?, estado = 'en_curso',
                    edicion_historico = 0, fecha_finalizacion = NULL
                WHERE id = ?
                """,
                (rondas_adicionales, torneo_id),
            )
    finally:
        conexion.close()


def reabrir_torneo_finalizado_para_edicion(torneo_id: int) -> None:
    """Habilita temporalmente la edición de un torneo archivado desde En Vivo."""
    conexion = obtener_conexion()
    try:
        with conexion:
            cursor = conexion.execute(
                """
                UPDATE torneos
                SET estado = 'en_curso', edicion_historico = 1
                WHERE id = ? AND estado = 'finalizado'
                """,
                (torneo_id,),
            )
            if cursor.rowcount == 0:
                existe = conexion.execute(
                    "SELECT 1 FROM torneos WHERE id = ?", (torneo_id,)
                ).fetchone()
                if existe is None:
                    raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")
                raise ErrorDatos("El torneo ya no está finalizado.")
    finally:
        conexion.close()


def archivar_edicion_historica(torneo_id: int) -> None:
    """Cierra una sesión de edición histórica si todas las rondas están completas."""
    conexion = obtener_conexion()
    try:
        with conexion:
            torneo = conexion.execute(
                """
                SELECT id, estado, edicion_historico, num_rondas,
                       (SELECT COUNT(*) FROM rondas r WHERE r.torneo_id = torneos.id) AS rondas
                FROM torneos WHERE id = ?
                """,
                (torneo_id,),
            ).fetchone()
            if torneo is None:
                raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")
            if not torneo["edicion_historico"] or torneo["estado"] != "en_curso":
                raise ErrorDatos("El torneo no está abierto desde el historial para editarse.")
            if torneo["rondas"] < torneo["num_rondas"]:
                raise ErrorDatos(
                    "No se puede archivar: faltan rondas programadas. "
                    "Completa la continuación o ajusta las rondas antes de cerrar la edición."
                )
            pendientes = conexion.execute(
                """
                SELECT COUNT(*) FROM mesas m
                JOIN rondas r ON r.id = m.ronda_id
                WHERE r.torneo_id = ? AND m.estado != 'finalizada'
                """,
                (torneo_id,),
            ).fetchone()[0]
            if pendientes:
                raise ErrorDatos("No se puede archivar: todavía hay mesas pendientes.")
            rondas_incompletas = conexion.execute(
                "SELECT COUNT(*) FROM rondas WHERE torneo_id = ? AND estado != 'finalizada'",
                (torneo_id,),
            ).fetchone()[0]
            if rondas_incompletas:
                raise ErrorDatos("No se puede archivar: todavía hay rondas sin finalizar.")
            conexion.execute(
                """
                UPDATE torneos
                SET estado = 'finalizado', edicion_historico = 0,
                    fecha_finalizacion = ?
                WHERE id = ?
                """,
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), torneo_id),
            )
    finally:
        conexion.close()
    _guardar_clasificaciones_archivadas(torneo_id)


def obtener_torneo(torneo_id: int) -> sqlite3.Row | None:
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            "SELECT id, nombre, duracion_minutos, tipo, puntaje_meta, num_rondas, "
            "estado, modalidad, jugadores_por_mesa, permite_retiros, "
            "fecha_finalizacion, edicion_historico "
            "FROM torneos WHERE id = ?",
            (torneo_id,),
        ).fetchone()
    finally:
        conexion.close()


def editar_torneo(torneo_id: int, **campos) -> None:
    if not campos:
        return
    columnas_validas = {
        "nombre", "duracion_minutos", "tipo", "puntaje_meta", "num_rondas",
        "estado", "modalidad", "jugadores_por_mesa", "permite_retiros",
    }
    campos = {k: v for k, v in campos.items() if k in columnas_validas and v is not None}
    if not campos:
        return

    actual = obtener_torneo(torneo_id)
    if actual is None:
        raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")

    campos_permitidos_iniciado = {"duracion_minutos", "num_rondas"}
    if actual["estado"] not in ("borrador", "inscripcion"):
        campos_no_permitidos = set(campos) - campos_permitidos_iniciado
        if campos_no_permitidos:
            raise ErrorDatos(
                "Un torneo iniciado solo permite modificar la duración "
                "y el número de rondas."
            )

    if "nombre" in campos and not str(campos["nombre"]).strip():
        raise ErrorDatos("El nombre del torneo no puede estar vacío.")
    if "tipo" in campos and str(campos["tipo"]).strip().lower() not in (
        "mixto",
        "hombres",
        "mujeres",
    ):
        raise ErrorDatos("El tipo debe ser 'mixto', 'hombres' o 'mujeres'.")
    if "tipo" in campos:
        nuevo_tipo = str(campos["tipo"]).strip().lower()
        requerido = sexo_requerido_por_tipo(nuevo_tipo)
        if requerido is not None and nuevo_tipo != str(actual["tipo"]).strip().lower():
            conexion = obtener_conexion()
            try:
                incompatibles = conexion.execute(
                    """
                    SELECT j.nombre
                    FROM torneo_jugadores tj
                    JOIN jugadores j ON j.cedula = tj.cedula
                    WHERE tj.torneo_id = ? AND j.sexo <> ?
                    ORDER BY j.nombre COLLATE NOCASE
                    """,
                    (torneo_id, requerido),
                ).fetchall()
            finally:
                conexion.close()
            if incompatibles:
                nombres = ", ".join(f["nombre"] for f in incompatibles[:3])
                resto = len(incompatibles) - 3
                if resto > 0:
                    nombres += f" y {resto} más"
                raise ErrorDatos(
                    f"No se puede cambiar el torneo a solo {nuevo_tipo}: hay "
                    f"{len(incompatibles)} jugador(es) inscrito(s) del otro sexo ({nombres}). "
                    "Retírelos del torneo o mantenga el tipo mixto."
                )
    if "estado" in campos and campos["estado"] not in (
        "borrador", "inscripcion", "en_curso", "pausado", "finalizado", "cancelado"
    ):
        raise ErrorDatos("Estado de torneo no válido.")
    if "modalidad" in campos and campos["modalidad"] not in ("intercalado", "suizo_puro"):
        raise ErrorDatos("Modalidad no válida.")
    for campo in ("duracion_minutos", "puntaje_meta", "num_rondas"):
        if campo in campos and (not isinstance(campos[campo], int) or campos[campo] <= 0):
            raise ErrorDatos(f"{campo} debe ser un entero mayor que 0.")

    if "nombre" in campos:
        campos["nombre"] = str(campos["nombre"]).strip()
    if "tipo" in campos:
        campos["tipo"] = str(campos["tipo"]).strip().lower()

    set_clause = ", ".join(f"{col} = ?" for col in campos)
    valores = list(campos.values()) + [torneo_id]

    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute(f"UPDATE torneos SET {set_clause} WHERE id = ?", valores)
    finally:
        conexion.close()
    if campos.get("estado") == "finalizado":
        _guardar_clasificaciones_archivadas(torneo_id)


def eliminar_torneo(torneo_id: int) -> None:
    actual = obtener_torneo(torneo_id)
    if actual is None:
        raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")

    conexion = obtener_conexion()
    try:
        with conexion:
            conexion.execute("DELETE FROM torneos WHERE id = ?", (torneo_id,))
    finally:
        conexion.close()


def eliminar_torneo_finalizado(torneo_id: int) -> None:
    """Elimina un torneo archivado y sus datos relacionados en una transacción."""
    conexion = obtener_conexion()
    try:
        with conexion:
            torneo = conexion.execute(
                "SELECT estado FROM torneos WHERE id = ?", (torneo_id,)
            ).fetchone()
            if torneo is None:
                raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")
            if torneo["estado"] != "finalizado":
                raise ErrorDatos("Solo se pueden eliminar torneos que estén finalizados.")
            conexion.execute("DELETE FROM torneos WHERE id = ?", (torneo_id,))
    finally:
        conexion.close()


# Tipos de torneo restringidos por sexo: tipo -> sexo permitido.
_SEXO_POR_TIPO = {"hombres": "M", "mujeres": "F"}
_NOMBRE_SEXO = {"M": "hombre", "F": "mujer"}


def sexo_requerido_por_tipo(tipo: str | None) -> str | None:
    """'M' si el torneo es solo de hombres, 'F' si es solo de mujeres, None si es mixto."""
    return _SEXO_POR_TIPO.get(str(tipo or "").strip().lower())


def validar_sexo_para_torneo(
    torneo_id: int, sexo: str | None, nombre_jugador: str | None = None
) -> None:
    """Rechaza a un jugador cuyo sexo no corresponde al tipo del torneo.

    Un torneo ``hombres`` solo admite sexo 'M' y uno ``mujeres`` solo 'F'; el
    ``mixto`` admite ambos. Se usa antes de crear o inscribir a un jugador.
    """
    torneo = obtener_torneo(torneo_id)
    if torneo is None:
        raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")
    requerido = sexo_requerido_por_tipo(torneo["tipo"])
    sexo_limpio = str(sexo or "").strip().upper()
    if requerido is None or sexo_limpio == requerido:
        return
    mensaje = f"El torneo '{torneo['nombre']}' es solo para {str(torneo['tipo']).lower()}."
    if sexo_limpio in _NOMBRE_SEXO:
        quien = f"El jugador '{nombre_jugador}'" if nombre_jugador else "El jugador"
        mensaje += f" {quien} está registrado como {_NOMBRE_SEXO[sexo_limpio]}."
    raise ErrorDatos(mensaje)


def listar_jugadores_para_inscripcion(torneo_id: int) -> list[sqlite3.Row]:
    """Jugadores que pueden inscribirse según el tipo del torneo (todos si es mixto)."""
    torneo = obtener_torneo(torneo_id)
    if torneo is None:
        raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")
    requerido = sexo_requerido_por_tipo(torneo["tipo"])
    jugadores = listar_jugadores()
    if requerido is None:
        return jugadores
    return [j for j in jugadores if j["sexo"] == requerido]


def inscribir_jugador_a_torneo(cedula: str, torneo_id: int) -> bool:
    jugador = obtener_jugador(cedula)
    if jugador is None:
        raise ErrorDatos(f"No existe un jugador con cédula {cedula}.")
    if obtener_torneo(torneo_id) is None:
        raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")
    validar_sexo_para_torneo(torneo_id, jugador["sexo"], jugador["nombre"])

    conexion = obtener_conexion()
    try:
        with conexion:
            expulsado = conexion.execute(
                """
                SELECT 1
                FROM torneo_jugadores_retirados
                WHERE torneo_id = ? AND cedula = ?
                  AND motivo LIKE 'Tarjeta roja%'
                """,
                (torneo_id, cedula),
            ).fetchone()
            if expulsado is not None:
                raise ErrorDatos(
                    "El jugador fue expulsado con tarjeta roja y no puede volver a ingresar al torneo."
                )
            vetado = conexion.execute(
                "SELECT 1 FROM jugadores_vetados WHERE cedula = ?", (cedula,)
            ).fetchone()
            if vetado is not None:
                raise ErrorDatos(
                    "El jugador está vetado y no puede inscribirse hasta que el veto sea levantado manualmente."
                )
            cursor = conexion.execute(
                "INSERT OR IGNORE INTO torneo_jugadores (torneo_id, cedula) VALUES (?, ?)",
                (torneo_id, cedula),
            )
            if cursor.rowcount == 0:
                return False
            conexion.execute(
                "DELETE FROM torneo_jugadores_retirados WHERE torneo_id = ? AND cedula = ?",
                (torneo_id, cedula),
            )
            registrar_historial_jugador(
                cedula,
                "TORNEO",
                f"Inscrito en torneo ID {torneo_id}",
                conexion=conexion,
            )
        return True
    finally:
        conexion.close()


def retirar_jugador_de_torneo(cedula: str, torneo_id: int) -> None:
    conexion = obtener_conexion()
    try:
        with conexion:
            inscrito = conexion.execute(
                """
                SELECT 1 FROM torneo_jugadores
                WHERE torneo_id = ? AND cedula = ?
                """,
                (torneo_id, cedula),
            ).fetchone()
            if inscrito is None:
                raise ErrorDatos("El jugador no está inscrito en este torneo.")

            conexion.execute(
                "DELETE FROM torneo_jugadores WHERE torneo_id = ? AND cedula = ?",
                (torneo_id, cedula),
            )
            conexion.execute(
                """
                INSERT OR REPLACE INTO torneo_jugadores_retirados
                    (torneo_id, cedula, fecha_hora, motivo)
                VALUES (?, ?, ?, ?)
                """,
                (torneo_id, cedula, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Retiro"),
            )
            registrar_historial_jugador(
                cedula,
                "TORNEO",
                f"Retirado del torneo ID {torneo_id}",
                conexion=conexion,
            )
    finally:
        conexion.close()


def listar_penalizaciones_torneo(torneo_id: int) -> list[sqlite3.Row]:
    """Lista participantes del torneo con sus faltas y estado disciplinario."""
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT j.cedula, j.nombre,
                   COUNT(p.id) AS faltas,
                   MAX(CASE WHEN p.tipo = 'tarjeta_roja' THEN 1 ELSE 0 END) AS tiene_roja
            FROM jugadores j
            JOIN (
                SELECT torneo_id, cedula FROM torneo_jugadores
                UNION
                SELECT torneo_id, cedula FROM torneo_jugadores_retirados
            ) participantes
              ON participantes.cedula = j.cedula
             AND participantes.torneo_id = ?
            LEFT JOIN penalizaciones p
              ON p.torneo_id = participantes.torneo_id
             AND p.cedula = participantes.cedula
            GROUP BY j.cedula, j.nombre
            ORDER BY j.nombre
            """,
            (torneo_id,),
        ).fetchall()
    finally:
        conexion.close()


def listar_detalle_penalizaciones_torneo(torneo_id: int) -> list[sqlite3.Row]:
    """Lista cada sanción con jugador, ronda, mesa y motivo para el archivo."""
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT p.id, p.cedula, COALESCE(ja.nombre, j.nombre) AS nombre,
                   p.numero_falta, p.tipo, p.motivo,
                   p.fecha_hora, p.aplicada, r.numero_ronda, m.numero_mesa
            FROM penalizaciones p
            JOIN jugadores j ON j.cedula = p.cedula
            LEFT JOIN torneo_jugadores_archivados ja
              ON ja.torneo_id = p.torneo_id AND ja.cedula = p.cedula
            LEFT JOIN mesas m ON m.id = p.mesa_id
            LEFT JOIN rondas r ON r.id = m.ronda_id
            WHERE p.torneo_id = ?
            ORDER BY p.fecha_hora, p.id
            """,
            (torneo_id,),
        ).fetchall()
    finally:
        conexion.close()


def rojas_aplicadas_en_ultima_ronda(torneo_id: int) -> list[str]:
    """Nombres de los jugadores expulsados con tarjeta roja en la última ronda.

    Eliminar la ronda no revierte esas expulsiones; la interfaz lo avisa con esta lista.
    """
    conexion = obtener_conexion()
    try:
        filas = conexion.execute(
            """
            SELECT DISTINCT j.nombre
            FROM penalizaciones p
            JOIN mesas m ON m.id = p.mesa_id
            JOIN rondas r ON r.id = m.ronda_id
            JOIN jugadores j ON j.cedula = p.cedula
            WHERE r.torneo_id = ? AND p.tipo = 'tarjeta_roja' AND p.aplicada = 1
              AND r.numero_ronda = (
                  SELECT MAX(numero_ronda) FROM rondas WHERE torneo_id = ?
              )
            ORDER BY j.nombre COLLATE NOCASE
            """,
            (torneo_id, torneo_id),
        ).fetchall()
        return [fila["nombre"] for fila in filas]
    finally:
        conexion.close()


def _mesa_tiene_roja(conexion: sqlite3.Connection, mesa_id: int) -> bool:
    """True si la mesa se cerró por una tarjeta roja registrada en ``penalizaciones``.

    Se consulta la tabla (no el texto del motivo, que el usuario puede escribir).
    """
    return conexion.execute(
        "SELECT 1 FROM penalizaciones WHERE mesa_id = ? AND tipo = 'tarjeta_roja' LIMIT 1",
        (mesa_id,),
    ).fetchone() is not None


def _cerrar_ronda_si_corresponde(conexion: sqlite3.Connection, mesa_id: int) -> int | None:
    """Cierra la ronda de la mesa si ya no quedan mesas sin resultado.

    Si era la última ronda del torneo (y no es una edición histórica) también
    finaliza el torneo. Devuelve el id del torneo finalizado, o ``None``. Quien
    la llame debe guardar las clasificaciones archivadas tras confirmar la
    transacción. Lo comparten el marcador, el forfeit y la tarjeta roja.
    """
    ronda = conexion.execute(
        """
        SELECT r.id, r.torneo_id, r.numero_ronda, t.num_rondas, t.edicion_historico
        FROM rondas r
        JOIN torneos t ON t.id = r.torneo_id
        JOIN mesas m ON m.ronda_id = r.id
        WHERE m.id = ?
        """,
        (mesa_id,),
    ).fetchone()
    if ronda is None:
        return None
    pendientes = conexion.execute(
        "SELECT COUNT(*) AS total FROM mesas WHERE ronda_id = ? AND estado != 'finalizada'",
        (ronda["id"],),
    ).fetchone()["total"]
    if pendientes:
        return None
    conexion.execute("UPDATE rondas SET estado = 'finalizada' WHERE id = ?", (ronda["id"],))
    if ronda["numero_ronda"] >= ronda["num_rondas"] and not ronda["edicion_historico"]:
        conexion.execute(
            "UPDATE torneos SET estado = 'finalizado', fecha_finalizacion = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ronda["torneo_id"]),
        )
        return ronda["torneo_id"]
    return None


def _registrar_penalizacion(
    torneo_id: int,
    cedula: str,
    motivo: str | None = None,
    roja_directa: bool = False,
) -> tuple[str, int | None]:
    """Núcleo de ``registrar_penalizacion``: devuelve (mensaje, torneo finalizado o None)."""
    torneo_finalizado_id = None
    conexion = obtener_conexion()
    try:
        with conexion:
            activo = conexion.execute(
                """
                SELECT j.nombre
                FROM torneo_jugadores tj
                JOIN jugadores j ON j.cedula = tj.cedula
                WHERE tj.torneo_id = ? AND tj.cedula = ?
                """,
                (torneo_id, cedula),
            ).fetchone()
            if activo is None:
                raise ErrorDatos("El jugador no está activo en este torneo.")

            faltas = conexion.execute(
                """
                SELECT COUNT(*) AS total
                FROM penalizaciones
                WHERE torneo_id = ? AND cedula = ?
                """,
                (torneo_id, cedula),
            ).fetchone()["total"]
            numero_falta = faltas + 1
            es_roja = roja_directa or numero_falta >= 3
            tipo = "tarjeta_roja" if es_roja else "tarjeta_amarilla"
            ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            penalizacion = conexion.execute(
                """
                INSERT INTO penalizaciones
                    (torneo_id, cedula, numero_falta, tipo, motivo, fecha_hora, aplicada)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (torneo_id, cedula, numero_falta, tipo, motivo, ahora),
            )

            if es_roja:
                mesa = conexion.execute(
                    """
                    SELECT m.id, m.j1_cedula, m.j2_cedula, m.j3_cedula,
                           m.j4_cedula, t.puntaje_meta
                    FROM mesas m
                    JOIN rondas r ON r.id = m.ronda_id
                    JOIN torneos t ON t.id = r.torneo_id
                    WHERE r.torneo_id = ? AND r.estado = 'en_curso'
                      AND m.estado != 'finalizada'
                      AND (
                          m.j1_cedula = ? OR m.j2_cedula = ?
                          OR m.j3_cedula = ? OR m.j4_cedula = ?
                      )
                    ORDER BY r.numero_ronda DESC
                    LIMIT 1
                    """,
                    (torneo_id, cedula, cedula, cedula, cedula),
                ).fetchone()
                if mesa is None:
                    # Sin mesa abierta: o está descansando (BYE) o su mesa de esta ronda
                    # ya tiene marcador. En ambos casos la roja queda pendiente y NO se
                    # toca ningún resultado ya registrado.
                    mesa_cerrada = conexion.execute(
                        """
                        SELECT 1
                        FROM mesas m
                        JOIN rondas r ON r.id = m.ronda_id
                        WHERE r.torneo_id = ? AND r.estado = 'en_curso'
                          AND m.estado = 'finalizada'
                          AND (
                              m.j1_cedula = ? OR m.j2_cedula = ?
                              OR m.j3_cedula = ? OR m.j4_cedula = ?
                          )
                        LIMIT 1
                        """,
                        (torneo_id, cedula, cedula, cedula, cedula),
                    ).fetchone()
                    registrar_historial_jugador(
                        cedula,
                        "TARJETA ROJA PENDIENTE",
                        "La expulsión se aplicará en la siguiente mesa donde sea emparejado.",
                        conexion=conexion,
                    )
                    if mesa_cerrada is not None:
                        return (
                            "Tarjeta roja registrada como pendiente. La mesa actual del "
                            "jugador ya tiene marcador y se conserva; la expulsión se "
                            "aplicará en la siguiente mesa donde sea emparejado.",
                            None,
                        )
                    return (
                        "Tarjeta roja registrada como pendiente. "
                        "Se aplicará automáticamente en la siguiente mesa.",
                        None,
                    )

                infractor_en_pareja_1 = cedula in (
                    mesa["j1_cedula"],
                    mesa["j2_cedula"],
                )
                puntos_p1 = 0 if infractor_en_pareja_1 else mesa["puntaje_meta"]
                puntos_p2 = mesa["puntaje_meta"] if infractor_en_pareja_1 else 0
                conexion.execute(
                    """
                    UPDATE mesas
                    SET puntos_p1 = ?, puntos_p2 = ?,
                        puntos_base_p1 = ?, puntos_base_p2 = ?,
                        descuento_p1 = 0, descuento_p2 = 0,
                        motivo_penalizacion = ?, estado = 'finalizada'
                    WHERE id = ?
                    """,
                    (
                        puntos_p1,
                        puntos_p2,
                        puntos_p1,
                        puntos_p2,
                        "Tarjeta roja: pareja no infractora gana por penalización",
                        mesa["id"],
                    ),
                )
                torneo_finalizado_id = _cerrar_ronda_si_corresponde(conexion, mesa["id"])
                conexion.execute(
                    """
                    INSERT INTO auditoria_resultados (
                        mesa_id, fecha_hora, puntos_base_p1, puntos_base_p2,
                        descuento_p1, descuento_p2, puntos_final_p1,
                        puntos_final_p2, motivo
                    ) VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?)
                    """,
                    (
                        mesa["id"],
                        ahora,
                        puntos_p1,
                        puntos_p2,
                        puntos_p1,
                        puntos_p2,
                        "Tarjeta roja",
                    ),
                )
                conexion.execute(
                    """
                    UPDATE penalizaciones
                    SET aplicada = 1, mesa_id = ?
                    WHERE id = ?
                    """,
                    (mesa["id"], penalizacion.lastrowid),
                )
                conexion.execute(
                    "DELETE FROM torneo_jugadores WHERE torneo_id = ? AND cedula = ?",
                    (torneo_id, cedula),
                )
                conexion.execute(
                    """
                    INSERT OR REPLACE INTO torneo_jugadores_retirados
                        (torneo_id, cedula, fecha_hora, motivo)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        torneo_id,
                        cedula,
                        ahora,
                        "Tarjeta roja directa" if roja_directa else "Tarjeta roja por tercera penalización",
                    ),
                )
                registrar_historial_jugador(
                    cedula,
                    "TARJETA ROJA",
                    f"Expulsado del torneo ID {torneo_id}: "
                    f"{'roja directa' if roja_directa else 'tercera penalización'}",
                    conexion=conexion,
                )
                return (
                    "Tarjeta roja. El jugador fue retirado y no puede volver a ingresar.",
                    torneo_finalizado_id,
                )

            registrar_historial_jugador(
                cedula,
                "PENALIZACIÓN",
                f"Falta {numero_falta} en torneo ID {torneo_id}"
                + (f": {motivo}" if motivo else ""),
                conexion=conexion,
            )
            return f"Tarjeta amarilla registrada. Faltas acumuladas: {numero_falta}/3.", None
    finally:
        conexion.close()


def registrar_penalizacion(
    torneo_id: int,
    cedula: str,
    motivo: str | None = None,
    roja_directa: bool = False,
) -> str:
    """Registra una falta y expulsa al jugador en la tercera o ante roja directa.

    Una roja nunca modifica una mesa que ya tiene marcador: queda pendiente y se
    aplica en la siguiente mesa. Si la roja cierra la última mesa de la última
    ronda, el torneo se finaliza igual que con un marcador normal.
    """
    mensaje, torneo_finalizado_id = _registrar_penalizacion(
        torneo_id, cedula, motivo, roja_directa
    )
    if torneo_finalizado_id is not None:
        _guardar_clasificaciones_archivadas(torneo_finalizado_id)
        mensaje += " Era la última mesa de la última ronda: el torneo quedó finalizado."
    return mensaje


def _aplicar_penalizaciones_pendientes(
    conexion: sqlite3.Connection,
    torneo_id: int,
    ronda_id: int,
) -> None:
    """Aplica rojas pendientes a las mesas recién generadas."""
    pendientes = conexion.execute(
        """
        SELECT p.id, p.cedula, m.id AS mesa_id,
               m.j1_cedula, m.j2_cedula, m.j3_cedula, m.j4_cedula,
               t.puntaje_meta
        FROM penalizaciones p
        JOIN mesas m ON m.ronda_id = ?
            AND (m.j1_cedula = p.cedula OR m.j2_cedula = p.cedula
                 OR m.j3_cedula = p.cedula OR m.j4_cedula = p.cedula)
        JOIN rondas r ON r.id = m.ronda_id AND r.torneo_id = p.torneo_id
        JOIN torneos t ON t.id = p.torneo_id
        WHERE p.torneo_id = ? AND p.tipo = 'tarjeta_roja' AND p.aplicada = 0
        """,
        (ronda_id, torneo_id),
    ).fetchall()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for pendiente in pendientes:
        infractor_en_pareja_1 = pendiente["cedula"] in (
            pendiente["j1_cedula"],
            pendiente["j2_cedula"],
        )
        puntos_p1 = 0 if infractor_en_pareja_1 else pendiente["puntaje_meta"]
        puntos_p2 = pendiente["puntaje_meta"] if infractor_en_pareja_1 else 0
        conexion.execute(
            """
            UPDATE mesas
            SET puntos_p1 = ?, puntos_p2 = ?,
                puntos_base_p1 = ?, puntos_base_p2 = ?,
                descuento_p1 = 0, descuento_p2 = 0,
                motivo_penalizacion = ?,
                estado = 'finalizada'
            WHERE id = ?
            """,
            (
                puntos_p1, puntos_p2, puntos_p1, puntos_p2,
                "Tarjeta roja pendiente: pareja no infractora gana",
                pendiente["mesa_id"],
            ),
        )
        conexion.execute(
            """
            INSERT INTO auditoria_resultados (
                mesa_id, fecha_hora, puntos_base_p1, puntos_base_p2,
                descuento_p1, descuento_p2, puntos_final_p1,
                puntos_final_p2, motivo
            ) VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?)
            """,
            (
                pendiente["mesa_id"], ahora, puntos_p1, puntos_p2,
                puntos_p1, puntos_p2, "Tarjeta roja pendiente",
            ),
        )
        conexion.execute(
            "UPDATE penalizaciones SET aplicada = 1, mesa_id = ? WHERE id = ?",
            (pendiente["mesa_id"], pendiente["id"]),
        )
        conexion.execute(
            "DELETE FROM torneo_jugadores WHERE torneo_id = ? AND cedula = ?",
            (torneo_id, pendiente["cedula"]),
        )
        conexion.execute(
            """
            INSERT OR REPLACE INTO torneo_jugadores_retirados
                (torneo_id, cedula, fecha_hora, motivo)
            VALUES (?, ?, ?, 'Tarjeta roja pendiente aplicada')
            """,
            (torneo_id, pendiente["cedula"], ahora),
        )
        registrar_historial_jugador(
            pendiente["cedula"],
            "TARJETA ROJA",
            f"Expulsión aplicada en mesa {pendiente['mesa_id']} del torneo ID {torneo_id}.",
            conexion=conexion,
        )

def listar_jugadores_retirados_de_torneo(torneo_id: int) -> list[sqlite3.Row]:
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT j.cedula, j.nombre, j.sexo, tjr.fecha_hora, tjr.motivo
            FROM jugadores j
            JOIN torneo_jugadores_retirados tjr ON tjr.cedula = j.cedula
            WHERE tjr.torneo_id = ?
            ORDER BY j.nombre
            """,
            (torneo_id,),
        ).fetchall()
    finally:
        conexion.close()

def listar_jugadores_de_torneo(torneo_id: int) -> list[sqlite3.Row]:
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT j.cedula, j.nombre, j.sexo
            FROM jugadores j
            JOIN torneo_jugadores tj ON tj.cedula = j.cedula
            WHERE tj.torneo_id = ?
            ORDER BY j.nombre
            """,
            (torneo_id,),
        ).fetchall()
    finally:
        conexion.close()


def listar_jugadores_disponibles_para_sustitucion(torneo_id: int) -> list[sqlite3.Row]:
    """Lista jugadores elegibles que aún no participan ni fueron expulsados del torneo."""
    conexion = obtener_conexion()
    try:
        torneo = conexion.execute(
            "SELECT id, tipo FROM torneos WHERE id = ?", (torneo_id,)
        ).fetchone()
        if torneo is None:
            raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")
        sexo_requerido = sexo_requerido_por_tipo(torneo["tipo"])
        return conexion.execute(
            """
            SELECT j.cedula, j.nombre, j.sexo
            FROM jugadores j
            WHERE (? IS NULL OR j.sexo = ?)
              AND NOT EXISTS (
                SELECT 1
                FROM torneo_jugadores tj
                WHERE tj.torneo_id = ? AND tj.cedula = j.cedula
            )
              AND NOT EXISTS (
                SELECT 1
                FROM torneo_jugadores_retirados tjr
                WHERE tjr.torneo_id = ?
                  AND tjr.cedula = j.cedula
                  AND tjr.motivo LIKE 'Tarjeta roja%'
            )
              AND NOT EXISTS (
                SELECT 1
                FROM jugadores_vetados jv
                WHERE jv.cedula = j.cedula
            )
            ORDER BY j.nombre COLLATE NOCASE, j.cedula
            """,
            (sexo_requerido, sexo_requerido, torneo_id, torneo_id),
        ).fetchall()
    finally:
        conexion.close()


# --------------------------------------------------------------------------
# Gestión de Rondas, Mesas y Ranking
# --------------------------------------------------------------------------

def obtener_ronda_activa(torneo_id: int) -> sqlite3.Row | None:
    """Retorna la última ronda creada para el torneo."""
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT id, numero_ronda, estado 
            FROM rondas 
            WHERE torneo_id = ? 
            ORDER BY numero_ronda DESC LIMIT 1
            """,
            (torneo_id,),
        ).fetchone()
    finally:
        conexion.close()


def contar_rondas_torneo(torneo_id: int) -> int:
    """Cantidad de rondas ya creadas para el torneo. Centraliza en el
    repositorio una consulta que la GUI hacía por su cuenta con SQL crudo
    y una conexión ad-hoc, fuera de la capa de acceso a datos."""
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            "SELECT COUNT(*) FROM rondas WHERE torneo_id = ?", (torneo_id,)
        ).fetchone()[0]
    finally:
        conexion.close()


def listar_rondas_de_torneo(torneo_id: int) -> list[sqlite3.Row]:
    """Lista todas las rondas del torneo en orden cronológico."""
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT r.id, r.numero_ronda, r.estado, r.modalidad, r.fecha_creacion,
                   COUNT(DISTINCT m.id) AS total_mesas,
                   COUNT(DISTINCT b.id) AS total_byes
            FROM rondas r
            LEFT JOIN mesas m ON m.ronda_id = r.id
            LEFT JOIN byes b ON b.ronda_id = r.id
            WHERE r.torneo_id = ?
            GROUP BY r.id
            ORDER BY r.numero_ronda ASC
            """,
            (torneo_id,),
        ).fetchall()
    finally:
        conexion.close()


def listar_byes_de_torneo(torneo_id: int) -> list[sqlite3.Row]:
    """Lista los BYE por ronda para mostrar los descansos del torneo archivado."""
    _asegurar_clasificaciones_archivadas(torneo_id)
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT r.numero_ronda, b.cedula, COALESCE(ja.nombre, j.nombre) AS nombre
            FROM byes b
            JOIN rondas r ON r.id = b.ronda_id
            JOIN jugadores j ON j.cedula = b.cedula
            LEFT JOIN torneo_jugadores_archivados ja
              ON ja.torneo_id = r.torneo_id AND ja.cedula = b.cedula
            WHERE r.torneo_id = ?
            ORDER BY r.numero_ronda, COALESCE(ja.nombre, j.nombre) COLLATE NOCASE
            """,
            (torneo_id,),
        ).fetchall()
    finally:
        conexion.close()


def obtener_historial_rondas_jugador(torneo_id: int, cedula: str) -> list[dict]:
    """Obtiene las rondas de un jugador con compañeros, rivales y resultado."""
    conexion = obtener_conexion()
    try:
        mesas = conexion.execute(
            """
            SELECT r.numero_ronda, r.estado AS estado_ronda,
                   m.numero_mesa, m.puntos_p1, m.puntos_p2, m.estado AS estado_mesa,
                   t.puntaje_meta,
                   m.motivo_penalizacion,
                   (
                       SELECT p.cedula
                       FROM penalizaciones p
                       WHERE p.mesa_id = m.id AND p.tipo = 'tarjeta_roja'
                       ORDER BY p.id DESC
                       LIMIT 1
                   ) AS infractor_cedula,
                   m.j1_cedula, j1.nombre AS j1_nombre,
                   m.j2_cedula, j2.nombre AS j2_nombre,
                   m.j3_cedula, j3.nombre AS j3_nombre,
                   m.j4_cedula, j4.nombre AS j4_nombre
            FROM mesas m
            JOIN rondas r ON r.id = m.ronda_id AND r.torneo_id = ?
            JOIN torneos t ON t.id = r.torneo_id
            JOIN jugadores j1 ON j1.cedula = m.j1_cedula
            JOIN jugadores j2 ON j2.cedula = m.j2_cedula
            JOIN jugadores j3 ON j3.cedula = m.j3_cedula
            JOIN jugadores j4 ON j4.cedula = m.j4_cedula
            WHERE m.j1_cedula = ? OR m.j2_cedula = ?
               OR m.j3_cedula = ? OR m.j4_cedula = ?
            ORDER BY r.numero_ronda ASC, m.numero_mesa ASC
            """,
            (torneo_id, cedula, cedula, cedula, cedula),
        ).fetchall()
        byes = conexion.execute(
            """
            SELECT r.numero_ronda, r.estado AS estado_ronda
            FROM byes b
            JOIN rondas r ON r.id = b.ronda_id
            WHERE r.torneo_id = ? AND b.cedula = ?
            ORDER BY r.numero_ronda ASC
            """,
            (torneo_id, cedula),
        ).fetchall()
    finally:
        conexion.close()

    historial = []
    for mesa in mesas:
        posiciones = [
            (mesa["j1_cedula"], mesa["j1_nombre"]),
            (mesa["j2_cedula"], mesa["j2_nombre"]),
            (mesa["j3_cedula"], mesa["j3_nombre"]),
            (mesa["j4_cedula"], mesa["j4_nombre"]),
        ]
        es_pareja_1 = cedula in (mesa["j1_cedula"], mesa["j2_cedula"])
        companeros = [nombre for cedula_j, nombre in posiciones if cedula_j != cedula and (
            (es_pareja_1 and cedula_j in (mesa["j1_cedula"], mesa["j2_cedula"]))
            or (not es_pareja_1 and cedula_j in (mesa["j3_cedula"], mesa["j4_cedula"]))
        )]
        rivales = [nombre for cedula_j, nombre in posiciones if cedula_j != cedula and nombre not in companeros]
        puntos = mesa["puntos_p1"] if es_pareja_1 else mesa["puntos_p2"]
        puntos_rivales = mesa["puntos_p2"] if es_pareja_1 else mesa["puntos_p1"]
        resultado = "Pendiente"
        if mesa["estado_mesa"] == "finalizada":
            es_roja = mesa["infractor_cedula"] is not None
            if es_roja and cedula != mesa["infractor_cedula"]:
                resultado = "Victoria"
                puntos = mesa["puntaje_meta"]
                puntos_rivales = 0
            else:
                resultado = "Victoria" if puntos > puntos_rivales else "Derrota" if puntos < puntos_rivales else "Empate"
            if es_roja and cedula == mesa["infractor_cedula"]:
                puntos = 0
                puntos_rivales = mesa["puntaje_meta"]
        historial.append({
            "numero_ronda": mesa["numero_ronda"],
            "estado_ronda": mesa["estado_ronda"],
            "mesa": mesa["numero_mesa"],
            "companeros": ", ".join(companeros),
            "rivales": ", ".join(rivales),
            "puntos_pareja": puntos,
            "puntos_rival": puntos_rivales,
            "marcador": f"{puntos} - {puntos_rivales}",
            "resultado": resultado,
        })
    historial.extend({
        "numero_ronda": bye["numero_ronda"],
        "estado_ronda": bye["estado_ronda"],
        "mesa": "-",
        "companeros": "-",
        "rivales": "-",
        "puntos_pareja": "-",
        "puntos_rival": "-",
        "marcador": "-",
        "resultado": "BYE",
    } for bye in byes)
    return sorted(historial, key=lambda item: item["numero_ronda"])


def eliminar_ultima_ronda(torneo_id: int) -> int:
    """Elimina la última ronda del torneo y revierte la anterior a en_curso."""
    conexion = obtener_conexion()
    try:
        ronda = conexion.execute(
            """
            SELECT id, numero_ronda
            FROM rondas
            WHERE torneo_id = ?
            ORDER BY numero_ronda DESC
            LIMIT 1
            """,
            (torneo_id,),
        ).fetchone()
        if ronda is None:
            raise ErrorDatos("El torneo no tiene rondas generadas.")

        ronda_anterior = conexion.execute(
            """
            SELECT id
            FROM rondas
            WHERE torneo_id = ? AND numero_ronda < ?
            ORDER BY numero_ronda DESC
            LIMIT 1
            """,
            (torneo_id, ronda["numero_ronda"]),
        ).fetchone()

        with conexion:
            conexion.execute("DELETE FROM rondas WHERE id = ?", (ronda["id"],))
            if ronda_anterior is not None:
                conexion.execute(
                    "UPDATE rondas SET estado = 'en_curso' WHERE id = ?",
                    (ronda_anterior["id"],),
                )
        return ronda["numero_ronda"]
    finally:
        conexion.close()


def obtener_ranking_torneo(
    torneo_id: int, sexo: str | None = None, club_id: int | None = None
) -> list[sqlite3.Row]:
    """Retorna la clasificación general o filtrada por sexo y club."""
    if sexo is not None:
        sexo = sexo.upper()
        if sexo not in ("M", "F"):
            raise ErrorDatos("El filtro de sexo debe ser 'M' o 'F'.")
    if club_id is not None:
        if obtener_club(club_id) is None:
            raise ErrorDatos(f"No existe un club con ID {club_id}.")

    conexion = obtener_conexion()
    try:
        filtro_sexo = " AND j.sexo = ?" if sexo is not None else ""
        filtro_club = (
            " AND EXISTS (SELECT 1 FROM club_jugadores cj "
            "WHERE cj.cedula = j.cedula AND cj.club_id = ?)"
            if club_id is not None else ""
        )
        parametros = [torneo_id, torneo_id]
        if sexo is not None:
            parametros.append(sexo)
        if club_id is not None:
            parametros.append(club_id)
        return conexion.execute(
            f"""
            SELECT 
                j.cedula, 
                j.nombre,
                COALESCE(SUM(
                    CASE 
                        WHEN rj.infractor IS NOT NULL AND j.cedula <> rj.infractor AND m.estado = 'finalizada' THEN 1
                        WHEN (m.j1_cedula = j.cedula OR m.j2_cedula = j.cedula) AND m.puntos_p1 > m.puntos_p2 AND m.estado = 'finalizada' THEN 1
                        WHEN (m.j3_cedula = j.cedula OR m.j4_cedula = j.cedula) AND m.puntos_p2 > m.puntos_p1 AND m.estado = 'finalizada' THEN 1
                        ELSE 0 
                    END), 0) + (
                        SELECT COUNT(*) 
                        FROM byes b 
                        JOIN rondas r ON b.ronda_id = r.id 
                        WHERE r.torneo_id = ? AND b.cedula = j.cedula
                    ) AS pg,
                COALESCE(SUM(
                    CASE 
                        WHEN rj.infractor IS NOT NULL AND j.cedula <> rj.infractor AND m.estado = 'finalizada' THEN 0
                        WHEN rj.infractor IS NOT NULL AND j.cedula = rj.infractor AND m.estado = 'finalizada' THEN 1
                        WHEN (m.j1_cedula = j.cedula OR m.j2_cedula = j.cedula) AND m.estado = 'finalizada' AND (m.puntos_p1 < m.puntos_p2 OR (m.puntos_p1 = 0 AND m.puntos_p2 = 0)) THEN 1
                        WHEN (m.j3_cedula = j.cedula OR m.j4_cedula = j.cedula) AND m.estado = 'finalizada' AND (m.puntos_p2 < m.puntos_p1 OR (m.puntos_p1 = 0 AND m.puntos_p2 = 0)) THEN 1
                        ELSE 0 
                    END), 0) AS pp,
                COALESCE(SUM(
                    CASE 
                        WHEN rj.infractor IS NOT NULL AND j.cedula <> rj.infractor AND m.estado = 'finalizada' THEN t.puntaje_meta
                        WHEN rj.infractor IS NOT NULL AND j.cedula = rj.infractor AND m.estado = 'finalizada' THEN -t.puntaje_meta
                        WHEN (m.j1_cedula = j.cedula OR m.j2_cedula = j.cedula)
                             AND m.estado = 'finalizada' AND m.puntos_p1 > m.puntos_p2
                            THEN (t.puntaje_meta - m.puntos_p2)
                        WHEN (m.j1_cedula = j.cedula OR m.j2_cedula = j.cedula)
                             AND m.estado = 'finalizada' AND m.puntos_p1 < m.puntos_p2
                            THEN -(t.puntaje_meta - m.puntos_p1)
                        WHEN (m.j3_cedula = j.cedula OR m.j4_cedula = j.cedula)
                             AND m.estado = 'finalizada' AND m.puntos_p2 > m.puntos_p1
                            THEN (t.puntaje_meta - m.puntos_p1)
                        WHEN (m.j3_cedula = j.cedula OR m.j4_cedula = j.cedula)
                             AND m.estado = 'finalizada' AND m.puntos_p2 < m.puntos_p1
                            THEN -(t.puntaje_meta - m.puntos_p2)
                        ELSE 0 
                    END), 0) AS ef,
                COALESCE(SUM(
                    CASE 
                        WHEN rj.infractor IS NOT NULL AND j.cedula <> rj.infractor AND m.estado = 'finalizada' THEN t.puntaje_meta
                        WHEN rj.infractor IS NOT NULL AND j.cedula = rj.infractor AND m.estado = 'finalizada' THEN 0
                        WHEN (m.j1_cedula = j.cedula OR m.j2_cedula = j.cedula) AND m.estado = 'finalizada' THEN m.puntos_p1
                        WHEN (m.j3_cedula = j.cedula OR m.j4_cedula = j.cedula) AND m.estado = 'finalizada' THEN m.puntos_p2
                        ELSE 0 
                    END), 0) AS pf
            FROM torneo_jugadores tj
            JOIN jugadores j ON j.cedula = tj.cedula
            JOIN torneos t ON t.id = tj.torneo_id
            LEFT JOIN mesas m ON (m.j1_cedula = j.cedula OR m.j2_cedula = j.cedula OR m.j3_cedula = j.cedula OR m.j4_cedula = j.cedula)
                AND EXISTS (
                    SELECT 1 FROM rondas r
                    WHERE r.id = m.ronda_id AND r.torneo_id = tj.torneo_id
                )
            LEFT JOIN (
                SELECT p.mesa_id, p.cedula AS infractor
                FROM penalizaciones p
                WHERE p.tipo = 'tarjeta_roja' AND p.mesa_id IS NOT NULL
                  AND p.id = (
                      SELECT MAX(p2.id) FROM penalizaciones p2
                      WHERE p2.mesa_id = p.mesa_id AND p2.tipo = 'tarjeta_roja'
                  )
            ) rj ON rj.mesa_id = m.id
            WHERE tj.torneo_id = ?{filtro_sexo}{filtro_club}
            GROUP BY j.cedula
            ORDER BY pg DESC, ef DESC, pf DESC, j.nombre ASC
            """,
            parametros,
        ).fetchall()
    finally:
        conexion.close()


def _seleccionar_jugadores_bye(
    conexion: sqlite3.Connection,
    torneo_id: int,
    jugadores: list[str],
    cantidad: int,
) -> tuple[list[str], list[str]]:
    """Separa jugadores para mesas y BYE priorizando a quienes menos descansaron."""
    if cantidad <= 0:
        return jugadores, []

    conteos = {
        fila["cedula"]: fila["total_byes"]
        for fila in conexion.execute(
            """
            SELECT b.cedula, COUNT(*) AS total_byes
            FROM byes b
            JOIN rondas r ON r.id = b.ronda_id
            WHERE r.torneo_id = ?
            GROUP BY b.cedula
            """,
            (torneo_id,),
        ).fetchall()
    }
    ultimos_bye = {
        fila["cedula"]
        for fila in conexion.execute(
            """
            SELECT b.cedula
            FROM byes b
            JOIN rondas r ON r.id = b.ronda_id
            WHERE r.torneo_id = ?
              AND r.numero_ronda = (
                  SELECT MAX(numero_ronda) FROM rondas WHERE torneo_id = ?
              )
            """,
            (torneo_id, torneo_id),
        ).fetchall()
    }
    ordenados = sorted(
        enumerate(jugadores),
        key=lambda item: (
            conteos.get(item[1], 0),
            item[1] in ultimos_bye,
            item[0],
        ),
    )
    cedulas_bye = {cedula for _, cedula in ordenados[:cantidad]}
    jugadores_mesas = [cedula for cedula in jugadores if cedula not in cedulas_bye]
    jugadores_bye = [cedula for cedula in jugadores if cedula in cedulas_bye]
    return jugadores_mesas, jugadores_bye


def _emparejamiento_intercalado_bloque(bloque: list[str]) -> list[str]:
    """Aplica el patrón Intercalado a un bloque de cuatro jugadores.

    El orden recibido ya es el ranking del torneo (posición 1, 2, 3, 4).
    Intercalado significa: pareja 1 = posiciones 1 y 3;
    pareja 2 = posiciones 2 y 4.

    Para [1, 2, 3, 4] se almacena [1, 3, 2, 4].
    """
    if len(bloque) != 4 or len(set(bloque)) != 4:
        raise ErrorDatos(
            "Una mesa del sistema intercalado debe contener cuatro jugadores distintos."
        )
    return [bloque[0], bloque[2], bloque[1], bloque[3]]


def _particiones_mesa(jugadores: list[str]) -> list[tuple[tuple[str, str], tuple[str, str]]]:
    """Retorna las tres formas posibles de dividir cuatro asientos en dos parejas."""
    if len(jugadores) != 4 or len(set(jugadores)) != 4:
        raise ErrorDatos("Una mesa del sistema suizo debe contener cuatro jugadores distintos.")
    a, b, c, d = jugadores
    return [
        ((a, b), (c, d)),
        ((a, c), (b, d)),
        ((a, d), (b, c)),
    ]


def _clave_pareja(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


def _historial_parejas(
    conexion: sqlite3.Connection, torneo_id: int, numero_ronda: int
) -> dict[tuple[str, str], int]:
    filas = conexion.execute(
        """
        SELECT r.numero_ronda, m.j1_cedula, m.j2_cedula,
               m.j3_cedula, m.j4_cedula
        FROM mesas m
        JOIN rondas r ON r.id = m.ronda_id
        WHERE r.torneo_id = ? AND r.numero_ronda < ?
        ORDER BY r.numero_ronda ASC
        """,
        (torneo_id, numero_ronda),
    ).fetchall()
    historial: dict[tuple[str, str], int] = {}
    for fila in filas:
        for pareja in (
            (fila["j1_cedula"], fila["j2_cedula"]),
            (fila["j3_cedula"], fila["j4_cedula"]),
        ):
            clave = _clave_pareja(*pareja)
            historial.setdefault(clave, fila["numero_ronda"])
    return historial


def _parejas_repetidas(
    particion: tuple[tuple[str, str], tuple[str, str]],
    historial: dict[tuple[str, str], int],
) -> list[int]:
    return [
        historial[_clave_pareja(*pareja)]
        for pareja in particion
        if _clave_pareja(*pareja) in historial
    ]


def resolver_conflictos_parejas_suizo(
    torneo_id: int,
    jugadores_mesas: list[str],
    numero_ronda: int,
    conexion: sqlite3.Connection | None = None,
) -> list[dict]:
    """Resuelve parejas repetidas en bloques Suizos y retorna las mesas resultantes.

    Primero prueba las tres particiones internas de cada mesa. Si no existe una
    partición inédita, prueba intercambios de un asiento con la mesa adyacente
    del mismo marcador. Cuando no hay solución completa, elige la alternativa
    cuya repetición corresponde a la ronda más antigua.
    """
    if numero_ronda < 1 or len(jugadores_mesas) % 4:
        raise ErrorDatos("La lista suiza debe contener un número de jugadores múltiplo de cuatro.")
    propia = conexion is None
    conexion = conexion or obtener_conexion()
    try:
        historial = _historial_parejas(conexion, torneo_id, numero_ronda)
        ranking = {
            fila["cedula"]: (fila["pg"], fila["ef"], fila["pf"])
            for fila in obtener_ranking_torneo(torneo_id)
        }
        mesas = [
            list(jugadores_mesas[pos:pos + 4])
            for pos in range(0, len(jugadores_mesas), 4)
        ]
        cambios: list[dict] = []

        for indice, mesa in enumerate(mesas):
            particiones = _particiones_mesa(mesa)
            valida = next(
                (particion for particion in particiones
                 if not _parejas_repetidas(particion, historial)),
                None,
            )
            if valida is not None:
                mesas[indice] = [*valida[0], *valida[1]]
                continue

            candidatos: list[tuple[tuple, int, int, list[str], list[str]]] = []
            if indice + 1 < len(mesas):
                siguiente = mesas[indice + 1]
                if ranking.get(mesa[0]) == ranking.get(siguiente[0]):
                    for asiento_a in range(4):
                        for asiento_b in range(4):
                            primera = mesa.copy()
                            segunda = siguiente.copy()
                            primera[asiento_a], segunda[asiento_b] = segunda[asiento_b], primera[asiento_a]
                            for particion_a in _particiones_mesa(primera):
                                for particion_b in _particiones_mesa(segunda):
                                    repetidas = (
                                        _parejas_repetidas(particion_a, historial)
                                        + _parejas_repetidas(particion_b, historial)
                                    )
                                    # Las soluciones inéditas siempre preceden al fallback.
                                    clave = (
                                        len(repetidas),
                                        min(repetidas, default=0),
                                        max(repetidas, default=0),
                                        sorted(repetidas),
                                    )
                                    candidatos.append((clave, asiento_a, asiento_b,
                                                       [*particion_a[0], *particion_a[1]],
                                                       [*particion_b[0], *particion_b[1]]))

            if candidatos:
                validos = [candidato for candidato in candidatos if candidato[0][0] == 0]
                opciones = validos or candidatos
                opciones.sort(key=lambda candidato: (
                    candidato[0][1] if candidato[0][0] else 0,
                    candidato[0][2],
                ))
                mejor = opciones[0]
                mesas[indice] = mejor[3]
                mesas[indice + 1] = mejor[4]
                detalle = (
                    f"Mesa {indice + 1} intercambió un asiento con mesa {indice + 2}; "
                    "se verificaron ambas matrices de compatibilidad."
                )
                cambios.append({
                    "tipo": "swap_externo",
                    "mesa_a": indice + 1,
                    "mesa_b": indice + 2,
                    "detalle": detalle,
                })
            else:
                # No hay mesa adyacente compatible: conservar el orden y forzar
                # la repetición más antigua entre las particiones posibles.
                mejor = min(
                    particiones,
                    key=lambda particion: (
                        min(_parejas_repetidas(particion, historial), default=0),
                        len(_parejas_repetidas(particion, historial)),
                        max(_parejas_repetidas(particion, historial), default=0),
                        sorted(_parejas_repetidas(particion, historial)),
                    ),
                )
                mesas[indice] = [*mejor[0], *mejor[1]]
                cambios.append({
                    "tipo": "repeticion_forzada",
                    "mesa_a": indice + 1,
                    "mesa_b": None,
                    "detalle": "No existe una permuta válida; se eligió la repetición de mayor antigüedad.",
                })

        if propia:
            conexion.commit()
        return [
            {
                "numero_mesa": indice + 1,
                "jugadores": mesa,
                "pareja_1": tuple(mesa[:2]),
                "pareja_2": tuple(mesa[2:]),
                "cambios": [cambio for cambio in cambios if cambio["mesa_a"] == indice + 1],
            }
            for indice, mesa in enumerate(mesas)
        ]
    finally:
        if propia:
            conexion.close()


def _registrar_cambios_emparejamiento(
    conexion: sqlite3.Connection,
    torneo_id: int,
    ronda_id: int,
    numero_ronda: int,
    mesas: list[dict],
) -> None:
    for mesa in mesas:
        for cambio in mesa["cambios"]:
            conexion.execute(
                """
                INSERT INTO historial_emparejamientos
                    (torneo_id, ronda_id, numero_ronda, tipo_cambio, mesa_a, mesa_b, detalle, fecha_hora)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    torneo_id, ronda_id, numero_ronda, cambio["tipo"],
                    cambio["mesa_a"], cambio["mesa_b"], cambio["detalle"],
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )


def listar_historial_emparejamientos(
    torneo_id: int, numero_ronda: int | None = None
) -> list[sqlite3.Row]:
    """Lista los cambios oficiales aplicados a los emparejamientos del torneo."""
    conexion = obtener_conexion()
    try:
        if numero_ronda is None:
            return conexion.execute(
                """
                SELECT id, ronda_id, numero_ronda, tipo_cambio, mesa_a, mesa_b,
                       detalle, fecha_hora
                FROM historial_emparejamientos
                WHERE torneo_id = ?
                ORDER BY numero_ronda ASC, id ASC
                """,
                (torneo_id,),
            ).fetchall()
        return conexion.execute(
            """
            SELECT id, ronda_id, numero_ronda, tipo_cambio, mesa_a, mesa_b,
                   detalle, fecha_hora
            FROM historial_emparejamientos
            WHERE torneo_id = ? AND numero_ronda = ?
            ORDER BY id ASC
            """,
            (torneo_id, numero_ronda),
        ).fetchall()
    finally:
        conexion.close()


def generar_emparejamientos(torneo_id: int, numero_ronda: int = 1, modalidad: str = "intercalado") -> int:
    """Genera la ronda 1 y sus mesas dividiendo la lista de inscritos en bloques de 4."""
    # Validación: Impedir iniciar la Ronda 1 si ya existe alguna ronda registrada
    ronda_existente = obtener_ronda_activa(torneo_id)
    if ronda_existente is not None:
        raise ErrorDatos(
            f"El torneo ya se encuentra en marcha (ronda {ronda_existente['numero_ronda']}). "
            "Para continuar con el torneo debes usar la opción 'Generar siguiente ronda'."
        )

    jugadores = [j["cedula"] for j in obtener_ranking_torneo(torneo_id)]
    
    if len(jugadores) < 4:
        raise ErrorDatos("Se requieren al menos 4 jugadores inscritos para iniciar el torneo.")

    conexion = obtener_conexion()
    try:
        jugadores_mesas, jugadores_bye = _seleccionar_jugadores_bye(
            conexion,
            torneo_id,
            jugadores,
            len(jugadores) % 4,
        )
        with conexion:
            cursor = conexion.execute(
                """
                INSERT INTO rondas (torneo_id, numero_ronda, estado, modalidad)
                VALUES (?, ?, 'en_curso', ?)
                """,
                (torneo_id, numero_ronda, modalidad),
            )
            ronda_id = cursor.lastrowid
            conexion.execute(
                "UPDATE torneos SET estado = 'en_curso' WHERE id = ?",
                (torneo_id,),
            )
            mesas_resueltas = resolver_conflictos_parejas_suizo(
                torneo_id, jugadores_mesas, numero_ronda, conexion
            ) if modalidad == "suizo_puro" else [
                {
                    "numero_mesa": indice + 1,
                    "jugadores": _emparejamiento_intercalado_bloque(bloque),
                    "cambios": [],
                }
                for indice, bloque in enumerate(
                    [jugadores_mesas[pos:pos + 4] for pos in range(0, len(jugadores_mesas), 4)]
                )
            ]
            _registrar_cambios_emparejamiento(
                conexion, torneo_id, ronda_id, numero_ronda, mesas_resueltas
            )

            for cedula in jugadores_bye:
                conexion.execute(
                    "INSERT INTO byes (ronda_id, cedula) VALUES (?, ?)",
                    (ronda_id, cedula),
                )

            num_mesa = 1
            for mesa in mesas_resueltas:
                conexion.execute(
                    """
                    INSERT INTO mesas (ronda_id, numero_mesa, j1_cedula, j2_cedula, j3_cedula, j4_cedula, estado)
                    VALUES (?, ?, ?, ?, ?, ?, 'pendiente')
                    """,
                    (ronda_id, mesa["numero_mesa"], *mesa["jugadores"]),
                )
                num_mesa += 1

            _aplicar_penalizaciones_pendientes(conexion, torneo_id, ronda_id)
            return ronda_id
    except sqlite3.IntegrityError:
        raise ErrorDatos(f"La ronda {numero_ronda} ya existe para este torneo.")
    finally:
        conexion.close()

def generar_siguiente_ronda(torneo_id: int, modalidad: str = "intercalado") -> int:
    """Genera la siguiente ronda asignando mesas y aplicando Bye si la cantidad no es múltiplo de 4."""
    torneo = obtener_torneo(torneo_id)
    if not torneo:
        raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")

    ronda_activa = obtener_ronda_activa(torneo_id)
    if not ronda_activa:
        raise ErrorDatos("No hay rondas previas iniciadas.")

    conexion = obtener_conexion()
    try:
        pendientes = conexion.execute(
            "SELECT COUNT(*) AS total FROM mesas WHERE ronda_id = ? AND estado != 'finalizada'",
            (ronda_activa["id"],),
        ).fetchone()["total"]

        if pendientes > 0:
            raise ErrorDatos(f"Aún hay {pendientes} mesa(s) sin resultado en la ronda {ronda_activa['numero_ronda']}.")

        siguiente_numero = ronda_activa["numero_ronda"] + 1
        if siguiente_numero > torneo["num_rondas"]:
            raise ErrorDatos(
                "No hay otra ronda programada. Aumente el número de rondas "
                "si desea continuar el torneo."
            )

        jugadores = [j["cedula"] for j in obtener_ranking_torneo(torneo_id)]
        if len(jugadores) < 4:
            raise ErrorDatos("Se requieren al menos 4 jugadores activos para continuar.")

        jugadores_mesas, jugadores_bye = _seleccionar_jugadores_bye(
            conexion,
            torneo_id,
            jugadores,
            len(jugadores) % 4,
        )

        with conexion:
            conexion.execute("UPDATE rondas SET estado = 'finalizada' WHERE id = ?", (ronda_activa["id"],))

            cursor = conexion.execute(
                """
                INSERT INTO rondas (torneo_id, numero_ronda, estado, modalidad)
                VALUES (?, ?, 'en_curso', ?)
                """,
                (torneo_id, siguiente_numero, modalidad),
            )
            nueva_ronda_id = cursor.lastrowid
            conexion.execute(
                "UPDATE torneos SET estado = 'en_curso' WHERE id = ?",
                (torneo_id,),
            )
            mesas_resueltas = resolver_conflictos_parejas_suizo(
                torneo_id, jugadores_mesas, siguiente_numero, conexion
            ) if modalidad == "suizo_puro" else [
                {
                    "numero_mesa": indice + 1,
                    "jugadores": _emparejamiento_intercalado_bloque(bloque),
                    "cambios": [],
                }
                for indice, bloque in enumerate(
                    [jugadores_mesas[pos:pos + 4] for pos in range(0, len(jugadores_mesas), 4)]
                )
            ]
            _registrar_cambios_emparejamiento(
                conexion, torneo_id, nueva_ronda_id, siguiente_numero, mesas_resueltas
            )

            # Registrar descansos (Byes)
            for c in jugadores_bye:
                conexion.execute("INSERT INTO byes (ronda_id, cedula) VALUES (?, ?)", (nueva_ronda_id, c))

            # Conformar mesas
            num_mesa = 1
            for mesa in mesas_resueltas:
                conexion.execute(
                    """
                    INSERT INTO mesas (ronda_id, numero_mesa, j1_cedula, j2_cedula, j3_cedula, j4_cedula, estado)
                    VALUES (?, ?, ?, ?, ?, ?, 'pendiente')
                    """,
                    (nueva_ronda_id, mesa["numero_mesa"], *mesa["jugadores"]),
                )
                num_mesa += 1

            _aplicar_penalizaciones_pendientes(conexion, torneo_id, nueva_ronda_id)
            return nueva_ronda_id
    finally:
        conexion.close()

def registrar_o_editar_resultado_mesa(
    mesa_id: int,
    puntos_p1: int,
    puntos_p2: int,
    descuento_p1: int = 0,
    descuento_p2: int = 0,
    motivo: str | None = None,
) -> None:
    """Registra un resultado, sus descuentos y una auditoría de la operación."""
    valores = (puntos_p1, puntos_p2, descuento_p1, descuento_p2)
    if any(not isinstance(valor, int) or valor < 0 for valor in valores):
        raise ErrorDatos("Los puntos y descuentos deben ser enteros no negativos.")
    # El descuento puede dejar el puntaje final por debajo de cero: el reglamento lo
    # anota como negativo, y la efectividad del rival lo refleja.
    puntos_final_p1 = puntos_p1 - descuento_p1
    puntos_final_p2 = puntos_p2 - descuento_p2
    torneo_finalizado_id = None
    conexion = obtener_conexion()
    try:
        with conexion:
            mesa = conexion.execute(
                """
                SELECT m.id, t.puntaje_meta
                FROM mesas m
                JOIN rondas r ON r.id = m.ronda_id
                JOIN torneos t ON t.id = r.torneo_id
                WHERE m.id = ?
                """,
                (mesa_id,),
            ).fetchone()
            if mesa is None:
                raise ErrorDatos(f"No existe una mesa con ID {mesa_id}.")
            if _mesa_tiene_roja(conexion, mesa_id):
                raise ErrorDatos(
                    "Esta mesa se cerró por tarjeta roja: su resultado lo fija el "
                    "reglamento (pareja contraria gana con la meta contra 0) y no se puede editar."
                )
            limite_puntos = mesa["puntaje_meta"] + EXCESO_MAXIMO_SOBRE_META
            if puntos_p1 > limite_puntos or puntos_p2 > limite_puntos:
                raise ErrorDatos(
                    f"Puntaje fuera de rango: con una meta de {mesa['puntaje_meta']} no puede "
                    f"superar {limite_puntos} puntos. Revise que no haya un dígito de más."
                )
            if descuento_p1 > mesa["puntaje_meta"] or descuento_p2 > mesa["puntaje_meta"]:
                raise ErrorDatos(
                    f"Un descuento no puede superar la meta del torneo ({mesa['puntaje_meta']} puntos)."
                )
            if puntos_final_p1 == puntos_final_p2:
                raise ErrorDatos(
                    "Una partida no puede terminar empatada: el reglamento exige jugar manos "
                    "adicionales hasta desempatar. Para un doble forfeit use «Declarar forfeit»."
                )
            if puntos_final_p1 >= mesa["puntaje_meta"] and puntos_final_p2 >= mesa["puntaje_meta"]:
                raise ErrorDatos(
                    "Una mesa no puede finalizar con ambas parejas alcanzando "
                    f"simultáneamente la meta de {mesa['puntaje_meta']} puntos."
                )

            cursor = conexion.execute(
                """
                UPDATE mesas 
                SET puntos_p1 = ?, puntos_p2 = ?, puntos_base_p1 = ?,
                    puntos_base_p2 = ?, descuento_p1 = ?, descuento_p2 = ?,
                    motivo_penalizacion = ?, estado = 'finalizada'
                WHERE id = ?
                """,
                (
                    puntos_final_p1, puntos_final_p2, puntos_p1, puntos_p2,
                    descuento_p1, descuento_p2, motivo, mesa_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ErrorDatos(f"No existe una mesa con ID {mesa_id}.")
            torneo_finalizado_id = _cerrar_ronda_si_corresponde(conexion, mesa_id)
            conexion.execute(
                """
                INSERT INTO auditoria_resultados (
                    mesa_id, fecha_hora, puntos_base_p1, puntos_base_p2,
                    descuento_p1, descuento_p2, puntos_final_p1,
                    puntos_final_p2, motivo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mesa_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    puntos_p1, puntos_p2, descuento_p1, descuento_p2,
                    puntos_final_p1, puntos_final_p2, motivo,
                ),
            )
    finally:
        conexion.close()
    if torneo_finalizado_id is not None:
        _guardar_clasificaciones_archivadas(torneo_finalizado_id)

def buscar_mesa_de_jugador(torneo_id: int, cedula: str) -> sqlite3.Row | None:
    """Busca en qué mesa se encuentra un jugador en la ronda activa del torneo."""
    ronda = obtener_ronda_activa(torneo_id)
    if not ronda:
        return None

    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT m.numero_mesa, m.puntos_p1, m.puntos_p2, m.estado,
                   r.numero_ronda,
                   j1.nombre AS j1_nom, j2.nombre AS j2_nom,
                   j3.nombre AS j3_nom, j4.nombre AS j4_nom,
                   CASE 
                       WHEN m.j1_cedula = ? OR m.j2_cedula = ? THEN 1 
                       ELSE 2 
                   END AS pareja_jugador
            FROM mesas m
            JOIN rondas r ON r.id = m.ronda_id
            JOIN jugadores j1 ON m.j1_cedula = j1.cedula
            JOIN jugadores j2 ON m.j2_cedula = j2.cedula
            JOIN jugadores j3 ON m.j3_cedula = j3.cedula
            JOIN jugadores j4 ON m.j4_cedula = j4.cedula
            WHERE m.ronda_id = ? AND (m.j1_cedula = ? OR m.j2_cedula = ? OR m.j3_cedula = ? OR m.j4_cedula = ?)
            """,
            (cedula, cedula, ronda["id"], cedula, cedula, cedula, cedula),
        ).fetchone()
    finally:
        conexion.close()

def listar_mesas_de_ronda(ronda_id: int) -> list[sqlite3.Row]:
    """Obtiene todas las mesas registradas para una ronda específica con los nombres de los jugadores."""
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT m.id, m.numero_mesa, m.puntos_p1, m.puntos_p2,
                   m.puntos_base_p1, m.puntos_base_p2,
                   m.descuento_p1, m.descuento_p2,
                   m.motivo_penalizacion, m.estado,
                   m.j1_cedula, m.j2_cedula, m.j3_cedula, m.j4_cedula,
                   j1.nombre AS j1_nom, j2.nombre AS j2_nom,
                   j3.nombre AS j3_nom, j4.nombre AS j4_nom
            FROM mesas m
            JOIN jugadores j1 ON m.j1_cedula = j1.cedula
            JOIN jugadores j2 ON m.j2_cedula = j2.cedula
            JOIN jugadores j3 ON m.j3_cedula = j3.cedula
            JOIN jugadores j4 ON m.j4_cedula = j4.cedula
            WHERE m.ronda_id = ?
            ORDER BY m.numero_mesa ASC
            """,
            (ronda_id,),
        ).fetchall()
    finally:
        conexion.close()


def listar_mesas_archivadas(torneo_id: int) -> list[sqlite3.Row]:
    """Lista los marcadores archivados usando los nombres capturados al cierre."""
    _asegurar_clasificaciones_archivadas(torneo_id)
    conexion = obtener_conexion()
    try:
        return conexion.execute(
            """
            SELECT r.numero_ronda, m.id, m.numero_mesa, m.puntos_p1, m.puntos_p2,
                   m.puntos_base_p1, m.puntos_base_p2,
                   m.descuento_p1, m.descuento_p2,
                   m.motivo_penalizacion, m.estado,
                   m.j1_cedula, m.j2_cedula, m.j3_cedula, m.j4_cedula,
                   COALESCE(a1.nombre, j1.nombre) AS j1_nom,
                   COALESCE(a2.nombre, j2.nombre) AS j2_nom,
                   COALESCE(a3.nombre, j3.nombre) AS j3_nom,
                   COALESCE(a4.nombre, j4.nombre) AS j4_nom
            FROM mesas m
            JOIN rondas r ON r.id = m.ronda_id
            JOIN jugadores j1 ON m.j1_cedula = j1.cedula
            JOIN jugadores j2 ON m.j2_cedula = j2.cedula
            JOIN jugadores j3 ON m.j3_cedula = j3.cedula
            JOIN jugadores j4 ON m.j4_cedula = j4.cedula
            LEFT JOIN torneo_jugadores_archivados a1
              ON a1.torneo_id = r.torneo_id AND a1.cedula = m.j1_cedula
            LEFT JOIN torneo_jugadores_archivados a2
              ON a2.torneo_id = r.torneo_id AND a2.cedula = m.j2_cedula
            LEFT JOIN torneo_jugadores_archivados a3
              ON a3.torneo_id = r.torneo_id AND a3.cedula = m.j3_cedula
            LEFT JOIN torneo_jugadores_archivados a4
              ON a4.torneo_id = r.torneo_id AND a4.cedula = m.j4_cedula
            WHERE r.torneo_id = ?
            ORDER BY r.numero_ronda, m.numero_mesa
            """,
            (torneo_id,),
        ).fetchall()
    finally:
        conexion.close()


def editar_disposicion_mesa(mesa_id: int, jugadores: list[str]) -> None:
    """Reordena los cuatro asientos de una mesa sin modificar su marcador."""
    if len(jugadores) != 4 or len(set(jugadores)) != 4:
        raise ErrorDatos("La mesa debe conservar cuatro participantes distintos.")

    conexion = obtener_conexion()
    try:
        with conexion:
            mesa = conexion.execute(
                """
                SELECT m.id, m.ronda_id, r.torneo_id, r.numero_ronda,
                       m.j1_cedula, m.j2_cedula, m.j3_cedula, m.j4_cedula
                FROM mesas m
                JOIN rondas r ON r.id = m.ronda_id
                WHERE m.id = ?
                """,
                (mesa_id,),
            ).fetchone()
            if mesa is None:
                raise ErrorDatos(f"No existe una mesa con ID {mesa_id}.")

            actuales = {
                mesa["j1_cedula"],
                mesa["j2_cedula"],
                mesa["j3_cedula"],
                mesa["j4_cedula"],
            }
            if set(jugadores) != actuales:
                raise ErrorDatos(
                    "La disposición manual solo puede reordenar los participantes "
                    "que ya pertenecen a la mesa."
                )

            if list(jugadores) == [
                mesa["j1_cedula"],
                mesa["j2_cedula"],
                mesa["j3_cedula"],
                mesa["j4_cedula"],
            ]:
                raise ErrorDatos("La disposición seleccionada no tiene cambios.")

            conexion.execute(
                """
                UPDATE mesas
                SET j1_cedula = ?, j2_cedula = ?, j3_cedula = ?, j4_cedula = ?
                WHERE id = ?
                """,
                (*jugadores, mesa_id),
            )
            conexion.execute(
                """
                INSERT INTO historial_emparejamientos
                    (torneo_id, ronda_id, numero_ronda, tipo_cambio,
                     mesa_a, mesa_b, detalle, fecha_hora)
                VALUES (?, ?, ?, 'disposicion_manual', ?, NULL, ?, ?)
                """,
                (
                    mesa["torneo_id"],
                    mesa["ronda_id"],
                    mesa["numero_ronda"],
                    mesa_id,
                    "Disposición manual actualizada: " + " / ".join(jugadores),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
    finally:
        conexion.close()


def realizar_swap_externo(
    mesa_a_id: int,
    mesa_b_id: int,
    posicion_a: int,
    posicion_b: int,
) -> None:
    """Intercambia un asiento entre dos mesas de la misma ronda."""
    if posicion_a not in range(4) or posicion_b not in range(4):
        raise ErrorDatos("Las posiciones de intercambio deben estar entre 1 y 4.")
    if mesa_a_id == mesa_b_id:
        raise ErrorDatos("El swap externo requiere dos mesas diferentes.")

    conexion = obtener_conexion()
    try:
        with conexion:
            mesas = conexion.execute(
                """
                SELECT m.id, m.ronda_id, r.torneo_id, r.numero_ronda,
                       m.j1_cedula, m.j2_cedula, m.j3_cedula, m.j4_cedula
                FROM mesas m
                JOIN rondas r ON r.id = m.ronda_id
                WHERE m.id IN (?, ?)
                """,
                (mesa_a_id, mesa_b_id),
            ).fetchall()
            if len(mesas) != 2:
                raise ErrorDatos("No se encontraron las dos mesas seleccionadas.")
            mesa_a = next(mesa for mesa in mesas if mesa["id"] == mesa_a_id)
            mesa_b = next(mesa for mesa in mesas if mesa["id"] == mesa_b_id)
            if mesa_a["ronda_id"] != mesa_b["ronda_id"]:
                raise ErrorDatos("El swap externo solo puede hacerse dentro de la misma ronda.")

            jugadores_a = [mesa_a[f"j{i}_cedula"] for i in range(1, 5)]
            jugadores_b = [mesa_b[f"j{i}_cedula"] for i in range(1, 5)]
            jugador_a, jugador_b = jugadores_a[posicion_a], jugadores_b[posicion_b]
            jugadores_a[posicion_a], jugadores_b[posicion_b] = jugador_b, jugador_a
            if len(set(jugadores_a)) != 4 or len(set(jugadores_b)) != 4:
                raise ErrorDatos("El swap produciría participantes repetidos en una mesa.")

            for mesa_id, jugadores in (
                (mesa_a_id, jugadores_a),
                (mesa_b_id, jugadores_b),
            ):
                conexion.execute(
                    """
                    UPDATE mesas
                    SET j1_cedula = ?, j2_cedula = ?, j3_cedula = ?, j4_cedula = ?
                    WHERE id = ?
                    """,
                    (*jugadores, mesa_id),
                )
            conexion.execute(
                """
                INSERT INTO historial_emparejamientos
                    (torneo_id, ronda_id, numero_ronda, tipo_cambio,
                     mesa_a, mesa_b, detalle, fecha_hora)
                VALUES (?, ?, ?, 'swap_externo_manual', ?, ?, ?, ?)
                """,
                (
                    mesa_a["torneo_id"],
                    mesa_a["ronda_id"],
                    mesa_a["numero_ronda"],
                    mesa_a_id,
                    mesa_b_id,
                    (
                        f"Intercambio manual: posición {posicion_a + 1} de mesa "
                        f"{mesa_a_id} ({jugador_a}) por posición {posicion_b + 1} "
                        f"de mesa {mesa_b_id} ({jugador_b})."
                    ),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
    finally:
        conexion.close()


def registrar_forfeit_mesa(
    mesa_id: int, pareja_ganadora: int, cedulas_retirar: list[str] | None = None
) -> None:
    """Registra la victoria por forfeit (1, 2 o 0 para doble forfeit) y retira jugadores opcionales del torneo."""
    if pareja_ganadora not in (0, 1, 2):
        raise ErrorDatos("La pareja ganadora debe ser 1, 2 o 0 para doble forfeit.")
    torneo_finalizado_id = None
    conexion = obtener_conexion()
    try:
        with conexion:
            mesa = conexion.execute(
                """
                SELECT m.id, m.motivo_penalizacion, r.id AS ronda_id, r.numero_ronda,
                       r.torneo_id, t.puntaje_meta, t.num_rondas,
                       t.edicion_historico
                FROM mesas m
                JOIN rondas r ON r.id = m.ronda_id
                JOIN torneos t ON t.id = r.torneo_id
                WHERE m.id = ?
                """,
                (mesa_id,),
            ).fetchone()

            if not mesa:
                raise ErrorDatos(f"No existe la mesa con ID {mesa_id}.")

            pts_meta = mesa["puntaje_meta"]
            torneo_id = mesa["torneo_id"]

            if pareja_ganadora == 1:
                p1, p2 = pts_meta, 0
            elif pareja_ganadora == 2:
                p1, p2 = 0, pts_meta
            else:
                p1, p2 = 0, 0  # Doble forfeit

            motivo_forfeit = (
                "Forfeit pareja 1" if pareja_ganadora == 1
                else "Forfeit pareja 2" if pareja_ganadora == 2
                else "Doble forfeit"
            )
            if _mesa_tiene_roja(conexion, mesa_id):
                raise ErrorDatos(
                    "Esta mesa se cerró por tarjeta roja y no admite un forfeit adicional."
                )
            conexion.execute(
                """
                UPDATE mesas
                SET puntos_p1 = ?, puntos_p2 = ?, puntos_base_p1 = ?,
                    puntos_base_p2 = ?, motivo_penalizacion = ?, estado = 'finalizada'
                WHERE id = ?
                """,
                (p1, p2, p1, p2, motivo_forfeit, mesa_id),
            )

            if cedulas_retirar:
                for cedula in cedulas_retirar:
                    conexion.execute(
                        "DELETE FROM torneo_jugadores WHERE torneo_id = ? AND cedula = ?",
                        (torneo_id, cedula),
                    )
                    conexion.execute(
                        """
                        INSERT OR REPLACE INTO torneo_jugadores_retirados
                            (torneo_id, cedula, fecha_hora, motivo)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            torneo_id,
                            cedula,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "Forfeit/abandono",
                        ),
                    )
                    registrar_historial_jugador(
                        cedula,
                        "FORFEIT/RETIRO",
                        f"Retirado del torneo ID {torneo_id} por sanción/forfeit",
                        conexion=conexion,
                    )
            torneo_finalizado_id = _cerrar_ronda_si_corresponde(conexion, mesa_id)
    finally:
        conexion.close()
    if torneo_finalizado_id is not None:
        _guardar_clasificaciones_archivadas(torneo_finalizado_id)

def sustituir_jugador_torneo(torneo_id: int, cedula_saliente: str, cedula_entrante: str) -> None:
    """Sustituye un jugador y transfiere su participación histórica del torneo."""
    if cedula_saliente == cedula_entrante:
        raise ErrorDatos("El jugador saliente y el jugador entrante deben ser diferentes.")
    if obtener_torneo(torneo_id) is None:
        raise ErrorDatos(f"No existe un torneo con ID {torneo_id}.")
    if obtener_jugador(cedula_saliente) is None:
        raise ErrorDatos(f"El jugador con cédula {cedula_saliente} no existe en la base de datos.")
    jugador_entrante = obtener_jugador(cedula_entrante)
    if jugador_entrante is None:
        raise ErrorDatos(f"El jugador con cédula {cedula_entrante} no existe en la base de datos.")
    validar_sexo_para_torneo(torneo_id, jugador_entrante["sexo"], jugador_entrante["nombre"])

    conexion = obtener_conexion()
    try:
        with conexion:
            saliente_retirado = conexion.execute(
                """
                SELECT 1
                FROM torneo_jugadores_retirados
                WHERE torneo_id = ? AND cedula = ?
                """,
                (torneo_id, cedula_saliente),
            ).fetchone()
            if saliente_retirado is None:
                raise ErrorDatos("El jugador a reemplazar no figura entre los retirados de este torneo.")
            saliente_expulsado = conexion.execute(
                """
                SELECT 1
                FROM torneo_jugadores_retirados
                WHERE torneo_id = ? AND cedula = ?
                  AND motivo LIKE 'Tarjeta roja%'
                """,
                (torneo_id, cedula_saliente),
            ).fetchone()
            if saliente_expulsado is not None:
                raise ErrorDatos(
                    "El jugador expulsado con tarjeta roja no puede ser sustituido."
                )

            entrante_inscrito = conexion.execute(
                """
                SELECT 1
                FROM torneo_jugadores
                WHERE torneo_id = ? AND cedula = ?
                """,
                (torneo_id, cedula_entrante),
            ).fetchone()
            if entrante_inscrito is not None:
                raise ErrorDatos("El jugador suplente ya está inscrito en este torneo.")
            entrante_expulsado = conexion.execute(
                """
                SELECT 1
                FROM torneo_jugadores_retirados
                WHERE torneo_id = ? AND cedula = ?
                  AND motivo LIKE 'Tarjeta roja%'
                """,
                (torneo_id, cedula_entrante),
            ).fetchone()
            if entrante_expulsado is not None:
                raise ErrorDatos(
                    "El jugador suplente fue expulsado con tarjeta roja y no puede ingresar al torneo."
                )
            entrante_vetado = conexion.execute(
                "SELECT 1 FROM jugadores_vetados WHERE cedula = ?",
                (cedula_entrante,),
            ).fetchone()
            if entrante_vetado is not None:
                raise ErrorDatos("El jugador suplente está vetado y no puede ingresar al torneo.")

            conexion.execute(
                """
                UPDATE mesas
                SET j1_cedula = CASE WHEN j1_cedula = ? THEN ? ELSE j1_cedula END,
                    j2_cedula = CASE WHEN j2_cedula = ? THEN ? ELSE j2_cedula END,
                    j3_cedula = CASE WHEN j3_cedula = ? THEN ? ELSE j3_cedula END,
                    j4_cedula = CASE WHEN j4_cedula = ? THEN ? ELSE j4_cedula END
                WHERE ronda_id IN (
                    SELECT id FROM rondas WHERE torneo_id = ?
                )
                """,
                (
                    cedula_saliente, cedula_entrante,
                    cedula_saliente, cedula_entrante,
                    cedula_saliente, cedula_entrante,
                    cedula_saliente, cedula_entrante,
                    torneo_id,
                ),
            )
            conexion.execute(
                """
                UPDATE byes
                SET cedula = ?
                WHERE cedula = ?
                  AND ronda_id IN (
                      SELECT id FROM rondas WHERE torneo_id = ?
                  )
                """,
                (cedula_entrante, cedula_saliente, torneo_id),
            )
            conexion.execute(
                "INSERT INTO torneo_jugadores (torneo_id, cedula) VALUES (?, ?)",
                (torneo_id, cedula_entrante),
            )
            conexion.execute(
                """
                DELETE FROM torneo_jugadores_retirados
                WHERE torneo_id = ? AND cedula = ?
                """,
                (torneo_id, cedula_entrante),
            )
            conexion.execute(
                """
                DELETE FROM torneo_jugadores_retirados
                WHERE torneo_id = ? AND cedula = ?
                """,
                (torneo_id, cedula_saliente),
            )

            registrar_historial_jugador(
                cedula_entrante,
                "SUSTITUCIÓN",
                f"Ingresó al torneo ID {torneo_id} reemplazando a {cedula_saliente}",
                conexion=conexion,
            )
            registrar_historial_jugador(
                cedula_saliente,
                "SUSTITUCIÓN",
                f"Fue reemplazado en el torneo ID {torneo_id} por {cedula_entrante}",
                conexion=conexion,
            )
    finally:
        conexion.close()

# --------------------------------------------------------------------------
# Visualización de Mesas por Número de Jugador (Orden de Ingreso)
# --------------------------------------------------------------------------

def obtener_numeros_jugadores_torneo(torneo_id: int) -> dict[str, int]:
    """
    Retorna un diccionario {cedula: numero_jugador} asignado según
    el orden cronológico de inscripción/ingreso al torneo (ROWID).
    """
    conexion = obtener_conexion()
    try:
        filas = conexion.execute(
            """
            SELECT cedula
            FROM torneo_jugadores
            WHERE torneo_id = ?
            ORDER BY rowid ASC
            """,
            (torneo_id,),
        ).fetchall()
        return {fila["cedula"]: idx + 1 for idx, fila in enumerate(filas)}
    finally:
        conexion.close()


def listar_mesas_con_numeros_jugador(ronda_id: int, torneo_id: int) -> list[dict]:
    """
    Obtiene las mesas de una ronda especificando el número de jugador
    correspondiente al orden de ingreso al torneo.
    """
    map_numeros = obtener_numeros_jugadores_torneo(torneo_id)
    mesas = listar_mesas_de_ronda(ronda_id)
    resultado = []
    
    for m in mesas:
        m_dict = dict(m)
        m_dict["j1_num"] = map_numeros.get(m["j1_cedula"], "-")
        m_dict["j2_num"] = map_numeros.get(m["j2_cedula"], "-")
        m_dict["j3_num"] = map_numeros.get(m["j3_cedula"], "-")
        m_dict["j4_num"] = map_numeros.get(m["j4_cedula"], "-")
        resultado.append(m_dict)
        
    return resultado