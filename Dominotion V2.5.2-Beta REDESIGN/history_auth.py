"""Credential storage and recovery for the finished-tournament history."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import unicodedata

import db

PREGUNTAS_SEGURIDAD = (
    ("cedula", "¿Cuál es tu número de cédula?"),
    ("color", "¿Cuál es tu color favorito?"),
    ("mascota", "¿Cuál es el nombre de tu mascota más querida?"),
    ("sangre", "¿Cuál es tu tipo de sangre?"),
    ("hermanos", "¿Cuántos hermanos tienes? (Puedes responder 0 si no tienes ninguno.)"),
    ("telefono", "¿Cuáles son los últimos 4 números de tu teléfono móvil?"),
    ("secundaria", "¿En qué año terminaste la escuela secundaria?"),
    ("calzado", "¿Cuál es tu número de calzado (talla de zapato)?"),
    ("amigo", "¿Quién es tu mejor amigo?"),
)

ITERACIONES_HASH = 310_000
INTENTOS_MAXIMOS = 5
SEGUNDOS_BLOQUEO = 15 * 60
RESPUESTAS_MINIMAS_RECUPERACION = 3


def normalizar_respuesta(respuesta: str) -> str:
    texto = unicodedata.normalize("NFKD", " ".join(respuesta.split()).casefold())
    return "".join(caracter for caracter in texto if not unicodedata.combining(caracter))


def _crear_hash(valor: str) -> tuple[bytes, bytes]:
    sal = secrets.token_bytes(16)
    valor_hash = hashlib.pbkdf2_hmac(
        "sha256", valor.encode("utf-8"), sal, ITERACIONES_HASH
    )
    return sal, valor_hash


def _coincide(valor: str, sal: bytes, valor_hash: bytes) -> bool:
    intento = hashlib.pbkdf2_hmac(
        "sha256", valor.encode("utf-8"), sal, ITERACIONES_HASH
    )
    return hmac.compare_digest(intento, valor_hash)


def esta_configurado() -> bool:
    conexion = db.obtener_conexion()
    try:
        fila = conexion.execute("SELECT 1 FROM history_auth WHERE id = 1").fetchone()
        return fila is not None
    finally:
        conexion.close()


def configurar_credenciales(
    contrasena: str,
    pin: str,
    respuestas: dict[str, str] | None,
    *,
    reemplazar: bool = False,
) -> None:
    if len(contrasena) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    if not pin.isdigit() or not 4 <= len(pin) <= 8:
        raise ValueError("El PIN debe contener entre 4 y 8 dígitos.")
    respuestas_hash = None
    if respuestas is None:
        if not reemplazar:
            raise ValueError("Debes responder todas las preguntas de seguridad.")
    else:
        if set(respuestas) != {clave for clave, _ in PREGUNTAS_SEGURIDAD}:
            raise ValueError("Debes responder todas las preguntas de seguridad.")
        normalizadas = {
            clave: normalizar_respuesta(valor) for clave, valor in respuestas.items()
        }
        if any(not valor for valor in normalizadas.values()):
            raise ValueError("Todas las respuestas de seguridad son obligatorias.")
        respuestas_hash = {
            clave: _crear_hash(valor) for clave, valor in normalizadas.items()
        }

    clave_sal, clave_hash = _crear_hash(contrasena)
    pin_sal, pin_hash = _crear_hash(pin)

    conexion = db.obtener_conexion()
    try:
        with conexion:
            configurada = conexion.execute(
                "SELECT 1 FROM history_auth WHERE id = 1"
            ).fetchone()
            if configurada and not reemplazar:
                raise ValueError("Las credenciales ya están configuradas.")
            conexion.execute(
                """
                INSERT INTO history_auth (
                    id, password_salt, password_hash, pin_salt, pin_hash,
                    failed_attempts, locked_until
                ) VALUES (1, ?, ?, ?, ?, 0, 0)
                ON CONFLICT(id) DO UPDATE SET
                    password_salt = excluded.password_salt,
                    password_hash = excluded.password_hash,
                    pin_salt = excluded.pin_salt,
                    pin_hash = excluded.pin_hash,
                    failed_attempts = 0,
                    locked_until = 0
                """,
                (clave_sal, clave_hash, pin_sal, pin_hash),
            )
            if respuestas_hash is not None:
                conexion.execute("DELETE FROM history_security_answers")
                conexion.executemany(
                    """
                    INSERT INTO history_security_answers
                        (question_id, answer_salt, answer_hash)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (clave, sal, valor_hash)
                        for clave, (sal, valor_hash) in respuestas_hash.items()
                    ],
                )
    finally:
        conexion.close()


