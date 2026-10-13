import tempfile
import unittest
from pathlib import Path

import db
import repository


class HistoryArchiveMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_database_path = db.RUTA_BD
        self.temporary_directory = tempfile.TemporaryDirectory()
        db.RUTA_BD = Path(self.temporary_directory.name) / "test.db"
        db.inicializar_bd()
        self._create_finished_tournament()

    def tearDown(self) -> None:
        db.RUTA_BD = self.original_database_path
        self.temporary_directory.cleanup()

    def _create_finished_tournament(self) -> None:
        connection = db.obtener_conexion()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO jugadores (cedula, nombre, sexo)
                    VALUES ('100', 'Nombre actual', 'F')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO torneos (
                        id, nombre, duracion_minutos, tipo, puntaje_meta,
                        num_rondas, estado
                    ) VALUES (1, 'Torneo', 10, 'mixto', 100, 1, 'finalizado')
                    """
                )
                connection.execute(
                    "INSERT INTO torneo_jugadores (torneo_id, cedula) VALUES (1, '100')"
                )
        finally:
            connection.close()

    def test_missing_player_snapshot_does_not_hide_or_replace_archived_ranking(self) -> None:
        connection = db.obtener_conexion()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO torneo_ranking_archivado (
                        torneo_id, posicion, cedula, nombre, pg, pp, ef, pf
                    ) VALUES (1, 1, '100', 'Nombre histórico', 7, 2, 125, 450)
                    """
                )
        finally:
            connection.close()

        ranking = repository.listar_clasificacion_archivada(1, sexo="F")

        self.assertEqual(len(ranking), 1)
        self.assertEqual(ranking[0]["nombre"], "Nombre histórico")
        self.assertEqual((ranking[0]["pg"], ranking[0]["pp"]), (7, 2))
        connection = db.obtener_conexion()
        try:
            jugador = connection.execute(
                """
                SELECT nombre, sexo FROM torneo_jugadores_archivados
                WHERE torneo_id = 1 AND cedula = '100'
                """
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(tuple(jugador), ("Nombre actual", "F"))

    def test_missing_ranking_snapshot_is_created_without_player_snapshot_changes(self) -> None:
        connection = db.obtener_conexion()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO torneo_jugadores_archivados
                        (torneo_id, cedula, nombre, sexo)
                    VALUES (1, '100', 'Nombre histórico', 'F')
                    """
                )
        finally:
            connection.close()

        ranking = repository.listar_clasificacion_archivada(1, sexo="F")

        self.assertEqual(len(ranking), 1)
        self.assertEqual(ranking[0]["nombre"], "Nombre actual")
        self.assertEqual((ranking[0]["pg"], ranking[0]["pp"]), (0, 0))
        connection = db.obtener_conexion()
        try:
            jugador = connection.execute(
                """
                SELECT nombre FROM torneo_jugadores_archivados
                WHERE torneo_id = 1 AND cedula = '100'
                """
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(jugador["nombre"], "Nombre histórico")


if __name__ == "__main__":
    unittest.main()
