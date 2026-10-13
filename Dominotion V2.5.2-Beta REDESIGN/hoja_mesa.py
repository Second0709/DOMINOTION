"""Diseño y generación de hojas imprimibles para anotar los puntos de una mesa.

Cada página A4 vertical presenta una mesa en dos columnas —una por pareja— y
una tarjeta por jugador con número, nombre, victorias, derrotas y eficiencia.

Este módulo es la única fuente de las medidas y posiciones de las tarjetas.
La vista previa de la interfaz importa esas mismas constantes y funciones para
que su distribución coincida con la del PDF.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# En ejecución normal, los recursos viven junto a este módulo. PyInstaller
# extrae los recursos incluidos en _MEIPASS tanto en builds onefile como onedir.
BASE_DIR = Path(__file__).resolve().parent
DIRECTORIO_RECURSOS = Path(getattr(sys, "_MEIPASS", BASE_DIR))

# Mantener A4 en orientación vertical, sin depender del orden de A4 importado.
ANCHO_A4, ALTO_A4 = min(A4), max(A4)
TAMANO_PAGINA = (ANCHO_A4, ALTO_A4)
MARGEN = 32

# Estas fuentes son parte del diseño de las hojas; fallar explícitamente evita
# generar PDFs con tipografía distinta cuando falte un recurso del paquete.
DIRECTORIO_FUENTES = DIRECTORIO_RECURSOS / "Fonts"
RUTA_REGULAR = DIRECTORIO_FUENTES / "GlacialIndifference-Regular.ttf"
RUTA_BOLD = DIRECTORIO_FUENTES / "GlacialIndifference-Bold.ttf"

for ruta_fuente in (RUTA_REGULAR, RUTA_BOLD):
    if not ruta_fuente.is_file():
        raise FileNotFoundError(
            f"No se encontró la fuente requerida para las hojas de mesa: {ruta_fuente}"
        )

FUENTE_NORMAL = "GlacialIndifference"
FUENTE_BOLD = "GlacialIndifference-Bold"
pdfmetrics.registerFont(TTFont(FUENTE_NORMAL, str(RUTA_REGULAR)))
pdfmetrics.registerFont(TTFont(FUENTE_BOLD, str(RUTA_BOLD)))


# ---------------------------------------------------------------------------
# Datos de un jugador en la hoja
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JugadorHoja:
    """Datos de un jugador tal como se imprimen en la hoja de mesa.

    - ``numero``: número de jugador dentro del torneo (orden de ingreso).
    - ``ganadas`` / ``perdidas``: partidas ganadas y perdidas acumuladas.
    - ``eficiencia``: suma del objetivo menos los puntos del perdedor por partida,
      positiva para el ganador y negativa para el perdedor.

    Cualquier valor en ``None`` se imprime como "-".
    """

    nombre: str
    numero: int | str | None = None
    ganadas: int | None = None
    perdidas: int | None = None
    eficiencia: int | None = None


Pareja = tuple[JugadorHoja, JugadorHoja]
MesaHoja = tuple[int, Pareja, Pareja]


def como_jugador_hoja(jugador: JugadorHoja | str) -> JugadorHoja:
    """Acepta un ``JugadorHoja`` o, por compatibilidad, solo el nombre."""
    if isinstance(jugador, JugadorHoja):
        return jugador
    return JugadorHoja(nombre=str(jugador))


def formatear_valor(valor: object) -> str:
    return "-" if valor is None or valor == "" else str(valor)


def formatear_eficiencia(valor: int | None) -> str:
    """Eficiencia con signo explícito (+45, -12) y 0 sin signo."""
    if valor is None:
        return "-"
    valor = int(valor)
    return f"{valor:+d}" if valor else "0"


def estadisticas_jugador(jugador: JugadorHoja) -> tuple[tuple[str, str], ...]:
    """Pares (etiqueta, valor) que se muestran bajo el nombre, en orden."""
    return (
        ("Ganadas", formatear_valor(jugador.ganadas)),
        ("Perdidas", formatear_valor(jugador.perdidas)),
        ("Eficiencia", formatear_eficiencia(jugador.eficiencia)),
    )


# ---------------------------------------------------------------------------
# Medidas compartidas por el PDF y la vista previa. Las coordenadas usan puntos
# PDF; las distancias superiores parten del borde superior de la página.
# ---------------------------------------------------------------------------

SEPARACION_CENTRAL = 12          # espacio entre la línea central y las tarjetas
DISTANCIA_TITULO_PAREJA = 35     # bajo el margen superior (línea base)
DISTANCIA_PRIMERA_TARJETA = 50   # bajo el margen superior (borde superior)
ALTO_TARJETA = 56
SEPARACION_TARJETAS = 10
ANCHO_ZONA_NUMERO = 44           # franja izquierda de la tarjeta con el número

# Desplazamientos verticales desde el borde superior de cada tarjeta.
DESPLAZ_ETIQUETA_NUMERO = 15
DESPLAZ_NUMERO = 46
DESPLAZ_NOMBRE = 17
DESPLAZ_DIVISOR = 24
DESPLAZ_ETIQUETA_ESTADISTICA = 34
DESPLAZ_VALOR_ESTADISTICA = 47

COLOR_TEXTO = (0, 0, 0)
COLOR_TENUE = (0.42, 0.42, 0.42)
COLOR_BORDE = (0.45, 0.45, 0.45)
COLOR_LINEA_TENUE = (0.75, 0.75, 0.75)


def geometria_columnas(ancho: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """(x_izquierdo, ancho) de la columna de cada pareja."""
    ancho_columna = ancho / 2 - MARGEN - SEPARACION_CENTRAL
    return (
        (MARGEN, ancho_columna),
        (ancho / 2 + SEPARACION_CENTRAL, ancho_columna),
    )


def distancia_superior_tarjeta(posicion: int) -> float:
    """Distancia desde el borde superior de la página al borde superior de la tarjeta."""
    return (
        MARGEN
        + DISTANCIA_PRIMERA_TARJETA
        + posicion * (ALTO_TARJETA + SEPARACION_TARJETAS)
    )


def ajustar_texto(
    texto: str,
    fuente: str,
    tamano: float,
    ancho_maximo: float,
    minimo: float = 7,
) -> tuple[str, float]:
    """Recorta el texto al ancho disponible sin reducir el tamaño de fuente.

    La misma jerarquía tipográfica debe mantenerse en todas las tarjetas; si un
    nombre no cabe, se trunca con puntos suspensivos. ``minimo`` sigue en la
    firma para conservar compatibilidad con los llamadores existentes.
    """
    del minimo

    if stringWidth(texto, fuente, tamano) <= ancho_maximo:
        return texto, tamano

    sufijo = "..."
    while len(texto) > 1 and stringWidth(texto + sufijo, fuente, tamano) > ancho_maximo:
        texto = texto[:-1]

    texto = texto.rstrip() + sufijo

    if stringWidth(texto, fuente, tamano) > ancho_maximo:
        texto = sufijo

    return texto, tamano



# ---------------------------------------------------------------------------
# Dibujo del PDF
# ---------------------------------------------------------------------------

def _dibujar_texto_ajustado(
    pagina: canvas.Canvas,
    texto: str,
    centro_x: float,
    y: float,
    ancho_maximo: float,
    fuente: str = FUENTE_NORMAL,
    tamano: int = 10,
    color: tuple[float, float, float] = COLOR_TEXTO,
) -> None:
    texto, tamano = ajustar_texto(texto, fuente, tamano, ancho_maximo)
    pagina.setFillColorRGB(*color)
    pagina.setFont(fuente, tamano)
    pagina.drawCentredString(centro_x, y, texto)


def _dibujar_tarjeta_jugador(
    pagina: canvas.Canvas,
    jugador: JugadorHoja,
    x_izq: float,
    y_sup: float,
    ancho: float,
) -> None:
    """Tarjeta: [ N° de jugador | nombre / ganadas · perdidas · eficiencia ]."""
    x_der = x_izq + ancho
    y_inf = y_sup - ALTO_TARJETA
    x_div = x_izq + ANCHO_ZONA_NUMERO

    pagina.setStrokeColorRGB(*COLOR_BORDE)
    pagina.setLineWidth(0.8)
    pagina.roundRect(x_izq, y_inf, ancho, ALTO_TARJETA, 4, stroke=1, fill=0)
    pagina.line(x_div, y_inf, x_div, y_sup)

    # La franja izquierda reserva espacio al número para separarlo del nombre.
    centro_numero = x_izq + ANCHO_ZONA_NUMERO / 2
    _dibujar_texto_ajustado(
        pagina, "JUGADOR", centro_numero, y_sup - DESPLAZ_ETIQUETA_NUMERO,
        ANCHO_ZONA_NUMERO - 6, fuente=FUENTE_NORMAL, tamano=7, color=COLOR_TENUE,
    )
    _dibujar_texto_ajustado(
        pagina, formatear_valor(jugador.numero), centro_numero, y_sup - DESPLAZ_NUMERO,
        ANCHO_ZONA_NUMERO - 6, fuente=FUENTE_BOLD, tamano=20,
    )

    # El resto de la tarjeta distribuye nombre y estadísticas en tres celdas.
    ancho_zona = x_der - x_div
    centro_zona = x_div + ancho_zona / 2
    _dibujar_texto_ajustado(
        pagina, jugador.nombre, centro_zona, y_sup - DESPLAZ_NOMBRE,
        ancho_zona - 12, fuente=FUENTE_BOLD, tamano=11,
    )

    pagina.setStrokeColorRGB(*COLOR_LINEA_TENUE)
    pagina.setLineWidth(0.5)
    pagina.line(x_div + 8, y_sup - DESPLAZ_DIVISOR, x_der - 8, y_sup - DESPLAZ_DIVISOR)

    ancho_celda = ancho_zona / 3
    for indice, (etiqueta, valor) in enumerate(estadisticas_jugador(jugador)):
        centro_celda = x_div + ancho_celda * (indice + 0.5)
        _dibujar_texto_ajustado(
            pagina, etiqueta, centro_celda, y_sup - DESPLAZ_ETIQUETA_ESTADISTICA,
            ancho_celda - 6, fuente=FUENTE_NORMAL, tamano=7, color=COLOR_TENUE,
        )
        _dibujar_texto_ajustado(
            pagina, valor, centro_celda, y_sup - DESPLAZ_VALOR_ESTADISTICA,
            ancho_celda - 6, fuente=FUENTE_BOLD, tamano=12,
        )


def generar_pdf_hoja_mesa(
    destino: str | Path,
    nombre_torneo: str,
    numero_ronda: int,
    mesas: list[MesaHoja],
) -> Path:
    """Crea un PDF vertical dividiendo la hoja en dos mitades (Pareja 1 | Pareja 2).

    Cada mesa es ``(numero_mesa, pareja1, pareja2)`` y cada pareja una tupla de
    ``JugadorHoja`` (también se aceptan nombres simples; sus estadísticas se
    imprimen como "-").
    """
    if not mesas:
        raise ValueError("Se requiere al menos una mesa para generar el PDF.")

    ruta = Path(destino)
    ancho, alto = TAMANO_PAGINA

    pagina = canvas.Canvas(str(ruta), pagesize=(ancho, alto), pageCompression=0)
    pagina.setTitle(f"Hojas de mesa - Ronda {numero_ronda} - {nombre_torneo}")

    for numero_mesa, pareja1, pareja2 in mesas:
        # El encabezado identifica el torneo, la ronda y la mesa en cada página.
        pagina.setFillColorRGB(*COLOR_TEXTO)
        pagina.setFont(FUENTE_NORMAL, 10)
        pagina.drawString(MARGEN, alto - MARGEN, nombre_torneo)
        pagina.drawRightString(
            ancho - MARGEN,
            alto - MARGEN,
            f"Ronda {numero_ronda} | Mesa {numero_mesa}",
        )

        # La línea horizontal cierra el encabezado; la vertical separa parejas.
        pagina.setStrokeColorRGB(0.7, 0.7, 0.7)
        pagina.setLineWidth(0.8)
        pagina.line(MARGEN, alto - MARGEN - 10, ancho - MARGEN, alto - MARGEN - 10)
        pagina.line(ancho / 2, MARGEN, ancho / 2, alto - MARGEN - 10)

        # PDF y vista previa usan la misma geometría de columnas.
        for indice, ((x_izq, ancho_columna), jugadores) in enumerate(
            zip(geometria_columnas(ancho), (pareja1, pareja2)),
            start=1,
        ):
            _dibujar_texto_ajustado(
                pagina,
                f"Pareja {indice}",
                x_izq + ancho_columna / 2,
                alto - MARGEN - DISTANCIA_TITULO_PAREJA,
                ancho_columna,
                fuente=FUENTE_BOLD,
                tamano=14,
            )
            for posicion, jugador in enumerate(jugadores):
                _dibujar_tarjeta_jugador(
                    pagina,
                    como_jugador_hoja(jugador),
                    x_izq,
                    alto - distancia_superior_tarjeta(posicion),
                    ancho_columna,
                )

        pagina.showPage()

    pagina.save()
    return ruta