def _segundos_bloqueo_restantes() -> int:
    conexion = db.obtener_conexion()
    try:
        fila = conexion.execute(
            "SELECT locked_until FROM history_auth WHERE id = 1"
        ).fetchone()
        return max(0, int(fila["locked_until"] - time.time())) if fila else 0
    finally:
        conexion.close()


def _registrar_intento(exitoso: bool) -> None:
    conexion = db.obtener_conexion()
    try:
        with conexion:
            if exitoso:
                conexion.execute(
                    "UPDATE history_auth SET failed_attempts = 0, locked_until = 0 WHERE id = 1"
                )
                return
            conexion.execute(
                """
                UPDATE history_auth
                SET failed_attempts = failed_attempts + 1,
                    locked_until = CASE
                        WHEN failed_attempts + 1 >= ?
                        THEN ? ELSE locked_until
                    END
                WHERE id = 1
                """,
                (INTENTOS_MAXIMOS, time.time() + SEGUNDOS_BLOQUEO),
            )
    finally:
        conexion.close()


def _reiniciar_bloqueo_vencido() -> None:
    """Si el bloqueo ya venció, el contador de intentos fallidos vuelve a cero.

    Sin esto, un solo fallo tras el bloqueo (con el contador aún en 5 o más) lo
    reactivaba otros 15 minutos.
    """
    conexion = db.obtener_conexion()
    try:
        with conexion:
            conexion.execute(
                """
                UPDATE history_auth
                SET failed_attempts = 0, locked_until = 0
                WHERE id = 1 AND locked_until > 0 AND locked_until <= ?
                """,
                (time.time(),),
            )
    finally:
        conexion.close()


def verificar_credencial(credencial: str) -> str:
    """Returns 'ok', 'invalid', 'locked', or 'not_configured'."""
    _reiniciar_bloqueo_vencido()
    conexion = db.obtener_conexion()
    try:
        fila = conexion.execute(
            "SELECT * FROM history_auth WHERE id = 1"
        ).fetchone()
    finally:
        conexion.close()
    if fila is None:
        return "not_configured"
    if fila["locked_until"] > time.time():
        return "locked"

    correcta = _coincide(credencial, fila["password_salt"], fila["password_hash"])
    correcta = _coincide(credencial, fila["pin_salt"], fila["pin_hash"]) or correcta
    _registrar_intento(correcta)
    if correcta:
        return "ok"
    return "locked" if _segundos_bloqueo_restantes() else "invalid"


def verificar_respuestas(respuestas: dict[str, str]) -> str:
    """Validates recovery answers; three correct answers are required."""
    preguntas_configuradas = {clave for clave, _ in PREGUNTAS_SEGURIDAD}
    contestadas = {
        clave: normalizar_respuesta(valor)
        for clave, valor in respuestas.items()
        if clave in preguntas_configuradas and valor.strip()
    }
    if len(contestadas) < RESPUESTAS_MINIMAS_RECUPERACION:
        return "insufficient"

    _reiniciar_bloqueo_vencido()
    conexion = db.obtener_conexion()
    try:
        credencial = conexion.execute(
            "SELECT locked_until FROM history_auth WHERE id = 1"
        ).fetchone()
        filas = conexion.execute(
            """
            SELECT question_id, answer_salt, answer_hash
            FROM history_security_answers
            """
        ).fetchall()
    finally:
        conexion.close()
    if credencial is None:
        return "not_configured"
    if credencial["locked_until"] > time.time():
        return "locked"

    hashes = {fila["question_id"]: fila for fila in filas}
    correctas = 0
    for clave, respuesta in contestadas.items():
        fila = hashes.get(clave)
        if fila is not None and _coincide(
            respuesta, fila["answer_salt"], fila["answer_hash"]
        ):
            correctas += 1
    aprobada = correctas >= RESPUESTAS_MINIMAS_RECUPERACION
    _registrar_intento(aprobada)
    if aprobada:
        return "ok"
    return "locked" if _segundos_bloqueo_restantes() else "invalid"


def segundos_bloqueo_restantes() -> int:
    return _segundos_bloqueo_restantes()