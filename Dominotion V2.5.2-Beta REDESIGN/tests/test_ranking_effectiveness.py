import tempfile
import unittest
from pathlib import Path

import db
import repository


class RankingEffectivenessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_database_path = db.RUTA_BD
        self.temporary_directory = tempfile.TemporaryDirectory()
        db.RUTA_BD = Path(self.temporary_directory.name) / "test.db"
        db.inicializar_bd()
        self._create_match()

    def tearDown(self) -> None:
        db.RUTA_BD = self.original_database_path
        self.temporary_directory.cleanup()

    def _create_match(self) -> None:
        connection = db.obtener_conexion()
        try:
            with connection:
                connection.executemany(
                    "INSERT INTO jugadores (cedula, nombre, sexo) VALUES (?, ?, 'M')",
                    [
                        ("100", "Ganador uno"),
                        ("101", "Ganador dos"),
                        ("102", "Perdedor uno"),
                        ("103", "Perdedor dos"),
                    ],
                )
                connection.execute(
                    """
                    INSERT INTO torneos (
                        id, nombre, duracion_minutos, tipo, puntaje_meta,
                        num_rondas, estado
                    ) VALUES (1, 'Torneo', 10, 'mixto', 200, 1, 'finalizado')
                    """
                )
                connection.executemany(
                    "INSERT INTO torneo_jugadores (torneo_id, cedula) VALUES (1, ?)",
                    [("100",), ("101",), ("102",), ("103",)],
                )
                connection.execute(
                    """
                    INSERT INTO rondas (id, torneo_id, numero_ronda, estado)
                    VALUES (1, 1, 1, 'finalizada')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO mesas (
                        id, ronda_id, numero_mesa, j1_cedula, j2_cedula,
                        j3_cedula, j4_cedula, puntos_p1, puntos_p2, estado
                    ) VALUES (1, 1, 1, '100', '101', '102', '103', 190, 80, 'finalizada')
                    """
                )
        finally:
            connection.close()

    def test_effectiveness_uses_objective_minus_losing_pair_score(self) -> None:
        ranking = {
            jugador["cedula"]: jugador
            for jugador in repository.obtener_ranking_torneo(1)
        }

        self.assertEqual(ranking["100"]["ef"], 120)
        self.assertEqual(ranking["101"]["ef"], 120)
        self.assertEqual(ranking["102"]["ef"], -120)
        self.assertEqual(ranking["103"]["ef"], -120)

    def test_effectiveness_sign_is_reversed_when_second_pair_wins(self) -> None:
        connection = db.obtener_conexion()
        try:
            with connection:
                connection.execute(
                    "UPDATE mesas SET puntos_p1 = 80, puntos_p2 = 190 WHERE id = 1"
                )
        finally:
            connection.close()

        ranking = {
            jugador["cedula"]: jugador
            for jugador in repository.obtener_ranking_torneo(1)
        }

        self.assertEqual(ranking["100"]["ef"], -120)
        self.assertEqual(ranking["101"]["ef"], -120)
        self.assertEqual(ranking["102"]["ef"], 120)
        self.assertEqual(ranking["103"]["ef"], 120)

    def test_archived_effectiveness_is_migrated_and_positions_reordered(self) -> None:
        connection = db.obtener_conexion()
        try:
            with connection:
                connection.executemany(
                    """
                    INSERT INTO torneo_jugadores_archivados
                        (torneo_id, cedula, nombre, sexo)
                    VALUES (1, ?, ?, 'M')
                    """,
                    [
                        ("100", "Ganador uno"),
                        ("101", "Ganador dos"),
                        ("102", "Perdedor uno"),
                        ("103", "Perdedor dos"),
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO torneo_ranking_archivado
                        (torneo_id, posicion, cedula, nombre, pg, pp, ef, pf)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (1, "100", "Ganador uno", 1, 0, 110, 190),
                        (2, "101", "Ganador dos", 1, 0, 110, 190),
                        (3, "102", "Perdedor uno", 0, 1, -110, 80),
                        (4, "103", "Perdedor dos", 0, 1, -110, 80),
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO torneo_ranking_club_archivado (
                        torneo_id, club_nombre, posicion, cedula, nombre,
                        pg, pp, ef, pf
                    ) VALUES (1, 'Club', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (1, "100", "Ganador uno", 1, 0, 110, 190),
                        (2, "101", "Ganador dos", 1, 0, 110, 190),
                        (3, "102", "Perdedor uno", 0, 1, -110, 80),
                        (4, "103", "Perdedor dos", 0, 1, -110, 80),
                    ],
                )
        finally:
            connection.close()

        ranking = repository.listar_clasificacion_archivada(1)
        efectividades = {jugador["cedula"]: jugador["ef"] for jugador in ranking}
        clasificaciones_club = repository.listar_clasificaciones_club_archivadas(1)
        efectividades_club = {
            jugador["cedula"]: jugador["ef"]
            for jugador in clasificaciones_club["Club"]
        }

        self.assertEqual(efectividades, {
            "100": 120,
            "101": 120,
            "102": -120,
            "103": -120,
        })
        self.assertEqual(efectividades_club, efectividades)
        self.assertEqual([jugador["posicion"] for jugador in ranking], [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
