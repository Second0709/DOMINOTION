"""Ventana de presentación que aparece antes de iniciar Dominotion.
"""
from __future__ import annotations

import math
import random
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

_DIR_RECURSOS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
_RUTA_ICONO_APP = (
    _DIR_RECURSOS / "Icons" / "Dominotion_App_Icons" / "Dominotion.ico"
)

Punto = tuple[float, float]


# ----------------------------------------------------------------- utilidades
def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _mezclar(a: str, b: str, t: float) -> str:
    """Interpola entre dos colores hex (t=0 -> a, t=1 -> b)."""
    t = max(0.0, min(1.0, t))
    return "#%02x%02x%02x" % tuple(
        round(x + (y - x) * t) for x, y in zip(_rgb(a), _rgb(b))
    )


def _salida_suave(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _rebote(t: float) -> float:
    """Ease-out-back: crece un poco de más y se asienta (efecto 'pop')."""
    t = max(0.0, min(1.0, t))
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _rotar(x: float, y: float, grados: float) -> Punto:
    a = math.radians(grados)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def _perimetro_redondeado(
    cx: float, cy: float, ancho: float, alto: float, radio: float,
    grados: float, pasos: int = 14,
) -> list[Punto]:
    """Puntos del contorno de un rectángulo redondeado girado `grados`.

    Empieza en la esquina inferior izquierda y sube por el lado izquierdo,
    como se ve en la animación de referencia.
    """
    mw, mh = ancho / 2, alto / 2
    esquinas = [  # (centro_x, centro_y, ángulo inicial) en sentido horario
        (-mw + radio, mh - radio, 90),     # inferior izquierda
        (-mw + radio, -mh + radio, 180),   # superior izquierda
        (mw - radio, -mh + radio, 270),    # superior derecha
        (mw - radio, mh - radio, 0),       # inferior derecha
    ]
    locales: list[Punto] = []
    for ex, ey, a0 in esquinas:
        for i in range(pasos + 1):
            a = math.radians(a0 + 90 * i / pasos)
            locales.append((ex + radio * math.cos(a), ey + radio * math.sin(a)))
    locales.append(locales[0])
    puntos = []
    for x, y in locales:
        rx, ry = _rotar(x, y, grados)
        puntos.append((cx + rx, cy + ry))
    return puntos


class _Contorno:
    """Línea con degradado que se puede 'dibujar' progresivamente."""

    def __init__(
        self, canvas: tk.Canvas, puntos: list[Punto], grosor: float,
        color_a: str, color_b: str,
    ) -> None:
        self.canvas = canvas
        diag = [x - y for x, y in puntos]
        lo, hi = min(diag), max(diag)
        rango = (hi - lo) or 1.0
        self.segmentos: list[int] = []
        for (x1, y1), (x2, y2) in zip(puntos, puntos[1:]):
            t = (((x1 - y1) + (x2 - y2)) / 2 - lo) / rango
            self.segmentos.append(
                canvas.create_line(
                    x1, y1, x2, y2, fill=_mezclar(color_a, color_b, t),
                    width=grosor, capstyle="round", state="hidden",
                )
            )
        self._visibles = 0

    def revelar(self, progreso: float) -> None:
        n = round(len(self.segmentos) * max(0.0, min(1.0, progreso)))
        if n == self._visibles:
            return
        lo, hi = sorted((n, self._visibles))
        estado = "normal" if n > self._visibles else "hidden"
        for seg in self.segmentos[lo:hi]:
            self.canvas.itemconfigure(seg, state=estado)
        self._visibles = n


class _Punto:
    """Punto de ficha que aparece con efecto 'pop'."""

    def __init__(
        self, canvas: tk.Canvas, x: float, y: float, radio: float,
        color: str, inicio_ms: float, duracion_ms: float = 200,
    ) -> None:
        self.canvas, self.x, self.y, self.radio = canvas, x, y, radio
        self.inicio, self.duracion = inicio_ms, duracion_ms
        self.item = canvas.create_oval(x, y, x, y, fill=color, outline="", state="hidden")
        self._listo = False

    def actualizar(self, t_ms: float) -> None:
        if self._listo:
            return
        p = (t_ms - self.inicio) / self.duracion
        if p <= 0:
            return
        r = max(0.0, self.radio * _rebote(p))
        self.canvas.itemconfigure(self.item, state="normal")
        self.canvas.coords(
            self.item, self.x - r, self.y - r, self.x + r, self.y + r
        )
        if p >= 1:
            self._listo = True


# ------------------------------------------------------------------- ventana
class VentanaPresentacion(tk.Tk):
    """Muestra la identidad del programa con una animación breve de inicio."""

    ANCHO = 680
    ALTO = 372
    INTERVALO_MS = 16

    # Paleta del programa
    FONDO_IZQ = "#5CDFE5"
    FONDO_DER = "#014BAD"
    AMARILLO = "#FDF3AC"
    ROSA = "#FCA8F5"
    TURQUESA = "#0BC0DE"
    TEXTO_MENSAJE = "#EAF6FF"

    # Posiciones verticales
    Y_LOGO = 121
    Y_INICIANDO = 267
    Y_MENSAJE = 316

    # Carrusel de fichas junto a "iniciando..."
    FICHAS_N = 7
    FICHA_W = 14
    FICHA_H = 28
    FICHA_GAP = 5
    CARRUSEL_INICIO_MS = 250
    CARRUSEL_CICLO_MS = 2500
    CARRUSEL_PAUSA_MS = 1650  # cuánto esperan juntas antes de irse

    # Tiempos (ms)
    INICIO_MENSAJES_MS = 900
    DURACION_MENSAJE_MS = 1150
    CANTIDAD_MENSAJES = 6  # cuántos mensajes se muestran (duración total ~ 0,9 s + 6 x 1,15 s)
    FUNDIDO_MENSAJE_MS = 220
    SALIDA_MS = 200  # fundido final; pon 0 para cerrar de golpe

    # Se eligen al azar (sin repetir) cada vez que se abre el programa.
    MENSAJES = [
        "Contando fichas...",
        "Revisando zapatos...",
        "¿Alguien realmente lee esto?",
        "Barajando las fichas...",
        "Buscando el doble seis...",
        "Asignando parejas...",
        "Afilando el lápiz del anotador...",
        "Discutiendo quién reparte...",
        "Vigilando que nadie haga trampa...",
        "Encendiendo el cronómetro de ronda...",
        "Poniendo las mesas en orden...",
    ]
    FUENTES = ("Quicksand", "Comfortaa", "Nunito", "Varela Round", "Segoe UI")

    def __init__(self) -> None:
        super().__init__()
        self.iconbitmap(str(_RUTA_ICONO_APP))
        self.withdraw()
        self.overrideredirect(True)
        self.configure(bg=self.FONDO_DER)

        cantidad = min(self.CANTIDAD_MENSAJES, len(self.MENSAJES))
        self._mensajes = random.sample(self.MENSAJES, cantidad)
        self._duracion = (
            self.INICIO_MENSAJES_MS
            + len(self._mensajes) * self.DURACION_MENSAJE_MS
        )
        self._cerrando = False
        self._t0 = 0.0

        self.canvas = tk.Canvas(
            self, width=self.ANCHO, height=self.ALTO,
            highlightthickness=0, bd=0,
        )
        self.canvas.pack()
        self._elegir_fuentes()
        self._dibujar_fondo()
        self._dibujar_logo()
        self._dibujar_iniciando()
        self._texto_mensaje = self.canvas.create_text(
            self.ANCHO / 2, self.Y_MENSAJE, text="", font=self._fuente_mensaje,
            fill=self.TEXTO_MENSAJE, state="hidden",
        )
        self._centrar()
        self.deiconify()
        self.lift()
        self._t0 = time.perf_counter()
        self.after(0, self._animar)

    # ------------------------------------------------------------ construcción
    def _elegir_fuentes(self) -> None:
        disponibles = set(tkfont.families(self))
        familia = next((f for f in self.FUENTES if f in disponibles), "Segoe UI")
        self._fuente_logo = tkfont.Font(self, family=familia, size=-60, weight="bold")
        self._fuente_iniciando = tkfont.Font(self, family=familia, size=-15, weight="bold")
        self._fuente_mensaje = tkfont.Font(self, family=familia, size=-14)

    def _color_fondo(self, x: float) -> str:
        return _mezclar(self.FONDO_IZQ, self.FONDO_DER, x / (self.ANCHO - 1))

    def _dibujar_fondo(self) -> None:
        for x in range(0, self.ANCHO, 2):
            self.canvas.create_line(
                x + 1, 0, x + 1, self.ALTO, fill=self._color_fondo(x), width=2
            )

    def _texto_degradado(
        self, texto: str, x0: float, y: float, fuente: tkfont.Font,
        espaciado: float = 0,
    ) -> tuple[list[int], list[float], list[str], float]:
        """Crea un texto con degradado amarillo->rosa letra por letra."""
        items, xs, colores = [], [], []
        x = x0
        n = max(1, len(texto) - 1)
        for i, letra in enumerate(texto):
            color = _mezclar(self.AMARILLO, self.ROSA, i / n)
            items.append(
                self.canvas.create_text(
                    x, y, text=letra, anchor="w", font=fuente, fill=color
                )
            )
            xs.append(x)
            colores.append(color)
            x += fuente.measure(letra) + espaciado
        return items, xs, colores, x - espaciado - x0

    def _dibujar_logo(self) -> None:
        espaciado, hueco, ancho_fichas = 3, 14, 80
        ancho_texto = sum(self._fuente_logo.measure(c) for c in "DOMINOTION") + espaciado * 9
        x0 = (self.ANCHO - (ancho_texto + hueco + ancho_fichas)) / 2
        self._texto_degradado("DOMINOTION", x0, self.Y_LOGO, self._fuente_logo, espaciado)
        ox = x0 + ancho_texto + hueco
        cy = self.Y_LOGO

        # Ficha trasera: solo contorno, inclinada (se traza al arrancar)
        cx2, ang = ox + 52, 16
        self._contorno_trasero = _Contorno(
            self.canvas, _perimetro_redondeado(cx2, cy, 36, 72, 11, ang),
            1.6, "#5DC1E8", "#FFB0C8",
        )
        p1 = _rotar(8, -24, ang)
        p2 = _rotar(-8, -8, ang)
        self._puntos_traseros = [
            _Punto(self.canvas, cx2 + p1[0], cy + p1[1], 2.2, "#FDC9DC", 250, 160),
            _Punto(self.canvas, cx2 + p2[0], cy + p2[1], 2.2, "#FDC9DC", 320, 160),
        ]
        d1, d2 = _rotar(-12, 2, ang), _rotar(12, 2, ang)
        self._divisor_trasero = self.canvas.create_line(
            cx2 + d1[0], cy + d1[1], cx2 + d2[0], cy + d2[1],
            fill="#F7B9D6", width=1.2, state="hidden",
        )

        # Ficha frontal con degradado amarillo -> rosa
        cx1, ancho, alto, radio = ox + 20, 39, 71, 10
        for i in range(ancho):
            d = min(i, ancho - 1 - i)
            inset = radio - math.sqrt(max(0.0, radio**2 - (radio - d) ** 2)) if d < radio else 0
            self.canvas.create_line(
                cx1 - ancho / 2 + i + 0.5, cy - alto / 2 + inset,
                cx1 - ancho / 2 + i + 0.5, cy + alto / 2 - inset,
                fill=_mezclar(self.AMARILLO, self.ROSA, i / (ancho - 1)),
            )
        # Divisor que se dibuja de izquierda a derecha
        self._divisor_frontal = self.canvas.create_line(
            cx1 - 17, cy + 1, cx1 - 17, cy + 1, fill="#2B6CB0", width=1.2
        )
        self._div_x = (cx1 - 17, cx1 + 17, cy + 1)
        self._puntos_frontales = [
            _Punto(self.canvas, cx1 + dx, cy + dy, 3.7, self.TURQUESA, 40 + i * 70)
            for i, (dx, dy) in enumerate(
                [(-9.5, -24), (9.5, -24), (-9.5, -8), (9.5, -8), (0, 17)]
            )
        ]

    def _dibujar_iniciando(self) -> None:
        texto = "Iniciando..."
        ancho_texto = sum(self._fuente_iniciando.measure(c) for c in texto)
        hueco = 14
        ancho_fila = self.FICHAS_N * self.FICHA_W + (self.FICHAS_N - 1) * self.FICHA_GAP
        x0 = (self.ANCHO - (ancho_texto + hueco + ancho_fila)) / 2
        self._ini_items, self._ini_xs, self._ini_colores, _ = self._texto_degradado(
            texto, x0, self.Y_INICIANDO, self._fuente_iniciando
        )
        for item in self._ini_items:
            self.canvas.itemconfigure(item, state="hidden")
        self._crear_carrusel(x0 + ancho_texto + hueco)

    # Pips (x, y) relativos al centro de cada mitad de la ficha, por valor 0-4
    _PIPS = {
        0: [],
        1: [(0, 0)],
        2: [(-2.6, -2.6), (2.6, 2.6)],
        4: [(-3.0, -3.0), (3.0, -3.0), (-3.0, 3.0), (3.0, 3.0)],
    }
    _VALORES_FICHAS = [(1, 2), (4, 1), (2, 2), (0, 4), (1, 1), (4, 2), (2, 1)]

    def _crear_carrusel(self, x_inicio: float) -> None:
        """Fila de fichas pequeñas que se juntan, se van y vuelven a juntarse."""
        w, h = self.FICHA_W, self.FICHA_H
        cy = self.Y_INICIANDO - 2
        self._fichas: list[dict] = []
        for i in range(self.FICHAS_N):
            cx = x_inicio + w / 2 + i * (w + self.FICHA_GAP)
            color = _mezclar("#5DC1E8", "#FFB0C8", i / (self.FICHAS_N - 1))
            color_pip = _mezclar("#BFE6F5", "#FDD3E4", i / (self.FICHAS_N - 1))
            items: list[tuple[int, str]] = []  # (item, color base)
            contorno = self.canvas.create_line(
                *[c for pt in _perimetro_redondeado(cx, cy, w, h, w * 0.4, 0, 10) for c in pt],
                fill=color, width=1.3, state="hidden",
                joinstyle="round", capstyle="round",
            )
            items.append((contorno, color))
            divisor = self.canvas.create_line(
                cx - w / 2 + 2.5, cy, cx + w / 2 - 2.5, cy,
                fill=color, width=1, state="hidden",
            )
            items.append((divisor, color))
            arriba, abajo = self._VALORES_FICHAS[i]
            for valor, centro_y in ((arriba, cy - h / 4), (abajo, cy + h / 4)):
                for dx, dy in self._PIPS[valor]:
                    r = 1.7
                    px, py = cx + dx * 0.9, centro_y + dy * 0.9
                    pip = self.canvas.create_oval(
                        px - r, py - r, px + r, py + r,
                        fill=color_pip, outline="", state="hidden",
                    )
                    items.append((pip, color_pip))
            tag = f"ficha{i}"
            for item, _ in items:
                self.canvas.addtag_withtag(tag, item)
            self._fichas.append(
                {"tag": tag, "items": items, "cx": cx, "dx": 0.0, "alfa": -1.0}
            )

    def _centrar(self) -> None:
        self.update_idletasks()
        x = max(0, (self.winfo_screenwidth() - self.ANCHO) // 2)
        y = max(0, (self.winfo_screenheight() - self.ALTO) // 2)
        self.geometry(f"{self.ANCHO}x{self.ALTO}+{x}+{y}")

    # --------------------------------------------------------------- animación
    def _animar(self) -> None:
        if self._cerrando:
            return
        t = (time.perf_counter() - self._t0) * 1000
        if t < 1400:
            self._actualizar_intro(t)
        self._actualizar_carrusel(t)
        self._actualizar_mensajes(t)
        if t >= self._duracion:
            self._salir()
            return
        self.after(self.INTERVALO_MS, self._animar)

    def _actualizar_intro(self, t: float) -> None:
        # Ficha del logo: divisor + puntos
        x1, x2, y = self._div_x
        p = _salida_suave(t / 250)
        self.canvas.coords(self._divisor_frontal, x1, y, x1 + (x2 - x1) * p, y)
        for punto in self._puntos_frontales + self._puntos_traseros:
            punto.actualizar(t)

        # Ficha trasera: contorno que se traza
        self._contorno_trasero.revelar(0.25 + 0.75 * _salida_suave(t / 450))
        if t > 450:
            self.canvas.itemconfigure(self._divisor_trasero, state="normal")

        # "iniciando...": sube y aparece
        p = _salida_suave((t - 100) / 320)
        if p > 0:
            for item, x, color in zip(self._ini_items, self._ini_xs, self._ini_colores):
                self.canvas.itemconfigure(
                    item, state="normal",
                    fill=_mezclar(self._color_fondo(x), color, p),
                )
                self.canvas.coords(item, x, self.Y_INICIANDO + 12 * (1 - p))

    def _actualizar_carrusel(self, t: float) -> None:
        t -= self.CARRUSEL_INICIO_MS
        if t < 0:
            return
        t %= self.CARRUSEL_CICLO_MS
        n = self.FICHAS_N
        for i, ficha in enumerate(self._fichas):
            # Entrada: llegan desde la derecha, las últimas viajan más lejos
            t_in = (t - i * 110) / 450
            # Salida: se van hacia la izquierda en cascada
            t_out = (t - self.CARRUSEL_PAUSA_MS - i * 70) / 350
            if t_out > 0:
                p = min(1.0, t_out)
                alfa = 1 - p**2
                dx = -12 * p**2
            else:
                p = _salida_suave(t_in)
                alfa = p
                dx = (30 + i * 10) * (1 - p)
            alfa = round(alfa, 2)
            if alfa == ficha["alfa"] and dx == ficha["dx"]:
                continue
            self.canvas.move(ficha["tag"], dx - ficha["dx"], 0)
            ficha["dx"] = dx
            if alfa != ficha["alfa"]:
                ficha["alfa"] = alfa
                fondo = self._color_fondo(ficha["cx"] + dx)
                estado = "hidden" if alfa <= 0 else "normal"
                for item, color in ficha["items"]:
                    self.canvas.itemconfigure(
                        item, state=estado, fill=_mezclar(fondo, color, alfa)
                    )

    def _actualizar_mensajes(self, t: float) -> None:
        t_msg = t - self.INICIO_MENSAJES_MS
        if t_msg < 0:
            return
        indice = int(t_msg // self.DURACION_MENSAJE_MS)
        if indice >= len(self._mensajes):
            return
        local = t_msg - indice * self.DURACION_MENSAJE_MS
        f = self.FUNDIDO_MENSAJE_MS
        alfa = _salida_suave(min(local / f, (self.DURACION_MENSAJE_MS - local) / f, 1.0))
        fondo = self._color_fondo(self.ANCHO / 2)
        self.canvas.itemconfigure(
            self._texto_mensaje, state="normal", text=self._mensajes[indice],
            fill=_mezclar(fondo, self.TEXTO_MENSAJE, alfa),
        )
        self.canvas.coords(
            self._texto_mensaje, self.ANCHO / 2, self.Y_MENSAJE + 6 * (1 - alfa)
        )

    def _salir(self) -> None:
        self._cerrando = True
        if self.SALIDA_MS <= 0:
            self.destroy()
            return
        inicio = time.perf_counter()

        def paso() -> None:
            p = (time.perf_counter() - inicio) * 1000 / self.SALIDA_MS
            if p >= 1:
                self.destroy()
                return
            try:
                self.attributes("-alpha", 1 - p)
            except tk.TclError:
                self.destroy()
                return
            self.after(self.INTERVALO_MS, paso)

        paso()


def mostrar_ventana_presentacion() -> None:
    """Muestra el splash brevemente y devuelve el control para iniciar la app."""
    ventana = VentanaPresentacion()
    ventana.mainloop()


if __name__ == "__main__":
    mostrar_ventana_presentacion()