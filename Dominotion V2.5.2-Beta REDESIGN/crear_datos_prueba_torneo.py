"""Crea un torneo de prueba con 40 jugadores distribuidos en dos clubes.

Ejecuta ``python crear_datos_prueba_torneo.py`` desde la carpeta del programa.
Los datos se agregan a la base configurada para Dominotion y no se inicia
ninguna ronda; el torneo queda disponible en «En Vivo / Rondas».
"""
from __future__ import annotations

from uuid import uuid4

import db
import repository as repo


def crear_datos_prueba() -> dict[str, object]:
    """Crea registros de prueba únicos y devuelve sus identificadores."""
    db.inicializar_bd()
    token = uuid4().hex[:8].upper()
    cedulas_creadas: list[str] = []
    clubes_creados: list[int] = []
    torneo_id: int | None = None

    try:
        club_ids = [
            repo.crear_club(f"Club de prueba A {token}"),
            repo.crear_club(f"Club de prueba B {token}"),
        ]
        clubes_creados.extend(club_ids)

        torneo_id = repo.crear_torneo(
            nombre=f"Torneo de prueba 40 jugadores {token}",
            duracion_minutos=30,
            tipo="mixto",
            puntaje_meta=200,
            num_rondas=5,
            modalidad="intercalado",
            jugadores_por_mesa=4,
        )

        for numero in range(1, 41):
            cedula = f"PRUEBA{token}{numero:02d}"
            sexo = "M" if numero % 2 else "F"
            nombre = f"Jugador de prueba {numero:02d} {token}"
            repo.crear_jugador(cedula, nombre, sexo)
            cedulas_creadas.append(cedula)

            club_id = club_ids[0] if numero <= 20 else club_ids[1]
            repo.asignar_jugador_a_club(cedula, club_id)
            repo.inscribir_jugador_a_torneo(cedula, torneo_id)

        participantes = repo.listar_jugadores_de_torneo(torneo_id)
        if len(participantes) != 40:
            raise RuntimeError(
                f"Se esperaban 40 participantes, pero se encontraron {len(participantes)}."
            )

        integrantes_por_club = [repo.listar_jugadores_de_club(club_id) for club_id in club_ids]
        cantidades = [len(integrantes) for integrantes in integrantes_por_club]
        if cantidades != [20, 20]:
            raise RuntimeError(
                f"Se esperaban 20 jugadores por club; se encontraron {cantidades}."
            )

        return {
            "torneo_id": torneo_id,
            "nombre_torneo": f"Torneo de prueba 40 jugadores {token}",
            "clubes": club_ids,
            "jugadores": 40,
            "jugadores_por_club": cantidades,
        }
    except Exception:
        _eliminar_datos_creados(torneo_id, clubes_creados, cedulas_creadas)
        raise


def _eliminar_datos_creados(
    torneo_id: int | None,
    clubes: list[int],
    cedulas: list[str],
) -> None:
    """Revierte únicamente los registros insertados por esta ejecución fallida."""
    conexion = db.obtener_conexion()
    try:
        with conexion:
            if torneo_id is not None:
                conexion.execute("DELETE FROM torneos WHERE id = ?", (torneo_id,))
            if clubes:
                marcadores = ",".join("?" for _ in clubes)
                conexion.execute(
                    f"DELETE FROM clubes WHERE id IN ({marcadores})",
                    clubes,
                )
            if cedulas:
                marcadores = ",".join("?" for _ in cedulas)
                conexion.execute(
                    f"DELETE FROM jugadores WHERE cedula IN ({marcadores})",
                    cedulas,
                )
    finally:
        conexion.close()


if __name__ == "__main__":
    datos = crear_datos_prueba()
    print("Torneo de prueba creado correctamente.")
    print(f"ID del torneo: {datos['torneo_id']}")
    print(f"Nombre: {datos['nombre_torneo']}")
    print("Participantes: 40 (20 por club)")
    print("El torneo ya está inscrito; todavía no se han generado rondas.")
