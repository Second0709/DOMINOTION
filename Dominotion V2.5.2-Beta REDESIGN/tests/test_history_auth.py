import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
import history_auth


class HistoryAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_database_path = db.RUTA_BD
        self.temporary_directory = tempfile.TemporaryDirectory()
        db.RUTA_BD = Path(self.temporary_directory.name) / "test.db"
        db.inicializar_bd()
        self.answers = {
            key: f"respuesta de prueba {index}"
            for index, (key, _question) in enumerate(
                history_auth.PREGUNTAS_SEGURIDAD
            )
        }

    def tearDown(self) -> None:
        db.RUTA_BD = self.original_database_path
        self.temporary_directory.cleanup()

    def test_initial_setup_stores_hashes_and_accepts_password_and_pin(self) -> None:
        history_auth.configurar_credenciales(
            "Una clave segura 2026", "246810", self.answers
        )

        self.assertTrue(history_auth.esta_configurado())
        self.assertEqual(
            history_auth.verificar_credencial("Una clave segura 2026"), "ok"
        )
        self.assertEqual(history_auth.verificar_credencial("246810"), "ok")
        self.assertEqual(history_auth.verificar_credencial("incorrecta"), "invalid")

        connection = db.obtener_conexion()
        try:
            credential_row = connection.execute(
                "SELECT password_hash, pin_hash FROM history_auth WHERE id = 1"
            ).fetchone()
            answer_row = connection.execute(
                """
                SELECT answer_hash FROM history_security_answers
                WHERE question_id = 'color'
                """
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(len(credential_row["password_hash"]), 32)
        self.assertEqual(len(credential_row["pin_hash"]), 32)
        self.assertEqual(len(answer_row["answer_hash"]), 32)

    def test_recovery_requires_three_matching_answers_and_resets_credentials(self) -> None:
        history_auth.configurar_credenciales(
            "Una clave segura 2026", "246810", self.answers
        )
        challenge = {
            "cedula": self.answers["cedula"],
            "color": self.answers["color"],
            "mascota": "respuesta equivocada",
            "amigo": self.answers["amigo"],
        }

        self.assertEqual(
            history_auth.verificar_respuestas(
                {"cedula": self.answers["cedula"], "color": self.answers["color"]}
            ),
            "insufficient",
        )
        self.assertEqual(
            history_auth.verificar_respuestas(
                {
                    "cedula": self.answers["cedula"],
                    "color": self.answers["color"],
                    "mascota": "respuesta equivocada",
                }
            ),
            "invalid",
        )
        self.assertEqual(history_auth.verificar_respuestas(challenge), "ok")

        history_auth.configurar_credenciales(
            "Nueva clave segura 2026",
            "135790",
            None,
            reemplazar=True,
        )
        self.assertEqual(
            history_auth.verificar_credencial("Nueva clave segura 2026"), "ok"
        )
        self.assertEqual(history_auth.verificar_credencial("135790"), "ok")
        self.assertEqual(history_auth.verificar_credencial("Una clave segura 2026"), "invalid")
        self.assertEqual(
            history_auth.verificar_respuestas(
                {
                    "cedula": self.answers["cedula"],
                    "color": self.answers["color"],
                    "amigo": self.answers["amigo"],
                }
            ),
            "ok",
        )

    def test_setup_requires_all_questions_and_valid_credentials(self) -> None:
        with self.assertRaises(ValueError):
            history_auth.configurar_credenciales("corta", "1234", self.answers)
        with self.assertRaises(ValueError):
            history_auth.configurar_credenciales(
                "Una clave segura 2026", "12ab", self.answers
            )
        with self.assertRaises(ValueError):
            history_auth.configurar_credenciales(
                "Una clave segura 2026", "246810", {"color": "azul"}
            )
        self.assertFalse(history_auth.esta_configurado())

    def test_failed_attempts_are_rate_limited(self) -> None:
        with (
            mock.patch.object(history_auth, "ITERACIONES_HASH", 1),
            mock.patch.object(history_auth, "INTENTOS_MAXIMOS", 2),
        ):
            history_auth.configurar_credenciales(
                "Una clave segura 2026", "246810", self.answers
            )
            self.assertEqual(
                history_auth.verificar_credencial("incorrecta"), "invalid"
            )
            self.assertEqual(
                history_auth.verificar_credencial("incorrecta"), "locked"
            )
            self.assertEqual(
                history_auth.verificar_credencial("Una clave segura 2026"), "locked"
            )
            self.assertGreater(history_auth.segundos_bloqueo_restantes(), 0)


if __name__ == "__main__":
    unittest.main()
