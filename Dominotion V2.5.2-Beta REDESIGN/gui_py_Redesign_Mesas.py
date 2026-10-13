"""Interfaz de Dominotion: vistas, ventanas, eventos y temporizador de rondas.

Las consultas y reglas de negocio pertenecen a ``repository``; aquí se
construyen y actualizan los widgets. Tkinter solo se modifica desde el hilo de
la interfaz. Los datos para las hojas imprimibles y sus medidas vienen de
``hoja_mesa`` para que la vista previa coincida con el PDF. (SI HAY CAMBIOS EN "hoja mesa" QUE SE REFLEJEN AQUI!)
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import random
import re
import sqlite3
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

import db
import history_auth
from hilos import ejecutar_en_segundo_plano, instalar_manejador_global_de_excepciones
from hoja_mesa import (
    ALTO_TARJETA,
    ANCHO_ZONA_NUMERO,
    DESPLAZ_DIVISOR,
    DESPLAZ_ETIQUETA_ESTADISTICA,
    DESPLAZ_ETIQUETA_NUMERO,
    DESPLAZ_NOMBRE,
    DESPLAZ_NUMERO,
    DESPLAZ_VALOR_ESTADISTICA,
    DISTANCIA_TITULO_PAREJA,
    FUENTE_BOLD,
    FUENTE_NORMAL,
    MARGEN as MARGEN_HOJA,
    TAMANO_PAGINA,
    JugadorHoja,
    MesaHoja,
    ajustar_texto,
    como_jugador_hoja,
    distancia_superior_tarjeta,
    estadisticas_jugador,
    formatear_valor,
    generar_pdf_hoja_mesa,
    geometria_columnas,
)
import repository as repo
from splash import mostrar_ventana_presentacion

_DIR_RECURSOS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
_RUTA_ICONO_APP = (
    _DIR_RECURSOS / "Icons" / "Dominotion_App_Icons" / "Dominotion.ico"
)
_RUTAS_ICONOS_MARCADOR = {
    "pendiente": _DIR_RECURSOS / "Icons" / "Mesas_Icons" / "Miss_Marcador_Pendiente.png",
    "finalizado": _DIR_RECURSOS / "Icons" / "Mesas_Icons" / "Check_Marcador_Finalizada.png",
}


def _aplicar_icono_ventana(ventana: tk.Misc) -> None:
    ventana.iconbitmap(str(_RUTA_ICONO_APP))


def _centrar_ventana_en_pantalla(
    ventana: tk.Toplevel, ancho: int, alto: int
) -> None:
    ventana.update_idletasks()
    ancho_pantalla = ventana.winfo_screenwidth()
    alto_pantalla = ventana.winfo_screenheight()
    ancho = min(ancho, ancho_pantalla - 40)
    alto = min(alto, alto_pantalla - 80)
    x = max(0, (ancho_pantalla - ancho) // 2)
    y = max(0, (alto_pantalla - alto) // 2)
    ventana.geometry(f"{ancho}x{alto}+{x}+{y}")


def _cargar_iconos_marcador(master: tk.Misc) -> dict[str, ImageTk.PhotoImage]:
    iconos = {}
    for estado, ruta in _RUTAS_ICONOS_MARCADOR.items():
        with Image.open(ruta) as imagen:
            imagen_redimensionada = imagen.convert("RGBA").resize(
                (20, 20), Image.Resampling.LANCZOS
            )
        iconos[estado] = ImageTk.PhotoImage(imagen_redimensionada, master=master)
    return iconos


# Configuración inicial del tema
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- Paleta personalizada sobre el tema "blue" de customtkinter --------------
# Cada tupla sigue el orden (Light, Dark). Aplicar la paleta antes de crear
# widgets porque cada widget toma sus colores al inicializarse.
COLOR_FONDO_VENTANA = ("#E9EEF6", "#111827")    # fondo de la ventana y diálogos
COLOR_PANEL = ("#F5F7FB", "#1A2335")            # tarjetas, tablas, tabview
COLOR_PANEL_ANIDADO = ("#E3E9F3", "#16233F")    # panel dentro de otro panel
COLOR_SIDEBAR = ("#DDE5F1", "#0C1220")          # barra lateral
COLOR_BORDE = ("#C9D3E4", "#25314A")            # bordes sutiles de tarjetas y botones
COLOR_BORDE_ACENTO = ("#9DB8E8", "#2A416B")     # borde de controles secundarios
COLOR_ACENTO = ("#2F6FE0", "#3B82F6")           # color principal (azul)
COLOR_ACENTO_HOVER = ("#2559B8", "#2F6FE0")
COLOR_ACENTO_SUAVE = ("#D6E6FF", "#15294D")     # fondo del elemento activo
COLOR_TEXTO_ACENTO = ("#1D4ED8", "#8CC2FF")
COLOR_TEXTO_SECUNDARIO = ("#5B6980", "#8D9BB5")
COLOR_TARJETA_TEMPORIZADOR = ("#DCE8FB", "#16233F")
COLOR_PELIGRO_TEXTO = ("#B3261E", "#F08585")
COLOR_PELIGRO_BORDE = ("#E6B3B0", "#5A2D2D")
COLOR_PELIGRO_FONDO = ("#FBEAE9", "#2A1A1F")
COLOR_AVISO_TEXTO = ("#8A5A00", "#F0C35A")
COLOR_AVISO_BORDE = ("#E8D49A", "#4A3D16")
COLOR_AVISO_FONDO = ("#FFF4D6", "#221E12")
COLOR_EXITO_TEXTO = ("#1E7A46", "#6FCF8F")
# En Dark, el placeholder usa un gris con suficiente contraste sobre los campos.
COLOR_PLACEHOLDER = ("gray52", "gray50")


def aplicar_paleta_personalizada() -> None:
    """Ajusta los colores globales del tema activo de customtkinter."""
    tema = ctk.ThemeManager.theme
    tema["CTk"]["fg_color"] = list(COLOR_FONDO_VENTANA)
    tema["CTkToplevel"]["fg_color"] = list(COLOR_FONDO_VENTANA)
    tema["CTkFrame"]["fg_color"] = list(COLOR_PANEL)
    tema["CTkFrame"]["top_fg_color"] = list(COLOR_PANEL_ANIDADO)
    tema["CTkFrame"]["border_color"] = list(COLOR_BORDE)
    tema["CTkEntry"]["placeholder_text_color"] = list(COLOR_PLACEHOLDER)
    tema["CTkEntry"]["fg_color"] = list(COLOR_FONDO_VENTANA)
    tema["CTkEntry"]["border_color"] = list(COLOR_BORDE_ACENTO)
    tema["CTkButton"]["fg_color"] = list(COLOR_ACENTO)
    tema["CTkButton"]["hover_color"] = list(COLOR_ACENTO_HOVER)
    for nombre in ("CTkComboBox", "CTkOptionMenu"):
        tema[nombre]["fg_color"] = list(COLOR_FONDO_VENTANA if nombre == "CTkComboBox" else COLOR_ACENTO_SUAVE)
        tema[nombre]["button_color"] = list(COLOR_ACENTO)
        tema[nombre]["button_hover_color"] = list(COLOR_ACENTO_HOVER)
    tema["CTkComboBox"]["border_color"] = list(COLOR_BORDE_ACENTO)
    tema["CTkOptionMenu"]["text_color"] = list(COLOR_TEXTO_ACENTO)
    tema["CTkScrollbar"]["button_color"] = list(COLOR_BORDE_ACENTO)
    tema["CTkScrollbar"]["button_hover_color"] = list(COLOR_ACENTO)


aplicar_paleta_personalizada()


# --- Botones planos ----------------------------------------------------------
# Cada estilo define (fg_color, hover_color, text_color, border_color, border_width).
# Cada color es una tupla (Light, Dark) para que el botón siga el tema activo.
ESTILOS_BOTON: dict[str, dict] = {
    "primario": dict(
        fg_color=COLOR_ACENTO, hover_color=COLOR_ACENTO_HOVER,
        text_color=("#FFFFFF", "#FFFFFF"), border_width=0, border_color=COLOR_ACENTO,
    ),
    "secundario": dict(
        fg_color="transparent", hover_color=COLOR_ACENTO_SUAVE,
        text_color=("#1F2A44", "#C9D3E4"), border_width=1, border_color=COLOR_BORDE_ACENTO,
    ),
    "peligro": dict(
        fg_color="transparent", hover_color=COLOR_PELIGRO_FONDO,
        text_color=COLOR_PELIGRO_TEXTO, border_width=1, border_color=COLOR_PELIGRO_BORDE,
    ),
    "aviso": dict(
        fg_color="transparent", hover_color=COLOR_AVISO_FONDO,
        text_color=COLOR_AVISO_TEXTO, border_width=1, border_color=COLOR_AVISO_BORDE,
    ),
    "exito": dict(
        fg_color=("#1E7A46", "#2E9E5B"), hover_color=("#176338", "#25834A"),
        text_color=("#FFFFFF", "#FFFFFF"), border_width=0, border_color=("#1E7A46", "#2E9E5B"),
    ),
    "menu": dict(  # elementos de la barra lateral
        fg_color="transparent", hover_color=COLOR_ACENTO_SUAVE,
        text_color=COLOR_TEXTO_SECUNDARIO, border_width=0, border_color=COLOR_ACENTO,
    ),
    "menu_activo": dict(
        fg_color=COLOR_ACENTO_SUAVE, hover_color=COLOR_ACENTO_SUAVE,
        text_color=COLOR_TEXTO_ACENTO, border_width=0, border_color=COLOR_ACENTO,
    ),
}
# Compatibilidad: relaciona el ``fg_color`` que ya pasaba cada botón del código
# anterior con su estilo nuevo. ``None`` era el azul predeterminado del tema.
_ESTILO_POR_COLOR: dict[str | None, str] = {
    None: "primario", "#2980b9": "primario",
    "#d32f2f": "peligro", "#b71c1c": "peligro",
    "#f1c40f": "aviso",
    "#27ae60": "exito", "#2e7d32": "exito",
    "#8e44ad": "secundario", "#d35400": "primario",
}


# ==========================================================================
# AYUDAS EMERGENTES (TOOLTIPS)
# ==========================================================================

def _color_segun_modo(color):
    """Resuelve un color o par (claro, oscuro) al del modo de apariencia activo."""
    if isinstance(color, str):
        return color
    return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]


def _clave_ayuda(texto) -> str:
    """Clave para buscar un texto visible: sin íconos ni signos en los extremos."""
    return re.sub(r"^\W+|\W+$", "", str(texto or "")).lower()


class Tooltip:
    """Ventana de ayuda breve que aparece al dejar el cursor sobre un widget.

    ``texto`` puede ser un ``str`` o una función sin argumentos que devuelva el
    texto en el momento de mostrarlo (útil si cambia con el estado del widget).

    Aparece tras ``RETARDO_MS``. Para que nunca quede "pegado", además de los
    eventos <Leave> / clic (que en los widgets de CustomTkinter pueden perderse)
    se vigila el puntero mientras está visible: se oculta en cuanto el cursor
    deja el widget, el widget deja de verse o pasa ``DURACION_MAX_MS``.
    """

    RETARDO_MS = 1500
    VIGILANCIA_MS = 100
    DURACION_MAX_MS = 12000
    ANCHO_MAX = 320

    def __init__(self, widget, texto) -> None:
        self.widget = widget
        self.texto = texto
        self._job = None
        self._vigia = None
        self._inicio = 0.0
        self._ventana: tk.Toplevel | None = None
        widget.bind("<Enter>", self._programar, add="+")
        widget.bind("<Leave>", self._al_salir, add="+")
        widget.bind("<ButtonPress>", self._ocultar, add="+")
        widget.bind("<MouseWheel>", self._ocultar, add="+")
        widget.bind("<Destroy>", self._ocultar, add="+")

    # --- Comprobaciones del puntero -------------------------------------
    def _puntero_sobre_widget(self) -> bool:
        """True si el widget bajo el cursor es este widget o uno de sus componentes."""
        try:
            x, y = self.widget.winfo_pointerxy()
            bajo = self.widget.winfo_containing(x, y)
        except (tk.TclError, KeyError):
            return False
        if bajo is None:  # fuera de la aplicación
            return False
        ruta, propia = str(bajo), str(self.widget)
        if self._ventana is not None:
            ventana = str(self._ventana)
            if ruta == ventana or ruta.startswith(ventana + "."):
                return False
        return ruta == propia or ruta.startswith(propia + ".")

    def _sigue_valido(self) -> bool:
        """Gancho para subclases: condiciones extra para mantener el tooltip."""
        return True

    # --- Ciclo de vida ---------------------------------------------------
    def _programar(self, _evento=None) -> None:
        if self._ventana is not None:
            return
        self._cancelar_espera()
        try:
            self._job = self.widget.after(self.RETARDO_MS, self._mostrar)
        except tk.TclError:
            self._job = None

    def _cancelar_espera(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _al_salir(self, _evento=None) -> None:
        # Los widgets de CTk se componen de varias capas: si el puntero sigue
        # dentro del widget no se trata como una salida real.
        if not self._puntero_sobre_widget():
            self._ocultar()

    def _mostrar(self) -> None:
        self._job = None
        if self._ventana is not None:
            return
        try:
            if not self.widget.winfo_exists() or not self._puntero_sobre_widget():
                return
            if not self._sigue_valido():
                return
            texto = self.texto() if callable(self.texto) else self.texto
            if not texto:
                return
            ventana = tk.Toplevel(self.widget)
            ventana.wm_overrideredirect(True)
            # Se construye oculta y se muestra ya en su posición final: si apareciera
            # primero en la esquina de la pantalla podría quedar bajo el cursor.
            ventana.withdraw()
            try:
                ventana.wm_attributes("-topmost", True)
            except tk.TclError:
                pass
            borde = _color_segun_modo(COLOR_BORDE_ACENTO)
            tk.Label(
                ventana,
                text=texto,
                justify="left",
                wraplength=self.ANCHO_MAX,
                bg=_color_segun_modo(COLOR_PANEL_ANIDADO),
                fg=_color_segun_modo(tuple(ctk.ThemeManager.theme["CTkLabel"]["text_color"])),
                font=("Segoe UI", 10),
                padx=10,
                pady=6,
                borderwidth=0,
                highlightthickness=1,
                highlightbackground=borde,
                highlightcolor=borde,
            ).pack()
            ventana.update_idletasks()
            ancho, alto = ventana.winfo_reqwidth(), ventana.winfo_reqheight()
            puntero_x, puntero_y = self.widget.winfo_pointerxy()
            x, y = puntero_x + 14, puntero_y + 20
            if x + ancho > ventana.winfo_screenwidth() - 8:
                x = max(8, ventana.winfo_screenwidth() - ancho - 8)
            if y + alto > ventana.winfo_screenheight() - 8:
                y = max(8, puntero_y - alto - 12)
            ventana.wm_geometry(f"+{x}+{y}")
            self._ventana = ventana
            ventana.deiconify()
            self._inicio = time.monotonic()
            self._vigia = self.widget.after(self.VIGILANCIA_MS, self._vigilar)
        except tk.TclError:
            self._ocultar()

    def _vigilar(self) -> None:
        """Oculta el tooltip si el cursor se fue, aunque no llegara el evento <Leave>."""
        self._vigia = None
        if self._ventana is None:
            return
        try:
            excedido = (time.monotonic() - self._inicio) * 1000 > self.DURACION_MAX_MS
            if (
                excedido
                or not self.widget.winfo_exists()
                or not self.widget.winfo_viewable()
                or not self._puntero_sobre_widget()
                or not self._sigue_valido()
            ):
                self._ocultar()
                return
            self._vigia = self.widget.after(self.VIGILANCIA_MS, self._vigilar)
        except tk.TclError:
            self._ocultar()

    def _ocultar(self, _evento=None) -> None:
        self._cancelar_espera()
        if self._vigia is not None:
            try:
                self.widget.after_cancel(self._vigia)
            except tk.TclError:
                pass
            self._vigia = None
        if self._ventana is not None:
            try:
                self._ventana.destroy()
            except tk.TclError:
                pass
            self._ventana = None


class TooltipEncabezados(Tooltip):
    """Tooltips para los encabezados de un ``ttk.Treeview`` (``{columna: texto}``)."""

    def __init__(self, tabla: ttk.Treeview, textos: dict[str, str]) -> None:
        self._textos = textos
        self._columna: str | None = None
        super().__init__(tabla, self._texto_columna)
        tabla.bind("<Motion>", self._al_mover, add="+")

    def _texto_columna(self) -> str | None:
        return self._textos.get(self._columna) if self._columna else None

    def _columna_en(self, x: int, y: int) -> str | None:
        """Columna cuyo encabezado está en (x, y) relativos a la tabla, si lo hay."""
        tabla = self.widget
        if tabla.identify_region(x, y) != "heading":
            return None
        indice = int(tabla.identify_column(x).lstrip("#") or 0)
        if indice == 0:
            return "#0"
        visibles = tabla.cget("displaycolumns")
        if isinstance(visibles, str):
            visibles = (visibles,)
        if not visibles or tuple(visibles) == ("#all",):
            visibles = tabla.cget("columns")
            if isinstance(visibles, str):
                visibles = (visibles,)
        return visibles[indice - 1] if 0 < indice <= len(visibles) else None

    def _sigue_valido(self) -> bool:
        """El tooltip solo vale mientras el cursor siga sobre el mismo encabezado."""
        if self._columna is None:
            return False
        try:
            x = self.widget.winfo_pointerx() - self.widget.winfo_rootx()
            y = self.widget.winfo_pointery() - self.widget.winfo_rooty()
            return self._columna_en(x, y) == self._columna
        except (tk.TclError, ValueError):
            return False

    def _al_mover(self, evento) -> None:
        try:
            columna = self._columna_en(evento.x, evento.y)
        except (tk.TclError, ValueError):
            columna = None
        if columna == self._columna:
            return
        self._columna = columna
        self._ocultar()
        if columna in self._textos:
            self._programar()


# Ayudas para botones y etiquetas, buscadas por su texto visible (sin ícono).
AYUDAS_ETIQUETAS: dict[str, str] = {
    _clave_ayuda(clave): texto
    for clave, texto in {
        # Vista "En vivo / rondas"
        "Panel de control de ronda": "Cronómetro de la ronda en curso.",
        "Iniciar primera ronda": "Genera las mesas de la primera ronda con el estilo de emparejamiento elegido.",
        "Generar siguiente ronda": "Crea las mesas de la siguiente ronda según el ranking actual y el estilo de emparejamiento elegido.",
        "Eliminar última ronda": "Elimina la última ronda y sus resultados. No se puede deshacer.",
        "Terminar edición histórica": "Guarda los cambios hechos a un torneo finalizado y lo devuelve al historial (pide la clave de historial).",
        "Hoja de mesa": "Abre las hojas de mesa de la ronda activa para imprimir, con el número de jugador y sus estadísticas (PG, PP, EF).",
        "Ver mesas por número de jugador": "Abre un tablero que indica la mesa que le toca a cada número de jugador.",
        "Anotar marcador": "Registra el marcador de la mesa seleccionada.",
        "Sustituir participante": "Reemplaza a un participante por un jugador que no esté inscrito. Respeta el tipo del torneo (mixto, hombres o mujeres).",
        "Historial de participante": "Muestra el historial de cambios de un participante, por ejemplo penalizaciones y retiros.",
        "Penalizaciones": "Registra faltas a un jugador. La tercera falta aplica tarjeta roja y lo retira del torneo.",
        "Declarar forfeit": "Da la mesa por perdida a una pareja o a ambas (doble forfeit, 0-0) y permite retirar jugadores.",
        "Ver ranking por clubes": "Muestra la clasificación agrupada por club.",
        "Visualizar ranking": "Filtra la clasificación: general, solo hombres o solo mujeres.",
        # Historial de rondas
        "Editar disposición": "Reordena los cuatro asientos de la mesa seleccionada sin modificar su marcador.",
        "Swap externo": "Intercambia un asiento entre dos mesas de la misma ronda.",
        "Editar resultado de la mesa": "Corrige el marcador de la mesa seleccionada. También se abre con doble clic sobre la mesa.",
        # Ventana de carga de marcador
        "Siguiente mesa": "Pasa a la siguiente mesa de la lista sin cerrar la ventana.",
        "Anterior mesa": "Vuelve a la mesa anterior de la lista sin cerrar la ventana.",
        "Descuento por infracción": "Puntos que se restan a una pareja por una infracción. Se puede escribir -30 o 30.",
        "Motivo del descuento": "Explica por qué se aplica el descuento (opcional).",
        "Resultado del marcador con el descuento": "Marcador final después de restar los descuentos. Nunca baja de 0.",
        "Mesas marcadas": "Mesas de la ronda. Las marcadas ya tienen resultado; haz clic en una para cargarla.",
        # Formularios de torneo
        "Duración (minutos)": "Tiempo disponible para jugar cada ronda.",
        "Duración en minutos": "Tiempo disponible para jugar cada ronda.",
        "Tipo": "Mixto admite hombres y mujeres. Hombres o Mujeres limita la inscripción a ese sexo.",
        "Tipo de torneo": "Mixto admite hombres y mujeres. Hombres o Mujeres limita la inscripción a ese sexo.",
        "Puntaje meta": "Puntos que una pareja debe alcanzar para ganar la mesa. También se usa para valorar las tarjetas rojas en el ranking.",
        "Número de rondas": "Cantidad de rondas que tendrá el torneo.",
    }.items()
}

# Ayudas para encabezados de tablas (``ttk.Treeview``), buscadas por el texto del encabezado.
AYUDAS_ENCABEZADOS: dict[str, str] = {
    _clave_ayuda(clave): texto
    for clave, texto in {
        "Pos": "Posición en la clasificación. Se ordena por PG, luego EF y luego PF.",
        "PG": "Partidas ganadas.",
        "PP": "Partidas perdidas.",
        "EF": "Efectividad: por partido, objetivo de puntos menos los puntos del perdedor. El ganador suma esa diferencia y el perdedor la recibe en negativo. La tarjeta roja suma o resta el puntaje meta.",
        "EF (Dif)": "Efectividad: por partido, objetivo de puntos menos los puntos del perdedor. El ganador suma esa diferencia y el perdedor la recibe en negativo. La tarjeta roja suma o resta el puntaje meta.",
        "PF": "Puntos a favor: total de puntos anotados.",
        "Pareja 1": "Los dos jugadores de la pareja 1 (asientos 1 y 2).",
        "Pareja 2": "Los dos jugadores de la pareja 2 (asientos 3 y 4).",
        "Pareja 1 (J1 / J2)": "Jugadores 1 y 2 de la mesa (primera pareja).",
        "Pareja 2 (J3 / J4)": "Jugadores 3 y 4 de la mesa (segunda pareja).",
        "Pareja 1 / BYE": "Si aparece BYE, ese jugador descansa en la ronda y no juega mesa.",
        "Marcador": "Puntos de cada pareja. Aparece un identificativo si la mesa aún no tiene resultado.",
        "Marcador final": "Resultado de la mesa después de aplicar los descuentos.",
        "Puntos base": "Puntos anotados antes de aplicar los descuentos.",
        "Descuentos": "Puntos restados por infracciones.",
        "Penalización / estado": "Motivo del descuento o estado especial de la mesa, por ejemplo forfeit o tarjeta roja.",
        "Minutos": "Duración de cada ronda, en minutos.",
        "Puntaje": "Puntaje meta: puntos que una pareja debe alcanzar para ganar la mesa.",
        "Rondas": "Cantidad de rondas del torneo.",
    }.items()
}

# Pestañas de la vista "En vivo / rondas" y de la vista de torneos finalizados.
AYUDAS_PESTANAS_EN_VIVO: dict[str, str] = {
    "Ronda y mesas activas": "Mesas de la ronda en juego y registro de marcadores.",
    "Mesas sin registrar": "Mesas de la ronda actual que todavía no tienen marcador.",
    "Clasificación general (ranking)": "Posición de cada jugador. Se ordena por PG, luego EF y luego PF.",
    "Historial de rondas": "Rondas anteriores con sus mesas y resultados. Permite corregir marcadores y asientos.",
}
AYUDAS_PESTANAS_ARCHIVADAS: dict[str, str] = {
    "Rondas y mesas": "Mesas y marcadores de cada ronda del torneo.",
    "Clasificación": "Posición final de cada jugador.",
    "Clasificación por club": "Posición final de cada club.",
    "Penalizaciones": "Faltas, tarjetas y descuentos registrados durante el torneo.",
}


def aplicar_ayudas(raiz, ayudas: dict[str, str] | None = None,
                   encabezados: dict[str, str] | None = None) -> None:
    """Agrega tooltips a los botones, etiquetas y encabezados de tabla bajo ``raiz``.

    Cada widget se identifica por su texto visible (sin íconos); los que no
    figuran en ``AYUDAS_ETIQUETAS`` / ``AYUDAS_ENCABEZADOS`` se ignoran. Es
    seguro llamarla varias veces: no duplica los tooltips ya creados.
    """
    ayudas = AYUDAS_ETIQUETAS if ayudas is None else ayudas
    encabezados = AYUDAS_ENCABEZADOS if encabezados is None else encabezados
    pendientes = [raiz]
    while pendientes:
        widget = pendientes.pop()
        try:
            pendientes.extend(widget.winfo_children())
        except tk.TclError:
            continue
        if getattr(widget, "_ayuda_aplicada", False):
            continue
        try:
            if isinstance(widget, ttk.Treeview):
                columnas = widget.cget("columns")
                if isinstance(columnas, str):
                    columnas = (columnas,)
                textos = {}
                for columna in ("#0", *columnas):
                    clave = _clave_ayuda(widget.heading(columna, "text"))
                    if clave in encabezados:
                        textos[columna] = encabezados[clave]
                if textos:
                    TooltipEncabezados(widget, textos)
                    widget._ayuda_aplicada = True
            elif isinstance(widget, (ctk.CTkButton, ctk.CTkLabel)):
                texto = ayudas.get(_clave_ayuda(widget.cget("text")))
                if texto:
                    Tooltip(widget, texto)
                    widget._ayuda_aplicada = True
        except (tk.TclError, ValueError, AttributeError):
            continue


class BotonPlano(ctk.CTkButton):
    """CTkButton con estilo plano (sin degradados) y variantes por ``estilo``.

    Se usa igual que ``ctk.CTkButton``. ``estilo`` elige entre ``ESTILOS_BOTON``;
    si no se indica, se deduce del ``fg_color`` heredado del código anterior
    (ver ``_ESTILO_POR_COLOR``) y cualquier otro color se respeta tal cual.
    ``padding_x`` se acepta por compatibilidad y se ignora.
    """

    def __init__(self, master, *args, estilo: str | None = None, fg_color=None,
                 padding_x: int | None = None, **kwargs):
        clave = fg_color.lower() if isinstance(fg_color, str) else fg_color
        if estilo is None and (clave is None or isinstance(clave, str)):
            estilo = _ESTILO_POR_COLOR.get(clave)
        if estilo is not None:
            kwargs.pop("hover_color", None)
            for nombre, valor in ESTILOS_BOTON[estilo].items():
                kwargs.setdefault(nombre, valor)
        elif fg_color is not None:
            kwargs["fg_color"] = fg_color
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("text_color_disabled", COLOR_TEXTO_SECUNDARIO)
        if "text" in kwargs:
            kwargs["text"] = self._espaciar_icono(kwargs["text"])
        super().__init__(master, *args, **kwargs)

    @staticmethod
    def _espaciar_icono(texto: str) -> str:
        """Si el texto empieza con un icono y un espacio, usa un espacio ancho."""
        return re.sub(r"^(\S*[^\x00-\x7f]\S*) (?=\S)", "\\1\u2002", texto or "")

    def configure(self, require_redraw=False, **kwargs):
        if isinstance(kwargs.get("text"), str):
            kwargs["text"] = self._espaciar_icono(kwargs["text"])
        super().configure(require_redraw=require_redraw, **kwargs)


# Nombre anterior: se conserva para no reescribir los usos existentes.
BotonDegradado = BotonPlano


def aplicar_estilo_treeview(mode: str = "Dark") -> None:
    """Aplica un tema visual a las tablas (Treeview) dinámicamente según el modo activo."""
    modo = (mode or "Dark").strip()
    if modo.lower() == "system":
        modo = ctk.get_appearance_mode()

    style = ttk.Style()
    style.theme_use("clam")

    if modo.lower() == "light":
        bg = "#FFFFFF"
        fg = "#1F2A44"
        fieldbg = "#FFFFFF"
        select_bg = "#D6E6FF"
        select_fg = "#1D4ED8"
        heading_bg = "#E3E9F3"
        heading_fg = "#5B6980"
        borde = "#C9D3E4"
    else:  # Dark Mode
        bg = "#151D2D"
        fg = "#E6EBF5"
        fieldbg = "#151D2D"
        select_bg = "#15294D"
        select_fg = "#8CC2FF"
        heading_bg = "#1A2335"
        heading_fg = "#8D9BB5"
        borde = "#25314A"

    style.configure(
        "Treeview",
        background=bg,
        foreground=fg,
        fieldbackground=fieldbg,
        borderwidth=0,
        rowheight=32,
        bordercolor=borde,
        lightcolor=borde,
        darkcolor=borde,
        font=("Segoe UI", 10),
    )
    cell_layout = style.layout("Treeview.Cell")
    if not cell_layout or cell_layout[0][0] != "border":
        style.layout(
            "Treeview.Cell",
            [("border", {"sticky": "nswe", "children": cell_layout})],
        )
    style.configure(
        "Treeview.Cell",
        borderwidth=1,
        relief="solid",
        bordercolor=borde,
        lightcolor=borde,
        darkcolor=borde,
        padding=(6, 4),
    )
    style.map(
        "Treeview",
        background=[("selected", select_bg)],
        foreground=[("selected", select_fg)],
    )
    style.configure(
        "Treeview.Heading",
        background=heading_bg,
        foreground=heading_fg,
        relief="solid",
        borderwidth=1,
        bordercolor=borde,
        lightcolor=borde,
        darkcolor=borde,
        padding=(8, 8),
        font=("Segoe UI", 10, "bold"),
    )
    style.map(
        "Treeview.Heading",
        background=[("active", heading_bg), ("!disabled", heading_bg)],
        foreground=[("active", heading_fg), ("!disabled", heading_fg)],
    )
    # Barras de desplazamiento finas y discretas.
    style.configure(
        "Vertical.TScrollbar",
        background=borde,
        troughcolor=bg,
        bordercolor=bg,
        arrowcolor=heading_fg,
        relief="flat",
        gripcount=0,
        width=12,
    )
    style.map("Vertical.TScrollbar", background=[("active", select_bg)])


def _limpiar_treeview(tabla: ttk.Treeview) -> None:
    """Elimina las filas actuales con una sola llamada a Tk."""
    elementos = tabla.get_children()
    if elementos:
        tabla.delete(*elementos)


def _ventanas_toplevel_abiertas(raiz: tk.Misc) -> list[tk.Misc]:
    """Devuelve la ventana raíz y todas las Toplevel (diálogos) abiertas."""
    encontradas: list[tk.Misc] = [raiz]
    pendientes = list(raiz.winfo_children())
    while pendientes:
        w = pendientes.pop()
        if isinstance(w, tk.Toplevel):
            encontradas.append(w)
        pendientes.extend(w.winfo_children())
    return encontradas


def _pintar_barra_titulo_windows(ventana: tk.Misc, modo: str) -> None:
    """Colorea la barra de título (claro/oscuro) en Windows SIN ocultar la ventana.

    El cambio de tema de CustomTkinter puede ocultar y volver a mostrar una
    ventana para repintar la barra. DWM y ``SetWindowPos(SWP_FRAMECHANGED)``
    actualizan el marco directamente para evitar ese parpadeo.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        valor = 1 if modo.lower() == "dark" else 0
        hwnd = ctypes.windll.user32.GetParent(ventana.winfo_id())
        dato = ctypes.c_int(valor)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE; 19 = versión previa a Win10 20H1
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dato), ctypes.sizeof(dato)) != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dato), ctypes.sizeof(dato))
        # SWP_NOSIZE|SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE|SWP_FRAMECHANGED
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
    except Exception:
        pass


def _detectar_tema_sistema() -> str:
    """Devuelve "Dark" o "Light" según el tema actual del sistema operativo."""
    try:
        import darkdetect  # dependencia de customtkinter

        return "Dark" if darkdetect.theme() == "Dark" else "Light"
    except Exception:
        return ctk.get_appearance_mode()


def debounce(widget, atributo_temporizador: str, retardo_ms: int, funcion) -> None:
    """Retrasa la ejecución de ``funcion`` ``retardo_ms`` después de la
    última llamada, cancelando cualquier llamada pendiente anterior.

    Los filtros de búsqueda pueden llamar esta función en cada ``<KeyRelease>``
    para esperar a que termine la escritura antes de consultar y redibujar.
    ``atributo_temporizador`` identifica en el widget el callback ``after``
    pendiente; cada campo debe guardar su propio identificador.
    """
    id_pendiente = getattr(widget, atributo_temporizador, None)
    if id_pendiente is not None:
        try:
            widget.after_cancel(id_pendiente)
        except Exception:
            pass
    nuevo_id = widget.after(retardo_ms, funcion)
    setattr(widget, atributo_temporizador, nuevo_id)


class EntryAutocompletado(ctk.CTkEntry):
    """``CTkEntry`` con una lista de sugerencias que aparece justo debajo
    mientras se escribe, con filtrado inmediato y navegación por teclado.

    - ``opciones``: lista de cadenas, o un dict ``{etiqueta: valor}`` cuando
      el texto mostrado y el dato real a usar son distintos (p. ej. un
      nombre visible que debe resolverse a una cédula).
    - ``on_select(etiqueta, valor)``: callback opcional, se dispara cuando
      el usuario elige una sugerencia (clic o Enter sobre la resaltada).
    - ``on_change(texto)``: callback opcional, se dispara en cada tecleo
      (útil para invalidar una selección previa apenas el texto cambia).
    - ``max_sugerencias``: cantidad máxima de filas mostradas a la vez.

    El placeholder es el nativo de ``CTkEntry`` (se pasa igual que siempre
    vía ``placeholder_text=...``); esta clase no reimplementa esa parte.
    """

    _ALTO_FILA = 32  # alto de cada botón sugerido
    _PADY_FILA = 3  # separación vertical arriba/abajo de cada botón
    _PADX_FILA = 6  # separación horizontal de cada botón dentro de la lista

    # Colores fijos para la lista de sugerencias. No se leen del tema activo
    # (``ctk.ThemeManager``) porque esa estructura puede variar entre
    # versiones de customtkinter o temas de color distintos al por defecto,
    # y una clave faltante ahí rompía silenciosamente el despliegue.
    _COLOR_FONDO_LISTA = ("gray90", "gray20")
    _COLOR_BORDE_LISTA = ("gray65", "gray28")
    _COLOR_HOVER_FILA = ("gray75", "gray28")
    _COLOR_TEXTO_FILA = ("gray10", "gray90")

    def __init__(
        self,
        master,
        opciones=None,
        on_select=None,
        on_change=None,
        max_sugerencias: int = 8,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._on_select = on_select
        self._on_change = on_change
        self._max_sugerencias = max_sugerencias
        self._opciones: dict[str, object] = {}
        self._marco_sugerencias: ctk.CTkFrame | None = None
        self._botones_sugerencias: list[ctk.CTkButton] = []
        self._indice_resaltado = -1
        self._valor_seleccionado = None
        self.establecer_opciones(opciones or [])

        self.bind("<KeyRelease>", self._al_escribir)
        self.bind("<FocusIn>", self._al_recibir_foco)
        self.bind("<FocusOut>", self._al_perder_foco)
        self.bind("<Down>", self._al_mover(1))
        self.bind("<Up>", self._al_mover(-1))
        self.bind("<Return>", self._al_presionar_enter)
        self.bind("<KP_Enter>", self._al_presionar_enter)
        self.bind("<Escape>", self._al_presionar_escape)
        # Si el entry se mueve o cambia de tamaño (p. ej. al redimensionar
        # la ventana) se reacomoda la lista en su nueva posición.
        self.bind("<Configure>", self._al_reconfigurar)

    # ------------------------------------------------------------------
    # Configuración de opciones
    # ------------------------------------------------------------------
    def establecer_opciones(self, opciones) -> None:
        """Reemplaza el universo de sugerencias. Acepta lista de cadenas o
        un dict ``{etiqueta: valor}``."""
        if isinstance(opciones, dict):
            self._opciones = dict(opciones)
        else:
            self._opciones = {etiqueta: etiqueta for etiqueta in opciones}

    def valor_seleccionado(self):
        """Valor real de la última sugerencia elegida; si el texto actual
        coincide exactamente con una etiqueta conocida también lo resuelve."""
        if self._valor_seleccionado is not None:
            return self._valor_seleccionado
        return self._opciones.get(self.get())

    # ------------------------------------------------------------------
    # Filtrado y despliegue de sugerencias
    # ------------------------------------------------------------------
    def _coincidencias(self, texto: str) -> list[str]:
        consulta = texto.strip().casefold()
        if not consulta:
            return []
        return [
            etiqueta for etiqueta in self._opciones if consulta in etiqueta.casefold()
        ][: self._max_sugerencias]

    def _al_escribir(self, event=None) -> None:
        if event is not None and event.keysym in ("Up", "Down", "Return", "KP_Enter", "Escape"):
            return
        self._valor_seleccionado = None
        self._actualizar_sugerencias()

    def _al_recibir_foco(self, event=None) -> None:
        """Vuelve a desplegar las coincidencias si el campo ya tiene texto."""
        self._actualizar_sugerencias()

    def _actualizar_sugerencias(self) -> None:
        texto = self.get()
        if self._on_change is not None:
            self._on_change(texto)
        coincidencias = self._coincidencias(texto)
        if coincidencias:
            self._mostrar_sugerencias(coincidencias)
        else:
            self._cerrar_sugerencias()

    def _al_reconfigurar(self, event=None) -> None:
        if self._marco_sugerencias is not None:
            self._posicionar_sugerencias()

    def _crear_marco_sugerencias(self) -> None:
        marco = ctk.CTkFrame(
            self.winfo_toplevel(),
            corner_radius=8,
            border_width=1,
            border_color=self._COLOR_BORDE_LISTA,
            fg_color=self._COLOR_FONDO_LISTA,
        )
        self._marco_sugerencias = marco

    def _mostrar_sugerencias(self, etiquetas: list[str]) -> None:
        if self._marco_sugerencias is None:
            self._crear_marco_sugerencias()

        for boton in self._botones_sugerencias:
            boton.destroy()
        self._botones_sugerencias = []
        self._indice_resaltado = -1

        for etiqueta in etiquetas:
            boton = ctk.CTkButton(
                self._marco_sugerencias,
                text=etiqueta,
                anchor="center",
                corner_radius=6,
                height=self._ALTO_FILA,
                fg_color="transparent",
                hover_color=self._COLOR_HOVER_FILA,
                text_color=self._COLOR_TEXTO_FILA,
                command=lambda valor=etiqueta: self._elegir(valor),
            )
            boton.pack(fill="x", padx=self._PADX_FILA, pady=self._PADY_FILA)
            self._botones_sugerencias.append(boton)

        self._posicionar_sugerencias()
        self._marco_sugerencias.lift()

    def _posicionar_sugerencias(self) -> None:
        if self._marco_sugerencias is None:
            return
        # El panel se monta en la ventana superior para que no quede recortado
        # por un frame de una sola fila, como el usado por la ventana modal.
        # ``place`` aplica de nuevo el escalado de customtkinter, por lo que
        # las coordenadas físicas se convierten al sistema lógico.
        contenedor = self.winfo_toplevel()
        x = self._reverse_widget_scaling(
            self.winfo_rootx() - contenedor.winfo_rootx()
        )
        y = self._reverse_widget_scaling(
            self.winfo_rooty() - contenedor.winfo_rooty() + self.winfo_height()
        )
        ancho = self._reverse_widget_scaling(self.winfo_width())
        alto = (
            self._ALTO_FILA + 2 * self._PADY_FILA
        ) * len(self._botones_sugerencias) + 2
        self._marco_sugerencias.configure(width=ancho, height=alto)
        self._marco_sugerencias.place(
            in_=contenedor,
            x=x,
            y=y,
        )
        self._marco_sugerencias.lift()

    def _cerrar_sugerencias(self) -> None:
        if self._marco_sugerencias is not None:
            self._marco_sugerencias.destroy()
        self._marco_sugerencias = None
        self._botones_sugerencias = []
        self._indice_resaltado = -1

    # ------------------------------------------------------------------
    # Navegación por teclado
    # ------------------------------------------------------------------
    def _al_mover(self, delta: int):
        def _manejador(event=None):
            if not self._botones_sugerencias:
                return None
            total = len(self._botones_sugerencias)
            self._indice_resaltado = (self._indice_resaltado + delta) % total
            self._resaltar()
            return "break"

        return _manejador

    def _resaltar(self) -> None:
        for indice, boton in enumerate(self._botones_sugerencias):
            boton.configure(
                fg_color=self._COLOR_HOVER_FILA if indice == self._indice_resaltado else "transparent"
            )

    def _al_presionar_enter(self, event=None):
        if self._botones_sugerencias and self._indice_resaltado >= 0:
            etiqueta = self._botones_sugerencias[self._indice_resaltado].cget("text")
            self._elegir(etiqueta)
            return "break"
        self._cerrar_sugerencias()
        return None

    def _al_presionar_escape(self, event=None):
        self._cerrar_sugerencias()
        return None

    # ------------------------------------------------------------------
    # Selección y cierre
    # ------------------------------------------------------------------
    def _elegir(self, etiqueta: str) -> None:
        self.delete(0, "end")
        self.insert(0, etiqueta)
        self._valor_seleccionado = self._opciones.get(etiqueta)
        self._cerrar_sugerencias()
        self.focus_set()
        if self._on_select is not None:
            self._on_select(etiqueta, self._valor_seleccionado)

    def _al_perder_foco(self, event=None) -> None:
        # Se retrasa el cierre para que un clic sobre una sugerencia
        # alcance a ejecutarse antes de destruir el panel.
        self.after(150, self._cerrar_sugerencias)

    def destroy(self) -> None:
        self._cerrar_sugerencias()
        super().destroy()


def mostrar_overlay_cargando(padre: tk.Misc, texto: str = "Cargando…"):
    """Cubre temporalmente la ventana padre mientras se construye una modal.

    El overlay vive dentro de la ventana principal, por lo que no depende de
    otra Toplevel que también tenga que renderizarse. Después de crearlo se
    fuerza ``update_idletasks()`` para que el usuario vea el estado "Cargando"
    antes de entrar en una operación síncrona y pesada.
    """
    overlay = ctk.CTkFrame(
        padre,
        fg_color=("gray86", "gray10"),
        corner_radius=0,
    )
    overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
    overlay.lift()

    tarjeta = ctk.CTkFrame(
        overlay,
        width=360,
        height=180,
        corner_radius=22,
        fg_color=("white", "gray18"),
        border_width=1,
        border_color=("gray70", "gray30"),
    )
    tarjeta.place(relx=0.5, rely=0.5, anchor="center")
    tarjeta.pack_propagate(False)

    ctk.CTkLabel(
        tarjeta,
        text="Cargando",
        font=ctk.CTkFont(size=24, weight="bold"),
    ).pack(pady=(24, 4))

    ctk.CTkLabel(
        tarjeta,
        text=texto,
        font=ctk.CTkFont(size=14),
        text_color=("gray30", "gray75"),
        wraplength=310,
    ).pack(pady=(0, 18))

    barra = ctk.CTkProgressBar(tarjeta, mode="indeterminate", width=260, height=8)
    barra.pack()
    barra.start()

    # La cubierta recibe clics y teclado mientras se construye la ventana; así
    # no se activan controles de la vista principal durante la preparación.
    overlay.bind("<Button>", lambda _e: "break")
    overlay.bind("<Key>", lambda _e: "break")
    overlay.focus_set()

    # Procesar las tareas de dibujo ahora muestra la cubierta antes de que la
    # construcción síncrona bloquee el event loop.
    padre.update_idletasks()
    return overlay, barra


def cerrar_overlay_cargando(overlay, barra=None) -> None:
    """Detiene y elimina de forma segura un overlay de carga."""
    if barra is not None:
        try:
            barra.stop()
        except (tk.TclError, AttributeError):
            pass
    try:
        if overlay is not None and overlay.winfo_exists():
            overlay.destroy()
    except tk.TclError:
        pass


def enlazar_enter_formulario(*widgets, accion_final=None):
    """Hace que Enter avance al siguiente campo y, en el último, ejecute la acción principal."""
    orden = [widget for widget in widgets if widget is not None]
    for index, widget in enumerate(orden):
        siguiente = orden[index + 1] if index + 1 < len(orden) else None

        def _on_enter(event, target=siguiente, accion=accion_final):
            if target is not None:
                target.focus_set()
                return "break"
            if accion is not None:
                accion()
            return "break"

        widget.bind("<Return>", _on_enter, add="+")
        widget.bind("<KP_Enter>", _on_enter, add="+")


def bloquear_reentrada(callback):
    """Evita disparar la misma acción más de una vez por click rápido o Enter."""
    def ejecutor(*args, **kwargs):
        if getattr(ejecutor, "_bloqueada", False):
            return None
        ejecutor._bloqueada = True
        try:
            return callback(*args, **kwargs)
        finally:
            ejecutor._bloqueada = False
    return ejecutor


# ==========================================================================
# VENTANAS EMERGENTES (MODALES)
# ==========================================================================

class VentanaModal(ctk.CTkToplevel):
    """Base común para los diálogos modales de la aplicación.

    Por defecto las ventanas siguen siendo modales. Las ventanas que necesiten
    convivir con la vista principal pueden construirse con ``modal=False`` y
    entonces no bloquean ni deshabilitan a su padre.

    En Windows, para una ventana modal se usa ``-disabled`` sobre el padre en
    lugar de ``grab_set()`` para conservar la posibilidad de minimizar/restaurar
    correctamente el diálogo.
    """

    def __init__(self, parent=None, *args, modal: bool = True, **kwargs):
        self._es_modal = bool(modal)
        super().__init__(parent, *args, **kwargs)
        _aplicar_icono_ventana(self)
        # La ventana recién creada devuelve a sí misma con winfo_toplevel().
        # Guardamos el padre que la abrió para bloquear solo esa ventana.
        try:
            self._modal_padre = parent.winfo_toplevel() if parent is not None else None
        except (tk.TclError, AttributeError):
            self._modal_padre = None
        self._modal_parent_bloqueado = False
        self._modal_minimizada = False

        if self._es_modal:
            self.bind("<Unmap>", self._al_minimizar_modal, add="+")
            self.bind("<Map>", self._al_restaurar_modal, add="+")
        self.protocol("WM_DELETE_WINDOW", self._cerrar_modal)

    def _cambiar_bloqueo_padre(self, bloqueado: bool) -> None:
        """Bloquea/desbloquea la Toplevel que estaba debajo del diálogo."""
        padre = self._modal_padre
        if padre is None or not padre.winfo_exists():
            self._modal_parent_bloqueado = False
            return

        if sys.platform.startswith("win"):
            # En Windows Tk expone -disabled específicamente para desactivar
            # la ventana subyacente sin tomar un grab de teclado/mouse.
            try:
                padre.attributes("-disabled", bool(bloqueado))
                self._modal_parent_bloqueado = bool(bloqueado)
            except tk.TclError:
                # No recurrimos a grab_set() en Windows: precisamente ese
                # grab es lo que puede impedir que esta Toplevel se minimice.
                self._modal_parent_bloqueado = False
            return

        if bloqueado:
            try:
                self.grab_set()
                self._modal_parent_bloqueado = True
            except tk.TclError:
                self._modal_parent_bloqueado = False
        elif self._modal_parent_bloqueado:
            try:
                self.grab_release()
            except tk.TclError:
                pass
            self._modal_parent_bloqueado = False

    def activar_modal(self) -> None:
        """Hace modal el diálogo mientras está visible, si corresponde."""
        if not self._es_modal:
            return
        if not self.winfo_exists() or self._modal_minimizada:
            return
        self._cambiar_bloqueo_padre(True)

    def _al_minimizar_modal(self, event=None) -> None:
        """Libera el bloqueo de la ventana padre cuando la Toplevel se minimiza."""
        if not self.winfo_exists():
            return
        try:
            if self.state() == "iconic":
                self._modal_minimizada = True
                self._cambiar_bloqueo_padre(False)
        except tk.TclError:
            pass

    def _al_restaurar_modal(self, event=None) -> None:
        """Vuelve a bloquear la ventana padre al restaurar la Toplevel."""
        if not self.winfo_exists():
            return
        try:
            if self.state() == "normal":
                self._modal_minimizada = False
                self.after_idle(self.activar_modal)
        except tk.TclError:
            pass

    def _cerrar_modal(self) -> None:
        self.destroy()

    def destroy(self) -> None:
        try:
            self._cambiar_bloqueo_padre(False)
        except (tk.TclError, AttributeError):
            pass
        super().destroy()


class VentanaVisualizacionMesasNumeros(VentanaModal):
    """Tablero de la ronda activa ordenado por número de jugador.

    El encabezado muestra la ronda y el temporizador compartido con la vista
    principal; la tabla central recorre las mesas automáticamente y el
    carrusel inferior presenta sus jugadores. El temporizador también puede
    abrirse en una Toplevel de pantalla completa.

    La paleta de marcador es fija y no cambia con el tema de la aplicación.
    El tablero deja activa la ventana principal, pero cubre su contenido
    durante la carga y el redimensionamiento para ocultar repintados parciales.
    """

    C_FONDO = "#1B1B1B"
    C_PANEL = "#C9D1DB"
    C_CAJA = "#555555"
    C_CARTA = "#1B1B1B"
    C_BLANCO = "#FFFFFF"
    C_TEXTO = "#111111"
    C_VS_V = "#3D5AFE"   # la "V" de VS, en azul
    C_VS_S = "#9B4DDB"   # la "S" de VS, en morado
    C_FINALIZADA = "#1E7A46"

    # Ritmos (a escala 1 = ventana de 1280x720; se escalan con el tamaño).
    VEL_TABLA = 38.0        # px/s bajando por la tabla
    VEL_RETORNO = 700.0     # px/s al volver arriba
    PAUSA_TABLA = 3.0       # s de pausa arriba y abajo
    VEL_CARRUSEL = 85.0     # px/s del carrusel (derecha -> izquierda)
    INTERVALO_MS = 33       # ~30 fps
    PAUSA_REDIMENSIONAMIENTO_MS = 500

    # En Windows, CustomTkinter puede ocultar/mostrar una Toplevel para pintar
    # su barra de título. La clase la desactiva y pinta el marco en _revelar.
    _deactivate_windows_window_header_manipulation = True

    PESOS_COLUMNAS = (2, 7, 7, 2)  # Mesa | Pareja 1 | Pareja 2 | Estado
    # Tamaños base (px a escala 1) de las fuentes.
    BASE_CTK = {"titulo": 40, "caja_tit": 14, "caja_val": 40, "enc": 15, "seccion": 16, "aviso": 18}
    BASE_TK = {"mesa": 16, "celda": 20, "estado": 18}

    def __init__(self, parent: ctk.CTkFrame, torneo_id: int) -> None:
        # El tablero no bloquea la vista principal; su overlay solo la cubre
        # durante la carga inicial o mientras termina un redimensionamiento.
        super().__init__(parent, modal=False)
        self.torneo_id = torneo_id
        self._destruida = False
        self._jobs: dict[str, str | None] = {
            "tabla": None,
            "carrusel": None,
            "resize": None,
            "overlay": None,
            "zoom_tiempo": None,
        }
        self._overlay_redimensionamiento: ctk.CTkFrame | None = None
        self._overlay_redimensionamiento_visible = False
        self._overlay_redimensionamiento_habilitado = False
        self._ventana_tiempo_completo: VentanaTemporizadorFullscreen | None = None
        self._tiempo_en_hover = False
        self._filas: list[tk.Frame] = []
        self._cartas: list[list] = []
        self._fuentes_carta: list[tkfont.Font] = []
        self._ancho_carrusel = 0
        self._es = 1.0
        self._tam_ventana = (0, 0)       # último tamaño conocido (px)
        self._tam_construido = (0, 0)    # tamaño con el que se armó el diseño por última vez
        self._revelada = False
        self._ultimo_movimiento = 0.0    # última vez que la ventana se movió/redimensionó
        self._recorrido = 0.0            # px que ha avanzado el carrusel
        self._ciclo_mesas = 0.0          # px que mide una vuelta completa de mesas

        torneo = repo.obtener_torneo(torneo_id)
        ronda_activa = repo.obtener_ronda_activa(torneo_id)
        nombre_torneo = torneo["nombre"] if torneo else f"Torneo #{torneo_id}"
        self.num_ronda = ronda_activa["numero_ronda"] if ronda_activa else None

        self.title(f"Mesas por Nº de jugador - {nombre_torneo}")
        self.minsize(900, 560)
        # Invisible mientras Tk y el sistema asientan tamaño y posición; se
        # muestra (una sola vez) cuando el diseño ya está armado.
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.after(1500, self._revelar)  # red de seguridad
        self._centrar_en_pantalla(1280, 720)
        self.configure(fg_color=self.C_FONDO)
        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()
        self.bind("<F11>", lambda _e: self._alternar_pantalla_completa())
        self.bind("<Escape>", self._al_presionar_escape)

        familia = ctk.ThemeManager.theme["CTkFont"]["family"]
        self._fc = {  # fuentes de widgets CTk (customtkinter las escala solo)
            n: ctk.CTkFont(family=familia, size=s, weight="bold" if n not in ("caja_val",) else "normal")
            for n, s in self.BASE_CTK.items()
        }
        self._ft = {  # fuentes de widgets tk / canvas (px reales)
            "mesa": tkfont.Font(root=self, family=familia, size=-16, weight="bold"),
            "celda": tkfont.Font(root=self, family=familia, size=-20),
            "estado": tkfont.Font(root=self, family=familia, size=-18, weight="bold"),
        }

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            self, text=nombre_torneo.upper(), font=self._fc["titulo"], text_color=self.C_PANEL
        ).grid(row=0, column=0, pady=(10, 6))

        if not ronda_activa:
            ctk.CTkLabel(
                self,
                text="⚠️ No hay una ronda en curso para visualizar.",
                font=self._fc["aviso"],
                text_color="#D97706",
            ).grid(row=1, column=0)
            self.after(50, self._revelar)
            return

        try:
            self.mesas = self._cargar_mesas(ronda_activa["id"], torneo_id)
        except repo.ErrorDatos as e:
            self._revelar()
            messagebox.showerror("Error al cargar mesas", str(e), parent=self)
            return

        self._construir_interfaz()
        self.temporizador = TemporizadorRonda.obtener()
        self.temporizador.suscribir(self._al_cambiar_temporizador)
        self._al_cambiar_temporizador(self.temporizador)

        self.bind("<Configure>", self._al_configurar_ventana, add="+")
        self._jobs["resize"] = self.after(
            self.PAUSA_REDIMENSIONAMIENTO_MS,
            self._al_redimensionar,
        )
        self._t_tabla = self._t_carrusel = time.monotonic()
        self._estado_tabla = "espera_arriba"
        self._espera = self.PAUSA_TABLA
        self._offset = 0.0
        self._jobs["tabla"] = self.after(self.INTERVALO_MS, self._tick_tabla)
        self._jobs["carrusel"] = self.after(self.INTERVALO_MS, self._tick_carrusel)

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------
    @staticmethod
    def _cargar_mesas(ronda_id: int, torneo_id: int) -> list[dict]:
        """Mesas de la ronda con el número de cada jugador y, si hay, su nombre."""
        numeros = [dict(m) for m in repo.listar_mesas_con_numeros_jugador(ronda_id, torneo_id)]
        try:
            nombres = {m["numero_mesa"]: dict(m) for m in repo.listar_mesas_de_ronda(ronda_id)}
        except (repo.ErrorDatos, KeyError, TypeError):
            nombres = {}
        mesas = []
        for m in sorted(numeros, key=lambda x: x["numero_mesa"]):
            datos = nombres.get(m["numero_mesa"], {})
            mesas.append({
                "numero_mesa": m["numero_mesa"],
                "estado": m["estado"],
                "jugadores": [
                    (m[f"j{i}_num"], (datos.get(f"j{i}_nom") or "").strip()) for i in range(1, 5)
                ],
            })
        return mesas

    # ------------------------------------------------------------------
    # Interfaz
    # ------------------------------------------------------------------
    def _construir_interfaz(self) -> None:
        self.panel = ctk.CTkFrame(self, fg_color=self.C_PANEL, corner_radius=36)
        self.panel.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 22))
        self.panel.grid_columnconfigure(0, weight=1)
        self.panel.grid_rowconfigure(2, weight=1)  # la tabla absorbe el espacio

        # Fila 0: ronda y tiempo
        # Las columnas laterales alojan ronda y tiempo; la columna central
        # absorbe el espacio sobrante y mantiene ambas cajas separadas.
        info = ctk.CTkFrame(self.panel, fg_color="transparent")
        info.grid(row=0, column=0, sticky="ew", padx=40, pady=(16, 6))
        info.grid_columnconfigure(0, weight=0, minsize=300)
        info.grid_columnconfigure(1, weight=1)
        info.grid_columnconfigure(2, weight=0, minsize=300)
        info.grid_rowconfigure(0, weight=0, minsize=84)
        self._info_superior = info

        self.caja_ronda = self._crear_caja(info, "RONDA", str(self.num_ronda))
        self.caja_ronda.grid(row=0, column=0, sticky="nsew")
        self.caja_tiempo = self._crear_caja(info, "TIEMPO DE LA RONDA", "--:--")
        self.caja_tiempo.grid(row=0, column=2, sticky="nsew")
        self.lbl_tiempo = self.caja_tiempo.valor
        self._font_tiempo = ctk.CTkFont(
            family=ctk.ThemeManager.theme["CTkFont"]["family"],
            size=self.BASE_CTK["caja_val"],
        )
        self.lbl_tiempo.configure(font=self._font_tiempo)
        for widget in (self.caja_tiempo, self.caja_tiempo.titulo, self.lbl_tiempo):
            widget.bind("<Enter>", self._programar_zoom_tiempo, add="+")
            widget.bind("<Leave>", self._programar_zoom_tiempo, add="+")
            widget.bind("<Button-1>", self._abrir_tiempo_completo, add="+")

        # Fila 1: encabezado de columnas
        self.encabezado = ctk.CTkFrame(self.panel, fg_color=self.C_CAJA, corner_radius=14, height=38)
        self.encabezado.grid(row=1, column=0, sticky="ew", padx=40, pady=(8, 6))
        for c, (texto, peso) in enumerate(zip(("", "PAREJA 1", "PAREJA 2", "ESTADO"), self.PESOS_COLUMNAS)):
            self.encabezado.grid_columnconfigure(c, weight=peso, uniform="col")
            ctk.CTkLabel(
                self.encabezado, text=texto, font=self._fc["enc"], text_color=self.C_BLANCO
            ).grid(row=0, column=c, pady=6)

        # Fila 2: tabla con desplazamiento automático
        self.canvas_tabla = tk.Canvas(self.panel, bg=self.C_PANEL, highlightthickness=0, bd=0)
        self.canvas_tabla.grid(row=2, column=0, sticky="nsew", padx=40)
        self.filas_frame = tk.Frame(self.canvas_tabla, bg="#000000")
        self._ventana_filas = self.canvas_tabla.create_window(0, 0, anchor="nw", window=self.filas_frame)
        self.canvas_tabla.bind("<Configure>", self._al_configurar_tabla)
        if not self.mesas:
            tk.Label(
                self.filas_frame, text="No hay mesas en esta ronda.", bg=self.C_PANEL,
                fg=self.C_TEXTO, font=self._ft["celda"],
            ).pack(fill="x", pady=20)
        for m in self.mesas:
            self._crear_fila(m)

        # Filas 3 y 4: emparejamiento (carrusel)
        ctk.CTkLabel(
            self.panel, text="EMPAREJAMIENTO", font=self._fc["seccion"], text_color=self.C_TEXTO
        ).grid(row=3, column=0, pady=(10, 4))
        banda = ctk.CTkFrame(self.panel, fg_color=self.C_CAJA, corner_radius=20)
        banda.grid(row=4, column=0, sticky="ew", padx=32, pady=(0, 18))
        banda.grid_columnconfigure(0, weight=1)
        self.canvas_carrusel = tk.Canvas(banda, bg=self.C_CAJA, highlightthickness=0, bd=0, height=150)
        self.canvas_carrusel.grid(row=0, column=0, sticky="ew", padx=14, pady=12)

    def _crear_caja(self, padre, titulo: str, valor: str) -> ctk.CTkFrame:
        caja = ctk.CTkFrame(padre, fg_color=self.C_CAJA, corner_radius=16, width=300, height=84)
        caja.grid_propagate(False)
        caja.grid_columnconfigure(0, weight=1)
        caja.grid_rowconfigure(0, weight=0)
        caja.grid_rowconfigure(1, weight=1)

        # El contenido se centra mediante grid dentro de la caja; así el número
        # queda siempre centrado sin alterar el tamaño ni la separación exterior.
        caja.titulo = ctk.CTkLabel(
            caja,
            text=titulo,
            font=self._fc["caja_tit"],
            text_color=self.C_PANEL,
            anchor="center",
            justify="center",
        )
        caja.titulo.grid(row=0, column=0, sticky="ew", padx=4, pady=(8, 0))

        caja.valor = ctk.CTkLabel(
            caja,
            text=valor,
            font=self._fc["caja_val"],
            text_color=self.C_BLANCO,
            anchor="center",
            justify="center",
        )
        caja.valor.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        return caja

    def _crear_fila(self, mesa: dict) -> None:
        fila = tk.Frame(self.filas_frame, bg="#000000", height=66)
        fila.pack(fill="x")
        fila.grid_propagate(False)
        fila.grid_rowconfigure(0, weight=1)
        for c, peso in enumerate(self.PESOS_COLUMNAS):
            fila.grid_columnconfigure(c, weight=peso, uniform="fila")
        nums = [n for n, _nombre in mesa["jugadores"]]

        tk.Label(
            fila, text=f"MESA {mesa['numero_mesa']}", bg=self.C_CAJA, fg=self.C_BLANCO, font=self._ft["mesa"]
        ).grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        for col, (a, b) in ((1, (nums[0], nums[1])), (2, (nums[2], nums[3]))):
            celda = tk.Frame(fila, bg=self.C_PANEL)
            celda.grid(row=0, column=col, sticky="nsew", padx=1, pady=1)
            celda.grid_rowconfigure(0, weight=1)
            for i, n in enumerate((a, b)):
                celda.grid_columnconfigure(i, weight=1, uniform="jug")
                tk.Label(
                    celda, text=f"Jugador {n}", bg=self.C_PANEL, fg=self.C_TEXTO, font=self._ft["celda"]
                ).grid(row=0, column=i, sticky="nsew")
        finalizada = mesa["estado"] == "finalizada"
        tk.Label(
            fila,
            text="Finalizada" if finalizada else "En juego",
            bg=self.C_PANEL,
            fg=self.C_FINALIZADA if finalizada else self.C_TEXTO,
            font=self._ft["estado"],
        ).grid(row=0, column=3, sticky="nsew", padx=1, pady=1)
        self._filas.append(fila)

    # ------------------------------------------------------------------
    # Tamaño / escala
    # ------------------------------------------------------------------
    def _escala_ventana(self) -> float:
        try:
            return float(self._get_window_scaling())
        except Exception:
            return 1.0

    def _centrar_en_pantalla(self, ancho: int, alto: int) -> None:
        """Abre la ventana centrada en la pantalla (y sin salirse de ella)."""
        ws = self._escala_ventana()
        pantalla_w, pantalla_h = self.winfo_screenwidth(), self.winfo_screenheight()
        ancho = min(ancho, int(pantalla_w * 0.92 / ws))
        alto = min(alto, int(pantalla_h * 0.88 / ws))
        x = max(0, (pantalla_w - round(ancho * ws)) // 2)
        # Un poco por encima del centro exacto: compensa la barra de título y
        # la barra de tareas para que se vea centrada.
        y = max(0, (pantalla_h - round(alto * ws)) // 2 - 30)
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

    def _en_movimiento(self) -> bool:
        """True mientras la ventana se está arrastrando o redimensionando."""
        return (
            time.monotonic() - self._ultimo_movimiento
            < self.PAUSA_REDIMENSIONAMIENTO_MS / 1000
        )

    def _al_configurar_ventana(self, event) -> None:
        if event.widget is not self or self._destruida:
            return
        # Tk envía <Configure> al mover y al redimensionar. El cambio de tamaño
        # activa un único callback diferido; _al_redimensionar espera a que el
        # gesto termine antes de recalcular fuentes, filas y carrusel.
        self._ultimo_movimiento = time.monotonic()
        tam = (event.width, event.height)
        if tam == self._tam_ventana:
            return
        self._tam_ventana = tam
        ventana_tiempo = self._ventana_tiempo_completo
        if ventana_tiempo is not None and ventana_tiempo.winfo_exists():
            return
        if self._overlay_redimensionamiento_habilitado:
            self._mostrar_overlay_redimensionamiento()
        if self._jobs["resize"] is None:
            self._jobs["resize"] = self.after(
                self.PAUSA_REDIMENSIONAMIENTO_MS,
                self._al_redimensionar,
            )

    def _al_redimensionar(self) -> None:
        """Recalcula una sola vez el diseño cuando termina el cambio de tamaño."""
        self._jobs["resize"] = None
        if self._destruida or not self.winfo_exists():
            return
        tiempo_sin_movimiento = time.monotonic() - self._ultimo_movimiento
        pausa_restante = self.PAUSA_REDIMENSIONAMIENTO_MS / 1000 - tiempo_sin_movimiento
        if pausa_restante > 0:
            self._jobs["resize"] = self.after(
                max(1, math.ceil(pausa_restante * 1000)),
                self._al_redimensionar,
            )
            return
        tam = (self.winfo_width(), self.winfo_height())
        try:
            if self.state() == "iconic":  # minimizada: se rehará al restaurar
                self._ocultar_overlay_redimensionamiento()
                return
        except tk.TclError:
            self._ocultar_overlay_redimensionamiento()
            return
        if tam[0] < 200 or tam[1] < 200:  # aún sin su tamaño definitivo: reintenta
            self._jobs["resize"] = self.after(100, self._al_redimensionar)
            return
        self._tam_ventana = tam
        if tam == self._tam_construido:  # nada cambió desde el último armado
            self._revelar()
            self._ocultar_overlay_redimensionamiento()
            return
        self._tam_construido = tam
        ws = self._escala_ventana()
        ancho = max(self.winfo_width(), 1) / ws
        alto = max(self.winfo_height(), 1) / ws
        # Se guarda cuánto ha avanzado la tabla para no saltar al re-escalar.
        maximo_previo = max(getattr(self, "_alto_total", 0) - self.canvas_tabla.winfo_height(), 0)
        fraccion_tabla = self._offset / maximo_previo if maximo_previo > 1 else 0.0
        self._es = max(0.6, min(ancho / 1280, alto / 720, 3.0))
        es = self._es
        for nombre, base in self.BASE_CTK.items():
            self._fc[nombre].configure(size=max(8, int(base * es)))
        for nombre, base in self.BASE_TK.items():
            self._ft[nombre].configure(size=-max(8, int(base * es * ws)))
        self._alto_fila = max(30, int(66 * es * ws))
        for fila in self._filas:
            fila.configure(height=self._alto_fila)
        ancho_caja = max(180, int(300 * es))
        alto_caja = max(60, int(84 * es))
        radio_caja = max(8, min(int(16 * es), ancho_caja // 2, alto_caja // 2))
        for caja in (self.caja_ronda, self.caja_tiempo):
            caja.configure(
                width=ancho_caja,
                height=alto_caja,
                corner_radius=radio_caja,
            )
        # Mantiene visibles las cajas completas al escalar: las columnas que las
        # contienen crecen junto con ellas, mientras la columna central conserva
        # la separación original.
        if hasattr(self, "_info_superior"):
            self._info_superior.grid_columnconfigure(0, minsize=ancho_caja)
            self._info_superior.grid_columnconfigure(2, minsize=ancho_caja)
            self._info_superior.grid_rowconfigure(0, minsize=alto_caja)
        self._actualizar_zoom_tiempo()
        self.encabezado.configure(height=int(38 * es))
        self.canvas_carrusel.configure(height=max(90, int(150 * es * ws)))
        self.update_idletasks()
        self._actualizar_region_tabla()
        maximo = max(self._alto_total - self.canvas_tabla.winfo_height(), 0)
        self._offset = fraccion_tabla * maximo
        self._construir_carrusel()
        self._revelar()
        self._ocultar_overlay_redimensionamiento()

    def _mostrar_overlay_redimensionamiento(self) -> None:
        """Cubre la vista principal durante el redimensionamiento del tablero."""
        padre = self._modal_padre
        if padre is None or not padre.winfo_exists():
            return
        overlay = self._overlay_redimensionamiento
        if overlay is None or not overlay.winfo_exists():
            overlay = ctk.CTkFrame(
                padre,
                fg_color=COLOR_FONDO_VENTANA,
                corner_radius=0,
            )
            ctk.CTkLabel(
                overlay,
                text="Redimensionando, un momento...",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color=("gray30", "gray80"),
            ).place(relx=0.5, rely=0.5, anchor="center")
            self._overlay_redimensionamiento = overlay
        if self._overlay_redimensionamiento_visible:
            return
        overlay.place(x=0, y=0, relwidth=1, relheight=1)
        overlay.lift()
        self._overlay_redimensionamiento_visible = True
        self._jobs["overlay"] = self.after(
            self.PAUSA_REDIMENSIONAMIENTO_MS,
            self._verificar_overlay_redimensionamiento,
        )

    def habilitar_overlay_redimensionamiento(self) -> None:
        """Habilita la cubierta tras retirar el overlay de carga inicial."""
        self._overlay_redimensionamiento_habilitado = True

    def _verificar_overlay_redimensionamiento(self) -> None:
        self._jobs["overlay"] = None
        if self._destruida or not self.winfo_exists():
            return
        if self._en_movimiento():
            self._jobs["overlay"] = self.after(
                self.PAUSA_REDIMENSIONAMIENTO_MS,
                self._verificar_overlay_redimensionamiento,
            )
            return
        self._ocultar_overlay_redimensionamiento()

    def _ocultar_overlay_redimensionamiento(self) -> None:
        if self._jobs["overlay"] is not None:
            try:
                self.after_cancel(self._jobs["overlay"])
            except (tk.TclError, ValueError):
                pass
        self._jobs["overlay"] = None
        overlay = self._overlay_redimensionamiento
        if self._overlay_redimensionamiento_visible and overlay is not None and overlay.winfo_exists():
            overlay.place_forget()
        self._overlay_redimensionamiento_visible = False

    def _revelar(self) -> None:
        """Muestra la ventana (una sola vez) cuando ya está lista."""
        if self._revelada or self._destruida or not self.winfo_exists():
            return
        self._revelada = True
        _pintar_barra_titulo_windows(self, "dark")  # la paleta de esta pantalla es fija
        try:
            self.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        self.lift()
        self.focus_force()

    def _al_configurar_tabla(self, event) -> None:
        self.canvas_tabla.itemconfigure(self._ventana_filas, width=event.width)
        self._actualizar_region_tabla()

    def _actualizar_region_tabla(self) -> None:
        n = max(len(self._filas), 1)
        self._alto_total = n * getattr(self, "_alto_fila", 66)
        ancho = max(self.canvas_tabla.winfo_width(), 1)
        self.canvas_tabla.configure(scrollregion=(0, 0, ancho, self._alto_total))

    def _alternar_pantalla_completa(self) -> None:
        try:
            self.attributes("-fullscreen", not bool(self.attributes("-fullscreen")))
        except tk.TclError:
            pass

    def _programar_zoom_tiempo(self, _event=None) -> None:
        job = self._jobs["zoom_tiempo"]
        if job is not None:
            self.after_cancel(job)
        self._jobs["zoom_tiempo"] = self.after_idle(self._actualizar_hover_tiempo)

    def _actualizar_hover_tiempo(self) -> None:
        self._jobs["zoom_tiempo"] = None
        if self._destruida or not self.winfo_exists():
            return
        x, y = self.winfo_pointerxy()
        caja = self.caja_tiempo
        dentro = (
            caja.winfo_rootx() <= x < caja.winfo_rootx() + caja.winfo_width()
            and caja.winfo_rooty() <= y < caja.winfo_rooty() + caja.winfo_height()
        )
        if dentro != self._tiempo_en_hover:
            self._tiempo_en_hover = dentro
            self._actualizar_zoom_tiempo()

    def _actualizar_zoom_tiempo(self) -> None:
        if not hasattr(self, "lbl_tiempo"):
            return
        factor = 1.35 if self._tiempo_en_hover else 1.0
        factor_caja = 1.25 if self._tiempo_en_hover else 1.0
        self._font_tiempo.configure(
            size=max(8, int(self.BASE_CTK["caja_val"] * self._es * factor))
        )
        ancho_caja = max(180, int(300 * self._es * factor_caja))
        alto_caja = max(60, int(84 * self._es * factor_caja))
        self.caja_tiempo.configure(
            width=ancho_caja,
            height=alto_caja,
            corner_radius=max(8, min(int(16 * self._es), ancho_caja // 2, alto_caja // 2)),
        )
        self._info_superior.grid_columnconfigure(2, minsize=ancho_caja)
        self._info_superior.grid_rowconfigure(0, minsize=alto_caja)

    def _abrir_tiempo_completo(self, _event=None) -> str:
        ventana = self._ventana_tiempo_completo
        if ventana is None or not ventana.winfo_exists():
            self._ventana_tiempo_completo = VentanaTemporizadorFullscreen(
                self,
                self.temporizador,
            )
        return "break"

    def _al_presionar_escape(self, _event=None) -> str:
        self._cerrar_modal()
        return "break"

    # ------------------------------------------------------------------
    # Tabla: se desliza sola hacia abajo y vuelve arriba
    # ------------------------------------------------------------------
    def _tick_tabla(self) -> None:
        if self._destruida:
            return
        ahora = time.monotonic()
        dt = min(ahora - self._t_tabla, 0.1)
        self._t_tabla = ahora
        if self._en_movimiento():  # ventana en movimiento: animación en pausa
            self._jobs["tabla"] = self.after(self.INTERVALO_MS, self._tick_tabla)
            return
        try:
            visible = self.canvas_tabla.winfo_height()
            total = getattr(self, "_alto_total", 0)
            maximo = max(0.0, total - visible)
            if maximo <= 1:  # todas las mesas caben: no hace falta desplazar
                self._offset = 0.0
                self._estado_tabla = "espera_arriba"
                self._espera = self.PAUSA_TABLA
            else:
                ws = self._escala_ventana()
                if self._estado_tabla in ("espera_arriba", "espera_abajo"):
                    self._espera -= dt
                    if self._espera <= 0:
                        self._estado_tabla = "bajando" if self._estado_tabla == "espera_arriba" else "subiendo"
                elif self._estado_tabla == "bajando":
                    self._offset += self.VEL_TABLA * self._es * ws * dt
                    if self._offset >= maximo:
                        self._offset = maximo
                        self._estado_tabla = "espera_abajo"
                        self._espera = self.PAUSA_TABLA
                else:  # subiendo
                    self._offset -= self.VEL_RETORNO * self._es * ws * dt
                    if self._offset <= 0:
                        self._offset = 0.0
                        self._estado_tabla = "espera_arriba"
                        self._espera = self.PAUSA_TABLA
            self.canvas_tabla.yview_moveto(self._offset / total if total else 0.0)
            self._jobs["tabla"] = self.after(self.INTERVALO_MS, self._tick_tabla)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Carrusel de emparejamientos: rota de derecha a izquierda
    # ------------------------------------------------------------------
    @staticmethod
    def _rect_redondeado(c: tk.Canvas, x1, y1, x2, y2, r, **kw) -> int:
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return c.create_polygon(pts, smooth=True, **kw)

    @staticmethod
    def _recortar(texto: str, fuente: tkfont.Font, ancho: float) -> str:
        if fuente.measure(texto) <= ancho:
            return texto
        while texto and fuente.measure(texto + "…") > ancho:
            texto = texto[:-1]
        return texto.rstrip() + "…"

    def _construir_carrusel(self) -> None:
        c = self.canvas_carrusel
        c.delete("all")
        self._cartas = []
        vw, vh = c.winfo_width(), c.winfo_height()
        if vw < 100 or vh < 60 or not self.mesas:
            return
        familia = ctk.ThemeManager.theme["CTkFont"]["family"]
        hueco = int(vw * 0.03)
        card_w = int((vw - 3 * hueco) / 2)  # dos tarjetas visibles a la vez
        card_h = int(vh * 0.90)
        y0 = (vh - card_h) // 2
        f_titulo = tkfont.Font(root=self, family=familia, size=-max(10, int(card_h * 0.15)), weight="bold")
        f_nombre = tkfont.Font(root=self, family=familia, size=-max(9, int(card_h * 0.125)))
        f_vs = tkfont.Font(root=self, family=familia, size=-max(14, int(card_h * 0.30)), weight="bold")
        self._fuentes_carta = [f_titulo, f_nombre, f_vs]  # evita que se liberen

        n = len(self.mesas)
        ciclo = card_w + hueco
        copias = math.ceil((vw + card_w + hueco) / (n * ciclo)) + 1
        self._largo_ciclo = n * copias * ciclo
        self._ancho_carta = card_w
        # Conserva el punto de la rotación en el que iba (como fracción de una
        # vuelta de todas las mesas) para que re-escalar no lo reinicie.
        fraccion = (self._recorrido % self._ciclo_mesas) / self._ciclo_mesas if self._ciclo_mesas else 0.0
        self._ciclo_mesas = float(n * ciclo)
        self._recorrido = fraccion * self._ciclo_mesas
        for k in range(n * copias):
            x = hueco + k * ciclo - self._recorrido
            if x + card_w < 0:  # ya habría salido por la izquierda: entra por la derecha
                x += self._largo_ciclo
            tag = f"carta{k}"
            self._dibujar_carta(c, self.mesas[k % n], x, y0, card_w, card_h, tag, f_titulo, f_nombre, f_vs)
            self._cartas.append([float(x), tag])

    def _dibujar_carta(self, c, mesa, x, y, w, h, tag, f_titulo, f_nombre, f_vs) -> None:
        tags = (tag, "carrusel")
        self._rect_redondeado(c, x, y, x + w, y + h, h * 0.16, fill=self.C_CARTA, outline="", tags=tags)
        c.create_text(x + w / 2, y + h * 0.17, text=f"MESA {mesa['numero_mesa']}",
                      fill=self.C_BLANCO, font=f_titulo, tags=tags)
        jugadores = mesa["jugadores"]
        columnas = ((x + w * 0.05, w * 0.36, jugadores[0:2]), (x + w * 0.60, w * 0.36, jugadores[2:4]))
        for x_txt, ancho_max, par in columnas:
            for i, (num, nombre) in enumerate(par):
                texto = self._recortar(f"J{num} {nombre}".strip(), f_nombre, ancho_max)
                c.create_text(x_txt, y + h * (0.47 + 0.27 * i), text=texto, anchor="w",
                              fill=self.C_BLANCO, font=f_nombre, tags=tags)
        ancho_v = f_vs.measure("V")
        inicio = x + w * 0.50 - (ancho_v + f_vs.measure("S")) / 2
        c.create_text(inicio, y + h * 0.60, text="V", anchor="w", fill=self.C_VS_V, font=f_vs, tags=tags)
        c.create_text(inicio + ancho_v, y + h * 0.60, text="S", anchor="w", fill=self.C_VS_S, font=f_vs, tags=tags)

    def _tick_carrusel(self) -> None:
        if self._destruida:
            return
        ahora = time.monotonic()
        dt = min(ahora - self._t_carrusel, 0.1)
        self._t_carrusel = ahora
        if self._en_movimiento():  # ventana en movimiento: animación en pausa
            self._jobs["carrusel"] = self.after(self.INTERVALO_MS, self._tick_carrusel)
            return
        try:
            if self._cartas:
                c = self.canvas_carrusel
                dx = self.VEL_CARRUSEL * self._es * self._escala_ventana() * dt
                self._recorrido += dx
                c.move("carrusel", -dx, 0)
                for carta in self._cartas:
                    carta[0] -= dx
                    if carta[0] + self._ancho_carta < 0:  # salió por la izquierda: vuelve por la derecha
                        c.move(carta[1], self._largo_ciclo, 0)
                        carta[0] += self._largo_ciclo
            self._jobs["carrusel"] = self.after(self.INTERVALO_MS, self._tick_carrusel)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Temporizador (compartido con la vista En vivo)
    # ------------------------------------------------------------------
    def _al_cambiar_temporizador(self, t: TemporizadorRonda) -> None:
        if self._destruida or not self.winfo_exists():
            return
        if t.estado == "finalizado":
            color = "#FF4000"
        elif t.estado == "corriendo" and t.restante <= TemporizadorRonda.ADVERTENCIA_SEGUNDOS:
            color = "#FF8000"
        else:
            color = self.C_BLANCO
        self.lbl_tiempo.configure(text=TemporizadorRonda.formatear(t.restante), text_color=color)

    def destroy(self) -> None:
        self._destruida = True
        ventana_tiempo = self._ventana_tiempo_completo
        self._ventana_tiempo_completo = None
        if ventana_tiempo is not None and ventana_tiempo.winfo_exists():
            ventana_tiempo.destroy()
        for job in self._jobs.values():
            if job is not None:
                try:
                    self.after_cancel(job)
                except (tk.TclError, ValueError):
                    pass
        overlay = self._overlay_redimensionamiento
        if overlay is not None and overlay.winfo_exists():
            overlay.destroy()
        self._overlay_redimensionamiento = None
        temporizador = getattr(self, "temporizador", None)
        if temporizador is not None:
            temporizador.desuscribir(self._al_cambiar_temporizador)
        super().destroy()


class VentanaTemporizadorFullscreen(VentanaModal):
    """Ventana independiente de pantalla completa para proyectar el reloj.

    Cubre por completo el monitor donde está la ventana de mesas (sin bordes,
    encima de todo) y la fuente del reloj se recalcula para ocupar el ancho y
    el alto disponibles, sea cual sea la resolución o la proporción.
    """

    # Evita el withdraw/deiconify de CTkToplevel en Windows (~200 ms).
    _deactivate_windows_window_header_manipulation = True

    def __init__(
        self,
        parent: VentanaVisualizacionMesasNumeros,
        temporizador: TemporizadorRonda,
    ) -> None:
        super().__init__(parent, modal=False)
        self.withdraw()  # invisible hasta que esté lista y a tamaño completo
        self.temporizador = temporizador
        self._destruida = False
        self._tam_fuente = 0
        self._parent_ref = parent
        self.title("Temporizador de ronda")
        self.configure(fg_color=VentanaVisualizacionMesasNumeros.C_CAJA)
        self.bind("<Escape>", self._cerrar_con_escape)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            self,
            text="TIEMPO DE LA RONDA",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=VentanaVisualizacionMesasNumeros.C_PANEL,
        ).grid(row=0, column=0, sticky="n", pady=(40, 0))

        self._fuente_tiempo = ctk.CTkFont(size=96, weight="bold")
        # Fuente auxiliar (sin escalado) solo para medir el ancho del texto.
        self._fuente_medida = tkfont.Font(
            family=self._fuente_tiempo.cget("family"), size=-100, weight="bold"
        )
        self.lbl_tiempo = ctk.CTkLabel(
            self,
            text="--:--",
            font=self._fuente_tiempo,
            text_color=VentanaVisualizacionMesasNumeros.C_BLANCO,
        )
        self.lbl_tiempo.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        ctk.CTkLabel(
            self,
            text="Pulsa Esc para volver",
            font=ctk.CTkFont(size=18),
            text_color=VentanaVisualizacionMesasNumeros.C_PANEL,
        ).grid(row=2, column=0, sticky="s", pady=(0, 30))

        # Cada vez que cambie el tamaño de la ventana se reajusta la fuente.
        self.bind("<Configure>", self._ajustar_fuente_tiempo, add="+")

        self.temporizador.suscribir(self._al_cambiar_temporizador)
        self._al_cambiar_temporizador(self.temporizador)

        self._cubrir_monitor()  # un único paso: se muestra ya a pantalla completa

    # ------------------------------------------------------------------
    # Pantalla completa
    # ------------------------------------------------------------------
    def _rect_monitor_del_padre(self) -> tuple[int, int, int, int]:
        """(x, y, ancho, alto) en píxeles reales del monitor donde está la
        ventana de mesas; si no se puede saber, la pantalla principal."""
        padre = getattr(self, "_parent_ref", None)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if sys.platform.startswith("win") and padre is not None:
            try:
                import ctypes
                from ctypes import wintypes

                class MONITORINFO(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD),
                    ]

                user32 = ctypes.windll.user32
                user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
                user32.MonitorFromPoint.restype = ctypes.c_void_p
                user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
                user32.GetMonitorInfoW.restype = wintypes.BOOL

                cx = padre.winfo_rootx() + padre.winfo_width() // 2
                cy = padre.winfo_rooty() + padre.winfo_height() // 2
                hmon = user32.MonitorFromPoint(wintypes.POINT(cx, cy), 2)  # nearest
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                    r = info.rcMonitor
                    return r.left, r.top, r.right - r.left, r.bottom - r.top
            except Exception:
                pass
        return 0, 0, sw, sh

    def _cubrir_monitor(self) -> None:
        """Pantalla completa 'manual': sin bordes y ocupando todo el monitor.

        Se hace una sola vez y con la ventana oculta; así no hay parpadeos.
        """
        if self._destruida or not self.winfo_exists():
            return
        x, y, ancho, alto = self._rect_monitor_del_padre()
        try:
            self.overrideredirect(True)
            # tk.Wm.geometry evita el escalado de CustomTkinter: son píxeles reales.
            tk.Wm.geometry(self, f"{ancho}x{alto}+{x}+{y}")
            # La fuente se calcula con el tamaño final ANTES de mostrar la ventana.
            self._ajustar_fuente_tiempo(dims_reales=(ancho, alto))
            self.update_idletasks()
            self.deiconify()
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Fuente adaptable
    # ------------------------------------------------------------------
    def _ajustar_fuente_tiempo(self, event=None, dims_reales=None) -> None:
        """Calcula el mayor tamaño de fuente que cabe en ancho y en alto."""
        if self._destruida or not self.winfo_exists():
            return
        if event is not None and event.widget is not self:
            return
        try:
            escala = float(self._get_window_scaling())
        except Exception:
            escala = 1.0
        if dims_reales is not None:
            ancho, alto = dims_reales[0] / escala, dims_reales[1] / escala
        else:
            ancho = self.winfo_width() / escala
            alto = self.winfo_height() / escala
        if ancho < 200 or alto < 150:  # todavía sin tamaño real
            return
        texto = self.lbl_tiempo.cget("text") or "00:00"
        ratio = max(self._fuente_medida.measure(texto) / 100, 0.5)  # ancho por px de fuente
        tam = max(48, int(min(alto * 0.50, ancho * 0.92 / ratio)))
        if tam != self._tam_fuente:
            self._tam_fuente = tam
            self._fuente_tiempo.configure(size=tam)

    def _cerrar_con_escape(self, _event=None) -> str:
        self.destroy()
        return "break"

    def _al_cambiar_temporizador(self, temporizador: TemporizadorRonda) -> None:
        if self._destruida or not self.winfo_exists():
            return
        if temporizador.estado == "finalizado":
            color = "#FF4000"
        elif (
            temporizador.estado == "corriendo"
            and temporizador.restante <= TemporizadorRonda.ADVERTENCIA_SEGUNDOS
        ):
            color = "#FF8000"
        else:
            color = VentanaVisualizacionMesasNumeros.C_BLANCO
        self.lbl_tiempo.configure(
            text=TemporizadorRonda.formatear(temporizador.restante),
            text_color=color,
        )
        # El texto puede pasar de "mm:ss" a "h:mm:ss"; se reajusta el ancho.
        self._ajustar_fuente_tiempo()

    def destroy(self) -> None:
        if self._destruida:
            return
        self._destruida = True
        self.temporizador.desuscribir(self._al_cambiar_temporizador)
        parent = getattr(self, "_modal_padre", None)
        if (
            parent is not None
            and parent.winfo_exists()
            and getattr(parent, "_ventana_tiempo_completo", None) is self
        ):
            parent._ventana_tiempo_completo = None
        super().destroy()


class VentanaRankingClub(VentanaModal):
    def __init__(self, parent: ctk.CTkFrame, torneo_id: int) -> None:
        super().__init__(parent)
        self.torneo_id = torneo_id
        self.map_clubes: dict[str, int] = {}

        self.title("Ranking por club")
        self.geometry("820x500")
        self.minsize(700, 400)
        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(
            self,
            text="🏛 Ranking de participantes por club",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(15, 8))

        filtro = ctk.CTkFrame(self, fg_color="transparent")
        filtro.pack(fill="x", padx=15, pady=(0, 8))
        ctk.CTkLabel(filtro, text="Club:").pack(side="left", padx=(0, 8))
        self.combo_clubes = ctk.CTkComboBox(
            filtro,
            values=["No hay clubes con jugadores"],
            state="readonly",
            width=300,
            command=lambda _valor: self.cargar_ranking(),
        )
        self.combo_clubes.pack(side="left")

        ctk.CTkLabel(filtro, text="Sexo:").pack(side="left", padx=(20, 8))
        self.combo_sexo = ctk.CTkComboBox(
            filtro,
            values=["General", "Hombres", "Mujeres"],
            state="readonly",
            width=140,
            command=lambda _valor: self.cargar_ranking(),
        )
        self.combo_sexo.set("General")
        self.combo_sexo.pack(side="left")

        tabla_frame = ctk.CTkFrame(self)
        tabla_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)
        columnas = ("pos", "cedula", "nombre", "pg", "pp", "ef", "pf")
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings")
        encabezados = {
            "pos": "Pos", "cedula": "Cédula", "nombre": "Nombre",
            "pg": "PG", "pp": "PP", "ef": "EF (Dif)", "pf": "PF",
        }
        for columna, texto in encabezados.items():
            self.tabla.heading(columna, text=texto)
        for columna, ancho in {
            "pos": 50, "cedula": 120, "nombre": 250,
            "pg": 60, "pp": 60, "ef": 80, "pf": 80,
        }.items():
            self.tabla.column(columna, width=ancho, anchor="center" if columna != "nombre" else "w")
        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        self.cargar_clubes()

    def cargar_clubes(self) -> None:
        # EXISTS filtra los clubes sin jugadores en una sola consulta y evita
        # repetir una consulta individual por cada club.
        for club in repo.listar_clubes_con_jugadores():
            etiqueta = f"{club['nombre']} (ID: {club['id']})"
            self.map_clubes[etiqueta] = club["id"]
        opciones = list(self.map_clubes)
        if not opciones:
            self.combo_clubes.configure(values=["No hay clubes con jugadores"])
            self.combo_clubes.set("No hay clubes con jugadores")
            messagebox.showinfo(
                "Ranking por club",
                "No hay clubes con jugadores asignados para visualizar.",
                parent=self,
            )
            return
        self.combo_clubes.configure(values=opciones)
        self.combo_clubes.set(opciones[0])
        self.cargar_ranking()

    def cargar_ranking(self) -> None:
        _limpiar_treeview(self.tabla)
        club_id = self.map_clubes.get(self.combo_clubes.get())
        if club_id is None:
            return
        sexo = {"Hombres": "M", "Mujeres": "F"}.get(self.combo_sexo.get())
        ranking = repo.obtener_ranking_torneo(
            self.torneo_id,
            sexo=sexo,
            club_id=club_id,
        )
        for posicion, jugador in enumerate(ranking, 1):
            self.tabla.insert("", "end", values=(
                posicion, jugador["cedula"], jugador["nombre"],
                jugador["pg"], jugador["pp"], jugador["ef"], jugador["pf"],
            ))


class VentanaEditarClub(VentanaModal):
    def __init__(self, parent: ctk.CTkFrame, club_id: int, al_guardar: callable) -> None:
        super().__init__(parent)
        raw_club = repo.obtener_club(club_id)
        if not raw_club:
            messagebox.showerror("Error", "No se encontró la información del club.")
            self.destroy()
            return

        club = dict(raw_club)
        self.club_id = club_id
        self.al_guardar = al_guardar

        self.title("Editar club")
        self.geometry("380x220")
        self.resizable(False, False)

        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(self, text="✏️ Editar club", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 10))
        ctk.CTkLabel(self, text="Nombre del club:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(5, 2))

        self.ent_nombre = ctk.CTkEntry(self, placeholder_text="Nombre del club")
        self.ent_nombre.insert(0, str(club.get("nombre", "") or ""))
        self.ent_nombre.pack(fill="x", padx=20, pady=(0, 15))
        enlazar_enter_formulario(self.ent_nombre, accion_final=self.guardar)

        btn_guardar = BotonDegradado(self, text="💾 Guardar cambios", font=ctk.CTkFont(weight="bold"), height=35, command=self.guardar)
        btn_guardar.pack(fill="x", padx=20, pady=5)

    def guardar(self) -> None:
        nuevo_nombre = self.ent_nombre.get().strip()
        if not nuevo_nombre:
            messagebox.showwarning("Atención", "El nombre del club no puede estar vacío.")
            return
        try:
            repo.editar_club(self.club_id, nombre=nuevo_nombre)
            messagebox.showinfo("Éxito", "Club actualizado correctamente.")
            self.al_guardar()
            self.destroy()
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))


class VentanaEditarJugador(VentanaModal):
    def __init__(self, parent: ctk.CTkFrame, cedula_actual: str, al_guardar: callable) -> None:
        super().__init__(parent)
        raw_jugador = repo.obtener_jugador(cedula_actual)
        if not raw_jugador:
            messagebox.showerror("Error", "No se encontró la información del jugador seleccionado.")
            self.destroy()
            return

        jugador = dict(raw_jugador)
        self.cedula_actual = cedula_actual
        self.al_guardar = al_guardar

        self.title("Editar jugador")
        self.geometry("400x320")
        self.resizable(False, False)

        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(self, text="Editar jugador", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=15)

        ctk.CTkLabel(self, text="Cédula:").pack(padx=20, anchor="w")
        self.ent_cedula = ctk.CTkEntry(self)
        self.ent_cedula.insert(0, jugador.get("cedula", ""))
        self.ent_cedula.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Nombre completo:").pack(padx=20, anchor="w")
        self.ent_nombre = ctk.CTkEntry(self)
        self.ent_nombre.insert(0, jugador.get("nombre", ""))
        self.ent_nombre.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Sexo:").pack(padx=20, anchor="w")
        self.combo_sexo = ctk.CTkComboBox(self, values=["M", "F"], state="readonly")
        self.combo_sexo.set(jugador.get("sexo", "M"))
        self.combo_sexo.pack(fill="x", padx=20, pady=(0, 15))
        enlazar_enter_formulario(
            self.ent_cedula,
            self.ent_nombre,
            self.combo_sexo,
            accion_final=self.guardar,
        )

        btn_guardar = BotonDegradado(self, text="💾 Guardar cambios", command=self.guardar)
        btn_guardar.pack(fill="x", padx=20, pady=5)

    def guardar(self) -> None:
        nueva_cedula = self.ent_cedula.get().strip()
        nuevo_nombre = self.ent_nombre.get().strip()
        nuevo_sexo = self.combo_sexo.get().strip()

        try:
            repo.editar_jugador(
                self.cedula_actual,
                nombre=nuevo_nombre or None,
                sexo=nuevo_sexo or None,
                nueva_cedula=nueva_cedula or None,
            )
            messagebox.showinfo("Éxito", "Jugador actualizado correctamente.")
            self.al_guardar()
            self.destroy()
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))


class VentanaHistorialJugador(VentanaModal):
    def __init__(self, parent: ctk.CTkFrame, cedula: str) -> None:
        super().__init__(parent)
        raw_jugador = repo.obtener_jugador(cedula)
        if not raw_jugador:
            messagebox.showerror("Error", "No se encontró el registro del jugador.")
            self.destroy()
            return

        jugador = dict(raw_jugador)
        self.title(f"Historial - {jugador.get('nombre', '')}")
        self.geometry("650x400")

        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(self, text=f"Historial de cambios: {jugador.get('nombre', '')} ({cedula})", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=15)

        tabla_frame = ctk.CTkFrame(self)
        tabla_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        columnas = ("fecha_hora", "accion", "detalle")
        tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings")
        tabla.heading("fecha_hora", text="Fecha / hora")
        tabla.heading("accion", text="Acción")
        tabla.heading("detalle", text="Detalle")

        tabla.column("fecha_hora", width=150)
        tabla.column("accion", width=120)
        tabla.column("detalle", width=320)

        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=scroll.set)

        tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        historial = repo.obtener_historial_jugador(cedula)
        for h in historial:
            h_dict = dict(h) if not isinstance(h, dict) else h
            tabla.insert("", "end", values=(h_dict.get("fecha_hora"), str(h_dict.get("accion") or "").capitalize(), h_dict.get("detalle")))


class VentanaSeleccionarParticipanteRondas(VentanaModal):
    def __init__(self, parent: ctk.CTkFrame, torneo_id: int) -> None:
        super().__init__(parent)
        self.torneo_id = torneo_id
        self.title("Seleccionar participante")
        self.geometry("520x400")
        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(
            self,
            text="Selecciona un participante para consultar sus rondas",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=15)

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        self.tabla_participantes = ttk.Treeview(
            frame,
            columns=("cedula", "nombre", "sexo"),
            show="headings",
            selectmode="browse",
        )
        for columna, texto in {"cedula": "Cédula", "nombre": "Nombre", "sexo": "Sexo"}.items():
            self.tabla_participantes.heading(columna, text=texto)
        self.tabla_participantes.column("cedula", width=130)
        self.tabla_participantes.column("nombre", width=240)
        self.tabla_participantes.column("sexo", width=70, anchor="center")
        self.tabla_participantes.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tabla_participantes.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tabla_participantes.configure(yscrollcommand=scroll.set)
        self.tabla_participantes.bind("<<TreeviewSelect>>", self.abrir_historial)
        self.tabla_participantes.bind("<Double-1>", self.abrir_historial)

        for participante in repo.listar_jugadores_de_torneo(torneo_id):
            self.tabla_participantes.insert(
                "", "end",
                values=(participante["cedula"], participante["nombre"], participante["sexo"]),
            )

        BotonDegradado(
            self,
            text="Ver rondas y marcadores",
            command=self.abrir_historial,
        ).pack(fill="x", padx=15, pady=(0, 15))

    def abrir_historial(self, event=None) -> None:
        seleccion = self.tabla_participantes.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Selecciona un participante.", parent=self)
            return
        cedula = self.tabla_participantes.item(seleccion[0], "values")[0]
        VentanaHistorialRondasJugador(self, cedula, self.torneo_id)


class VentanaHistorialRondasJugador(VentanaModal):
    def __init__(self, parent: ctk.CTkFrame, cedula: str, torneo_id: int) -> None:
        super().__init__(parent)
        jugador = repo.obtener_jugador(cedula)
        if not jugador:
            messagebox.showerror("Error", "No se encontró el registro del jugador.")
            self.destroy()
            return

        self.title(f"Rondas - {jugador['nombre']}")
        self.geometry("1250x450")
        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(
            self,
            text=f"Historial de rondas: {jugador['nombre']} ({cedula})",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=12)

        tabla_frame = ctk.CTkFrame(self)
        tabla_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        columnas = (
            "ronda",
            "mesa",
            "companeros",
            "rivales",
            "puntos_pareja",
            "puntos_rival",
            "resultado",
        )
        tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings")
        encabezados = {
            "ronda": "Ronda", "mesa": "Mesa", "companeros": "Compañero(s)",
            "rivales": "Rival(es)", "puntos_pareja": "Puntos pareja",
            "puntos_rival": "Puntos rival", "resultado": "Resultado",
        }
        for columna, texto in encabezados.items():
            tabla.heading(columna, text=texto)
        for columna, ancho in {
            "ronda": 60, "mesa": 60, "companeros": 220, "rivales": 300,
            "puntos_pareja": 110, "puntos_rival": 100, "resultado": 100,
        }.items():
            tabla.column(
                columna,
                width=ancho,
                anchor="center" if columna in (
                    "ronda", "mesa", "puntos_pareja", "puntos_rival", "resultado"
                ) else "w",
            )
        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=scroll.set)
        tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for ronda in repo.obtener_historial_rondas_jugador(torneo_id, cedula):
            tabla.insert("", "end", values=(
                ronda["numero_ronda"], ronda["mesa"], ronda["companeros"],
                ronda["rivales"], ronda["puntos_pareja"], ronda["puntos_rival"],
                ronda["resultado"],
            ))


class VentanaEditarTorneo(VentanaModal):
    def __init__(self, parent: ctk.CTkFrame, torneo_id: int, al_guardar: callable) -> None:
        super().__init__(parent)
        raw_torneo = repo.obtener_torneo(torneo_id)
        if not raw_torneo:
            messagebox.showerror("Error", "No se encontró la información del torneo.")
            self.destroy()
            return

        torneo = dict(raw_torneo)
        self.torneo_id = torneo_id
        self.al_guardar = al_guardar
        self.torneo_iniciado = torneo.get("estado") not in ("borrador", "inscripcion")

        self.title("Editar torneo")
        self.geometry("420x550")
        self.minsize(380, 450)
        self.resizable(True, True)

        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(self, text="✏️ Editar torneo", font=ctk.CTkFont(size=18, weight="bold")).pack(side="top", pady=(15, 10))

        btn_guardar = BotonDegradado(self, text="💾 Guardar cambios", font=ctk.CTkFont(size=14, weight="bold"), height=38, command=self.guardar)
        btn_guardar.pack(side="bottom", fill="x", padx=20, pady=(10, 15))

        scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll_frame.pack(side="top", fill="both", expand=True, padx=20, pady=(0, 5))

        ctk.CTkLabel(scroll_frame, text="Nombre del torneo:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(5, 2))
        self.ent_nombre = ctk.CTkEntry(scroll_frame, placeholder_text="Nombre del torneo")
        self.ent_nombre.insert(0, str(torneo.get("nombre", "") or ""))
        self.ent_nombre.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(scroll_frame, text="Duración en minutos:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(5, 2))
        self.ent_duracion = ctk.CTkEntry(scroll_frame, placeholder_text="Ej: 120")
        val_duracion = torneo.get("duracion_minutos") if torneo.get("duracion_minutos") is not None else torneo.get("duracion", "")
        self.ent_duracion.insert(0, str(val_duracion if val_duracion is not None else ""))
        self.ent_duracion.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(scroll_frame, text="Tipo de torneo:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(5, 2))
        self.combo_tipo = ctk.CTkComboBox(scroll_frame, values=["Mixto", "Hombres", "Mujeres"], state="readonly")
        tipo_val = str(torneo.get("tipo", "mixto") or "mixto").lower()
        self.combo_tipo.set(tipo_val.capitalize() if tipo_val in ["mixto", "hombres", "mujeres"] else "Mixto")
        self.combo_tipo.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(scroll_frame, text="Puntaje meta:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(5, 2))
        self.ent_puntaje = ctk.CTkEntry(scroll_frame, placeholder_text="Ej: 200")
        self.ent_puntaje.insert(0, str(torneo.get("puntaje_meta", "") or ""))
        self.ent_puntaje.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(scroll_frame, text="Número de rondas:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(5, 2))
        self.ent_rondas = ctk.CTkEntry(scroll_frame, placeholder_text="Ej: 5")
        self.ent_rondas.insert(0, str(torneo.get("num_rondas", "") or ""))
        self.ent_rondas.pack(fill="x", pady=(0, 12))

        if self.torneo_iniciado:
            enlazar_enter_formulario(
                self.ent_duracion,
                self.ent_rondas,
                accion_final=self.guardar,
            )
        else:
            enlazar_enter_formulario(
                self.ent_nombre,
                self.ent_duracion,
                self.combo_tipo,
                self.ent_puntaje,
                self.ent_rondas,
                accion_final=self.guardar,
            )

        if self.torneo_iniciado:
            self.ent_nombre.configure(state="disabled")
            self.combo_tipo.configure(state="disabled")
            self.ent_puntaje.configure(state="disabled")
            ctk.CTkLabel(
                scroll_frame,
                text="El torneo ya inició: solo se pueden modificar duración y número de rondas.",
                text_color="#D97706",
                wraplength=360,
            ).pack(anchor="w", pady=(0, 8))

        aplicar_ayudas(self)

    def guardar(self) -> None:
        try:
            duracion = int(self.ent_duracion.get().strip())
            rondas = int(self.ent_rondas.get().strip())

            campos = {
                "duracion_minutos": duracion,
                "num_rondas": rondas,
            }
            if not self.torneo_iniciado:
                nombre = self.ent_nombre.get().strip()
                if not nombre:
                    messagebox.showwarning("Atención", "El nombre del torneo no puede estar vacío.")
                    return
                campos.update(
                    nombre=nombre,
                    tipo=self.combo_tipo.get().strip().lower() or None,
                    puntaje_meta=int(self.ent_puntaje.get().strip()),
                )

            repo.editar_torneo(self.torneo_id, **campos)
            messagebox.showinfo("Éxito", "Torneo actualizado correctamente.")
            self.al_guardar()
            self.destroy()
        except ValueError:
            messagebox.showwarning("Atención", "Duración, puntaje y rondas deben ser números enteros.")
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))


class VentanaInscribirTorneo(VentanaModal):
    def __init__(self, parent: ctk.CTkFrame, torneo_id: int, al_guardar: callable) -> None:
        super().__init__(parent)
        raw_torneo = repo.obtener_torneo(torneo_id)
        if not raw_torneo:
            messagebox.showerror("Error", "No se encontró el torneo seleccionado.")
            self.destroy()
            return

        torneo = dict(raw_torneo)
        self.torneo_id = torneo_id
        self.al_guardar = al_guardar
        # 'M' (solo hombres), 'F' (solo mujeres) o None (mixto).
        self.sexo_requerido = repo.sexo_requerido_por_tipo(torneo.get("tipo"))

        self.title(f"Inscribir jugador en: {torneo.get('nombre', '')}")
        self.geometry("540x560")
        self.minsize(500, 520)

        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(self, text=f"Jugadores en: {torneo.get('nombre', '')}", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 5))
        if self.sexo_requerido:
            ctk.CTkLabel(
                self,
                text=f"Torneo solo para {'hombres' if self.sexo_requerido == 'M' else 'mujeres'}",
                font=ctk.CTkFont(size=12),
                text_color=COLOR_TEXTO_SECUNDARIO,
            ).pack(pady=(0, 5))

        frame_agregar = ctk.CTkFrame(self, fg_color="transparent")
        frame_agregar.pack(fill="x", padx=15, pady=5)

        self.actualizar_opciones_jugadores()
        self.jugador_seleccionado = None
        self.combo_jugadores = EntryAutocompletado(
            frame_agregar,
            opciones=self.opciones_jugadores,
            on_select=self._al_elegir_jugador,
            on_change=lambda _texto: setattr(self, "jugador_seleccionado", None),
            placeholder_text=(
                "Escriba nombre, apellido o cédula"
                if self.opciones_jugadores
                else "No hay jugadores"
            ),
        )
        self.combo_jugadores.pack(side="left", padx=(0, 10), expand=True, fill="x")
        enlazar_enter_formulario(self.combo_jugadores, accion_final=self.inscribir_seleccionado)

        btn_inscribir = BotonDegradado(frame_agregar, text="➕ Inscribir", width=100, command=self.inscribir_seleccionado)
        btn_inscribir.pack(side="right")

        ctk.CTkLabel(self, text="Jugadores inscritos:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(10, 2))

        tabla_frame = ctk.CTkFrame(self)
        tabla_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        columnas = ("cedula", "nombre", "sexo")
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings")
        self.tabla.heading("cedula", text="Cédula")
        self.tabla.heading("nombre", text="Nombre")
        self.tabla.heading("sexo", text="Sexo")

        self.tabla.column("cedula", width=110)
        self.tabla.column("nombre", width=250)
        self.tabla.column("sexo", width=60, anchor="center")

        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)

        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        frame_rapido = ctk.CTkFrame(self)
        frame_rapido.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkLabel(frame_rapido, text="⚡ ¿Jugador nuevo? Inscripción rápida", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 6))

        campos_frame = ctk.CTkFrame(frame_rapido, fg_color="transparent")
        campos_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.ent_rapido_cedula = ctk.CTkEntry(campos_frame, placeholder_text="Cédula", width=110)
        self.ent_rapido_cedula.pack(side="left", padx=(0, 5))

        self.ent_rapido_nombre = ctk.CTkEntry(campos_frame, placeholder_text="Nombre completo")
        self.ent_rapido_nombre.pack(side="left", fill="x", expand=True, padx=(0, 5))

        if self.sexo_requerido:
            self.combo_rapido_sexo = ctk.CTkComboBox(
                campos_frame, values=[self.sexo_requerido], width=65, state="readonly"
            )
        else:
            self.combo_rapido_sexo = ctk.CTkComboBox(campos_frame, values=["M", "F"], width=65, state="normal")
        self.combo_rapido_sexo.set(self.sexo_requerido or "M")
        self.combo_rapido_sexo.pack(side="left", padx=(0, 5))

        enlazar_enter_formulario(
            self.ent_rapido_cedula,
            self.ent_rapido_nombre,
            self.combo_rapido_sexo,
            accion_final=self.crear_e_inscribir_rapido,
        )

        btn_crear_inscribir = BotonDegradado(campos_frame, text="✨ Crear e inscribir", width=130, command=self.crear_e_inscribir_rapido)
        btn_crear_inscribir.pack(side="left")

        self.cargar_inscritos()

    def actualizar_opciones_jugadores(self) -> None:
        jugadores = repo.listar_jugadores_para_inscripcion(self.torneo_id)
        self.opciones_jugadores = {f"{j['nombre']} ({j['cedula']})": j['cedula'] for j in jugadores}
        if hasattr(self, "combo_jugadores"):
            self.combo_jugadores.establecer_opciones(self.opciones_jugadores)
            self.combo_jugadores.delete(0, "end")
            self.combo_jugadores.configure(
                placeholder_text=(
                    "Escriba nombre, apellido o cédula"
                    if self.opciones_jugadores
                    else "No hay jugadores"
                )
            )
            self.jugador_seleccionado = None

    def _al_elegir_jugador(self, etiqueta: str, cedula) -> None:
        self.jugador_seleccionado = cedula

    def cargar_inscritos(self) -> None:
        _limpiar_treeview(self.tabla)

        inscritos = repo.listar_jugadores_de_torneo(self.torneo_id)
        for j in inscritos:
            j_dict = dict(j)
            self.tabla.insert("", "end", values=(j_dict.get("cedula"), j_dict.get("nombre"), j_dict.get("sexo")))

    def inscribir_seleccionado(self) -> None:
        seleccion = self.combo_jugadores.get()
        cedula = self.jugador_seleccionado or self.opciones_jugadores.get(seleccion)
        if cedula is None:
            messagebox.showwarning("Atención", "Seleccione un jugador válido de la lista.")
            return

        try:
            if not repo.inscribir_jugador_a_torneo(cedula, self.torneo_id):
                messagebox.showwarning(
                    "Jugador ya inscrito",
                    "Este jugador ya está inscrito en el torneo.",
                    parent=self,
                )
                return
            self.cargar_inscritos()
            self.al_guardar()
            self.combo_jugadores.delete(0, "end")
            self.jugador_seleccionado = None
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))

    def crear_e_inscribir_rapido(self) -> None:
        cedula = self.ent_rapido_cedula.get().strip()
        nombre = self.ent_rapido_nombre.get().strip()
        sexo = self.combo_rapido_sexo.get().strip()

        if not cedula or not nombre:
            messagebox.showwarning("Atención", "Debe ingresar la cédula y el nombre completo del jugador.")
            return

        try:
            # Se valida antes de crear, para no dejar un jugador creado y sin inscribir.
            repo.validar_sexo_para_torneo(self.torneo_id, sexo, nombre)
            repo.crear_jugador(cedula, nombre, sexo)
            repo.inscribir_jugador_a_torneo(cedula, self.torneo_id)

            self.ent_rapido_cedula.delete(0, "end")
            self.ent_rapido_nombre.delete(0, "end")
            self.combo_rapido_sexo.set(self.sexo_requerido or "M")

            self.actualizar_opciones_jugadores()

            self.cargar_inscritos()
            self.al_guardar()

            messagebox.showinfo("Éxito", f"Jugador '{nombre}' registrado e inscrito exitosamente.")
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))


class VentanaSustituirJugador(VentanaModal):
    def __init__(self, parent: ctk.CTkFrame, torneo_id: int, al_guardar: callable) -> None:
        super().__init__(parent)
        raw_torneo = repo.obtener_torneo(torneo_id)
        if not raw_torneo:
            messagebox.showerror("Error", "No se encontró el torneo seleccionado.")
            self.destroy()
            return

        self.torneo_id = torneo_id
        self.al_guardar = al_guardar
        torneo = dict(raw_torneo)

        self.title(f"Sustituir jugador en: {torneo.get('nombre', '')}")
        self.geometry("480x260")
        self.resizable(False, False)

        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(
            self,
            text="🔄 Sustituir participante",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(15, 5))
        ctk.CTkLabel(
            self,
            text=f"Torneo: {torneo.get('nombre', '')}",
            font=ctk.CTkFont(weight="bold"),
        ).pack(pady=(0, 12))

        self.jugadores_retirados = {
            f"{j['nombre']} ({j['cedula']})": j["cedula"]
            for j in repo.listar_jugadores_retirados_de_torneo(torneo_id)
        }
        self.jugadores_disponibles = {
            f"{j['nombre']} ({j['cedula']})": j["cedula"]
            for j in repo.listar_jugadores_disponibles_para_sustitucion(torneo_id)
        }

        if not self.jugadores_retirados:
            messagebox.showwarning("Atención", "No hay jugadores retirados de este torneo para sustituir.")
            self.destroy()
            return
        if not self.jugadores_disponibles:
            messagebox.showwarning("Atención", "No hay jugadores disponibles para ingresar como sustitutos.")
            self.destroy()
            return

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=25)

        ctk.CTkLabel(form, text="Jugador a reemplazar:").pack(anchor="w")
        self.combo_saliente = ctk.CTkComboBox(
            form,
            values=list(self.jugadores_retirados),
            state="readonly",
            width=430,
        )
        self.combo_saliente.set(list(self.jugadores_retirados)[0])
        self.combo_saliente.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            form,
            text="Jugador suplente (de jugadores y no inscrito):",
        ).pack(anchor="w")
        self.combo_entrante = ctk.CTkComboBox(
            form,
            values=list(self.jugadores_disponibles),
            state="readonly",
            width=430,
        )
        self.combo_entrante.set(list(self.jugadores_disponibles)[0])
        self.combo_entrante.pack(fill="x")

        BotonDegradado(
            self,
            text="🔄 Confirmar sustitución",
            font=ctk.CTkFont(weight="bold"),
            command=self.guardar,
        ).pack(fill="x", padx=25, pady=18)

    def guardar(self) -> None:
        cedula_saliente = self.jugadores_retirados.get(self.combo_saliente.get())
        cedula_entrante = self.jugadores_disponibles.get(self.combo_entrante.get())
        if not cedula_saliente or not cedula_entrante:
            messagebox.showwarning("Atención", "Seleccione un jugador saliente y uno entrante válidos.")
            return

        try:
            repo.sustituir_jugador_torneo(
                self.torneo_id,
                cedula_saliente,
                cedula_entrante,
            )
            self.al_guardar()
            messagebox.showinfo(
                "Éxito",
                "Sustitución realizada correctamente.\n\n"
                "Las mesas, byes y estadísticas acumuladas fueron transferidos "
                "al jugador suplente.",
            )
            self.destroy()
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))


def _mesas_ronda_con_numeros(ronda_id: int, torneo_id: int | None) -> list[dict]:
    """Mesas de la ronda (ordenadas) con el número de cada jugador (``jN_num``).

    Es la lista que muestra el panel "Mesas marcadas" de ``VentanaRegistrarMesa``.
    Si no se pueden obtener los números, la ventana simplemente los omite.
    """
    mesas = [dict(m) for m in repo.listar_mesas_de_ronda(ronda_id)]
    try:
        numeros = {
            m["numero_mesa"]: dict(m)
            for m in repo.listar_mesas_con_numeros_jugador(ronda_id, torneo_id)
        }
    except (repo.ErrorDatos, sqlite3.Error, KeyError, TypeError):
        numeros = {}
    for mesa in mesas:
        datos = numeros.get(mesa["numero_mesa"], {})
        for i in range(1, 5):
            mesa[f"j{i}_num"] = datos.get(f"j{i}_num")
    return sorted(mesas, key=lambda m: m["numero_mesa"])


class _LineaRombos(tk.Canvas):
    """Línea fina con un rombo en cada extremo (separador decorativo).

    ``color`` y ``fondo`` pueden ser un color o un par (claro, oscuro); como un
    ``tk.Canvas`` no sigue solo el modo de apariencia, se resuelven al dibujar.
    """

    def __init__(
        self, master, color, fondo, ancho: int | None = None, alto: int = 10
    ) -> None:
        opciones = {"width": ancho} if ancho else {}
        super().__init__(
            master, height=alto, highlightthickness=0, bd=0,
            bg=self._resolver(fondo), **opciones,
        )
        self._color = color
        self._fondo = fondo
        self.bind("<Configure>", self._dibujar)
        self.bind("<Map>", self._dibujar, add="+")

    @staticmethod
    def _resolver(color):
        if isinstance(color, str):
            return color
        return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]

    def _dibujar(self, _evento=None) -> None:
        color, fondo = self._resolver(self._color), self._resolver(self._fondo)
        self.configure(bg=fondo)
        self.delete("all")
        ancho, alto = self.winfo_width(), self.winfo_height()
        medio, r = alto / 2, 4
        self.create_line(r, medio, ancho - r, medio, fill=color)
        for x in (r + 1, ancho - r - 1):
            self.create_polygon(
                x, medio - r, x + r, medio, x, medio + r, x - r, medio,
                fill=fondo, outline=color,
            )


class VentanaRegistrarMesa(VentanaModal):
    """Modal para registrar o editar el marcador oficial de una mesa.

    A la derecha lista todas las mesas de la ronda ("Marcada" / "Sin marcar");
    al elegir una (o con Siguiente / Anterior) el formulario cambia a esa mesa y,
    si ya tenía resultado, queda en modo edición.
    """

    # Colores tomados del tema de la app (paleta global COLOR_*), de modo que la
    # ventana cambia con el modo claro/oscuro igual que el resto de la interfaz.
    C_FONDO = COLOR_FONDO_VENTANA
    C_PANEL = COLOR_PANEL
    C_CAMPO = COLOR_FONDO_VENTANA
    C_BORDE_CAMPO = COLOR_BORDE_ACENTO
    C_TEXTO = tuple(ctk.ThemeManager.theme["CTkLabel"]["text_color"])
    C_TITULO = COLOR_TEXTO_SECUNDARIO
    C_LINEA = COLOR_BORDE_ACENTO
    C_ROJO = ("#e8192c", "#ed1c2e")            # tarjetas de infracción (rojo intenso)
    C_TEXTO_ROJO = "#ffffff"
    C_AMARILLO = "#fadb4f"
    C_AMARILLO_HOVER = "#e8c93a"
    C_TEXTO_AMARILLO = "#3a3a3a"
    C_FILA = ("#dce6f5", "#1f3358")            # filas de la lista: azul algo más claro
    C_FILA_SEL = ("#bfd4f5", "#2b4c85")        # fila activa
    C_TEXTO_FILA_SEL = COLOR_TEXTO_ACENTO
    C_OK = COLOR_EXITO_TEXTO
    C_NO = COLOR_TEXTO_SECUNDARIO

    def __init__(
        self,
        parent: ctk.CTkFrame,
        mesa_id: int,
        info_mesa: str,
        pts_meta: int,
        al_guardar: callable,
        resultado_actual: dict | None = None,
        mesas_pendientes: list[dict] | None = None,
        mesas_ronda: list[dict] | None = None,
    ) -> None:
        super().__init__(parent)
        self.mesa_id = mesa_id
        self.al_guardar = al_guardar
        obtener_torneo_id = getattr(parent, "obtener_torneo_id_sel", None)
        self.torneo_id = obtener_torneo_id() if callable(obtener_torneo_id) else None
        self.pts_meta = pts_meta
        self.es_edicion = resultado_actual is not None
        # Mesa que se abrió explícitamente para editar (aunque no figure finalizada).
        self._id_edicion_inicial = mesa_id if resultado_actual is not None else None
        self._guardando = False

        # Lista de mesas del panel derecho. Si el llamador no la entrega se usa
        # lo que haya (pendientes o la mesa en edición) para no dejar la vista vacía.
        if mesas_ronda:
            self._mesas = [dict(m) for m in mesas_ronda]
        elif mesas_pendientes:
            self._mesas = [dict(m) for m in mesas_pendientes]
        elif resultado_actual is not None:
            self._mesas = [dict(resultado_actual)]
        else:
            self._mesas = [{"id": mesa_id, "numero_mesa": "?", "estado": "en_juego"}]
        self._indice = next(
            (i for i, m in enumerate(self._mesas) if int(m["id"]) == int(mesa_id)), 0
        )

        _centrar_ventana_en_pantalla(self, 1100, 670)
        self.resizable(False, False)
        self.configure(fg_color=self.C_FONDO)

        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        self._crear_fuentes()
        self._icono_marcada = self._cargar_icono("finalizado")
        self._icono_sin_marcar = self._cargar_icono("pendiente")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._construir_encabezado()

        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.grid(row=1, column=0, sticky="nsew", padx=22, pady=(4, 20))
        cuerpo.grid_columnconfigure(0, weight=3, uniform="cols")
        cuerpo.grid_columnconfigure(1, weight=2, uniform="cols")
        cuerpo.grid_rowconfigure(0, weight=1)

        self._construir_columna_izquierda(cuerpo)
        self._construir_panel_mesas(cuerpo)

        enlazar_enter_formulario(
            self.ent_p1,
            self.ent_p2,
            self.ent_descuento_p1,
            self.ent_descuento_p2,
            self.ent_motivo,
            accion_final=self.guardar,
        )
        for entrada in (
            self.ent_p1, self.ent_p2, self.ent_descuento_p1, self.ent_descuento_p2
        ):
            entrada.bind("<KeyRelease>", self._actualizar_resultado, add="+")

        self._cargar_mesa()

        Tooltip(self.ent_p1, "Puntos anotados por la pareja 1 en la mesa.")
        Tooltip(self.ent_p2, "Puntos anotados por la pareja 2 en la mesa.")
        Tooltip(
            self.ent_descuento_p1,
            "Puntos a restar a la pareja 1. Puede escribirse -30 o 30; vacío equivale a 0.",
        )
        Tooltip(
            self.ent_descuento_p2,
            "Puntos a restar a la pareja 2. Puede escribirse -30 o 30; vacío equivale a 0.",
        )
        aplicar_ayudas(self)

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------
    def _crear_fuentes(self) -> None:
        # Sin ``family``: se usa la fuente predeterminada del tema de la app.
        self._f_titulo = ctk.CTkFont(size=28)
        self._f_mesa = ctk.CTkFont(size=14)
        self._f_seccion = ctk.CTkFont(size=22)
        self._f_pequena = ctk.CTkFont(size=12)
        self._f_jugador = ctk.CTkFont(size=12)
        self._f_puntos = ctk.CTkFont(size=28)
        self._f_descuento = ctk.CTkFont(size=18)
        self._f_resultado = ctk.CTkFont(size=34)
        self._f_boton = ctk.CTkFont(size=22)
        self._f_nav = ctk.CTkFont(size=13)
        self._f_fila_estado = ctk.CTkFont(size=14)
        self._f_fila_mesa = ctk.CTkFont(size=19)

    @staticmethod
    def _cargar_icono(estado: str) -> ctk.CTkImage | None:
        """Ícono de estado reutilizando los PNG de la app; None si faltan."""
        try:
            with Image.open(_RUTAS_ICONOS_MARCADOR[estado]) as imagen:
                imagen = imagen.convert("RGBA")
            return ctk.CTkImage(light_image=imagen, dark_image=imagen, size=(22, 22))
        except (OSError, KeyError):
            return None

    def _construir_encabezado(self) -> None:
        encabezado = ctk.CTkFrame(self, fg_color="transparent")
        encabezado.grid(row=0, column=0, sticky="ew", padx=40, pady=(14, 4))
        encabezado.grid_columnconfigure(0, weight=1, uniform="enc")
        encabezado.grid_columnconfigure(1, weight=0)
        encabezado.grid_columnconfigure(2, weight=1, uniform="enc")

        self.lbl_mesa = ctk.CTkLabel(
            encabezado, text="", anchor="w", font=self._f_mesa, text_color=self.C_TEXTO
        )
        self.lbl_mesa.grid(row=0, column=0, sticky="sw", padx=(10, 0), pady=(0, 6))
        ctk.CTkLabel(
            encabezado,
            text="📝  Carga de marcador",
            font=self._f_titulo,
            text_color=self.C_TITULO,
        ).grid(row=0, column=1)
        _LineaRombos(encabezado, self.C_LINEA, self.C_FONDO).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(2, 0)
        )

    def _crear_panel_pareja(self, padre, numero: int):
        panel = ctk.CTkFrame(padre, fg_color=self.C_PANEL, corner_radius=26)
        panel.grid_columnconfigure(0, minsize=330)
        panel.grid_columnconfigure(1, weight=1)
        panel.grid_rowconfigure(0, weight=1)

        info = ctk.CTkFrame(panel, fg_color="transparent")
        info.grid(row=0, column=0, sticky="w", padx=(18, 0), pady=12)
        ctk.CTkLabel(
            info, text=f"Pareja {numero}", font=self._f_seccion, text_color=self.C_TITULO
        ).grid(row=0, column=0, columnspan=2)
        _LineaRombos(info, self.C_LINEA, self.C_PANEL, ancho=150).grid(
            row=1, column=0, columnspan=2, pady=(2, 6)
        )
        jugadores = []
        for fila in range(2):
            lbl_num = ctk.CTkLabel(
                info, text="", anchor="w", font=self._f_jugador, text_color=self.C_TITULO
            )
            lbl_nom = ctk.CTkLabel(
                info, text="", anchor="w", font=self._f_jugador, text_color=self.C_TITULO
            )
            lbl_num.grid(row=2 + fila, column=0, sticky="w", padx=(0, 14))
            lbl_nom.grid(row=2 + fila, column=1, sticky="w")
            jugadores.append((lbl_num, lbl_nom))

        entrada = ctk.CTkEntry(
            panel,
            height=54,
            corner_radius=27,
            border_width=1,
            border_color=self.C_BORDE_CAMPO,
            fg_color=self.C_CAMPO,
            text_color=self.C_TEXTO,
            justify="center",
            font=self._f_puntos,
            placeholder_text="0",
        )
        entrada.grid(row=0, column=1, sticky="ew", padx=(10, 24), pady=18)
        return panel, jugadores, entrada

    def _crear_tarjeta_descuento(self, padre, numero: int):
        tarjeta = ctk.CTkFrame(
            padre, fg_color=self.C_ROJO, corner_radius=24,
        )
        ctk.CTkLabel(
            tarjeta, text=f"Pareja {numero}", font=self._f_pequena, text_color=self.C_TEXTO_ROJO
        ).pack(pady=(9, 2))
        entrada = ctk.CTkEntry(
            tarjeta,
            width=190,
            height=40,
            corner_radius=20,
            border_width=0,
            fg_color=self.C_CAMPO,
            text_color=self.C_TEXTO,
            justify="center",
            font=self._f_descuento,
            placeholder_text="0",
        )
        entrada.pack(padx=18, pady=(0, 14))
        return tarjeta, entrada

    def _construir_columna_izquierda(self, cuerpo) -> None:
        izquierda = ctk.CTkFrame(cuerpo, fg_color="transparent")
        izquierda.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        izquierda.grid_columnconfigure(0, weight=1)
        izquierda.grid_rowconfigure(2, weight=1)

        panel1, self._jugadores_p1, self.ent_p1 = self._crear_panel_pareja(izquierda, 1)
        panel1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        panel2, self._jugadores_p2, self.ent_p2 = self._crear_panel_pareja(izquierda, 2)
        panel2.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        # --- Descuento por infracción ---------------------------------
        panel_desc = ctk.CTkFrame(izquierda, fg_color=self.C_PANEL, corner_radius=26)
        panel_desc.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        panel_desc.grid_columnconfigure(0, weight=0)
        panel_desc.grid_columnconfigure(1, weight=1)
        panel_desc.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            panel_desc,
            text="🚫  Descuento por infracción",
            font=self._f_seccion,
            text_color=self.C_TITULO,
        ).grid(row=0, column=0, columnspan=2, pady=(14, 8))

        columna_pareja = ctk.CTkFrame(panel_desc, fg_color="transparent")
        columna_pareja.grid(row=1, column=0, sticky="ns", padx=(12, 6), pady=(0, 14))
        columna_pareja.grid_rowconfigure((0, 1), weight=1)
        tarjeta1, self.ent_descuento_p1 = self._crear_tarjeta_descuento(columna_pareja, 1)
        tarjeta1.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        tarjeta2, self.ent_descuento_p2 = self._crear_tarjeta_descuento(columna_pareja, 2)
        tarjeta2.grid(row=1, column=0, sticky="nsew")

        tarjeta_motivo = ctk.CTkFrame(
            panel_desc, fg_color=self.C_ROJO, corner_radius=24,
        )
        tarjeta_motivo.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 14))
        tarjeta_motivo.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            tarjeta_motivo, text="Motivo del descuento",
            font=self._f_pequena, text_color=self.C_TEXTO_ROJO,
        ).grid(row=0, column=0, pady=(10, 3))
        self.ent_motivo = ctk.CTkEntry(
            tarjeta_motivo,
            height=40,
            corner_radius=20,
            border_width=0,
            fg_color=self.C_CAMPO,
            text_color=self.C_TEXTO,
            justify="center",
            font=self._f_nav,
            placeholder_text="Motivo (opcional)",
        )
        self.ent_motivo.grid(row=1, column=0, sticky="ew", padx=16)
        ctk.CTkLabel(
            tarjeta_motivo, text="Resultado del marcador con el descuento",
            font=self._f_pequena, text_color=self.C_TEXTO_ROJO,
        ).grid(row=2, column=0, pady=(14, 0))

        fila_resultado = ctk.CTkFrame(tarjeta_motivo, fg_color="transparent")
        fila_resultado.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        fila_resultado.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            fila_resultado, text="P1", font=self._f_pequena, text_color=self.C_TEXTO_ROJO
        ).grid(row=0, column=0)
        self.lbl_resultado = ctk.CTkLabel(
            fila_resultado, text="– vs –", font=self._f_resultado, text_color=self.C_TEXTO_ROJO
        )
        self.lbl_resultado.grid(row=0, column=1, pady=(0, 2))
        ctk.CTkLabel(
            fila_resultado, text="P2", font=self._f_pequena, text_color=self.C_TEXTO_ROJO
        ).grid(row=0, column=2)
        tarjeta_motivo.grid_rowconfigure(3, weight=1)

        # --- Botón principal ------------------------------------------
        self.btn_guardar = BotonDegradado(
            izquierda,
            text="📋  Registrar marcador",
            font=self._f_boton,
            height=48,
            corner_radius=24,
            fg_color=self.C_AMARILLO,
            hover_color=self.C_AMARILLO_HOVER,
            text_color=self.C_TEXTO_AMARILLO,
            command=self.guardar,
        )
        self.btn_guardar.grid(row=3, column=0, sticky="ew", padx=50)

    def _construir_panel_mesas(self, cuerpo) -> None:
        panel = ctk.CTkFrame(cuerpo, fg_color=self.C_PANEL, corner_radius=26)
        panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            panel, text="Mesas marcadas", font=self._f_seccion, text_color=self.C_TITULO
        ).grid(row=0, column=0, pady=(14, 8))

        navegacion = ctk.CTkFrame(panel, fg_color="transparent")
        navegacion.grid(row=1, column=0, sticky="ew", padx=16)
        navegacion.grid_columnconfigure((0, 1), weight=1)
        estilo_nav = dict(
            estilo="secundario", font=self._f_nav, height=28, corner_radius=14, width=150
        )
        BotonDegradado(
            navegacion, text="Siguiente mesa  ❯", command=self._mesa_siguiente, **estilo_nav
        ).grid(row=0, column=0, sticky="w")
        BotonDegradado(
            navegacion, text="❮  Anterior mesa", command=self._mesa_anterior, **estilo_nav
        ).grid(row=0, column=1, sticky="e")

        _LineaRombos(panel, self.C_LINEA, self.C_PANEL).grid(
            row=2, column=0, sticky="ew", padx=16, pady=(10, 8)
        )

        self.lista_mesas = ctk.CTkScrollableFrame(
            panel,
            fg_color="transparent",
            corner_radius=0,
        )
        self.lista_mesas.grid(row=3, column=0, sticky="nsew", padx=(10, 6), pady=(0, 14))
        self.lista_mesas.grid_columnconfigure(0, weight=1)

        self._filas_mesas: list[dict] = []
        for indice, mesa in enumerate(self._mesas):
            self._crear_fila_mesa(indice, mesa)

    def _crear_fila_mesa(self, indice: int, mesa: dict) -> None:
        fila = ctk.CTkFrame(self.lista_mesas, fg_color=self.C_FILA, corner_radius=16)
        fila.grid(row=indice, column=0, sticky="ew", padx=(0, 6), pady=3)
        fila.grid_columnconfigure(2, weight=1)

        lbl_estado = ctk.CTkLabel(fila, text="", font=self._f_fila_estado, anchor="w")
        lbl_estado.grid(row=0, column=0, sticky="w", padx=(16, 8), pady=5)
        lbl_icono = ctk.CTkLabel(fila, text="", width=22)
        lbl_icono.grid(row=0, column=1, sticky="w")
        lbl_mesa = ctk.CTkLabel(
            fila, text=f"Mesa {mesa.get('numero_mesa', '?')}", font=self._f_fila_mesa
        )
        lbl_mesa.grid(row=0, column=3, sticky="e", padx=(8, 20))

        for widget in (fila, lbl_estado, lbl_icono, lbl_mesa):
            widget.bind("<Button-1>", lambda _e, i=indice: self._seleccionar_mesa(i))
        self._filas_mesas.append(
            {"frame": fila, "estado": lbl_estado, "icono": lbl_icono, "mesa": lbl_mesa}
        )
        self._pintar_fila(indice)

    def _pintar_fila(self, indice: int) -> None:
        widgets = self._filas_mesas[indice]
        marcada = self._mesas[indice].get("estado") == "finalizada"
        seleccionada = indice == self._indice
        widgets["frame"].configure(fg_color=self.C_FILA_SEL if seleccionada else self.C_FILA)
        color_texto = self.C_TEXTO_FILA_SEL if seleccionada else self.C_TITULO
        widgets["estado"].configure(
            text="Marcada" if marcada else "Sin marcar", text_color=color_texto
        )
        widgets["mesa"].configure(text_color=color_texto)

        icono = self._icono_marcada if marcada else self._icono_sin_marcar
        if icono is not None:
            widgets["icono"].configure(image=icono, text="")
        else:  # sin PNG disponible: símbolo de respaldo
            widgets["icono"].configure(
                image=None,
                text="✔" if marcada else "✖",
                text_color=self.C_OK if marcada else self.C_NO,
            )

    # ------------------------------------------------------------------
    # Navegación entre mesas
    # ------------------------------------------------------------------
    def _mesa_siguiente(self) -> None:
        self._seleccionar_mesa(min(self._indice + 1, len(self._mesas) - 1))

    def _mesa_anterior(self) -> None:
        self._seleccionar_mesa(max(self._indice - 1, 0))

    def _seleccionar_mesa(self, indice: int) -> None:
        if self._guardando or indice == self._indice:
            return
        anterior, self._indice = self._indice, indice
        self._pintar_fila(anterior)
        self._pintar_fila(indice)
        self._cargar_mesa()

    def _mostrar_fila_seleccionada(self) -> None:
        """Desplaza la lista para que la mesa activa quede visible."""
        try:
            lienzo = self.lista_mesas._parent_canvas
            self.lista_mesas.update_idletasks()
            total = lienzo.bbox("all")[3]
            fila = self._filas_mesas[self._indice]["frame"]
            if total > 0:
                lienzo.yview_moveto(max(0.0, (fila.winfo_y() - 60) / total))
        except (AttributeError, IndexError, tk.TclError, TypeError):
            pass

    # ------------------------------------------------------------------
    # Datos de la mesa activa
    # ------------------------------------------------------------------
    @staticmethod
    def _primer_valor(datos: dict, *claves: str, defecto=0):
        for clave in claves:
            if datos.get(clave) is not None:
                return datos[clave]
        return defecto

    @staticmethod
    def _poner_texto(entrada: ctk.CTkEntry, texto: str) -> None:
        # ``get()`` devuelve "" mientras el placeholder está activo; no hay que
        # borrarlo, o CTkEntry lo pierde y el campo queda sin su texto guía.
        if entrada.get():
            entrada.delete(0, "end")
        if texto:
            entrada.insert(0, texto)

    @staticmethod
    def _recortar_nombre(nombre: str, maximo: int = 26) -> str:
        nombre = (nombre or "").strip()
        return nombre if len(nombre) <= maximo else nombre[: maximo - 1].rstrip() + "…"

    def _cargar_mesa(self) -> None:
        mesa = self._mesas[self._indice]
        self.mesa_id = int(mesa["id"])
        self.es_edicion = (
            mesa.get("estado") == "finalizada" or self.mesa_id == self._id_edicion_inicial
        )

        self.title("Editar resultado de mesa" if self.es_edicion else "Anotar resultado de mesa")
        self.lbl_mesa.configure(text=f"MESA {mesa.get('numero_mesa', '?')}")
        self.btn_guardar.configure(
            text="💾  Guardar edición" if self.es_edicion else "📋  Registrar marcador"
        )

        for pareja, jugadores in ((1, self._jugadores_p1), (2, self._jugadores_p2)):
            for posicion, (lbl_num, lbl_nom) in enumerate(jugadores):
                n = (pareja - 1) * 2 + posicion + 1
                numero = mesa.get(f"j{n}_num")
                lbl_num.configure(text=f"Jugador {numero}" if numero is not None else "")
                lbl_nom.configure(text=self._recortar_nombre(mesa.get(f"j{n}_nom") or ""))

        if self.es_edicion:
            p1 = self._primer_valor(mesa, "puntos_base_p1", "puntos_p1")
            p2 = self._primer_valor(mesa, "puntos_base_p2", "puntos_p2")
            d1 = int(self._primer_valor(mesa, "descuento_p1"))
            d2 = int(self._primer_valor(mesa, "descuento_p2"))
            motivo = str(mesa.get("motivo_penalizacion") or "")
            self._poner_texto(self.ent_p1, str(p1))
            self._poner_texto(self.ent_p2, str(p2))
            self._poner_texto(self.ent_descuento_p1, f"-{d1}" if d1 > 0 else "")
            self._poner_texto(self.ent_descuento_p2, f"-{d2}" if d2 > 0 else "")
            self._poner_texto(self.ent_motivo, motivo)
        else:
            for entrada in (
                self.ent_p1, self.ent_p2, self.ent_descuento_p1,
                self.ent_descuento_p2, self.ent_motivo,
            ):
                self._poner_texto(entrada, "")

        self._actualizar_resultado()
        self.after(60, self._mostrar_fila_seleccionada)
        self.after(80, self.ent_p1.focus_set)

    @staticmethod
    def _leer_entero(texto: str, *, descuento: bool = False) -> int:
        """Convierte el texto a entero. Los descuentos aceptan "-30" o "30" y vacío = 0."""
        texto = (texto or "").strip().replace("−", "-")
        if descuento:
            if texto.startswith("-"):
                texto = texto[1:].strip()
            if not texto:
                return 0
        return int(texto)

    def _actualizar_resultado(self, _evento=None) -> None:
        """Vista previa "P1 vs P2" del marcador con los descuentos aplicados."""
        try:
            p1 = self._leer_entero(self.ent_p1.get())
            p2 = self._leer_entero(self.ent_p2.get())
            d1 = self._leer_entero(self.ent_descuento_p1.get(), descuento=True)
            d2 = self._leer_entero(self.ent_descuento_p2.get(), descuento=True)
            if min(p1, p2, d1, d2) < 0:
                raise ValueError
            texto = f"{max(0, p1 - d1)} vs {max(0, p2 - d2)}"
        except ValueError:
            texto = "– vs –"
        self.lbl_resultado.configure(text=texto)

    def guardar(self) -> None:
        if getattr(self, "_guardando", False):
            return

        self._guardando = True
        entradas = (
            self.ent_p1, self.ent_p2, self.ent_descuento_p1,
            self.ent_descuento_p2, self.ent_motivo,
        )
        if self.winfo_exists():
            self.btn_guardar.configure(state="disabled")
            for entrada in entradas:
                entrada.configure(state="disabled")

        try:
            p1 = self._leer_entero(self.ent_p1.get())
            p2 = self._leer_entero(self.ent_p2.get())
            descuento_p1 = self._leer_entero(self.ent_descuento_p1.get(), descuento=True)
            descuento_p2 = self._leer_entero(self.ent_descuento_p2.get(), descuento=True)
            if min(p1, p2, descuento_p1, descuento_p2) < 0:
                raise ValueError
            p1_final = max(0, p1 - descuento_p1)
            p2_final = max(0, p2 - descuento_p2)
            torneo_antes = (
                repo.obtener_torneo(self.torneo_id)
                if self.torneo_id is not None
                else None
            )
            repo.registrar_o_editar_resultado_mesa(
                self.mesa_id,
                p1,
                p2,
                descuento_p1,
                descuento_p2,
                self.ent_motivo.get().strip() or None,
            )
            torneo_despues = (
                repo.obtener_torneo(self.torneo_id)
                if self.torneo_id is not None
                else None
            )
            finalizado_ahora = (
                torneo_antes is not None
                and torneo_antes["estado"] != "finalizado"
                and torneo_despues is not None
                and torneo_despues["estado"] == "finalizado"
            )
            self.al_guardar()
            if finalizado_ahora:
                messagebox.showinfo(
                    "Torneo finalizado",
                    f"El marcador {p1_final} - {p2_final} fue guardado. "
                    "El torneo ha finalizado y la vista En vivo / rondas se limpió.",
                    parent=self,
                )
            else:
                messagebox.showinfo(
                    "Éxito",
                    f"Marcador {'editado' if self.es_edicion else 'registrado'} correctamente: "
                    f"{p1_final} - {p2_final}.\nEl ranking fue recalculado.",
                    parent=self,
                )
            self.destroy()
        except ValueError:
            messagebox.showwarning(
                "Atención",
                "Los puntos y descuentos deben ser enteros no negativos.",
                parent=self,
            )
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e), parent=self)
        finally:
            if self.winfo_exists():
                self._guardando = False
                self.btn_guardar.configure(state="normal")
                for entrada in entradas:
                    entrada.configure(state="normal")


class VentanaHojaMesa(VentanaModal):
    """Vista previa de la hoja en blanco para anotar manualmente una mesa."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        nombre_torneo: str,
        numero_ronda: int,
        mesas: list[MesaHoja],
    ) -> None:
        super().__init__(parent)
        self.nombre_torneo = nombre_torneo
        self.numero_ronda = numero_ronda
        self.mesas = mesas
        self.indice_mesa = 0

        self.title(f"Vista previa - Hojas de mesa - Ronda {numero_ronda}")
        self.geometry("920x650")
        self.minsize(700, 520)

        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(
            self,
            text="Vista previa de las hojas para anotar puntos a mano",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(14, 8))

        self.lbl_pagina_mesa = ctk.CTkLabel(self, text="")
        self.lbl_pagina_mesa.pack(pady=(0, 6))

        self.vista_previa = tk.Canvas(
            self,
            background="#e5e7eb",
            highlightthickness=0,
        )
        self.vista_previa.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        self.vista_previa.bind("<Configure>", self._dibujar_vista_previa)

        botones = ctk.CTkFrame(self, fg_color="transparent")
        botones.pack(fill="x", padx=18, pady=(0, 14))
        navegacion = ctk.CTkFrame(botones, fg_color="transparent")
        navegacion.pack(side="left")
        self.btn_anterior = BotonDegradado(
            navegacion,
            text="◀ Anterior",
            command=lambda: self._cambiar_pagina(-1),
            width=110,
        )
        self.btn_anterior.pack(side="left", padx=(0, 8))
        self.btn_siguiente = BotonDegradado(
            navegacion,
            text="Siguiente ▶",
            command=lambda: self._cambiar_pagina(1),
            width=110,
        )
        self.btn_siguiente.pack(side="left")
        BotonDegradado(
            botones,
            text="📄 Guardar y abrir todas las hojas (PDF)",
            command=self.guardar_y_abrir_pdf,
        ).pack(side="right", padx=(8, 0))
        BotonDegradado(
            botones,
            text="Cerrar",
            fg_color="gray",
            hover_color="gray30",
            command=self.destroy,
        ).pack(side="right")
        self._actualizar_navegacion()

    def _dibujar_vista_previa(self, _evento=None) -> None:
        numero_mesa, pareja1, pareja2 = self.mesas[self.indice_mesa]
        self.lbl_pagina_mesa.configure(
            text=f"Mesa {numero_mesa} — Hoja {self.indice_mesa + 1} de {len(self.mesas)}"
        )
        self.title(f"Vista previa - Mesa {numero_mesa} de {len(self.mesas)}")
        lienzo = self.vista_previa
        lienzo.delete("all")
        ancho_lienzo = lienzo.winfo_width()
        alto_lienzo = lienzo.winfo_height()
        relacion = TAMANO_PAGINA[0] / TAMANO_PAGINA[1]
        ancho_pagina = min(ancho_lienzo - 28, (alto_lienzo - 28) * relacion)
        if ancho_pagina <= 0:
            return
        alto_pagina = ancho_pagina / relacion
        izquierda = (ancho_lienzo - ancho_pagina) / 2
        arriba = (alto_lienzo - alto_pagina) / 2
        derecha = izquierda + ancho_pagina
        abajo = arriba + alto_pagina

        lienzo.create_rectangle(
            izquierda,
            arriba,
            derecha,
            abajo,
            fill="white",
            outline="#a3a3a3",
        )

        # Escala única de toda la página: el PDF trabaja en puntos y la
        # previsualización en píxeles.
        escala = ancho_pagina / TAMANO_PAGINA[0]

        def pos_x(fraccion: float) -> float:
            return izquierda + ancho_pagina * fraccion

        lienzo.create_text(
            izquierda + MARGEN_HOJA * escala,
            arriba + MARGEN_HOJA * escala,
            text=self.nombre_torneo,
            anchor="sw",
            fill="#111827",
            font=tkfont.Font(
                family="Arial",
                size=-max(6, int(round(10 * escala))),
            ),
        )
        lienzo.create_text(
            derecha - MARGEN_HOJA * escala,
            arriba + MARGEN_HOJA * escala,
            text=f"Ronda {self.numero_ronda} | Mesa {numero_mesa}",
            anchor="se",
            fill="#111827",
            font=tkfont.Font(
                family="Arial",
                size=-max(6, int(round(10 * escala))),
            ),
        )

        # Misma geometría que el PDF (ver hoja_mesa.py), escalada a la vista previa.

        # La vista previa dibuja con Arial; medir con esa misma fuente mantiene
        # el recorte y el tamaño alineados con el texto que renderiza Tk.
        fuente_cache: dict[tuple[bool, int], tkfont.Font] = {}

        def fuente_tk(tamano_pt: float, negrita: bool = False) -> tkfont.Font:
            # Tk interpreta un tamaño negativo como píxeles; aplicar la escala
            # de la página alinea la vista previa con la geometría del PDF.
            px = max(6, int(round(tamano_pt * escala)))
            clave = (negrita, px)
            if clave not in fuente_cache:
                fuente_cache[clave] = tkfont.Font(
                    family="Arial",
                    size=-px,
                    weight="bold" if negrita else "normal",
                )
            return fuente_cache[clave]

        def ajustar_texto_previsualizacion(
            texto: str,
            tamano_pt: float,
            ancho_pt: float,
            negrita: bool = False,
        ) -> tuple[str, float]:
            # Medir con la misma fuente que se renderiza evita que las métricas
            # de ReportLab provoquen una reducción exagerada o insuficiente.
            tamano = float(tamano_pt)
            while tamano > 7:
                fuente = fuente_tk(tamano, negrita)
                if fuente.measure(texto) <= ancho_pt * escala:
                    break
                tamano -= 1

            fuente = fuente_tk(tamano, negrita)
            if fuente.measure(texto) > ancho_pt * escala:
                while len(texto) > 1 and fuente.measure(texto + "...") > ancho_pt * escala:
                    texto = texto[:-1]
                texto = texto.rstrip() + "..."
            return texto, tamano

        def texto_ajustado(
            texto: str,
            x: float,
            y: float,
            ancho_pt: float,
            tamano_pt: float,
            negrita: bool = False,
            color: str = "#111827",
        ) -> None:
            texto, tamano = ajustar_texto_previsualizacion(
                texto, tamano_pt, ancho_pt, negrita
            )
            lienzo.create_text(
                x,
                y,
                text=texto,
                anchor="s",
                fill=color,
                font=fuente_tk(tamano, negrita),
            )

        def dibujar_tarjeta(
            jugador: JugadorHoja,
            x_col: float,
            ancho_col: float,
            posicion: int,
        ) -> None:
            x_izq = izquierda + x_col * escala
            x_der = x_izq + ancho_col * escala
            x_div = x_izq + ANCHO_ZONA_NUMERO * escala
            y_sup = arriba + distancia_superior_tarjeta(posicion) * escala
            y_inf = y_sup + ALTO_TARJETA * escala

            lienzo.create_rectangle(
                x_izq, y_sup, x_der, y_inf, outline="#737373", width=1
            )
            lienzo.create_line(x_div, y_sup, x_div, y_inf, fill="#737373")

            centro_numero = (x_izq + x_div) / 2
            texto_ajustado(
                "JUGADOR",
                centro_numero,
                y_sup + DESPLAZ_ETIQUETA_NUMERO * escala,
                ANCHO_ZONA_NUMERO - 6,
                7,
                color="#6b7280",
            )
            texto_ajustado(
                formatear_valor(jugador.numero),
                centro_numero,
                y_sup + DESPLAZ_NUMERO * escala,
                ANCHO_ZONA_NUMERO - 6,
                20,
                negrita=True,
            )

            ancho_zona = ancho_col - ANCHO_ZONA_NUMERO
            centro_zona = (x_div + x_der) / 2
            texto_ajustado(
                jugador.nombre,
                centro_zona,
                y_sup + DESPLAZ_NOMBRE * escala,
                ancho_zona - 12,
                11,
                negrita=True,
            )
            lienzo.create_line(
                x_div + 8 * escala,
                y_sup + DESPLAZ_DIVISOR * escala,
                x_der - 8 * escala,
                y_sup + DESPLAZ_DIVISOR * escala,
                fill="#d1d5db",
            )
            ancho_celda = ancho_zona / 3
            for numero_celda, (etiqueta, valor) in enumerate(
                estadisticas_jugador(jugador)
            ):
                centro_celda = x_div + ancho_celda * (numero_celda + 0.5) * escala
                texto_ajustado(
                    etiqueta,
                    centro_celda,
                    y_sup + DESPLAZ_ETIQUETA_ESTADISTICA * escala,
                    ancho_celda - 6,
                    7,
                    color="#6b7280",
                )
                texto_ajustado(
                    valor,
                    centro_celda,
                    y_sup + DESPLAZ_VALOR_ESTADISTICA * escala,
                    ancho_celda - 6,
                    12,
                    negrita=True,
                )

        for indice, ((x_col, ancho_col), jugadores) in enumerate(
            zip(geometria_columnas(TAMANO_PAGINA[0]), (pareja1, pareja2)),
            start=1,
        ):
            texto_ajustado(
                f"Pareja {indice}",
                izquierda + (x_col + ancho_col / 2) * escala,
                arriba + (MARGEN_HOJA + DISTANCIA_TITULO_PAREJA) * escala,
                ancho_col,
                14,
                negrita=True,
            )
            for posicion, jugador in enumerate(jugadores):
                dibujar_tarjeta(
                    como_jugador_hoja(jugador), x_col, ancho_col, posicion
                )

        lienzo.create_line(
            pos_x(0.5),
            arriba + alto_pagina * 0.035,
            pos_x(0.5),
            abajo - alto_pagina * 0.045,
            fill="#9ca3af",
            width=2,
        )

    def _cambiar_pagina(self, desplazamiento: int) -> None:
        self.indice_mesa += desplazamiento
        self._actualizar_navegacion()
        self._dibujar_vista_previa()

    def _actualizar_navegacion(self) -> None:
        self.btn_anterior.configure(
            state="normal" if self.indice_mesa > 0 else "disabled"
        )
        self.btn_siguiente.configure(
            state=(
                "normal"
                if self.indice_mesa < len(self.mesas) - 1
                else "disabled"
            )
        )

    def guardar_y_abrir_pdf(self) -> None:
        ruta = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar hojas de mesa",
            defaultextension=".pdf",
            initialfile=f"Hojas_Ronda_{self.numero_ronda}.pdf",
            filetypes=(("Documento PDF", "*.pdf"),),
        )
        if not ruta:
            return

        try:
            archivo = generar_pdf_hoja_mesa(
                ruta,
                self.nombre_torneo,
                self.numero_ronda,
                self.mesas,
            )
        except (OSError, UnicodeError, ValueError) as error:
            messagebox.showerror(
                "Error al generar PDF",
                f"No se pudo generar la hoja de mesa:\n{error}",
                parent=self,
            )
            return

        try:
            os.startfile(str(archivo))
        except OSError as error:
            messagebox.showerror(
                "No se pudo abrir el PDF",
                f"El PDF se guardó en:\n{archivo}\n\n"
                f"Pero no se pudo abrir con la aplicación predeterminada:\n{error}",
                parent=self,
            )


class VentanaEditarDisposicionMesa(VentanaModal):
    """Modal para reordenar los cuatro participantes de una mesa."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        mesa: dict,
        al_guardar: callable,
    ) -> None:
        super().__init__(parent)
        self.mesa_id = mesa["id"]
        self.al_guardar = al_guardar
        self.jugadores = [
            mesa["j1_cedula"],
            mesa["j2_cedula"],
            mesa["j3_cedula"],
            mesa["j4_cedula"],
        ]
        self.nombres = {
            mesa["j1_cedula"]: mesa["j1_nom"],
            mesa["j2_cedula"]: mesa["j2_nom"],
            mesa["j3_cedula"]: mesa["j3_nom"],
            mesa["j4_cedula"]: mesa["j4_nom"],
        }

        self.title(f"Editar disposición - Mesa {mesa['numero_mesa']}")
        self.geometry("500x360")
        self.resizable(False, False)
        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(
            self,
            text="👥 Editar disposición de participantes",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(15, 5))
        ctk.CTkLabel(
            self,
            text="Reordena los cuatro participantes de esta mesa. El marcador se conserva.",
            wraplength=440,
        ).pack(pady=(0, 12))

        opciones = [f"{cedula} - {self.nombres[cedula]}" for cedula in self.jugadores]
        self.mapa_opciones = dict(zip(opciones, self.jugadores))
        formulario = ctk.CTkFrame(self)
        formulario.pack(fill="x", padx=25, pady=5)
        self.combos: list[ctk.CTkComboBox] = []
        for indice, cedula in enumerate(self.jugadores):
            ctk.CTkLabel(
                formulario,
                text=f"Posición {indice + 1}:",
                width=100,
                anchor="w",
            ).grid(row=indice, column=0, padx=10, pady=6, sticky="w")
            combo = ctk.CTkComboBox(
                formulario,
                values=opciones,
                state="readonly",
                width=290,
            )
            combo.set(f"{cedula} - {self.nombres[cedula]}")
            combo.grid(row=indice, column=1, padx=10, pady=6)
            self.combos.append(combo)

        self._guardando = False
        self.btn_guardar = BotonDegradado(
            self,
            text="💾 Guardar disposición",
            font=ctk.CTkFont(weight="bold"),
            command=self.guardar,
        )
        self.btn_guardar.pack(fill="x", padx=25, pady=18)

    def guardar(self) -> None:
        if getattr(self, "_guardando", False):
            return
        self._guardando = True
        if self.winfo_exists():
            self.btn_guardar.configure(state="disabled")
            for combo in self.combos:
                combo.configure(state="disabled")
        try:
            seleccionados = [
                self.mapa_opciones.get(combo.get())
                for combo in self.combos
            ]
            if any(cedula is None for cedula in seleccionados):
                messagebox.showwarning("Atención", "Seleccione un participante válido en cada posición.", parent=self)
                return
            if len(set(seleccionados)) != 4:
                messagebox.showwarning(
                    "Atención",
                    "Cada participante debe ocupar una sola posición.",
                    parent=self,
                )
                return
            repo.editar_disposicion_mesa(self.mesa_id, seleccionados)
            self.al_guardar()
            messagebox.showinfo(
                "Éxito",
                "La disposición de la mesa fue actualizada y registrada en el historial.",
                parent=self,
            )
            self.destroy()
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e), parent=self)
        finally:
            if self.winfo_exists():
                self._guardando = False
                self.btn_guardar.configure(state="normal")
                for combo in self.combos:
                    combo.configure(state="normal")


class VentanaSwapExternoMesa(VentanaModal):
    """Modal para intercambiar un asiento entre dos mesas de una ronda."""

    def __init__(self, parent: ctk.CTkFrame, mesa_origen: dict, mesas: list[dict], al_guardar: callable) -> None:
        super().__init__(parent)
        self.mesa_origen = mesa_origen
        self.mesas = mesas
        self.al_guardar = al_guardar
        self.mapa_mesas = {
            f"Mesa {mesa['numero_mesa']} - {mesa['j1_nom']} / {mesa['j2_nom']} vs "
            f"{mesa['j3_nom']} / {mesa['j4_nom']}": mesa
            for mesa in mesas
            if mesa["id"] != mesa_origen["id"]
        }
        self.mapa_jugadores_origen = {
            f"{mesa_origen[f'j{i}_cedula']} - {mesa_origen[f'j{i}_nom']}": i - 1
            for i in range(1, 5)
        }

        self.title(f"Swap externo - Mesa {mesa_origen['numero_mesa']}")
        self.geometry("620x340")
        self.resizable(False, False)
        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(
            self,
            text="🔄 Swap externo entre mesas",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(15, 5))
        ctk.CTkLabel(
            self,
            text="Intercambia un participante de la mesa seleccionada por uno de otra mesa de la misma ronda. "
                 "Los marcadores se conservan.",
            wraplength=570,
        ).pack(pady=(0, 12))

        formulario = ctk.CTkFrame(self)
        formulario.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(formulario, text="Mesa destino:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.combo_mesa = ctk.CTkComboBox(
            formulario,
            values=list(self.mapa_mesas) or ["No hay otra mesa disponible"],
            state="readonly",
            width=400,
            command=self.cargar_jugadores_destino,
        )
        self.combo_mesa.grid(row=0, column=1, padx=10, pady=8)
        if self.mapa_mesas:
            self.combo_mesa.set(next(iter(self.mapa_mesas)))

        ctk.CTkLabel(formulario, text="Participante de origen:").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.combo_origen = ctk.CTkComboBox(
            formulario, values=list(self.mapa_jugadores_origen), state="readonly", width=400
        )
        self.combo_origen.grid(row=1, column=1, padx=10, pady=8)
        self.combo_origen.set(next(iter(self.mapa_jugadores_origen)))

        ctk.CTkLabel(formulario, text="Participante destino:").grid(row=2, column=0, padx=10, pady=8, sticky="w")
        self.combo_destino = ctk.CTkComboBox(formulario, values=[""], state="readonly", width=400)
        self.combo_destino.grid(row=2, column=1, padx=10, pady=8)
        self.cargar_jugadores_destino(self.combo_mesa.get())

        self._guardando = False
        self.btn_guardar = BotonDegradado(
            self,
            text="💾 Confirmar swap externo",
            font=ctk.CTkFont(weight="bold"),
            command=self.guardar,
        )
        self.btn_guardar.pack(fill="x", padx=25, pady=18)

    def cargar_jugadores_destino(self, valor: str) -> None:
        mesa = self.mapa_mesas.get(valor)
        if mesa is None:
            self.combo_destino.configure(values=[""])
            self.combo_destino.set("")
            return
        opciones = [
            f"{mesa[f'j{i}_cedula']} - {mesa[f'j{i}_nom']}"
            for i in range(1, 5)
        ]
        self.combo_destino.configure(values=opciones)
        self.combo_destino.set(opciones[0])

    def guardar(self) -> None:
        if getattr(self, "_guardando", False):
            return
        self._guardando = True
        if self.winfo_exists():
            self.btn_guardar.configure(state="disabled")
            for combo in (self.combo_mesa, self.combo_origen, self.combo_destino):
                combo.configure(state="disabled")
        try:
            mesa_destino = self.mapa_mesas.get(self.combo_mesa.get())
            posicion_origen = self.mapa_jugadores_origen.get(self.combo_origen.get())
            if mesa_destino is None or posicion_origen is None:
                messagebox.showwarning("Atención", "Seleccione una mesa y participantes válidos.", parent=self)
                return
            opciones_destino = [
                f"{mesa_destino[f'j{i}_cedula']} - {mesa_destino[f'j{i}_nom']}"
                for i in range(1, 5)
            ]
            posicion_destino = opciones_destino.index(self.combo_destino.get())
            repo.realizar_swap_externo(
                self.mesa_origen["id"],
                mesa_destino["id"],
                posicion_origen,
                posicion_destino,
            )
            self.al_guardar()
            messagebox.showinfo(
                "Éxito",
                "El swap externo fue aplicado y registrado en el historial.",
                parent=self,
            )
            self.destroy()
        except (ValueError, repo.ErrorDatos) as e:
            messagebox.showerror("Error", str(e), parent=self)
        finally:
            if self.winfo_exists():
                self._guardando = False
                self.btn_guardar.configure(state="normal")
                for combo in (self.combo_mesa, self.combo_origen, self.combo_destino):
                    combo.configure(state="normal")


class VentanaForfeitMesa(VentanaModal):
    """Modal para la aplicación de sanciones / Forfeits en mesa."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        mesa_id: int,
        torneo_id: int,
        info_mesa: str,
        al_guardar: callable,
    ) -> None:
        super().__init__(parent)
        self.mesa_id = mesa_id
        self.torneo_id = torneo_id
        self.al_guardar = al_guardar

        self.title("Registrar forfeit / abandono")
        self.geometry("500x500")
        self.resizable(False, False)

        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(self, text="⚠️ Declarar forfeit / sanción", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(self, text=info_mesa, font=ctk.CTkFont(size=12), wraplength=420).pack(pady=(0, 10))

        ctk.CTkLabel(self, text="Seleccione ganador por forfeit:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(5, 2))
        self.combo_ganador = ctk.CTkComboBox(
            self,
            values=["1 - Gana pareja 1", "2 - Gana pareja 2", "0 - Doble forfeit (ambas pierden 0-0)"],
            state="readonly",
            width=400,
        )
        self.combo_ganador.set("1 - Gana pareja 1")
        self.combo_ganador.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(
            self,
            text="Participantes activos a retirar (opcional):",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=20, pady=(5, 2))

        participantes_frame = ctk.CTkFrame(self)
        participantes_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        participantes_frame.grid_rowconfigure(0, weight=1)
        participantes_frame.grid_columnconfigure(0, weight=1)

        self.tabla_retirar = ttk.Treeview(
            participantes_frame,
            columns=("cedula", "nombre", "sexo"),
            show="headings",
            selectmode="extended",
            height=6,
        )
        for columna, texto in {"cedula": "Cédula", "nombre": "Nombre", "sexo": "Sexo"}.items():
            self.tabla_retirar.heading(columna, text=texto)
        self.tabla_retirar.column("cedula", width=130)
        self.tabla_retirar.column("nombre", width=240)
        self.tabla_retirar.column("sexo", width=60, anchor="center")
        self.tabla_retirar.grid(row=0, column=0, sticky="nsew")

        scroll_retirar = ttk.Scrollbar(
            participantes_frame,
            orient="vertical",
            command=self.tabla_retirar.yview,
        )
        scroll_retirar.grid(row=0, column=1, sticky="ns")
        self.tabla_retirar.configure(yscrollcommand=scroll_retirar.set)

        for participante in repo.listar_jugadores_de_torneo(self.torneo_id):
            self.tabla_retirar.insert(
                "",
                "end",
                values=(participante["cedula"], participante["nombre"], participante["sexo"]),
            )

        self._guardando = False
        self.btn_aplicar = BotonDegradado(
            self,
            text="🚫 Aplicar forfeit",
            fg_color="#D32F2F",
            hover_color="#9A0007",
            font=ctk.CTkFont(weight="bold"),
            command=self.aplicar,
        )
        self.btn_aplicar.pack(fill="x", padx=20, pady=5)

    def aplicar(self) -> None:
        if getattr(self, "_guardando", False):
            return
        self._guardando = True
        if self.winfo_exists():
            self.btn_aplicar.configure(state="disabled")
            self.combo_ganador.configure(state="disabled")
        try:
            ganador_op = self.combo_ganador.get()
            pareja_ganadora = 1
            if "2" in ganador_op:
                pareja_ganadora = 2
            elif "0" in ganador_op:
                pareja_ganadora = 0

            cedulas_retirar = [
                self.tabla_retirar.item(item, "values")[0]
                for item in self.tabla_retirar.selection()
            ]

            torneo_antes = repo.obtener_torneo(self.torneo_id)
            repo.registrar_forfeit_mesa(self.mesa_id, pareja_ganadora, cedulas_retirar)
            torneo_despues = repo.obtener_torneo(self.torneo_id)
            finalizado_ahora = (
                torneo_antes is not None
                and torneo_antes["estado"] != "finalizado"
                and torneo_despues is not None
                and torneo_despues["estado"] == "finalizado"
            )
            self.al_guardar()
            if finalizado_ahora:
                messagebox.showinfo(
                    "Torneo finalizado",
                    "El forfeit fue registrado. El torneo ha finalizado y la vista "
                    "En vivo / rondas se limpió.",
                    parent=self,
                )
            else:
                messagebox.showinfo("Éxito", "Forfeit procesado exitosamente.", parent=self)
            self.destroy()
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e), parent=self)
        finally:
            if self.winfo_exists():
                self._guardando = False
                self.btn_aplicar.configure(state="normal")
                self.combo_ganador.configure(state="normal")


class VentanaPenalizaciones(VentanaModal):
    """Modal para administrar faltas y expulsiones disciplinarias."""

    def __init__(self, parent: ctk.CTkFrame, torneo_id: int, al_guardar: callable) -> None:
        super().__init__(parent)
        self.torneo_id = torneo_id
        self.al_guardar = al_guardar
        torneo = repo.obtener_torneo(torneo_id)

        self.title("Penalizaciones")
        self.geometry("760x480")
        self.minsize(650, 380)
        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(
            self,
            text=f"⚠️ Penalizaciones - {torneo['nombre'] if torneo else 'Torneo'}",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(15, 5))
        ctk.CTkLabel(
            self,
            text="La tercera falta aplica tarjeta roja y retira al jugador del torneo. "
                 "La tarjeta roja directa también impide su reingreso.",
            wraplength=700,
        ).pack(pady=(0, 12))

        tabla_frame = ctk.CTkFrame(self)
        tabla_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)
        self.tabla = ttk.Treeview(
            tabla_frame,
            columns=("cedula", "nombre", "faltas", "estado"),
            show="headings",
            selectmode="browse",
        )
        for columna, texto in {
            "cedula": "Cédula",
            "nombre": "Jugador",
            "faltas": "Faltas",
            "estado": "Estado",
        }.items():
            self.tabla.heading(columna, text=texto)
        self.tabla.column("cedula", width=140)
        self.tabla.column("nombre", width=300)
        self.tabla.column("faltas", width=100, anchor="center")
        self.tabla.column("estado", width=150, anchor="center")
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tabla.configure(yscrollcommand=scroll.set)

        self.ent_motivo = ctk.CTkEntry(
            self,
            placeholder_text="Motivo de la penalización (opcional)",
        )
        self.ent_motivo.pack(fill="x", padx=20, pady=(0, 10))
        enlazar_enter_formulario(self.ent_motivo, accion_final=self.registrar_falta)

        botones = ctk.CTkFrame(self, fg_color="transparent")
        botones.pack(fill="x", padx=20, pady=(0, 15))
        BotonDegradado(
            botones,
            text="🟨 Registrar penalización",
            fg_color="#F1C40F",
            hover_color="#D4AC0D",
            text_color="#000000",
            command=self.registrar_falta,
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))
        BotonDegradado(
            botones,
            text="🟥 Tarjeta roja directa",
            fg_color="#D32F2F",
            hover_color="#9A0007",
            command=self.registrar_roja_directa,
        ).pack(side="left", expand=True, fill="x", padx=(5, 0))
        self.cargar_jugadores()

    def cargar_jugadores(self) -> None:
        _limpiar_treeview(self.tabla)
        for jugador in repo.listar_penalizaciones_torneo(self.torneo_id):
            faltas = int(jugador["faltas"])
            estado = "Descalificado" if jugador["tiene_roja"] else "Activo"
            self.tabla.insert(
                "",
                "end",
                values=(jugador["cedula"], jugador["nombre"], f"{faltas}/3", estado),
            )

    def jugador_seleccionado(self) -> str | None:
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Seleccione un jugador.", parent=self)
            return None
        return str(self.tabla.item(seleccion[0], "values")[0])

    def registrar_falta(self) -> None:
        cedula = self.jugador_seleccionado()
        if cedula is None:
            return
        try:
            mensaje = repo.registrar_penalizacion(
                self.torneo_id,
                cedula,
                self.ent_motivo.get().strip() or None,
            )
            messagebox.showinfo("Penalización registrada", mensaje, parent=self)
            self.ent_motivo.delete(0, "end")
            self.cargar_jugadores()
            self.al_guardar()
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e), parent=self)

    def registrar_roja_directa(self) -> None:
        cedula = self.jugador_seleccionado()
        if cedula is None:
            return
        if not messagebox.askyesno(
            "Confirmar tarjeta roja",
            "El jugador será retirado del torneo y no podrá volver a ingresar.\n\n"
            "Si su mesa actual ya tiene marcador, ese resultado se conserva y la "
            "expulsión se aplicará en la siguiente mesa donde sea emparejado.\n\n"
            "¿Continuar?",
            parent=self,
        ):
            return
        try:
            mensaje = repo.registrar_penalizacion(
                self.torneo_id,
                cedula,
                self.ent_motivo.get().strip() or None,
                roja_directa=True,
            )
            messagebox.showinfo("Tarjeta roja", mensaje, parent=self)
            self.ent_motivo.delete(0, "end")
            self.cargar_jugadores()
            self.al_guardar()
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e), parent=self)


class VentanaVetarJugador(VentanaModal):
    def __init__(self, parent: ctk.CTkFrame, cedula: str, nombre: str, al_guardar: callable) -> None:
        super().__init__(parent)
        self.cedula = cedula
        self.al_guardar = al_guardar
        self.title("Vetar jugador")
        self.geometry("430x250")
        self.resizable(False, False)
        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(
            self,
            text="🚫 Vetar jugador",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(18, 8))
        ctk.CTkLabel(
            self,
            text=f"{nombre} ({cedula})\nEl veto solo podrá levantarse manualmente.",
            justify="center",
        ).pack(pady=(0, 12))
        ctk.CTkLabel(self, text="Motivo del veto:").pack(anchor="w", padx=25)
        self.ent_motivo = ctk.CTkEntry(self, placeholder_text="Indique el motivo")
        self.ent_motivo.pack(fill="x", padx=25, pady=(3, 15))
        enlazar_enter_formulario(self.ent_motivo, accion_final=self.confirmar)
        BotonDegradado(
            self,
            text="Confirmar veto",
            fg_color="#B71C1C",
            hover_color="#7F0000",
            command=self.confirmar,
        ).pack(pady=5)

    def confirmar(self) -> None:
        try:
            repo.vetar_jugador(self.cedula, self.ent_motivo.get())
            messagebox.showinfo("Veto registrado", "El jugador ha sido vetado.", parent=self)
            self.al_guardar()
            self.destroy()
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e), parent=self)


class VentanaJugadoresVetados(VentanaModal):
    def __init__(self, parent: ctk.CTkFrame, al_cambiar: callable) -> None:
        super().__init__(parent)
        self.al_cambiar = al_cambiar
        self.title("Lista de jugadores vetados")
        self.geometry("760x430")
        self.minsize(650, 350)
        self.after(10, self.lift)
        self.after(10, self.activar_modal)
        self.focus_force()

        ctk.CTkLabel(
            self,
            text="🚫 Lista de jugadores vetados",
            font=ctk.CTkFont(size=19, weight="bold"),
        ).pack(pady=(15, 4))
        ctk.CTkLabel(
            self,
            text="Seleccione un jugador para levantar su veto manualmente.",
            text_color="gray",
        ).pack(pady=(0, 10))

        tabla_frame = ctk.CTkFrame(self)
        tabla_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)
        columnas = ("cedula", "nombre", "fecha", "motivo")
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", selectmode="browse")
        for columna, texto in {
            "cedula": "Cédula",
            "nombre": "Nombre",
            "fecha": "Fecha del veto",
            "motivo": "Motivo",
        }.items():
            self.tabla.heading(columna, text=texto)
        for columna, ancho in {
            "cedula": 125,
            "nombre": 200,
            "fecha": 145,
            "motivo": 250,
        }.items():
            self.tabla.column(columna, width=ancho, anchor="w")
        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        BotonDegradado(
            self,
            text="🔓 Levantar veto",
            fg_color="#2E7D32",
            hover_color="#1B5E20",
            command=self.levantar_veto,
        ).pack(pady=(0, 15))
        self.cargar_datos()

    def cargar_datos(self) -> None:
        _limpiar_treeview(self.tabla)
        for jugador in repo.listar_jugadores_vetados():
            self.tabla.insert(
                "",
                "end",
                values=(
                    jugador["cedula"],
                    jugador["nombre"],
                    jugador["fecha_hora"],
                    jugador["motivo"],
                ),
            )

    def levantar_veto(self) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Seleccione un jugador vetado.", parent=self)
            return
        valores = self.tabla.item(seleccion[0], "values")
        cedula, nombre = valores[0], valores[1]
        if not messagebox.askyesno(
            "Confirmar levantamiento",
            f"¿Desea levantar manualmente el veto de '{nombre}' ({cedula})?",
            parent=self,
        ):
            return
        try:
            repo.levantar_veto_jugador(cedula)
            self.cargar_datos()
            self.al_cambiar()
            messagebox.showinfo("Veto levantado", "El jugador puede volver a inscribirse.", parent=self)
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e), parent=self)


# ==========================================================================
# VISTAS PRINCIPALES
# ==========================================================================

class VistaJugadores(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame) -> None:
        super().__init__(parent, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        lbl_titulo = ctk.CTkLabel(self, text="Gestión de jugadores", font=ctk.CTkFont(size=22, weight="bold"))
        lbl_titulo.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 20), sticky="w")

        form_frame = ctk.CTkFrame(self, width=280)
        form_frame.grid(row=1, column=0, padx=(0, 15), sticky="nsew")

        lbl_form = ctk.CTkLabel(form_frame, text="Nuevo jugador", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_form.pack(pady=15, padx=15, anchor="w")

        ctk.CTkLabel(form_frame, text="Cédula:").pack(padx=15, anchor="w")
        self.ent_cedula = ctk.CTkEntry(form_frame, placeholder_text="Ej: V-12345678")
        self.ent_cedula.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(form_frame, text="Nombre completo:").pack(padx=15, anchor="w")
        self.ent_nombre = ctk.CTkEntry(form_frame, placeholder_text="Ej: Carlos Pérez")
        self.ent_nombre.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(form_frame, text="Sexo:").pack(padx=15, anchor="w")
        self.combo_sexo = ctk.CTkComboBox(form_frame, values=["M", "F"], state="normal")
        self.combo_sexo.set("M")
        self.combo_sexo.pack(fill="x", padx=15, pady=(0, 15))

        enlazar_enter_formulario(
            self.ent_cedula,
            self.ent_nombre,
            self.combo_sexo,
            accion_final=self.guardar_jugador,
        )

        btn_guardar = BotonDegradado(form_frame, text="💾 Registrar jugador", command=self.guardar_jugador)
        btn_guardar.pack(fill="x", padx=15, pady=5)
        BotonDegradado(
            form_frame,
            text="📋 Jugadores vetados",
            command=self.abrir_lista_vetados,
        ).pack(fill="x", padx=15, pady=(5, 15))

        tabla_container = ctk.CTkFrame(self)
        tabla_container.grid(row=1, column=1, sticky="nsew")
        tabla_container.grid_rowconfigure(0, weight=0)
        tabla_container.grid_rowconfigure(1, weight=1)
        tabla_container.grid_rowconfigure(2, weight=0)
        tabla_container.grid_columnconfigure(0, weight=1)

        filtro_frame = ctk.CTkFrame(tabla_container, fg_color="transparent")
        filtro_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(4, 0))
        filtro_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(filtro_frame, text="Buscar jugador:").grid(
            row=0, column=0, padx=(0, 6), pady=2
        )
        self.ent_busqueda = ctk.CTkEntry(
            filtro_frame,
            placeholder_text="Nombre, apellido o cédula",
            height=30,
        )
        self.ent_busqueda.grid(row=0, column=1, sticky="ew", pady=2)
        self.ent_busqueda.bind(
            "<KeyRelease>",
            lambda _evento: debounce(self, "_temporizador_busqueda", 250, self.cargar_datos),
        )
        self.ent_busqueda.bind("<Return>", lambda _evento: self.cargar_datos() or "break")
        self.ent_busqueda.bind("<KP_Enter>", lambda _evento: self.cargar_datos() or "break")

        ctk.CTkLabel(filtro_frame, text="Sexo:").grid(
            row=0, column=2, padx=(10, 5), pady=2
        )
        self.combo_filtro_sexo = ctk.CTkComboBox(
            filtro_frame,
            values=["Todos", "Hombres", "Mujeres"],
            state="normal",
            width=110,
            height=30,
            command=lambda _valor: self.cargar_datos(),
        )
        self.combo_filtro_sexo.set("Todos")
        self.combo_filtro_sexo.grid(row=0, column=3, pady=2)

        columnas = ("num", "cedula", "nombre", "sexo")
        self.tabla = ttk.Treeview(tabla_container, columns=columnas, show="headings", selectmode="browse")
        self.tabla.heading("num", text="N°")
        self.tabla.heading("cedula", text="Cédula")
        self.tabla.heading("nombre", text="Nombre completo")
        self.tabla.heading("sexo", text="Sexo")

        self.tabla.column("num", width=45, anchor="center")
        self.tabla.column("cedula", width=120)
        self.tabla.column("nombre", width=250)
        self.tabla.column("sexo", width=60, anchor="center")

        scroll = ttk.Scrollbar(tabla_container, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)

        self.tabla.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 8))
        scroll.grid(row=1, column=1, sticky="ns", pady=(5, 8))

        btn_box = ctk.CTkFrame(tabla_container, fg_color="transparent")
        btn_box.grid(row=2, column=0, columnspan=2, pady=(0, 10), padx=10, sticky="ew")

        BotonDegradado(btn_box, text="✏️ Editar", command=self.abrir_editar).pack(side="left", padx=(0, 5))
        BotonDegradado(btn_box, text="📜 Ver historial", command=self.abrir_historial).pack(side="left", padx=5)
        BotonDegradado(
            btn_box,
            text="X Vetar jugador",
            fg_color="#B71C1C",
            hover_color="#7F0000",
            command=self.abrir_veto,
        ).pack(side="left", padx=5)
        BotonDegradado(btn_box, text="🗑️ Eliminar", fg_color="#D32F2F", hover_color="#9A0007", command=self.eliminar_jugador).pack(side="right")

        self.cargar_datos()

    def cargar_datos(self) -> None:
        _limpiar_treeview(self.tabla)
        texto_busqueda = self.ent_busqueda.get().strip().casefold()
        sexo_filtro = {"Hombres": "M", "Mujeres": "F"}.get(
            self.combo_filtro_sexo.get()
        )
        jugadores = repo.listar_jugadores()
        jugadores_filtrados = [
            jugador
            for jugador in jugadores
            if (
                not texto_busqueda
                or texto_busqueda in str(jugador["nombre"]).casefold()
                or texto_busqueda in str(jugador["cedula"]).casefold()
            )
            and (sexo_filtro is None or jugador["sexo"] == sexo_filtro)
        ]
        for i, j in enumerate(jugadores_filtrados, start=1):
            self.tabla.insert("", "end", values=(i, j["cedula"], j["nombre"], j["sexo"]))

    def guardar_jugador(self) -> None:
        cedula = self.ent_cedula.get().strip()
        nombre = self.ent_nombre.get().strip()
        sexo = self.combo_sexo.get().strip()

        if not cedula or not nombre:
            messagebox.showwarning("Atención", "Todos los campos son obligatorios.")
            return

        try:
            repo.crear_jugador(cedula, nombre, sexo)
            self.ent_cedula.delete(0, "end")
            self.ent_nombre.delete(0, "end")
            self.cargar_datos()
            messagebox.showinfo("Éxito", f"Jugador '{nombre}' registrado.")
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))

    def abrir_editar(self) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Selecciona un jugador para editar.")
            return
        cedula = self.tabla.item(seleccion[0], "values")[1]
        VentanaEditarJugador(self, cedula, self.cargar_datos)

    def abrir_historial(self) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Selecciona un jugador para ver su historial.")
            return
        cedula = self.tabla.item(seleccion[0], "values")[1]
        VentanaHistorialJugador(self, cedula)

    def abrir_veto(self) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Seleccione un jugador para vetar.")
            return
        valores = self.tabla.item(seleccion[0], "values")
        if repo.esta_jugador_vetado(valores[1]):
            messagebox.showwarning(
                "Jugador ya vetado",
                f"El jugador '{valores[2]}' ({valores[1]}) ya tiene un veto registrado. "
                "Debe levantarlo manualmente desde 'Jugadores vetados' antes de realizar otra acción.",
            )
            return
        VentanaVetarJugador(self, valores[1], valores[2], self.cargar_datos)

    def abrir_lista_vetados(self) -> None:
        VentanaJugadoresVetados(self, self.cargar_datos)

    def eliminar_jugador(self) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Selecciona un jugador para eliminar.")
            return

        valores = self.tabla.item(seleccion[0], "values")
        cedula, nombre = valores[1], valores[2]

        if messagebox.askyesno("Confirmar", f"¿Desea eliminar a '{nombre}' (cédula: {cedula})?"):
            try:
                repo.eliminar_jugador(cedula)
                self.cargar_datos()
                messagebox.showinfo("Éxito", "Jugador eliminado correctamente.")
            except repo.ErrorDatos as e:
                messagebox.showerror("Error", str(e))


class VistaClubes(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame) -> None:
        super().__init__(parent, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        lbl_titulo = ctk.CTkLabel(self, text="Gestión de clubes", font=ctk.CTkFont(size=22, weight="bold"))
        lbl_titulo.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 20), sticky="w")

        left_frame = ctk.CTkFrame(self, width=280)
        left_frame.grid(row=1, column=0, padx=(0, 15), sticky="nsew")

        ctk.CTkLabel(left_frame, text="Crear nuevo club", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10, padx=15, anchor="w")

        ctk.CTkLabel(left_frame, text="Nombre del club:").pack(padx=15, anchor="w")
        self.ent_club_nombre = ctk.CTkEntry(left_frame, placeholder_text="Ej: Los Halcones")
        self.ent_club_nombre.pack(fill="x", padx=15, pady=(0, 10))

        enlazar_enter_formulario(self.ent_club_nombre, accion_final=self.crear_club)

        btn_crear = BotonDegradado(left_frame, text="➕ Crear club", command=self.crear_club)
        btn_crear.pack(fill="x", padx=15, pady=(0, 20))

        ctk.CTkLabel(left_frame, text="Asignar / retirar jugador", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10, padx=15, anchor="w")

        ctk.CTkLabel(left_frame, text="Jugador:").pack(padx=15, anchor="w")
        self.actualizar_opciones_jugadores()
        self.combo_jugador_miembro = EntryAutocompletado(
            left_frame,
            opciones=self.opciones_jugadores,
            on_select=self._al_elegir_jugador_miembro,
            on_change=lambda _texto: setattr(self, "jugador_miembro_seleccionado", None),
            placeholder_text=(
                "Ej: nombre, apellido o cédula" if self.opciones_jugadores else "No hay jugadores"
            ),
        )
        self.combo_jugador_miembro.pack(fill="x", padx=15, pady=(0, 10))
        self.jugador_miembro_seleccionado = None
        enlazar_enter_formulario(
            self.combo_jugador_miembro,
            accion_final=self.asignar_jugador,
        )

        btn_asignar = BotonDegradado(left_frame, text="📌 Asignar al club seleccionado", command=self.asignar_jugador)
        btn_asignar.pack(fill="x", padx=15, pady=4)

        btn_retirar = BotonDegradado(left_frame, text="🚪 Retirar del club seleccionado", fg_color="#D32F2F", hover_color="#9A0007", command=self.retirar_jugador)
        btn_retirar.pack(fill="x", padx=15, pady=4)

        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=0)
        right_frame.grid_rowconfigure(2, weight=1)
        right_frame.grid_rowconfigure(6, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right_frame, text="Clubes registrados:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(5, 0))

        filtro_clubes = ctk.CTkFrame(right_frame, fg_color="transparent")
        filtro_clubes.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 0))
        filtro_clubes.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(filtro_clubes, text="Buscar club:").grid(
            row=0, column=0, padx=(0, 6), pady=2
        )
        self.ent_busqueda_club = ctk.CTkEntry(
            filtro_clubes,
            placeholder_text="Nombre del club",
            height=30,
        )
        self.ent_busqueda_club.grid(row=0, column=1, sticky="ew", pady=2)
        self.ent_busqueda_club.bind(
            "<KeyRelease>",
            lambda _evento: debounce(self, "_temporizador_busqueda_club", 250, self.cargar_clubes),
        )
        self.ent_busqueda_club.bind("<Return>", lambda _evento: self.cargar_clubes() or "break")
        self.ent_busqueda_club.bind("<KP_Enter>", lambda _evento: self.cargar_clubes() or "break")

        tabla_clubes_frame = ctk.CTkFrame(right_frame)
        tabla_clubes_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        tabla_clubes_frame.grid_rowconfigure(0, weight=1)
        tabla_clubes_frame.grid_columnconfigure(0, weight=1)

        columnas_c = ("id", "nombre")
        self.tabla_clubes = ttk.Treeview(tabla_clubes_frame, columns=columnas_c, show="headings", selectmode="browse")
        self.tabla_clubes.heading("id", text="ID")
        self.tabla_clubes.heading("nombre", text="Nombre del club")
        self.tabla_clubes.column("id", width=60, anchor="center")
        self.tabla_clubes.column("nombre", width=300)
        self.tabla_clubes.bind("<<TreeviewSelect>>", self.on_club_seleccionado)

        scroll_c = ttk.Scrollbar(tabla_clubes_frame, orient="vertical", command=self.tabla_clubes.yview)
        self.tabla_clubes.configure(yscrollcommand=scroll_c.set)
        self.tabla_clubes.grid(row=0, column=0, sticky="nsew")
        scroll_c.grid(row=0, column=1, sticky="ns")

        btns_club_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        btns_club_frame.grid(row=3, column=0, sticky="e", padx=10, pady=6)

        btn_edit_club = BotonDegradado(btns_club_frame, text="✏️\u2002Editar club", fg_color="#D32F2F", hover_color="##9A0007", width=150, height=32, command=self.editar_club)
        btn_edit_club.pack(side="left", padx=(0, 10))

        btn_del_club = BotonDegradado(btns_club_frame, text="🗑\u2002Eliminar club seleccionado", fg_color="#D32F2F", hover_color="#9A0007", width=210, height=32, command=self.eliminar_club)
        btn_del_club.pack(side="left")

        ctk.CTkLabel(
            right_frame,
            text="Miembros del club seleccionado:",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=4, column=0, sticky="w", padx=10, pady=(10, 0))

        filtro_miembros = ctk.CTkFrame(right_frame, fg_color="transparent")
        filtro_miembros.grid(row=5, column=0, sticky="ew", padx=10, pady=(2, 0))
        filtro_miembros.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(filtro_miembros, text="Buscar miembro:").grid(
            row=0, column=0, padx=(0, 6), pady=2
        )
        self.ent_busqueda_miembro = ctk.CTkEntry(
            filtro_miembros,
            placeholder_text="Nombre, apellido o cédula",
            height=30,
        )
        self.ent_busqueda_miembro.grid(row=0, column=1, sticky="ew", pady=2)
        self.ent_busqueda_miembro.bind(
            "<KeyRelease>",
            lambda _evento: debounce(self, "_temporizador_busqueda_miembro", 250, self.cargar_miembros),
        )
        self.ent_busqueda_miembro.bind(
            "<Return>", lambda _evento: self.cargar_miembros() or "break"
        )
        self.ent_busqueda_miembro.bind(
            "<KP_Enter>", lambda _evento: self.cargar_miembros() or "break"
        )
        ctk.CTkLabel(filtro_miembros, text="Sexo").grid(
            row=0, column=2, padx=(10, 5), pady=2
        )
        self.combo_filtro_miembro_sexo = ctk.CTkComboBox(
            filtro_miembros,
            values=["Todos", "Hombres", "Mujeres"],
            state="normal",
            width=110,
            height=30,
            command=lambda _valor: self.cargar_miembros(),
        )
        self.combo_filtro_miembro_sexo.set("Todos")
        self.combo_filtro_miembro_sexo.grid(row=0, column=3, pady=2)

        tabla_miembros_frame = ctk.CTkFrame(right_frame)
        tabla_miembros_frame.grid(row=6, column=0, sticky="nsew", padx=10, pady=(5, 10))
        tabla_miembros_frame.grid_rowconfigure(0, weight=1)
        tabla_miembros_frame.grid_columnconfigure(0, weight=1)

        columnas_m = ("cedula", "nombre", "sexo")
        self.tabla_miembros = ttk.Treeview(tabla_miembros_frame, columns=columnas_m, show="headings")
        self.tabla_miembros.heading("cedula", text="Cédula")
        self.tabla_miembros.heading("nombre", text="Nombre")
        self.tabla_miembros.heading("sexo", text="Sexo")
        self.tabla_miembros.column("cedula", width=120)
        self.tabla_miembros.column("nombre", width=240)
        self.tabla_miembros.column("sexo", width=60, anchor="center")

        scroll_m = ttk.Scrollbar(tabla_miembros_frame, orient="vertical", command=self.tabla_miembros.yview)
        self.tabla_miembros.configure(yscrollcommand=scroll_m.set)
        self.tabla_miembros.grid(row=0, column=0, sticky="nsew")
        scroll_m.grid(row=0, column=1, sticky="ns")

        self.cargar_datos()

    def cargar_datos(self) -> None:
        self.cargar_clubes()
        self.actualizar_opciones_jugadores(repo.listar_jugadores())
        self.limpiar_miembros()

    def cargar_clubes(self) -> None:
        _limpiar_treeview(self.tabla_clubes)
        texto_busqueda = self.ent_busqueda_club.get().strip().casefold()
        clubes = repo.listar_clubes()
        for club in clubes:
            if (
                not texto_busqueda
                or texto_busqueda in str(club["nombre"]).casefold()
                or texto_busqueda in str(club["id"]).casefold()
            ):
                self.tabla_clubes.insert("", "end", values=(club["id"], club["nombre"]))

    def actualizar_opciones_jugadores(
        self, jugadores: list[sqlite3.Row] | None = None
    ) -> None:
        if jugadores is None:
            jugadores = repo.listar_jugadores()
        self.opciones_jugadores = {
            f"{jugador['nombre']} ({jugador['cedula']})": jugador["cedula"]
            for jugador in jugadores
        }
        if not hasattr(self, "combo_jugador_miembro"):
            return
        self.combo_jugador_miembro.establecer_opciones(self.opciones_jugadores)
        self.combo_jugador_miembro.delete(0, "end")
        self.combo_jugador_miembro.configure(
            placeholder_text=(
                "Ej: nombre, apellido o cédula" if self.opciones_jugadores else "No hay jugadores"
            )
        )
        self.jugador_miembro_seleccionado = None

    def _al_elegir_jugador_miembro(self, etiqueta: str, cedula) -> None:
        """Se dispara cuando el usuario elige una sugerencia de la lista."""
        self.jugador_miembro_seleccionado = cedula

    def limpiar_miembros(self) -> None:
        _limpiar_treeview(self.tabla_miembros)

    def on_club_seleccionado(self, event) -> None:
        seleccion = self.tabla_clubes.selection()
        if not seleccion:
            return
        club_id = int(self.tabla_clubes.item(seleccion[0], "values")[0])
        self.cargar_miembros(club_id)

    def cargar_miembros(self, club_id: int | None = None) -> None:
        self.limpiar_miembros()
        if club_id is None:
            seleccion = self.tabla_clubes.selection()
            if not seleccion:
                return
            club_id = int(self.tabla_clubes.item(seleccion[0], "values")[0])
        texto_busqueda = self.ent_busqueda_miembro.get().strip().casefold()
        sexo_filtro = {"Hombres": "M", "Mujeres": "F"}.get(
            self.combo_filtro_miembro_sexo.get()
        )
        miembros = [
            miembro
            for miembro in repo.listar_jugadores_de_club(club_id)
            if (
                not texto_busqueda
                or texto_busqueda in str(miembro["nombre"]).casefold()
                or texto_busqueda in str(miembro["cedula"]).casefold()
            )
            and (sexo_filtro is None or miembro["sexo"] == sexo_filtro)
        ]
        for m in miembros:
            self.tabla_miembros.insert("", "end", values=(m["cedula"], m["nombre"], m["sexo"]))

    def crear_club(self) -> None:
        nombre = self.ent_club_nombre.get().strip()
        if not nombre:
            messagebox.showwarning("Atención", "Ingresa un nombre para el club.")
            return
        try:
            repo.crear_club(nombre)
            self.ent_club_nombre.delete(0, "end")
            self.cargar_datos()
            messagebox.showinfo("Éxito", f"Club '{nombre}' creado.")
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))

    def editar_club(self) -> None:
        seleccion = self.tabla_clubes.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Selecciona un club en la tabla para editar.")
            return
        valores = self.tabla_clubes.item(seleccion[0], "values")
        VentanaEditarClub(self, int(valores[0]), self.cargar_datos)

    def asignar_jugador(self) -> None:
        seleccion = self.tabla_clubes.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Selecciona un club en la tabla superior.")
            return
        club_id = int(self.tabla_clubes.item(seleccion[0], "values")[0])
        texto = self.combo_jugador_miembro.get().strip()
        cedula = self.jugador_miembro_seleccionado or self.opciones_jugadores.get(texto)
        if cedula is None and texto:
            coincidencias = [
                cedula_jugador
                for etiqueta, cedula_jugador in self.opciones_jugadores.items()
                if texto.casefold() in etiqueta.casefold()
                or texto.casefold() == str(cedula_jugador).casefold()
            ]
            if len(coincidencias) == 1:
                cedula = coincidencias[0]
        if not cedula:
            messagebox.showwarning("Atención", "Selecciona un jugador de la lista.")
            return
        try:
            repo.asignar_jugador_a_club(cedula, club_id)
            self.combo_jugador_miembro.delete(0, "end")
            self.jugador_miembro_seleccionado = None
            self.on_club_seleccionado(None)
            messagebox.showinfo("Éxito", "Jugador asignado al club.")
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))

    def retirar_jugador(self) -> None:
        seleccion_club = self.tabla_clubes.selection()
        if not seleccion_club:
            messagebox.showwarning("Atención", "Selecciona un club en la tabla superior.")
            return
        club_id = int(self.tabla_clubes.item(seleccion_club[0], "values")[0])

        seleccion_miembro = self.tabla_miembros.selection()
        if not seleccion_miembro:
            messagebox.showwarning("Atención", "Selecciona un miembro de la lista.")
            return
        cedula = self.tabla_miembros.item(seleccion_miembro[0], "values")[0]
        try:
            repo.retirar_jugador_de_club(cedula, club_id)
            self.on_club_seleccionado(None)
            messagebox.showinfo("Éxito", "Jugador retirado del club.")
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))

    def eliminar_club(self) -> None:
        seleccion = self.tabla_clubes.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Selecciona un club para eliminar.")
            return
        valores = self.tabla_clubes.item(seleccion[0], "values")
        club_id, nombre = int(valores[0]), valores[1]
        if messagebox.askyesno("Confirmar", f"¿Desea eliminar el club '{nombre}' (ID: {club_id})?"):
            try:
                repo.eliminar_club(club_id)
                self.cargar_datos()
                self.limpiar_miembros()
                messagebox.showinfo("Éxito", "Club eliminado.")
            except repo.ErrorDatos as e:
                messagebox.showerror("Error", str(e))


class VentanaConfigurarAccesoHistorial(VentanaModal):
    """Configura una contraseña, un PIN y todas las respuestas de recuperación."""

    def __init__(self, parent, *, reemplazar: bool = False) -> None:
        super().__init__(parent, modal=True)
        self.title("Restablecer acceso" if reemplazar else "Configurar acceso")
        self.geometry("620x500" if reemplazar else "700x760")
        if reemplazar:
            self.minsize(580, 440)
        else:
            self.minsize(580, 520)
        self.configurada = False
        self.reemplazar = reemplazar
        self.transient(parent.winfo_toplevel())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        titulo = (
            "Restablecer contraseña\ny PIN"
            if reemplazar
            else "Primer acceso a torneos finalizados"
        )
        ctk.CTkLabel(
            self,
            text=titulo,
            font=ctk.CTkFont(size=18, weight="bold"),
            justify="center",
        ).grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        ctk.CTkLabel(
            self,
            text=(
                "Define una nueva contraseña y un nuevo PIN. Se conservarán las preguntas de recuperación."
                if reemplazar
                else "Crea una contraseña, un PIN de emergencia y responde todas las preguntas."
            ),
            wraplength=540 if reemplazar else 620,
            justify="center",
            anchor="center",
        ).grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 16))

        formulario = ctk.CTkScrollableFrame(self)
        formulario.grid(row=2, column=0, sticky="nsew", padx=18, pady=5)
        formulario.grid_columnconfigure(1, weight=1)

        self.entradas_credenciales = {}
        campos = (
            ("password", "Nueva contraseña", "*"),
            ("password_confirm", "Confirmar contraseña", "*"),
            ("pin", "PIN de emergencia (4 a 8 dígitos)", "*"),
            ("pin_confirm", "Confirmar PIN", "*"),
        )
        for fila, (clave, etiqueta, ocultar) in enumerate(campos):
            ctk.CTkLabel(formulario, text=etiqueta).grid(
                row=fila, column=0, sticky="w", padx=(8, 12), pady=6
            )
            entrada = ctk.CTkEntry(formulario, show=ocultar)
            entrada.grid(row=fila, column=1, sticky="ew", padx=8, pady=6)
            self.entradas_credenciales[clave] = entrada

        self.entradas_respuestas = {}
        if not reemplazar:
            ctk.CTkLabel(
                formulario,
                text="Responde obligatoriamente las nueve preguntas. Se mostrarán en orden aleatorio.",
                font=ctk.CTkFont(weight="bold"),
                wraplength=590,
            ).grid(row=len(campos), column=0, columnspan=2, sticky="w", padx=8, pady=(15, 5))
            preguntas = list(history_auth.PREGUNTAS_SEGURIDAD)
            random.shuffle(preguntas)
            for indice, (clave, pregunta) in enumerate(preguntas):
                ctk.CTkLabel(formulario, text=pregunta, wraplength=570, justify="left").grid(
                    row=len(campos) + 1 + indice * 2,
                    column=0,
                    columnspan=2,
                    sticky="w",
                    padx=8,
                    pady=(8, 1),
                )
                entrada = ctk.CTkEntry(formulario)
                entrada.grid(
                    row=len(campos) + 2 + indice * 2,
                    column=0,
                    columnspan=2,
                    sticky="ew",
                    padx=8,
                    pady=(0, 4),
                )
                self.entradas_respuestas[clave] = entrada

        self.btn_guardar = BotonDegradado(
            self, text="Guardar credenciales", command=self._guardar
        )
        self.btn_guardar.grid(row=3, column=0, padx=20, pady=(8, 18))
        dimensiones = (620, 500) if reemplazar else (700, 760)
        self.after_idle(
            lambda: _centrar_ventana_en_pantalla(self, *dimensiones)
        )
        self.after(0, self.activar_modal)
        self.after(50, self.entradas_credenciales["password"].focus_set)

    def _guardar(self) -> None:
        contrasena = self.entradas_credenciales["password"].get()
        confirmacion = self.entradas_credenciales["password_confirm"].get()
        pin = self.entradas_credenciales["pin"].get()
        pin_confirmacion = self.entradas_credenciales["pin_confirm"].get()
        if contrasena != confirmacion or pin != pin_confirmacion:
            messagebox.showwarning(
                "Datos distintos",
                "La confirmación de la contraseña y del PIN debe coincidir.",
                parent=self,
            )
            return
        respuestas = None
        if not self.reemplazar:
            respuestas = {
                clave: entrada.get() for clave, entrada in self.entradas_respuestas.items()
            }
        try:
            history_auth.configurar_credenciales(
                contrasena, pin, respuestas, reemplazar=self.reemplazar
            )
        except ValueError as error:
            messagebox.showwarning("Revisa los datos", str(error), parent=self)
            return
        except sqlite3.Error as error:
            messagebox.showerror(
                "No se pudo guardar",
                f"No fue posible guardar las credenciales: {error}",
                parent=self,
            )
            return
        self.configurada = True
        self.destroy()


class VentanaRecuperarHistorial(VentanaModal):
    """Verifica al menos tres respuestas antes de permitir el restablecimiento."""

    def __init__(self, parent) -> None:
        super().__init__(parent, modal=True)
        self.title("Recuperar acceso")
        self.geometry("700x700")
        self.minsize(580, 500)
        self.respuestas_validas = False
        self.transient(parent.winfo_toplevel())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            self,
            text="Responde al menos tres preguntas correctamente para restablecer el acceso.",
            font=ctk.CTkFont(size=16, weight="bold"),
            wraplength=620,
        ).grid(row=0, column=0, padx=20, pady=(18, 10))

        formulario = ctk.CTkScrollableFrame(self)
        formulario.grid(row=1, column=0, sticky="nsew", padx=18, pady=5)
        formulario.grid_columnconfigure(0, weight=1)
        self.entradas_respuestas = {}
        preguntas = list(history_auth.PREGUNTAS_SEGURIDAD)
        random.shuffle(preguntas)
        for fila, (clave, pregunta) in enumerate(preguntas):
            ctk.CTkLabel(formulario, text=pregunta, wraplength=580, justify="left").grid(
                row=fila * 2, column=0, sticky="w", padx=8, pady=(8, 1)
            )
            entrada = ctk.CTkEntry(formulario)
            entrada.grid(row=fila * 2 + 1, column=0, sticky="ew", padx=8, pady=(0, 4))
            self.entradas_respuestas[clave] = entrada

        BotonDegradado(
            self, text="Ingresar respuestas", command=self._validar
        ).grid(row=2, column=0, padx=20, pady=(8, 18))
        self.after_idle(
            lambda: _centrar_ventana_en_pantalla(self, 700, 700)
        )
        self.after(0, self.activar_modal)
        self.after(50, next(iter(self.entradas_respuestas.values())).focus_set)

    def _validar(self) -> None:
        respuestas = {
            clave: entrada.get() for clave, entrada in self.entradas_respuestas.items()
        }
        contestadas = sum(bool(respuesta.strip()) for respuesta in respuestas.values())
        if contestadas < history_auth.RESPUESTAS_MINIMAS_RECUPERACION:
            messagebox.showwarning(
                "Faltan respuestas",
                "Debes contestar al menos tres preguntas para continuar.",
                parent=self,
            )
            return
        try:
            estado = history_auth.verificar_respuestas(respuestas)
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de recuperación",
                f"No fue posible verificar las respuestas: {error}",
                parent=self,
            )
            return
        if estado == "insufficient":
            messagebox.showwarning(
                "Faltan respuestas",
                "Ingresa al menos tres respuestas para continuar.",
                parent=self,
            )
            return
        if estado == "locked":
            minutos = max(1, (history_auth.segundos_bloqueo_restantes() + 59) // 60)
            messagebox.showerror(
                "Acceso temporalmente bloqueado",
                f"Demasiados intentos. Intenta de nuevo en aproximadamente {minutos} minutos.",
                parent=self,
            )
            return
        if estado != "ok":
            if estado == "not_configured":
                detalle = "Primero deben configurarse las preguntas de seguridad."
            else:
                detalle = "No se reconocieron tres respuestas correctas."
            messagebox.showerror("No se pudo recuperar el acceso", detalle, parent=self)
            return
        self.respuestas_validas = True
        self.destroy()


class VentanaClaveHistorial(VentanaModal):
    """Solicita la contraseña o el PIN de emergencia para el historial."""

    def __init__(self, parent) -> None:
        super().__init__(parent, modal=True)
        self.title("Acceso al historial")
        self.geometry("420x240")
        self.resizable(False, False)
        self.clave_valida = False
        self.transient(parent.winfo_toplevel())

        ctk.CTkLabel(
            self,
            text="Ingresa la contraseña o el PIN de emergencia:",
            font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=360,
        ).pack(padx=20, pady=(22, 8))
        self.entrada_clave = ctk.CTkEntry(self, show="*", width=300)
        self.entrada_clave.pack(padx=20, pady=5)
        self.entrada_clave.bind("<Return>", lambda _evento: self._validar())
        BotonDegradado(self, text="Continuar", command=self._validar).pack(
            padx=20, pady=(8, 4)
        )
        ctk.CTkButton(
            self,
            text="Olvidé la contraseña y el PIN",
            fg_color="transparent",
            command=self._recuperar,
        ).pack(padx=20, pady=(0, 12))
        self.after_idle(
            lambda: _centrar_ventana_en_pantalla(self, 420, 240)
        )
        self.after(0, self.activar_modal)
        self.after(50, self.entrada_clave.focus_set)

    def _validar(self) -> None:
        try:
            estado = history_auth.verificar_credencial(self.entrada_clave.get())
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de acceso",
                f"No fue posible verificar las credenciales: {error}",
                parent=self,
            )
            return
        if estado == "locked":
            minutos = max(1, (history_auth.segundos_bloqueo_restantes() + 59) // 60)
            mensaje = f"Demasiados intentos. Intenta de nuevo en aproximadamente {minutos} minutos."
        elif estado == "not_configured":
            mensaje = "Debes configurar el acceso antes de entrar."
        else:
            mensaje = "La contraseña o el PIN ingresado no es correcto."
        if estado != "ok":
            messagebox.showerror("Acceso denegado", mensaje, parent=self)
            self.entrada_clave.delete(0, "end")
            self.entrada_clave.focus_set()
            return
        self.clave_valida = True
        self.destroy()

    def _recuperar(self) -> None:
        recuperacion = VentanaRecuperarHistorial(self)
        self.wait_window(recuperacion)
        if not recuperacion.respuestas_validas:
            return
        restablecer = VentanaConfigurarAccesoHistorial(self, reemplazar=True)
        self.wait_window(restablecer)
        if restablecer.configurada:
            self.clave_valida = True
            self.destroy()


def solicitar_clave_historial(parent) -> bool:
    """Configura las credenciales al primer uso o autentica el acceso."""
    try:
        configurado = history_auth.esta_configurado()
    except sqlite3.Error as error:
        messagebox.showerror(
            "Error de acceso",
            f"No fue posible consultar la configuración de seguridad: {error}",
            parent=parent,
        )
        return False

    if not configurado:
        configuracion = VentanaConfigurarAccesoHistorial(parent)
        parent.wait_window(configuracion)
        return configuracion.configurada

    dialogo = VentanaClaveHistorial(parent)
    parent.wait_window(dialogo)
    return dialogo.clave_valida


class VentanaHistorialTorneos(VentanaModal):
    """Consulta resultados históricos y permite continuar o editar un torneo."""

    def __init__(self, parent, abrir_en_vivo) -> None:
        super().__init__(parent, modal=True)
        self.title("Torneos finalizados")
        self.geometry("1160x720")
        self.minsize(900, 560)
        self.abrir_en_vivo = abrir_en_vivo
        self.vista_torneos = parent
        self.transient(parent.winfo_toplevel())
        self.torneo_id: int | None = None
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        panel_lista = ctk.CTkFrame(self)
        panel_lista.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        panel_lista.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            panel_lista,
            text="Torneos finalizados",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=10)
        self.tabla_torneos_finalizados = ttk.Treeview(
            panel_lista,
            columns=("id", "nombre", "fecha"),
            show="headings",
            selectmode="browse",
            height=18,
        )
        for columna, titulo, ancho in (
            ("id", "ID", 45),
            ("nombre", "Torneo", 190),
            ("fecha", "Finalizado", 130),
        ):
            self.tabla_torneos_finalizados.heading(columna, text=titulo)
            self.tabla_torneos_finalizados.column(
                columna, width=ancho, anchor="center" if columna != "nombre" else "w"
            )
        self.tabla_torneos_finalizados.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.tabla_torneos_finalizados.bind(
            "<<TreeviewSelect>>", self._al_seleccionar_torneo
        )
        scroll_torneos = ttk.Scrollbar(
            panel_lista, orient="vertical", command=self.tabla_torneos_finalizados.yview
        )
        self.tabla_torneos_finalizados.configure(yscrollcommand=scroll_torneos.set)
        scroll_torneos.grid(row=1, column=1, sticky="ns", pady=(0, 8))

        panel_detalle = ctk.CTkFrame(self)
        panel_detalle.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        panel_detalle.grid_columnconfigure(0, weight=1)
        panel_detalle.grid_rowconfigure(1, weight=1)
        self.lbl_torneo = ctk.CTkLabel(
            panel_detalle,
            text="Selecciona un torneo para ver sus resultados.",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.lbl_torneo.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        self.detalles = ctk.CTkTabview(panel_detalle)
        self.detalles.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.tab_mesas_archivadas = self.detalles.add("Rondas y mesas")
        self.tab_ranking_archivado = self.detalles.add("Clasificación")
        self.tab_clubes_archivados = self.detalles.add("Clasificación por club")
        self.tab_penalizaciones_archivadas = self.detalles.add("Penalizaciones")
        self._crear_tabla(
            self.tab_mesas_archivadas,
            "mesas",
            (
                ("ronda", "Ronda", 55),
                ("mesa", "Mesa", 55),
                ("pareja1", "Pareja 1 / BYE", 220),
                ("pareja2", "Pareja 2", 220),
                ("marcador", "Marcador final", 95),
                ("base", "Puntos base", 100),
                ("descuento", "Descuentos", 90),
                ("motivo", "Penalización / estado", 180),
            ),
        )
        filtro_ranking_archivado = ctk.CTkFrame(
            self.tab_ranking_archivado,
            fg_color="transparent",
        )
        filtro_ranking_archivado.pack(fill="x", padx=8, pady=(8, 0))
        ctk.CTkLabel(
            filtro_ranking_archivado,
            text="Visualizar ranking:",
        ).pack(side="left", padx=(0, 8))
        self.combo_filtro_ranking_archivado = ctk.CTkComboBox(
            filtro_ranking_archivado,
            values=["General", "Hombres", "Mujeres"],
            state="readonly",
            width=160,
            command=lambda _valor: self._cargar_clasificacion_archivada(),
        )
        self.combo_filtro_ranking_archivado.set("General")
        self.combo_filtro_ranking_archivado.pack(side="left")
        self._crear_tabla(
            self.tab_ranking_archivado,
            "ranking",
            (
                ("posicion", "Pos.", 55),
                ("cedula", "Cédula", 100),
                ("nombre", "Jugador", 220),
                ("pg", "PG", 55),
                ("pp", "PP", 55),
                ("ef", "EF", 70),
                ("pf", "PF", 70),
            ),
        )
        self.combo_clubes_archivados = ctk.CTkComboBox(
            self.tab_clubes_archivados,
            values=["Sin clasificación por club"],
            state="readonly",
            command=self._cargar_clasificacion_club,
        )
        self.combo_clubes_archivados.pack(fill="x", padx=8, pady=(8, 4))
        self._crear_tabla(
            self.tab_clubes_archivados,
            "ranking_club",
            (
                ("posicion", "Pos.", 55),
                ("cedula", "Cédula", 100),
                ("nombre", "Jugador", 220),
                ("pg", "PG", 55),
                ("pp", "PP", 55),
                ("ef", "EF", 70),
                ("pf", "PF", 70),
            ),
        )
        self._crear_tabla(
            self.tab_penalizaciones_archivadas,
            "penalizaciones",
            (
                ("ronda", "Ronda", 55),
                ("mesa", "Mesa", 55),
                ("nombre", "Jugador", 200),
                ("tipo", "Tipo", 130),
                ("motivo", "Motivo", 250),
                ("fecha", "Fecha", 145),
            ),
        )

        acciones = ctk.CTkFrame(panel_detalle, fg_color="transparent")
        acciones.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkLabel(acciones, text="Rondas adicionales:").pack(side="left", padx=(0, 5))
        self.entrada_rondas_adicionales = ctk.CTkEntry(
            acciones, width=65, placeholder_text="1"
        )
        self.entrada_rondas_adicionales.pack(side="left", padx=(0, 10))
        BotonDegradado(
            acciones,
            text="Continuar torneo",
            command=self._continuar_torneo,
            fg_color="#2980B9",
        ).pack(side="left", padx=4)
        BotonDegradado(
            acciones,
            text="Editar en vivo",
            command=self._editar_torneo,
            fg_color="#F1C40F"
        ).pack(side="left", padx=4)
        BotonDegradado(
            acciones,
            text="Eliminar torneo",
            command=self._eliminar_torneo,
            fg_color="#D32F2F",
        ).pack(side="right", padx=4)
        aplicar_ayudas(self)
        try:
            botones_pestanas = self.detalles._segmented_button._buttons_dict
            for nombre, texto in AYUDAS_PESTANAS_ARCHIVADAS.items():
                if nombre in botones_pestanas:
                    Tooltip(botones_pestanas[nombre], texto)
        except AttributeError:
            pass
        self._cargar_torneos()
        self.after_idle(self._centrar_en_pantalla)
        self.after(0, self.activar_modal)

    def _centrar_en_pantalla(self) -> None:
        self.update_idletasks()
        ancho = min(1160, self.winfo_screenwidth() - 40)
        alto = min(720, self.winfo_screenheight() - 80)
        x = max(0, (self.winfo_screenwidth() - ancho) // 2)
        y = max(0, (self.winfo_screenheight() - alto) // 2)
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

    def _crear_tabla(self, contenedor, atributo: str, columnas) -> None:
        marco = ctk.CTkFrame(contenedor)
        marco.pack(fill="both", expand=True, padx=6, pady=6)
        marco.grid_rowconfigure(0, weight=1)
        marco.grid_columnconfigure(0, weight=1)
        nombres = tuple(columna[0] for columna in columnas)
        es_tabla_mesas = atributo == "mesas"
        opciones_tabla: dict[str, object] = {"show": "headings"}
        if es_tabla_mesas:
            self._iconos_marcador = _cargar_iconos_marcador(self)
            opciones_tabla.update(
                displaycolumns=tuple(nombre for nombre in nombres if nombre != "marcador"),
                show="tree headings",
            )
        tabla = ttk.Treeview(
            marco,
            columns=nombres,
            selectmode="browse",
            **opciones_tabla,
        )
        if es_tabla_mesas:
            tabla.heading("#0", text="Marcador final")
            tabla.column("#0", width=140, minwidth=120, anchor="center", stretch=False)
            tabla.column("marcador", width=0, minwidth=0, stretch=False)
        for nombre, titulo, ancho in columnas:
            tabla.heading(nombre, text=titulo)
            if nombre != "marcador" or not es_tabla_mesas:
                tabla.column(nombre, width=ancho, anchor="center" if nombre in {"ronda", "mesa", "posicion", "pg", "pp", "ef", "pf"} else "w")
        tabla.grid(row=0, column=0, sticky="nsew")
        barra = ttk.Scrollbar(marco, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=barra.set)
        barra.grid(row=0, column=1, sticky="ns")
        setattr(self, f"tabla_{atributo}", tabla)

    @staticmethod
    def _limpiar_tabla(tabla) -> None:
        _limpiar_treeview(tabla)

    def _cargar_torneos(self) -> None:
        self._limpiar_tabla(self.tabla_torneos_finalizados)
        for torneo in repo.listar_torneos_finalizados():
            self.tabla_torneos_finalizados.insert(
                "",
                "end",
                values=(
                    torneo["id"],
                    torneo["nombre"],
                    torneo["fecha_finalizacion"] or "No disponible",
                ),
            )

    def _al_seleccionar_torneo(self, _evento=None) -> None:
        seleccion = self.tabla_torneos_finalizados.selection()
        if not seleccion:
            return
        self.torneo_id = int(
            self.tabla_torneos_finalizados.item(seleccion[0], "values")[0]
        )
        torneo = repo.obtener_torneo(self.torneo_id)
        if torneo is None:
            messagebox.showerror("Error", "El torneo seleccionado ya no existe.", parent=self)
            self._cargar_torneos()
            return
        self.lbl_torneo.configure(
            text=f"{torneo['nombre']}  |  {torneo['num_rondas']} rondas  |  "
            f"Finalizado: {torneo['fecha_finalizacion'] or 'sin fecha'}"
        )
        self._cargar_detalles()

    def _cargar_detalles(self) -> None:
        if self.torneo_id is None:
            return
        mesas = self.tabla_mesas
        self._limpiar_tabla(mesas)
        byes_por_ronda: dict[int, list] = {}
        for bye in repo.listar_byes_de_torneo(self.torneo_id):
            byes_por_ronda.setdefault(bye["numero_ronda"], []).append(bye)
        mesas_por_ronda: dict[int, list] = {}
        for mesa in repo.listar_mesas_archivadas(self.torneo_id):
            mesas_por_ronda.setdefault(mesa["numero_ronda"], []).append(mesa)
        for ronda in repo.listar_rondas_de_torneo(self.torneo_id):
            for mesa in mesas_por_ronda.get(ronda["numero_ronda"], []):
                finalizada = mesa["estado"] == "finalizada"
                marcador = (
                    f"{mesa['puntos_p1']} - {mesa['puntos_p2']}"
                    if finalizada else "Pendiente"
                )
                self.tabla_mesas.insert(
                    "",
                    "end",
                    text=marcador if finalizada else "",
                    image=self._iconos_marcador["finalizado" if finalizada else "pendiente"],
                    values=(
                        ronda["numero_ronda"],
                        mesa["numero_mesa"],
                        f"{mesa['j1_nom']} / {mesa['j2_nom']}",
                        f"{mesa['j3_nom']} / {mesa['j4_nom']}",
                        marcador,
                        f"{mesa['puntos_base_p1']} - {mesa['puntos_base_p2']}",
                        f"{mesa['descuento_p1']} - {mesa['descuento_p2']}",
                        mesa["motivo_penalizacion"] or mesa["estado"],
                    ),
                )
            # Los BYE también forman parte del resultado de una ronda.
            for bye in byes_por_ronda.get(ronda["numero_ronda"], []):
                self.tabla_mesas.insert(
                    "", "end",
                    text="Descanso",
                    values=(ronda["numero_ronda"], "BYE", bye["nombre"], "—", "Descanso", "—", "—", "—"),
                )

        self._cargar_clasificacion_archivada()

        self.clasificaciones_club = repo.listar_clasificaciones_club_archivadas(self.torneo_id)
        nombres_clubes = list(self.clasificaciones_club)
        self.combo_clubes_archivados.configure(
            values=nombres_clubes or ["Sin clasificación por club"]
        )
        self.combo_clubes_archivados.set(nombres_clubes[0] if nombres_clubes else "Sin clasificación por club")
        self._cargar_clasificacion_club(self.combo_clubes_archivados.get())

        self._limpiar_tabla(self.tabla_penalizaciones)
        for sancion in repo.listar_detalle_penalizaciones_torneo(self.torneo_id):
            self.tabla_penalizaciones.insert(
                "", "end",
                values=(
                    sancion["numero_ronda"] or "—",
                    sancion["numero_mesa"] or "—",
                    sancion["nombre"],
                    sancion["tipo"].replace("_", " ").capitalize(),
                    sancion["motivo"] or "—",
                    sancion["fecha_hora"],
                ),
            )

    def _cargar_clasificacion_archivada(self) -> None:
        if self.torneo_id is None or not hasattr(self, "tabla_ranking"):
            return
        filtro = self.combo_filtro_ranking_archivado.get()
        sexo = {"Hombres": "M", "Mujeres": "F"}.get(filtro)
        ranking = repo.listar_clasificacion_archivada(self.torneo_id, sexo=sexo)
        self._limpiar_tabla(self.tabla_ranking)
        for posicion, jugador in enumerate(ranking, start=1):
            self.tabla_ranking.insert(
                "",
                "end",
                values=(
                    posicion,
                    jugador["cedula"],
                    jugador["nombre"],
                    jugador["pg"],
                    jugador["pp"],
                    jugador["ef"],
                    jugador["pf"],
                ),
            )

    def _cargar_clasificacion_club(self, nombre_club: str) -> None:
        if not hasattr(self, "tabla_ranking_club"):
            return
        self._limpiar_tabla(self.tabla_ranking_club)
        for jugador in getattr(self, "clasificaciones_club", {}).get(nombre_club, []):
            self.tabla_ranking_club.insert(
                "", "end",
                values=tuple(jugador[columna] for columna in ("posicion", "cedula", "nombre", "pg", "pp", "ef", "pf")),
            )

    def _continuar_torneo(self) -> None:
        if self.torneo_id is None:
            messagebox.showwarning("Selecciona un torneo", "Selecciona un torneo finalizado.", parent=self)
            return
        if not solicitar_clave_historial(self):
            return
        try:
            cantidad = int(self.entrada_rondas_adicionales.get().strip())
            repo.continuar_torneo_finalizado(self.torneo_id, cantidad)
        except ValueError:
            messagebox.showwarning("Dato inválido", "Indica un número entero de rondas.", parent=self)
            return
        except repo.ErrorDatos as error:
            messagebox.showerror("No se pudo continuar", str(error), parent=self)
            return
        torneo_id = self.torneo_id
        vista_torneos = self.vista_torneos
        self.destroy()
        vista_torneos.cargar_datos()
        self.abrir_en_vivo(torneo_id)

    def _editar_torneo(self) -> None:
        if self.torneo_id is None:
            messagebox.showwarning("Selecciona un torneo", "Selecciona un torneo finalizado.", parent=self)
            return
        if not solicitar_clave_historial(self):
            return
        try:
            repo.reabrir_torneo_finalizado_para_edicion(self.torneo_id)
        except repo.ErrorDatos as error:
            messagebox.showerror("No se pudo abrir", str(error), parent=self)
            return
        torneo_id = self.torneo_id
        vista_torneos = self.vista_torneos
        self.destroy()
        vista_torneos.cargar_datos()
        self.abrir_en_vivo(torneo_id)

    def _eliminar_torneo(self) -> None:
        seleccion = self.tabla_torneos_finalizados.selection()
        if not seleccion or self.torneo_id is None:
            messagebox.showwarning(
                "Selecciona un torneo",
                "Selecciona el torneo finalizado que deseas eliminar.",
                parent=self,
            )
            return
        nombre = str(self.tabla_torneos_finalizados.item(seleccion[0], "values")[1])
        if not messagebox.askyesno(
            "Eliminar torneo permanentemente",
            f"¿Eliminar '{nombre}' y todos sus resultados, rondas e historial?\n\n"
            "Esta acción no se puede deshacer.",
            icon="warning",
            parent=self,
        ):
            return
        if not solicitar_clave_historial(self):
            return
        try:
            repo.eliminar_torneo_finalizado(self.torneo_id)
        except repo.ErrorDatos as error:
            messagebox.showerror("No se pudo eliminar", str(error), parent=self)
            return

        self.torneo_id = None
        self.lbl_torneo.configure(text="Selecciona un torneo para ver sus resultados.")
        for nombre_tabla in (
            "tabla_mesas",
            "tabla_ranking",
            "tabla_ranking_club",
            "tabla_penalizaciones",
        ):
            self._limpiar_tabla(getattr(self, nombre_tabla))
        self.clasificaciones_club = {}
        self.combo_clubes_archivados.configure(values=["Sin clasificación por club"])
        self.combo_clubes_archivados.set("Sin clasificación por club")
        self._cargar_torneos()
        messagebox.showinfo(
            "Torneo eliminado",
            f"'{nombre}' y sus datos relacionados fueron eliminados.",
            parent=self,
        )


class VistaTorneos(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame) -> None:
        super().__init__(parent, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        lbl_titulo = ctk.CTkLabel(self, text="Gestión de torneos", font=ctk.CTkFont(size=22, weight="bold"))
        lbl_titulo.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 20), sticky="w")

        form = ctk.CTkFrame(self, width=280)
        form.grid(row=1, column=0, padx=(0, 15), sticky="nsew")

        ctk.CTkLabel(form, text="Nuevo torneo", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10, padx=15, anchor="w")

        ctk.CTkLabel(form, text="Nombre del torneo:").pack(padx=15, anchor="w")
        self.ent_nombre = ctk.CTkEntry(form, placeholder_text="Ej: Torneo Aniversario")
        self.ent_nombre.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(form, text="Duración (minutos):").pack(padx=15, anchor="w")
        self.ent_duracion = ctk.CTkEntry(form, placeholder_text="120")
        self.ent_duracion.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(form, text="Tipo:").pack(padx=15, anchor="w")
        self.combo_tipo = ctk.CTkComboBox(form, values=["Mixto", "Hombres", "Mujeres"], state="normal")
        self.combo_tipo.set("Mixto")
        self.combo_tipo.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(form, text="Puntaje meta:").pack(padx=15, anchor="w")
        self.ent_puntaje = ctk.CTkEntry(form, placeholder_text="200")
        self.ent_puntaje.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(form, text="Número de rondas:").pack(padx=15, anchor="w")
        self.ent_rondas = ctk.CTkEntry(form, placeholder_text="5")
        self.ent_rondas.pack(fill="x", padx=15, pady=(0, 12))

        enlazar_enter_formulario(
            self.ent_nombre,
            self.ent_duracion,
            self.combo_tipo,
            self.ent_puntaje,
            self.ent_rondas,
            accion_final=self.crear_torneo,
        )

        btn_crear = BotonDegradado(form, text="🏆 Crear torneo", command=self.crear_torneo)
        btn_crear.pack(fill="x", padx=15, pady=5)

        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_rowconfigure(5, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right_frame, text="Torneos registrados:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(5, 0))

        tabla_torneos_frame = ctk.CTkFrame(right_frame)
        tabla_torneos_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        tabla_torneos_frame.grid_rowconfigure(0, weight=1)
        tabla_torneos_frame.grid_columnconfigure(0, weight=1)
        self.tabla_torneos_frame = tabla_torneos_frame

        columnas_t = ("id", "nombre", "duracion", "tipo", "puntaje", "rondas")
        self.tabla_torneos = ttk.Treeview(tabla_torneos_frame, columns=columnas_t, show="headings", selectmode="browse")
        self.tabla_torneos.heading("id", text="ID")
        self.tabla_torneos.heading("nombre", text="Nombre")
        self.tabla_torneos.heading("duracion", text="Minutos")
        self.tabla_torneos.heading("tipo", text="Tipo")
        self.tabla_torneos.heading("puntaje", text="Puntaje")
        self.tabla_torneos.heading("rondas", text="Rondas")

        self.tabla_torneos.column("id", width=35, anchor="center")
        self.tabla_torneos.column("nombre", width=160)
        self.tabla_torneos.column("duracion", width=60, anchor="center")
        self.tabla_torneos.column("tipo", width=70, anchor="center")
        self.tabla_torneos.column("puntaje", width=60, anchor="center")
        self.tabla_torneos.column("rondas", width=50, anchor="center")
        self.tabla_torneos.bind("<<TreeviewSelect>>", self.on_torneo_seleccionado)

        scroll_t = ttk.Scrollbar(tabla_torneos_frame, orient="vertical", command=self.tabla_torneos.yview)
        self.tabla_torneos.configure(yscrollcommand=scroll_t.set)
        self.tabla_torneos.grid(row=0, column=0, sticky="nsew")
        scroll_t.grid(row=0, column=1, sticky="ns")

        btn_box_t = ctk.CTkFrame(right_frame, fg_color="transparent")
        btn_box_t.grid(row=2, column=0, sticky="ew", padx=10, pady=2)

        BotonDegradado(
            btn_box_t,
            text="🔒 Torneos finalizados",
            command=self.abrir_historial_finalizados,
            fg_color="#2980B9",
        ).pack(side="left", padx=(0, 5))
        BotonDegradado(btn_box_t, text="✏️ Editar torneo", command=self.abrir_editar_torneo).pack(side="left", padx=(0, 5))
        BotonDegradado(btn_box_t, text="🗑️ Eliminar torneo", fg_color="#D32F2F", hover_color="#9A0007", command=self.eliminar_torneo).pack(side="right")

        self.lbl_participantes = ctk.CTkLabel(
            right_frame,
            text="Participantes inscritos:",
            font=ctk.CTkFont(weight="bold"),
        )
        self.lbl_participantes.grid(row=3, column=0, sticky="w", padx=10, pady=(10, 0))

        filtro_participantes = ctk.CTkFrame(right_frame, fg_color="transparent")
        filtro_participantes.grid(row=4, column=0, sticky="ew", padx=10, pady=(2, 0))
        filtro_participantes.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(filtro_participantes, text="Buscar participante:").grid(
            row=0, column=0, padx=(0, 6), pady=2
        )
        self.ent_busqueda_participante = ctk.CTkEntry(
            filtro_participantes,
            placeholder_text="Nombre, apellido o cédula",
            height=30,
        )
        self.ent_busqueda_participante.grid(row=0, column=1, sticky="ew", pady=2)
        self.ent_busqueda_participante.bind(
            "<KeyRelease>",
            lambda _evento: debounce(
                self, "_temporizador_busqueda_participante", 250, self.cargar_participantes
            ),
        )
        self.ent_busqueda_participante.bind(
            "<Return>", lambda _evento: self.cargar_participantes() or "break"
        )
        self.ent_busqueda_participante.bind(
            "<KP_Enter>", lambda _evento: self.cargar_participantes() or "break"
        )
        ctk.CTkLabel(filtro_participantes, text="Sexo").grid(
            row=0, column=2, padx=(10, 5), pady=2
        )
        self.combo_filtro_participante_sexo = ctk.CTkComboBox(
            filtro_participantes,
            values=["Todos", "Hombres", "Mujeres"],
            state="readonly",
            width=110,
            height=30,
            command=lambda _valor: self.cargar_participantes(),
        )
        self.combo_filtro_participante_sexo.set("Todos")
        self.combo_filtro_participante_sexo.grid(row=0, column=3, pady=2)

        tabla_p_frame = ctk.CTkFrame(right_frame)
        tabla_p_frame.grid(row=5, column=0, sticky="nsew", padx=10, pady=5)
        tabla_p_frame.grid_rowconfigure(0, weight=1)
        tabla_p_frame.grid_columnconfigure(0, weight=1)
        self.tabla_participantes_frame = tabla_p_frame

        columnas_p = ("cedula", "nombre", "sexo")
        self.tabla_participantes = ttk.Treeview(tabla_p_frame, columns=columnas_p, show="headings", selectmode="browse")
        self.tabla_participantes.heading("cedula", text="Cédula")
        self.tabla_participantes.heading("nombre", text="Nombre")
        self.tabla_participantes.heading("sexo", text="Sexo")
        self.tabla_participantes.column("cedula", width=120)
        self.tabla_participantes.column("nombre", width=240)
        self.tabla_participantes.column("sexo", width=60, anchor="center")

        scroll_p = ttk.Scrollbar(tabla_p_frame, orient="vertical", command=self.tabla_participantes.yview)
        self.tabla_participantes.configure(yscrollcommand=scroll_p.set)
        self.tabla_participantes.grid(row=0, column=0, sticky="nsew")
        scroll_p.grid(row=0, column=1, sticky="ns")

        btn_box_p = ctk.CTkFrame(right_frame, fg_color="transparent")
        btn_box_p.grid(row=6, column=0, sticky="ew", padx=10, pady=(2, 10))
        self.btn_box_participantes = btn_box_p
        self.filtro_participantes = filtro_participantes

        BotonDegradado(btn_box_p, text="📝 Inscribir jugador", command=self.abrir_inscribir).pack(side="left", padx=(0, 5))
        BotonDegradado(btn_box_p, text="🚪 Retirar participante", fg_color="#D32F2F", hover_color="#9A0007", command=self.retirar_participante).pack(side="right")

        self.mostrar_panel_participantes(False)
        self.cargar_datos()
        aplicar_ayudas(self)

    def cargar_datos(self) -> None:
        _limpiar_treeview(self.tabla_torneos)
        for t in repo.listar_torneos_activos():
            self.tabla_torneos.insert("", "end", values=(t["id"], t["nombre"], t["duracion_minutos"], str(t["tipo"]).capitalize(), t["puntaje_meta"], t["num_rondas"]))
        self.mostrar_panel_participantes(False)
        self.limpiar_participantes()

    def abrir_historial_finalizados(self) -> None:
        if not solicitar_clave_historial(self):
            return
        VentanaHistorialTorneos(self, self.abrir_torneo_en_vivo)

    def abrir_torneo_en_vivo(self, torneo_id: int) -> None:
        aplicacion = self.winfo_toplevel()
        mostrar_vista = getattr(aplicacion, "mostrar_vista_ejecucion", None)
        if not callable(mostrar_vista):
            messagebox.showerror(
                "No se pudo abrir",
                "No se encontró la vista En vivo de la aplicación.",
                parent=self,
            )
            return
        mostrar_vista()
        vista = getattr(aplicacion, "vista_actual", None)
        if isinstance(vista, VistaEjecucionTorneo):
            vista.cargar_torneos_combo(seleccionar_id=torneo_id)

    def limpiar_participantes(self) -> None:
        _limpiar_treeview(self.tabla_participantes)

    def mostrar_panel_participantes(self, visible: bool) -> None:
        if visible:
            self.lbl_participantes.grid()
            self.filtro_participantes.grid()
            self.tabla_participantes_frame.grid()
            self.btn_box_participantes.grid()
            self.tabla_torneos_frame.master.grid_rowconfigure(1, weight=1)
            self.tabla_torneos_frame.master.grid_rowconfigure(5, weight=1)
        else:
            self.lbl_participantes.grid_remove()
            self.filtro_participantes.grid_remove()
            self.tabla_participantes_frame.grid_remove()
            self.btn_box_participantes.grid_remove()
            self.tabla_torneos_frame.master.grid_rowconfigure(1, weight=1)
            self.tabla_torneos_frame.master.grid_rowconfigure(5, weight=0)

    def on_torneo_seleccionado(self, event) -> None:
        seleccion = self.tabla_torneos.selection()
        if not seleccion:
            self.mostrar_panel_participantes(False)
            self.limpiar_participantes()
            return
        self.mostrar_panel_participantes(True)
        torneo_id = int(self.tabla_torneos.item(seleccion[0], "values")[0])
        self.cargar_participantes(torneo_id)

    def cargar_participantes(self, torneo_id: int | None = None) -> None:
        if torneo_id is None:
            seleccion = self.tabla_torneos.selection()
            if not seleccion:
                self.limpiar_participantes()
                return
            torneo_id = int(self.tabla_torneos.item(seleccion[0], "values")[0])

        self.limpiar_participantes()
        texto_busqueda = self.ent_busqueda_participante.get().strip().casefold()
        sexo_filtro = {"Hombres": "M", "Mujeres": "F"}.get(
            self.combo_filtro_participante_sexo.get()
        )
        participantes = [
            participante
            for participante in repo.listar_jugadores_de_torneo(torneo_id)
            if (
                not texto_busqueda
                or texto_busqueda in str(participante["nombre"]).casefold()
                or texto_busqueda in str(participante["cedula"]).casefold()
            )
            and (
                sexo_filtro is None
                or participante["sexo"] == sexo_filtro
            )
        ]
        for participante in participantes:
            self.tabla_participantes.insert(
                "",
                "end",
                values=(
                    participante["cedula"],
                    participante["nombre"],
                    participante["sexo"],
                ),
            )

    def crear_torneo(self) -> None:
        try:
            duracion = int(self.ent_duracion.get().strip())
            puntaje = int(self.ent_puntaje.get().strip())
            rondas = int(self.ent_rondas.get().strip())
            nombre = self.ent_nombre.get().strip()
            tipo = self.combo_tipo.get().strip().lower()

            repo.crear_torneo(nombre, duracion, tipo, puntaje, rondas)
            self.cargar_datos()
            messagebox.showinfo("Éxito", f"Torneo '{nombre}' creado exitosamente.")
        except ValueError:
            messagebox.showwarning("Datos inválidos", "Duración, puntaje y rondas deben ser números enteros.")
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))

    def abrir_editar_torneo(self) -> None:
        seleccion = self.tabla_torneos.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Selecciona un torneo para editar.")
            return
        VentanaEditarTorneo(self, int(self.tabla_torneos.item(seleccion[0], "values")[0]), self.cargar_datos)

    def eliminar_torneo(self) -> None:
        seleccion = self.tabla_torneos.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Selecciona un torneo para eliminar.")
            return
        valores = self.tabla_torneos.item(seleccion[0], "values")
        torneo_id, nombre = int(valores[0]), valores[1]
        if messagebox.askyesno("Confirmar", f"¿Desea eliminar el torneo '{nombre}' (ID: {torneo_id})?"):
            try:
                repo.eliminar_torneo(torneo_id)
                self.cargar_datos()
                self.limpiar_participantes()
                messagebox.showinfo("Éxito", "Torneo eliminado.")
            except repo.ErrorDatos as e:
                messagebox.showerror("Error", str(e))

    def abrir_inscribir(self) -> None:
        seleccion = self.tabla_torneos.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Selecciona un torneo de la lista superior.")
            return
        VentanaInscribirTorneo(self, int(self.tabla_torneos.item(seleccion[0], "values")[0]), lambda: self.on_torneo_seleccionado(None))

    def retirar_participante(self) -> None:
        seleccion_t = self.tabla_torneos.selection()
        if not seleccion_t:
            messagebox.showwarning("Atención", "Selecciona un torneo de la lista superior.")
            return
        torneo_id = int(self.tabla_torneos.item(seleccion_t[0], "values")[0])

        seleccion_p = self.tabla_participantes.selection()
        if not seleccion_p:
            messagebox.showwarning("Atención", "Selecciona un participante de la lista inferior.")
            return

        cedula = self.tabla_participantes.item(seleccion_p[0], "values")[0]
        try:
            repo.retirar_jugador_de_torneo(cedula, torneo_id)
            self.on_torneo_seleccionado(None)
            messagebox.showinfo("Éxito", "Participante retirado del torneo.")
        except repo.ErrorDatos as e:
            messagebox.showerror("Error", str(e))


class TemporizadorRonda:
    """Estado y cuenta regresiva compartidos por las vistas de la aplicación.

    ``obtener()`` entrega una única instancia que sobrevive al cambio de
    sección. Las vistas se suscriben para dibujar sus propios controles, pero
    el reloj sigue avanzando aunque ninguna vista esté abierta. La hora límite
    usa ``time.monotonic`` para no depender de ajustes del reloj del sistema;
    ``after`` agenda los ticks en el hilo principal de Tkinter.
    """

    ADVERTENCIA_SEGUNDOS = 60
    DURACION_POR_DEFECTO_MIN = 30
    MINUTOS_MAX = 600
    PASO_AJUSTE_MIN = 1  # minutos que suman/restan los botones − y +

    _instancia: "TemporizadorRonda | None" = None

    def __init__(self) -> None:
        self.duracion: float = self.DURACION_POR_DEFECTO_MIN * 60.0
        self.restante: float = self.duracion
        self.estado: str = "detenido"  # detenido | corriendo | pausado | finalizado
        self._fin: float = 0.0
        self._raiz: tk.Misc | None = None
        self._job: str | None = None
        self._oyentes: list = []

    @classmethod
    def obtener(cls) -> "TemporizadorRonda":
        if cls._instancia is None:
            cls._instancia = cls()
        return cls._instancia

    def vincular(self, raiz: tk.Misc) -> None:
        """Ventana raíz que programa los ticks (sobrevive a las vistas)."""
        self._raiz = raiz

    def suscribir(self, callback) -> None:
        if callback not in self._oyentes:
            self._oyentes.append(callback)

    def desuscribir(self, callback) -> None:
        if callback in self._oyentes:
            self._oyentes.remove(callback)

    def _notificar(self) -> None:
        for cb in list(self._oyentes):
            try:
                cb(self)
            except tk.TclError:  # la vista ya fue destruida
                self.desuscribir(cb)

    def _programar(self) -> None:
        self._cancelar()
        if self._raiz is not None:
            self._job = self._raiz.after(200, self._tick)

    def _cancelar(self) -> None:
        if self._job is not None and self._raiz is not None:
            try:
                self._raiz.after_cancel(self._job)
            except tk.TclError:
                pass
        self._job = None

    def establecer_duracion(self, minutos: float) -> None:
        """Cambia la duración (solo si no está corriendo ni en pausa)."""
        if self.estado in ("corriendo", "pausado"):
            return
        self.duracion = minutos * 60.0
        self.restante = self.duracion
        self.estado = "detenido"
        self._notificar()

    def iniciar(self, minutos: float | None = None) -> None:
        if minutos is not None:
            self.duracion = minutos * 60.0
        self.restante = self.duracion
        self._fin = time.monotonic() + self.restante
        self.estado = "corriendo"
        self._programar()
        self._notificar()

    def pausar(self) -> None:
        if self.estado != "corriendo":
            return
        self.restante = max(0.0, self._fin - time.monotonic())
        self._cancelar()
        self.estado = "pausado"
        self._notificar()

    def reanudar(self) -> None:
        if self.estado != "pausado":
            return
        self._fin = time.monotonic() + self.restante
        self.estado = "corriendo"
        self._programar()
        self._notificar()

    def reiniciar(self) -> None:
        self._cancelar()
        self.restante = self.duracion
        self.estado = "detenido"
        self._notificar()

    def _tick(self) -> None:
        self._job = None
        if self.estado != "corriendo":
            return
        self.restante = max(0.0, self._fin - time.monotonic())
        if self.restante <= 0:
            self._finalizar()
        else:
            self._notificar()
            self._programar()

    def _finalizar(self) -> None:
        self._cancelar()
        self.restante = 0.0
        self.estado = "finalizado"
        self._notificar()
        self._alarma()

    def ajustar(self, minutos: float) -> None:
        """Suma (o resta, si es negativo) minutos sin reiniciar nada.

        - Detenido: cambia la duración configurada (mínimo 1 min).
        - Corriendo o en pausa: cambia solo el tiempo restante; si se resta
          más de lo que queda, la ronda termina en ese momento.
        - Finalizado: sumar da tiempo extra y la cuenta continúa; restar no
          tiene efecto.
        """
        delta = minutos * 60.0
        tope = self.MINUTOS_MAX * 60.0
        ahora = time.monotonic()
        if self.estado == "detenido":
            self.duracion = min(tope, max(60.0, self.duracion + delta))
            self.restante = self.duracion
            self._notificar()
        elif self.estado == "corriendo":
            nuevo = min(tope, max(0.0, self._fin - ahora) + delta)
            if nuevo <= 0:
                self._finalizar()
            else:
                self._fin = ahora + nuevo
                self.restante = nuevo
                self._notificar()
        elif self.estado == "pausado":
            nuevo = min(tope, self.restante + delta)
            if nuevo <= 0:
                self._finalizar()
            else:
                self.restante = nuevo
                self._notificar()
        elif self.estado == "finalizado" and delta > 0:
            self._fin = ahora + delta
            self.restante = delta
            self.estado = "corriendo"
            self._programar()
            self._notificar()

    def _alarma(self) -> None:
        """Tres pitidos y un aviso (visible aunque se esté en otra pantalla)."""
        raiz = self._raiz
        if raiz is None:
            return

        def pitar(quedan: int) -> None:
            try:
                try:
                    import winsound

                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except ImportError:
                    raiz.bell()
                if quedan > 1:
                    raiz.after(700, lambda: pitar(quedan - 1))
                else:
                    raiz.after(100, avisar)
            except tk.TclError:
                pass

        def avisar() -> None:
            try:
                messagebox.showinfo(
                    "Temporizador de ronda", "⏰ ¡Se acabó el tiempo de la ronda!", parent=raiz
                )
            except tk.TclError:
                pass

        pitar(3)

    @staticmethod
    def formatear(segundos: float) -> str:
        total = max(0, math.ceil(segundos))
        h, resto = divmod(total, 3600)
        m, sec = divmod(resto, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


class PestanasSubrayado(ctk.CTkFrame):
    """Pestañas con subrayado de color en la activa y contador opcional.

    Sustituye a ``CTkTabview`` conservando su uso básico: ``add(nombre)``
    devuelve el marco de contenido y ``set(nombre)`` cambia la pestaña activa.
    ``establecer_insignia(nombre, n)`` muestra un contador junto al título.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._barra = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._barra.grid(row=0, column=0, sticky="w")
        ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=COLOR_BORDE).grid(row=1, column=0, sticky="ew")
        self._cuerpo = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._cuerpo.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        self._cuerpo.grid_columnconfigure(0, weight=1)
        self._cuerpo.grid_rowconfigure(0, weight=1)
        self._pestanas: dict[str, dict] = {}
        self._activa: str | None = None
        self.al_cambiar_pestana = None

    def add(self, nombre: str) -> ctk.CTkFrame:
        celda = ctk.CTkFrame(self._barra, fg_color="transparent", corner_radius=0)
        celda.grid(row=0, column=len(self._pestanas), padx=(0, 20))
        fila = ctk.CTkFrame(celda, fg_color="transparent", corner_radius=0)
        fila.pack()
        boton = ctk.CTkButton(
            fila,
            text=nombre,
            height=34,
            corner_radius=6,
            fg_color="transparent",
            hover_color=COLOR_ACENTO_SUAVE,
            text_color=COLOR_TEXTO_SECUNDARIO,
            font=ctk.CTkFont(size=13),
            command=lambda n=nombre: self.set(n),
        )
        boton.pack(side="left")
        insignia = ctk.CTkLabel(
            fila,
            text="0",
            width=22,
            height=18,
            corner_radius=9,
            fg_color=COLOR_AVISO_FONDO,
            text_color=COLOR_AVISO_TEXTO,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        linea = ctk.CTkFrame(celda, height=2, corner_radius=0, fg_color="transparent")
        linea.pack(fill="x")
        contenido = ctk.CTkFrame(self._cuerpo, fg_color="transparent", corner_radius=0)
        contenido.grid(row=0, column=0, sticky="nsew")
        contenido.grid_remove()
        self._pestanas[nombre] = {
            "contenido": contenido, "boton": boton, "linea": linea, "insignia": insignia,
        }
        if self._activa is None:
            self.set(nombre)
        return contenido

    def set(self, nombre: str) -> None:
        if nombre not in self._pestanas:
            return
        self._activa = nombre
        for clave, p in self._pestanas.items():
            activa = clave == nombre
            if activa:
                p["contenido"].grid()
            else:
                p["contenido"].grid_remove()
            p["linea"].configure(fg_color=COLOR_ACENTO if activa else "transparent")
            p["boton"].configure(text_color=COLOR_TEXTO_ACENTO if activa else COLOR_TEXTO_SECUNDARIO)
        if self.al_cambiar_pestana is not None:
            self.al_cambiar_pestana(nombre)

    def get(self) -> str | None:
        return self._activa

    def establecer_insignia(self, nombre: str, cantidad: int) -> None:
        p = self._pestanas.get(nombre)
        if p is None:
            return
        if cantidad > 0:
            p["insignia"].configure(text=str(cantidad))
            if not p["insignia"].winfo_ismapped():
                p["insignia"].pack(side="left", padx=(2, 4))
        else:
            p["insignia"].pack_forget()


class VistaEjecucionTorneo(ctk.CTkFrame):
    """Vista principal para la gestión en tiempo real de partidas, pairing Suizo y Ranking."""


    # ------------------------------------------------------------------
    # Temporizador de ronda
    # ------------------------------------------------------------------
    _COLOR_TIEMPO_NORMAL = ("#16233F", "#CFE4FF")
    _COLOR_TIEMPO_AVISO = "#FF8000"
    _COLOR_TIEMPO_FIN = "#FF4000"

    def _construir_temporizador(self, padre: ctk.CTkFrame) -> None:
        self.temporizador = TemporizadorRonda.obtener()
        self.temporizador.vincular(self.winfo_toplevel())
        self._job_parpadeo: str | None = None

        marco = ctk.CTkFrame(padre, fg_color="transparent")
        marco.pack(anchor="w")

        ctk.CTkLabel(
            marco, text="Panel de control de ronda", anchor="w",
            text_color=COLOR_TEXTO_SECUNDARIO, font=ctk.CTkFont(size=12),
        ).pack(anchor="w")
        self.lbl_tiempo = ctk.CTkLabel(
            marco,
            text="--:--",
            width=190,
            anchor="w",
            text_color=self._COLOR_TIEMPO_NORMAL,
            font=ctk.CTkFont(family="Consolas", size=46, weight="bold"),
        )
        self.lbl_tiempo.pack(anchor="w", pady=(0, 8))

        fila_tiempo = ctk.CTkFrame(marco, fg_color="transparent")
        fila_tiempo.pack(anchor="w")
        self.btn_quitar_minuto = BotonPlano(
            fila_tiempo,
            text="−",
            estilo="secundario",
            width=30,
            height=30,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=lambda: self._ajustar_minutos(-TemporizadorRonda.PASO_AJUSTE_MIN),
        )
        self.btn_quitar_minuto.pack(side="left")
        self.entry_minutos = ctk.CTkEntry(fila_tiempo, width=50, height=30, justify="center")
        self.entry_minutos.insert(0, str(int(self.temporizador.duracion // 60)))
        self.entry_minutos.pack(side="left", padx=4)
        self.entry_minutos.bind("<KeyRelease>", lambda _e: self._aplicar_minutos())
        self.entry_minutos.bind("<Return>", lambda _e: self._aplicar_minutos())
        self.btn_agregar_minuto = BotonPlano(
            fila_tiempo,
            text="+",
            estilo="secundario",
            width=30,
            height=30,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=lambda: self._ajustar_minutos(TemporizadorRonda.PASO_AJUSTE_MIN),
        )
        self.btn_agregar_minuto.pack(side="left")
        ctk.CTkLabel(fila_tiempo, text="min", text_color=COLOR_TEXTO_SECUNDARIO).pack(side="left", padx=(6, 18))

        self.btn_temporizador = BotonPlano(
            fila_tiempo,
            text="▶ Iniciar",
            estilo="primario",
            width=110,
            height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._alternar_temporizador,
        )
        self.btn_temporizador.pack(side="left")
        self.btn_reiniciar_temporizador = BotonPlano(
            fila_tiempo,
            text="↺ Reiniciar",
            estilo="peligro",
            width=110,
            height=32,
            font=ctk.CTkFont(size=13),
            command=self._reiniciar_temporizador,
        )
        self.btn_reiniciar_temporizador.pack(side="left", padx=(8, 0))

        Tooltip(self.btn_quitar_minuto, f"Quita {TemporizadorRonda.PASO_AJUSTE_MIN} min al cronómetro.")
        Tooltip(self.btn_agregar_minuto, f"Suma {TemporizadorRonda.PASO_AJUSTE_MIN} min al cronómetro.")
        Tooltip(
            self.entry_minutos,
            "Duración de la ronda en minutos. Solo se puede editar con el cronómetro detenido.",
        )
        Tooltip(
            self.btn_reiniciar_temporizador,
            "Detiene el cronómetro y lo devuelve a la duración completa.",
        )
        # El texto del botón principal cambia con el estado del cronómetro.
        Tooltip(
            self.btn_temporizador,
            lambda: {
                "corriendo": "Pausa el cronómetro.",
                "pausado": "Reanuda el cronómetro desde donde quedó.",
            }.get(self.temporizador.estado, "Inicia la cuenta regresiva de la ronda."),
        )

        self.temporizador.suscribir(self._al_cambiar_temporizador)
        self._al_cambiar_temporizador(self.temporizador)

    def _leer_minutos(self) -> int | None:
        """Minutos del campo, o None si no es un entero válido (1..máximo)."""
        try:
            minutos = int(self.entry_minutos.get().strip())
        except ValueError:
            return None
        return minutos if 1 <= minutos <= TemporizadorRonda.MINUTOS_MAX else None

    def _aplicar_minutos(self) -> None:
        minutos = self._leer_minutos()
        if minutos is not None:
            self.temporizador.establecer_duracion(minutos)

    def _alternar_temporizador(self) -> None:
        t = self.temporizador
        if t.estado == "corriendo":
            t.pausar()
        elif t.estado == "pausado":
            t.reanudar()
        else:
            minutos = self._leer_minutos()
            if minutos is None:
                messagebox.showwarning(
                    "Temporizador",
                    f"Indique los minutos como un número entero entre 1 y {TemporizadorRonda.MINUTOS_MAX}.",
                )
                return
            t.iniciar(minutos)

    def _reiniciar_temporizador(self) -> None:
        self.temporizador.reiniciar()

    def _ajustar_minutos(self, delta: int) -> None:
        """Agrega o quita minutos (ver ``TemporizadorRonda.ajustar``)."""
        if self.temporizador.estado == "detenido":
            # Toma como base lo escrito en el campo, por si aún no se aplicó.
            self._aplicar_minutos()
        self.temporizador.ajustar(delta)
        self._sincronizar_entrada()

    def _sincronizar_entrada(self) -> None:
        """Muestra en el campo la duración configurada si es editable."""
        t = self.temporizador
        if t.estado not in ("detenido", "finalizado"):
            return
        texto = str(int(t.duracion // 60))
        if self.entry_minutos.get() != texto:
            self.entry_minutos.delete(0, "end")
            self.entry_minutos.insert(0, texto)

    def _al_cambiar_temporizador(self, t: TemporizadorRonda) -> None:
        """Dibuja el estado del temporizador (se llama en cada tick)."""
        if not self.winfo_exists():
            return
        self.lbl_tiempo.configure(text=TemporizadorRonda.formatear(t.restante))
        editable = t.estado in ("detenido", "finalizado")
        self.entry_minutos.configure(state="normal" if editable else "disabled")
        # Restar no tiene sentido cuando el tiempo ya se agotó.
        self.btn_quitar_minuto.configure(state="disabled" if t.estado == "finalizado" else "normal")

        if t.estado == "corriendo":
            self.btn_temporizador.configure(text="⏸ Pausar")
        elif t.estado == "pausado":
            self.btn_temporizador.configure(text="▶ Reanudar")
        else:
            self.btn_temporizador.configure(text="▶ Iniciar")

        if t.estado == "finalizado":
            self.lbl_tiempo.configure(text_color=self._COLOR_TIEMPO_FIN)
            self._parpadear_tiempo(12)
        else:
            self._detener_parpadeo()
            aviso = t.estado == "corriendo" and t.restante <= TemporizadorRonda.ADVERTENCIA_SEGUNDOS
            self.lbl_tiempo.configure(
                text_color=self._COLOR_TIEMPO_AVISO if aviso else self._COLOR_TIEMPO_NORMAL
            )

    def _parpadear_tiempo(self, veces: int) -> None:
        """Alterna el color del tiempo agotado unos segundos."""
        self._detener_parpadeo()
        if veces <= 0 or self.temporizador.estado != "finalizado":
            return
        actual = self.lbl_tiempo.cget("text_color")
        self.lbl_tiempo.configure(
            text_color=self._COLOR_TIEMPO_NORMAL if actual == self._COLOR_TIEMPO_FIN else self._COLOR_TIEMPO_FIN
        )
        self._job_parpadeo = self.after(500, lambda: self._parpadear_tiempo(veces - 1))

    def _detener_parpadeo(self) -> None:
        job = getattr(self, "_job_parpadeo", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._job_parpadeo = None

    def destroy(self) -> None:
        # El temporizador sigue corriendo; solo se deja de dibujar en esta vista.
        temporizador = getattr(self, "temporizador", None)
        if temporizador is not None:
            temporizador.desuscribir(self._al_cambiar_temporizador)
        self._detener_parpadeo()
        super().destroy()

    def al_ocultar(self) -> None:
        """Deja de actualizar los widgets mientras la vista no está visible."""
        self.temporizador.desuscribir(self._al_cambiar_temporizador)
        self._detener_parpadeo()

    def al_mostrar(self) -> None:
        """Reanuda la actualización visual del temporizador al volver a la vista."""
        self.temporizador.suscribir(self._al_cambiar_temporizador)
        self._al_cambiar_temporizador(self.temporizador)

    def __init__(self, parent: ctk.CTkFrame) -> None:
        super().__init__(parent, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Barra superior: título de la sección y selector de torneo activo.
        barra_superior = ctk.CTkFrame(self, fg_color="transparent")
        barra_superior.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(
            barra_superior, text="En vivo / rondas", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")
        self.map_torneos = {}
        self.combo_torneos = ctk.CTkComboBox(
            barra_superior, values=["Seleccione un torneo..."], width=300, command=self.on_torneo_cambiado
        )
        self.combo_torneos.pack(side="right")

        # Tarjeta de control de ronda: temporizador a la izquierda y, a la
        # derecha, los botones para generar o eliminar rondas.
        header_frame = ctk.CTkFrame(
            self, fg_color=COLOR_TARJETA_TEMPORIZADOR, corner_radius=12,
            border_width=1, border_color=COLOR_BORDE_ACENTO,
        )
        header_frame.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        col_titulo = ctk.CTkFrame(header_frame, fg_color="transparent")
        col_titulo.pack(side="left", padx=20, pady=14)
        self._construir_temporizador(col_titulo)

        self.btn_rondas_frame = ctk.CTkFrame(header_frame, fg_color="transparent", width=1, height=1)
        self.btn_rondas_frame.pack(side="right", padx=20, pady=12)

        # Botón para la primera ronda
        self.btn_iniciar_primera = BotonPlano(
            self.btn_rondas_frame,
            text="🚀 Iniciar primera ronda",
            estilo="exito",
            command=self.generar_ronda,
            width=210,
            height=34,
        )

        self.combo_modalidad = ctk.CTkComboBox(
            self.btn_rondas_frame,
            values=["Intercalado", "Suizo puro"],
            state="readonly",
            width=210,
            height=32,
        )
        self.combo_modalidad.set("Intercalado")

        # Botón para las rondas siguientes
        self.btn_generar_ronda = BotonPlano(
            self.btn_rondas_frame,
            text="🎲 Generar siguiente ronda",
            estilo="secundario",
            command=self.generar_ronda,
            width=210,
            height=34,
        )
        self.btn_eliminar_ronda = BotonPlano(
            self.btn_rondas_frame,
            text="🗑️ Eliminar última ronda",
            estilo="peligro",
            command=self.eliminar_ultima_ronda,
            width=210,
            height=34,
        )
        self.btn_archivar_edicion = BotonPlano(
            self.btn_rondas_frame,
            text="🔒 Terminar edición histórica",
            estilo="secundario",
            command=self.finalizar_edicion_historica,
            width=210,
            height=34,
        )

        # Pestañas con subrayado: mesas activas / sin registrar / ranking / historial
        self.tabview = PestanasSubrayado(self)
        self.tabview.grid(row=2, column=0, sticky="nsew")

        self._nombre_tab_pendientes = "Mesas sin registrar"
        self.tab_mesas = self.tabview.add("Ronda y mesas activas")
        self.tab_pendientes = self.tabview.add(self._nombre_tab_pendientes)
        self.tab_ranking = self.tabview.add("Clasificación general (ranking)")
        self.tab_historial = self.tabview.add("Historial de rondas")

        self.configurar_tab_mesas()
        self._pestanas_configuradas = {"Ronda y mesas activas"}
        self._mesas_actuales = []
        self.tabview.al_cambiar_pestana = self._al_cambiar_pestana

        Tooltip(
            self.combo_modalidad,
            "Estilo de emparejamiento de la ronda. Intercalado: en cada bloque de cuatro jugadores "
            "del ranking, la pareja 1 son las posiciones 1 y 3 y la pareja 2 las posiciones 2 y 4. "
            "Suizo puro: empareja según el ranking y evita repetir parejas.",
        )
        for nombre, texto in AYUDAS_PESTANAS_EN_VIVO.items():
            try:
                Tooltip(self.tabview._pestanas[nombre]["boton"], texto)
            except KeyError:
                pass
        aplicar_ayudas(self)

        self.cargar_torneos_combo()

    def _al_cambiar_pestana(self, nombre: str) -> None:
        """Construye y carga cada pestaña secundaria solo cuando se visita."""
        if nombre not in self._pestanas_configuradas:
            if nombre == self._nombre_tab_pendientes:
                self.configurar_tab_pendientes()
            elif nombre == "Clasificación general (ranking)":
                self.configurar_tab_ranking()
            elif nombre == "Historial de rondas":
                self.configurar_tab_historial()
            self._pestanas_configuradas.add(nombre)
            aplicar_ayudas(self)

        if nombre == self._nombre_tab_pendientes:
            self._actualizar_pendientes(self._mesas_actuales)
        elif nombre == "Clasificación general (ranking)":
            self.actualizar_ranking()
        elif nombre == "Historial de rondas":
            self.actualizar_historial_rondas()

    def cargar_torneos_combo(
        self,
        seleccionar_id: int | None = None,
        seleccionar_primero: bool = True,
    ) -> None:
        torneos = repo.listar_torneos_activos()
        self.map_torneos = {f"{t['id']} - {t['nombre']}": t['id'] for t in torneos}
        opciones = list(self.map_torneos.keys())
        valores = ["Seleccione un torneo..."] + opciones if opciones else ["No hay torneos activos"]
        self.combo_torneos.configure(values=valores)
        if opciones:
            seleccion = next((
                nombre for nombre, torneo_id in self.map_torneos.items()
                if torneo_id == seleccionar_id
            ), None)
            if seleccion is None and seleccionar_primero:
                seleccion = opciones[0]
            seleccion = seleccion or "Seleccione un torneo..."
            self.combo_torneos.set(seleccion)
        else:
            self.combo_torneos.set("No hay torneos activos")
        self.actualizar_vista_completa()
    def obtener_torneo_id_sel(self) -> int | None:
        val = self.combo_torneos.get()
        return self.map_torneos.get(val)

    def abrir_historial_participante(self) -> None:
        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            messagebox.showwarning("Atención", "Seleccione un torneo válido.")
            return
        if not repo.listar_jugadores_de_torneo(torneo_id):
            messagebox.showwarning("Atención", "El torneo no tiene participantes inscritos.")
            return
        VentanaSeleccionarParticipanteRondas(self, torneo_id)

    def configurar_tab_mesas(self) -> None:
        self.tab_mesas.grid_columnconfigure(0, weight=1)
        self.tab_mesas.grid_rowconfigure(1, weight=1)

        info_ronda_frame = ctk.CTkFrame(self.tab_mesas, fg_color="transparent")
        info_ronda_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.lbl_info_ronda = ctk.CTkLabel(
            info_ronda_frame,
            text="Seleccione un torneo para ver las mesas",
            text_color=COLOR_TEXTO_SECUNDARIO,
            font=ctk.CTkFont(size=14),
        )
        self.lbl_info_ronda.pack(side="left")
        self.btn_hoja_mesa = BotonPlano(
            info_ronda_frame,
            text="📝 Hoja de mesa",
            estilo="secundario",
            command=self.abrir_hoja_mesa,
            state="normal",
        )
        self.btn_hoja_mesa.pack(side="right")
        # Botón que abre el tablero "Mesas por número de jugador" (la ventana
        # en sí no se modifica; solo el aspecto del botón).
        self.btn_visualizar_mesas = BotonPlano(
            info_ronda_frame,
            text="🔢 Ver mesas por número de jugador",
            estilo="secundario",
            command=self.abrir_mesas_por_numero,
            width=230,
        )
        self.btn_visualizar_mesas.pack(side="right", padx=(0, 10))

        tabla_frame = ctk.CTkFrame(self.tab_mesas, corner_radius=12, border_width=1, border_color=COLOR_BORDE)
        tabla_frame.grid(row=1, column=0, sticky="nsew")
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas_m = ("id", "mesa", "pareja1", "pareja2", "marcador", "estado")
        self._iconos_marcador_mesas = _cargar_iconos_marcador(self)
        self.tabla_mesas = ttk.Treeview(
            tabla_frame,
            columns=columnas_m,
            displaycolumns=("id", "mesa", "pareja1", "pareja2", "estado"),
            show="tree headings",
            selectmode="browse",
        )
        self.tabla_mesas.heading("#0", text="Marcador")
        self.tabla_mesas.column("#0", width=130, minwidth=120, anchor="center", stretch=False)
        self.tabla_mesas.heading("id", text="ID")
        self.tabla_mesas.heading("mesa", text="N° mesa")
        self.tabla_mesas.heading("pareja1", text="Pareja 1 (J1 / J2)")
        self.tabla_mesas.heading("pareja2", text="Pareja 2 (J3 / J4)")
        self.tabla_mesas.heading("marcador", text="Marcador")
        self.tabla_mesas.heading("estado", text="Estado")

        self.tabla_mesas.column("id", width=40, anchor="center")
        self.tabla_mesas.column("mesa", width=70, anchor="center")
        self.tabla_mesas.column("pareja1", width=250)
        self.tabla_mesas.column("pareja2", width=250)
        self.tabla_mesas.column("marcador", width=0, minwidth=0, stretch=False)
        self.tabla_mesas.column("estado", width=100, anchor="center")
        # Las mesas ya registradas se atenúan para que destaquen las pendientes.
        self.tabla_mesas.tag_configure("finalizada", foreground="#8D9BB5")

        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla_mesas.yview)
        self.tabla_mesas.configure(yscrollcommand=scroll.set)
        self.tabla_mesas.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        scroll.grid(row=0, column=1, sticky="ns", pady=10, padx=(0, 10))

        # Estado vacío: se superpone a la tabla cuando no hay mesas que mostrar.
        self.lbl_vacio_mesas = ctk.CTkLabel(
            tabla_frame,
            text="",
            justify="center",
            fg_color=("#FFFFFF", "#151D2D"),
            text_color=COLOR_TEXTO_SECUNDARIO,
            font=ctk.CTkFont(size=13),
        )

        # Barra inferior: una acción principal, varias secundarias y la
        # acción destructiva separada a la derecha.
        btn_box = ctk.CTkFrame(self.tab_mesas, fg_color="transparent")
        btn_box.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        BotonPlano(
            btn_box, text="✎ Anotar marcador", estilo="primario",
            font=ctk.CTkFont(weight="bold"), command=self.abrir_anotar_marcador,
        ).pack(side="left", padx=(0, 10))
        BotonPlano(
            btn_box, text="🔄 Sustituir participante", estilo="secundario",
            command=self.abrir_sustituir,
        ).pack(side="left", padx=(0, 10))
        BotonPlano(
            btn_box, text="📜 Historial de participante", estilo="secundario",
            command=self.abrir_historial_participante,
        ).pack(side="left", padx=(0, 10))
        BotonPlano(
            btn_box, text="⚠ Penalizaciones", estilo="secundario",
            command=self.abrir_penalizaciones,
        ).pack(side="left")
        BotonPlano(
            btn_box, text="⚠ Declarar forfeit", estilo="peligro",
            font=ctk.CTkFont(weight="bold"), command=self.abrir_forfeit,
        ).pack(side="right")

    def configurar_tab_pendientes(self) -> None:
        """Pestaña "Mesas sin registrar": resumen y lista de mesas sin marcador."""
        self.tab_pendientes.grid_columnconfigure(0, weight=1)
        self.tab_pendientes.grid_rowconfigure(1, weight=1)

        resumen = ctk.CTkFrame(self.tab_pendientes, fg_color="transparent")
        resumen.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for columna in range(3):
            resumen.grid_columnconfigure(columna, weight=1, uniform="resumen")

        def tarjeta(columna: int, titulo: str, color_fondo, color_titulo, color_valor) -> ctk.CTkLabel:
            caja = ctk.CTkFrame(resumen, corner_radius=10, fg_color=color_fondo)
            caja.grid(row=0, column=columna, sticky="ew", padx=(0 if columna == 0 else 10, 0))
            ctk.CTkLabel(
                caja, text=titulo, anchor="w", text_color=color_titulo, font=ctk.CTkFont(size=12)
            ).pack(anchor="w", padx=14, pady=(8, 0))
            valor = ctk.CTkLabel(
                caja, text="0", anchor="w", text_color=color_valor,
                font=ctk.CTkFont(size=22, weight="bold"),
            )
            valor.pack(anchor="w", padx=14, pady=(0, 8))
            return valor

        self.lbl_total_mesas = tarjeta(
            0, "Mesas totales", COLOR_PANEL, COLOR_TEXTO_SECUNDARIO, ("#1F2A44", "#E6EBF5")
        )
        self.lbl_mesas_registradas = tarjeta(
            1, "Registradas", COLOR_PANEL, COLOR_TEXTO_SECUNDARIO, COLOR_EXITO_TEXTO
        )
        self.lbl_mesas_pendientes = tarjeta(
            2, "Sin registrar", COLOR_AVISO_FONDO, COLOR_AVISO_TEXTO, COLOR_AVISO_TEXTO
        )

        tabla_frame = ctk.CTkFrame(
            self.tab_pendientes, corner_radius=12, border_width=1, border_color=COLOR_AVISO_BORDE
        )
        tabla_frame.grid(row=1, column=0, sticky="nsew")
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas = ("id", "mesa", "pareja1", "pareja2", "estado")
        self.tabla_pendientes = ttk.Treeview(tabla_frame, columns=columnas, show="headings", selectmode="browse")
        self.tabla_pendientes.heading("id", text="ID")
        self.tabla_pendientes.heading("mesa", text="Mesa")
        self.tabla_pendientes.heading("pareja1", text="Pareja 1")
        self.tabla_pendientes.heading("pareja2", text="Pareja 2")
        self.tabla_pendientes.heading("estado", text="Estado")
        self.tabla_pendientes.column("id", width=40, anchor="center")
        self.tabla_pendientes.column("mesa", width=80, anchor="center")
        self.tabla_pendientes.column("pareja1", width=250)
        self.tabla_pendientes.column("pareja2", width=250)
        self.tabla_pendientes.column("estado", width=110, anchor="center")
        self.tabla_pendientes.tag_configure("pendiente", foreground="#D99A00")
        self.tabla_pendientes.bind("<Double-1>", lambda _e: self._anotar_desde_pendientes())

        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla_pendientes.yview)
        self.tabla_pendientes.configure(yscrollcommand=scroll.set)
        self.tabla_pendientes.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        scroll.grid(row=0, column=1, sticky="ns", pady=10, padx=(0, 10))

        self.lbl_vacio_pendientes = ctk.CTkLabel(
            tabla_frame, text="", justify="center", fg_color=("#FFFFFF", "#151D2D"),
            text_color=COLOR_TEXTO_SECUNDARIO, font=ctk.CTkFont(size=13),
        )

        barra = ctk.CTkFrame(self.tab_pendientes, fg_color="transparent")
        barra.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        BotonPlano(
            barra, text="✎ Anotar marcador", estilo="primario",
            font=ctk.CTkFont(weight="bold"), command=self._anotar_desde_pendientes,
        ).pack(side="left")
        ctk.CTkLabel(
            barra, text="Doble clic en una mesa para anotar su marcador.",
            text_color=COLOR_TEXTO_SECUNDARIO, font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=14)

    def _mostrar_vacio(self, etiqueta: ctk.CTkLabel, texto: str | None) -> None:
        """Muestra u oculta el mensaje de estado vacío sobre una tabla."""
        if texto:
            etiqueta.configure(text=texto)
            etiqueta.place(relx=0.5, rely=0.55, anchor="center")
            etiqueta.lift()
        else:
            etiqueta.place_forget()

    def _actualizar_pendientes(self, mesas: list, mensaje_vacio: str | None = None) -> None:
        """Rellena la pestaña "Mesas sin registrar" con las mesas sin marcador."""
        self._mesas_actuales = mesas
        pendientes = [m for m in mesas if m["estado"] != "finalizada"]
        total = len(mesas)
        sin_registrar = len(pendientes)
        self.tabview.establecer_insignia(self._nombre_tab_pendientes, sin_registrar)
        if self._nombre_tab_pendientes not in self._pestanas_configuradas:
            return

        _limpiar_treeview(self.tabla_pendientes)
        for m in pendientes:
            estado = str(m["estado"]).replace("_", " ").capitalize()
            etiqueta = "pendiente" if m["estado"] != "en_juego" else "en_juego"
            self.tabla_pendientes.insert(
                "", "end",
                values=(
                    m["id"], f"Mesa {m['numero_mesa']}",
                    f"{m['j1_nom']} / {m['j2_nom']}", f"{m['j3_nom']} / {m['j4_nom']}", estado,
                ),
                tags=(etiqueta,),
            )
        self.lbl_total_mesas.configure(text=str(total))
        self.lbl_mesas_registradas.configure(text=str(total - sin_registrar))
        self.lbl_mesas_pendientes.configure(text=str(sin_registrar))
        if mensaje_vacio is None and not pendientes:
            mensaje_vacio = "Todas las mesas están registradas\nNo queda ningún marcador pendiente."
        self._mostrar_vacio(self.lbl_vacio_pendientes, mensaje_vacio if not pendientes else None)

    def _anotar_desde_pendientes(self) -> None:
        """Selecciona la mesa elegida en la tabla principal y abre el registro."""
        seleccion = self.tabla_pendientes.selection()
        if seleccion:
            mesa_id = str(self.tabla_pendientes.item(seleccion[0], "values")[0])
            for item in self.tabla_mesas.get_children():
                if str(self.tabla_mesas.item(item, "values")[0]) == mesa_id:
                    self.tabla_mesas.selection_set(item)
                    self.tabla_mesas.focus(item)
                    break
        self.abrir_anotar_marcador()

    def configurar_tab_ranking(self) -> None:
        self.tab_ranking.grid_columnconfigure(0, weight=1)
        self.tab_ranking.grid_rowconfigure(1, weight=1)

        filtro_frame = ctk.CTkFrame(self.tab_ranking, fg_color="transparent")
        filtro_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        ctk.CTkLabel(filtro_frame, text="Visualizar ranking:").pack(side="left", padx=(0, 8))
        self.combo_filtro_ranking = ctk.CTkComboBox(
            filtro_frame,
            values=["General", "Hombres", "Mujeres"],
            state="readonly",
            width=160,
            command=lambda _valor: self.actualizar_ranking(),
        )
        self.combo_filtro_ranking.set("General")
        self.combo_filtro_ranking.pack(side="left")
        BotonDegradado(
            filtro_frame,
            text="🏛 Ver ranking por clubes",
            command=self.abrir_ranking_club,
            width=180,
        ).pack(side="left", padx=(15, 0))

        tabla_frame = ctk.CTkFrame(self.tab_ranking)
        tabla_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 10))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas_r = ("pos", "cedula", "nombre", "pg", "pp", "ef", "pf")
        self.tabla_ranking = ttk.Treeview(tabla_frame, columns=columnas_r, show="headings")
        self.tabla_ranking.heading("pos", text="Pos")
        self.tabla_ranking.heading("cedula", text="Cédula")
        self.tabla_ranking.heading("nombre", text="Nombre completo")
        self.tabla_ranking.heading("pg", text="PG")
        self.tabla_ranking.heading("pp", text="PP")
        self.tabla_ranking.heading("ef", text="EF (Dif)")
        self.tabla_ranking.heading("pf", text="PF")

        self.tabla_ranking.column("pos", width=50, anchor="center")
        self.tabla_ranking.column("cedula", width=120)
        self.tabla_ranking.column("nombre", width=250)
        self.tabla_ranking.column("pg", width=60, anchor="center")
        self.tabla_ranking.column("pp", width=60, anchor="center")
        self.tabla_ranking.column("ef", width=80, anchor="center")
        self.tabla_ranking.column("pf", width=80, anchor="center")

        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla_ranking.yview)
        self.tabla_ranking.configure(yscrollcommand=scroll.set)
        self.tabla_ranking.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def configurar_tab_historial(self) -> None:
        """Historial en dos columnas: rondas (izquierda) y mesas de la ronda (derecha)."""
        tab = self.tab_historial
        tab.grid_columnconfigure(0, weight=2, uniform="historial")
        tab.grid_columnconfigure(1, weight=5, uniform="historial")
        tab.grid_rowconfigure(1, weight=1)
        self._mesa_historial_a_restaurar: str | None = None
        self._numeros_ronda_historial: dict[str, int] = {}
        self._ronda_historial_mostrada: str | None = None

        estilo = ttk.Style()
        estilo.configure("HistorialRondas.Treeview", rowheight=42, font=("Segoe UI", 11))
        estilo.configure("HistorialMesas.Treeview", rowheight=62, font=("Segoe UI", 11))
        self._iconos_marcador_historial = _cargar_iconos_marcador(self)

        # --- Títulos ----------------------------------------------------
        ctk.CTkLabel(
            tab, text="Rondas", anchor="w", text_color=COLOR_TEXTO_SECUNDARIO,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=(12, 6), pady=(8, 4))

        cabecera_mesas = ctk.CTkFrame(tab, fg_color="transparent")
        cabecera_mesas.grid(row=0, column=1, sticky="ew", padx=(6, 12), pady=(8, 4))
        cabecera_mesas.grid_columnconfigure(0, weight=1)
        self.lbl_historial_titulo_mesas = ctk.CTkLabel(
            cabecera_mesas, text="Mesas de la ronda", anchor="w",
            text_color=COLOR_TEXTO_SECUNDARIO,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.lbl_historial_titulo_mesas.grid(row=0, column=0, sticky="w")
        self.lbl_historial_pendientes = ctk.CTkLabel(
            cabecera_mesas, text="", height=22, corner_radius=11,
            fg_color=COLOR_AVISO_FONDO, text_color=COLOR_AVISO_TEXTO,
            font=ctk.CTkFont(size=12),
        )
        self.lbl_historial_pendientes.grid(row=0, column=1, sticky="e")
        self.lbl_historial_pendientes.grid_remove()

        # --- Columna izquierda: rondas -----------------------------------
        marco_rondas = ctk.CTkFrame(tab)
        marco_rondas.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 8))
        marco_rondas.grid_rowconfigure(0, weight=1)
        marco_rondas.grid_columnconfigure(0, weight=1)
        self.tabla_historial_rondas = ttk.Treeview(
            marco_rondas,
            columns=("ronda", "mesas", "estado"),
            show="headings",
            selectmode="browse",
            style="HistorialRondas.Treeview",
        )
        for columna, texto, ancho in (
            ("ronda", "Ronda", 95), ("mesas", "Mesas", 75), ("estado", "Estado", 115)
        ):
            self.tabla_historial_rondas.heading(columna, text=texto)
            self.tabla_historial_rondas.column(
                columna, width=ancho, minwidth=ancho, anchor="center"
            )
        scroll_rondas = ttk.Scrollbar(
            marco_rondas, orient="vertical", command=self.tabla_historial_rondas.yview
        )
        self.tabla_historial_rondas.configure(yscrollcommand=scroll_rondas.set)
        self.tabla_historial_rondas.grid(row=0, column=0, sticky="nsew")
        scroll_rondas.grid(row=0, column=1, sticky="ns")
        self.tabla_historial_rondas.bind(
            "<<TreeviewSelect>>", self.on_ronda_historial_seleccionada
        )

        # --- Columna derecha: mesas de la ronda ----------------------------
        marco_mesas = ctk.CTkFrame(tab)
        marco_mesas.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 8))
        marco_mesas.grid_rowconfigure(0, weight=1)
        marco_mesas.grid_columnconfigure(0, weight=1)
        # El ícono solo puede ir en la columna de árbol (#0), por eso "Estado"
        # (ícono + texto) es la primera columna.
        self.tabla_historial_mesas = ttk.Treeview(
            marco_mesas,
            columns=("mesa", "pareja1", "pareja2", "marcador"),
            show="tree headings",
            selectmode="browse",
            style="HistorialMesas.Treeview",
        )
        self.tabla_historial_mesas.heading("#0", text="Estado")
        self.tabla_historial_mesas.column(
            "#0", width=140, minwidth=130, anchor="w", stretch=False
        )
        for columna, texto, ancho, minimo, ancla, estira in (
            ("mesa", "Mesa", 70, 60, "center", False),
            ("pareja1", "Pareja 1", 200, 160, "w", True),
            ("pareja2", "Pareja 2", 200, 160, "w", True),
            ("marcador", "Marcador", 110, 90, "center", False),
        ):
            self.tabla_historial_mesas.heading(columna, text=texto)
            self.tabla_historial_mesas.column(
                columna, width=ancho, minwidth=minimo, anchor=ancla, stretch=estira
            )
        scroll_mesas = ttk.Scrollbar(
            marco_mesas, orient="vertical", command=self.tabla_historial_mesas.yview
        )
        self.tabla_historial_mesas.configure(yscrollcommand=scroll_mesas.set)
        self.tabla_historial_mesas.grid(row=0, column=0, sticky="nsew")
        scroll_mesas.grid(row=0, column=1, sticky="ns")
        self.tabla_historial_mesas.bind(
            "<Double-1>", lambda _event: self.abrir_edicion_historial()
        )

        # --- Acciones (una sola fila bajo ambas columnas) --------------------
        acciones = ctk.CTkFrame(tab, fg_color="transparent")
        acciones.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))
        acciones.grid_columnconfigure(2, weight=1)
        BotonDegradado(
            acciones,
            text="👥 Editar disposición",
            estilo="secundario",
            command=self.abrir_disposicion_historial,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        BotonDegradado(
            acciones,
            text="🔄 Swap externo",
            estilo="secundario",
            command=self.abrir_swap_externo_historial,
        ).grid(row=0, column=1, sticky="w")
        BotonDegradado(
            acciones,
            text="✏️ Editar resultado de la mesa",
            estilo="primario",
            command=self.abrir_edicion_historial,
        ).grid(row=0, column=3, sticky="e")

    def _actualizar_resumen_mesas_historial(self, numero_ronda: int | None, mesas) -> None:
        """Título y contador de mesas sin marcar de la ronda mostrada."""
        if numero_ronda is None:
            self.lbl_historial_titulo_mesas.configure(text="Mesas de la ronda")
            self.lbl_historial_pendientes.grid_remove()
            return
        self.lbl_historial_titulo_mesas.configure(text=f"Mesas de la ronda {numero_ronda}")
        total = len(mesas)
        pendientes = sum(1 for mesa in mesas if mesa["estado"] != "finalizada")
        if pendientes:
            self.lbl_historial_pendientes.configure(
                text=f"{pendientes} de {total} sin marcar",
                fg_color=COLOR_AVISO_FONDO, text_color=COLOR_AVISO_TEXTO,
            )
        else:
            self.lbl_historial_pendientes.configure(
                text="Todas las mesas marcadas",
                fg_color=COLOR_ACENTO_SUAVE, text_color=COLOR_EXITO_TEXTO,
            )
        if total:
            self.lbl_historial_pendientes.grid()
        else:
            self.lbl_historial_pendientes.grid_remove()

    def actualizar_historial_rondas(self) -> None:
        # Conserva la ronda y la mesa elegidas para no perder el sitio tras editar.
        ronda_previa = (self.tabla_historial_rondas.selection() or (None,))[0]
        mesa_previa = (self.tabla_historial_mesas.selection() or (None,))[0]
        _limpiar_treeview(self.tabla_historial_rondas)
        _limpiar_treeview(self.tabla_historial_mesas)
        self._numeros_ronda_historial = {}
        self._ronda_historial_mostrada = None
        self._actualizar_resumen_mesas_historial(None, [])
        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            return
        rondas = list(repo.listar_rondas_de_torneo(torneo_id))
        for ronda in rondas:
            iid = str(ronda["id"])
            self._numeros_ronda_historial[iid] = ronda["numero_ronda"]
            self.tabla_historial_rondas.insert("", "end", iid=iid, values=(
                f"Ronda {ronda['numero_ronda']}",
                ronda["total_mesas"],
                str(ronda["estado"]).replace("_", " ").capitalize(),
            ))
        if not rondas:
            return
        iid_final = ronda_previa if ronda_previa in self._numeros_ronda_historial else str(rondas[-1]["id"])
        self._mesa_historial_a_restaurar = mesa_previa if iid_final == ronda_previa else None
        self.tabla_historial_rondas.selection_set(iid_final)
        self.tabla_historial_rondas.see(iid_final)

    def on_ronda_historial_seleccionada(self, event) -> None:
        seleccion = self.tabla_historial_rondas.selection()
        # Tk puede encolar varios <<TreeviewSelect>> seguidos; si la ronda ya está
        # cargada no se reconstruye la tabla (así no se pierde la mesa restaurada).
        if not seleccion or seleccion[0] == self._ronda_historial_mostrada:
            return
        self._ronda_historial_mostrada = seleccion[0]
        _limpiar_treeview(self.tabla_historial_mesas)
        mesas = list(repo.listar_mesas_de_ronda(int(seleccion[0])))
        for mesa in mesas:
            finalizada = mesa["estado"] == "finalizada"
            marcador = f"{mesa['puntos_p1']} - {mesa['puntos_p2']}" if finalizada else "—"
            self.tabla_historial_mesas.insert(
                "",
                "end",
                iid=str(mesa["id"]),
                text=str(mesa["estado"]).replace("_", " ").capitalize(),
                image=self._iconos_marcador_historial[
                    "finalizado" if finalizada else "pendiente"
                ],
                values=(
                    mesa["numero_mesa"],
                    f"{mesa['j1_nom']}\n{mesa['j2_nom']}",
                    f"{mesa['j3_nom']}\n{mesa['j4_nom']}",
                    marcador,
                ),
            )
        self._actualizar_resumen_mesas_historial(
            self._numeros_ronda_historial.get(seleccion[0]), mesas
        )
        pendiente, self._mesa_historial_a_restaurar = self._mesa_historial_a_restaurar, None
        if pendiente and self.tabla_historial_mesas.exists(pendiente):
            self.tabla_historial_mesas.selection_set(pendiente)
            self.tabla_historial_mesas.see(pendiente)

    def abrir_edicion_historial(self) -> None:
        seleccion_ronda = self.tabla_historial_rondas.selection()
        seleccion_mesa = self.tabla_historial_mesas.selection()
        if not seleccion_ronda or not seleccion_mesa:
            messagebox.showwarning(
                "Atención",
                "Seleccione una ronda y una mesa para editar su resultado.",
                parent=self,
            )
            return

        mesa_id = int(seleccion_mesa[0])
        mesa = next(
            (
                item for item in repo.listar_mesas_de_ronda(int(seleccion_ronda[0]))
                if item["id"] == mesa_id
            ),
            None,
        )
        if mesa is None:
            messagebox.showerror("Error", "No se encontró la mesa seleccionada.", parent=self)
            return

        torneo = repo.obtener_torneo(self.obtener_torneo_id_sel())
        if torneo is None:
            messagebox.showerror("Error", "No se encontró el torneo seleccionado.", parent=self)
            return

        info = (
            f"Mesa {mesa['numero_mesa']}: "
            f"{mesa['j1_nom']} / {mesa['j2_nom']} VS "
            f"{mesa['j3_nom']} / {mesa['j4_nom']}"
        )
        VentanaRegistrarMesa(
            self,
            mesa_id,
            info,
            torneo["puntaje_meta"],
            self.actualizar_vista_completa,
            resultado_actual=dict(mesa),
            mesas_ronda=_mesas_ronda_con_numeros(
                int(seleccion_ronda[0]), self.obtener_torneo_id_sel()
            ),
        )

    def abrir_disposicion_historial(self) -> None:
        seleccion_ronda = self.tabla_historial_rondas.selection()
        seleccion_mesa = self.tabla_historial_mesas.selection()
        if not seleccion_ronda or not seleccion_mesa:
            messagebox.showwarning(
                "Atención",
                "Seleccione una ronda y una mesa para editar su disposición.",
                parent=self,
            )
            return
        mesa = next(
            (
                item for item in repo.listar_mesas_de_ronda(int(seleccion_ronda[0]))
                if item["id"] == int(seleccion_mesa[0])
            ),
            None,
        )
        if mesa is None:
            messagebox.showerror("Error", "No se encontró la mesa seleccionada.", parent=self)
            return
        VentanaEditarDisposicionMesa(
            self,
            dict(mesa),
            self.actualizar_vista_completa,
        )

    def abrir_swap_externo_historial(self) -> None:
        seleccion_ronda = self.tabla_historial_rondas.selection()
        seleccion_mesa = self.tabla_historial_mesas.selection()
        if not seleccion_ronda or not seleccion_mesa:
            messagebox.showwarning(
                "Atención",
                "Seleccione una ronda y una mesa de origen.",
                parent=self,
            )
            return
        mesas = [dict(mesa) for mesa in repo.listar_mesas_de_ronda(int(seleccion_ronda[0]))]
        mesa_origen = next(
            (mesa for mesa in mesas if mesa["id"] == int(seleccion_mesa[0])),
            None,
        )
        if mesa_origen is None:
            messagebox.showerror("Error", "No se encontró la mesa seleccionada.", parent=self)
            return
        if len(mesas) < 2:
            messagebox.showwarning(
                "Atención",
                "La ronda no tiene otra mesa disponible para realizar un swap externo.",
                parent=self,
            )
            return
        VentanaSwapExternoMesa(self, mesa_origen, mesas, self.actualizar_vista_completa)

    def actualizar_botones_ronda(self, torneo_id: int) -> None:
        """Verifica si el torneo tiene rondas y muestra u oculta el botón correspondiente."""
        conexion = db.obtener_conexion()
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT COUNT(*) FROM rondas WHERE torneo_id = ?", (torneo_id,))
            count = cursor.fetchone()[0]
        finally:
            conexion.close()

        if count == 0:
            # La primera ronda también permite elegir la modalidad.
            self.combo_modalidad.pack(pady=(0, 5))
            self.btn_generar_ronda.pack_forget()
            self.btn_eliminar_ronda.pack_forget()
            self.btn_archivar_edicion.pack_forget()
            self.btn_iniciar_primera.pack(pady=(0, 5))
        else:
            # Si ya hay rondas, oculta "Iniciar primera ronda" y muestra "Generar siguiente ronda"
            self.btn_iniciar_primera.pack_forget()
            self.combo_modalidad.pack(pady=(0, 5))
            self.btn_generar_ronda.pack(pady=(0, 5))
            self.btn_eliminar_ronda.pack()
            torneo = repo.obtener_torneo(torneo_id)
            if torneo is not None and torneo["edicion_historico"]:
                self.btn_archivar_edicion.pack(pady=(5, 0))
            else:
                self.btn_archivar_edicion.pack_forget()

    def finalizar_edicion_historica(self) -> None:
        torneo_id = self.obtener_torneo_id_sel()
        if torneo_id is None:
            messagebox.showwarning("Atención", "Seleccione un torneo válido.")
            return
        if not solicitar_clave_historial(self):
            return
        try:
            repo.archivar_edicion_historica(torneo_id)
            self.cargar_torneos_combo()
            messagebox.showinfo(
                "Edición finalizada",
                "Los cambios se guardaron y el torneo volvió al historial.",
            )
        except repo.ErrorDatos as error:
            messagebox.showerror("No se pudo archivar", str(error))

    def on_torneo_cambiado(self, val: str) -> None:
        self.actualizar_vista_completa()

    def actualizar_vista_completa(self) -> None:
        torneo_id = self.obtener_torneo_id_sel()
        if torneo_id:
            torneo = repo.obtener_torneo(torneo_id)
            if torneo is None or torneo["estado"] == "finalizado":
                self.cargar_torneos_combo(seleccionar_primero=False)
                return
            self.actualizar_botones_ronda(torneo_id)
        else:
            self.combo_modalidad.pack_forget()
            self.btn_iniciar_primera.pack_forget()
            self.btn_generar_ronda.pack_forget()
            self.btn_eliminar_ronda.pack_forget()
            self.btn_archivar_edicion.pack_forget()
        self.actualizar_mesas()
        pestana_activa = self.tabview.get()
        if pestana_activa == "Clasificación general (ranking)" and pestana_activa in self._pestanas_configuradas:
            self.actualizar_ranking()
        elif pestana_activa == "Historial de rondas" and pestana_activa in self._pestanas_configuradas:
            self.actualizar_historial_rondas()

    def actualizar_mesas(self) -> None:
        _limpiar_treeview(self.tabla_mesas)
        self.btn_hoja_mesa.configure(state="disabled")

        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            self.lbl_info_ronda.configure(text="No hay torneo seleccionado.")
            self.btn_hoja_mesa.configure(state="disabled")
            vacio = "Selecciona un torneo\nAquí verás las mesas y el estado de cada partida."
            self._mostrar_vacio(self.lbl_vacio_mesas, vacio)
            self._actualizar_pendientes([], vacio)
            return

        ronda = repo.obtener_ronda_activa(torneo_id)
        if not ronda:
            self.lbl_info_ronda.configure(text="Sin rondas activas. Presione 'Generar siguiente ronda' para iniciar.")
            self.btn_hoja_mesa.configure(state="disabled")
            vacio = "Sin rondas activas\nGenera la siguiente ronda para ver las mesas."
            self._mostrar_vacio(self.lbl_vacio_mesas, vacio)
            self._actualizar_pendientes([], vacio)
            return

        estado_ronda = str(ronda["estado"]).replace("_", " ").capitalize()
        self.lbl_info_ronda.configure(text=f"Ronda actual: N° {ronda['numero_ronda']} | Estado: {estado_ronda}")

        mesas = repo.listar_mesas_de_ronda(ronda["id"])
        self.btn_hoja_mesa.configure(state="normal" if mesas else "disabled")
        for m in mesas:
            pareja1 = f"{m['j1_nom']} / {m['j2_nom']}"
            pareja2 = f"{m['j3_nom']} / {m['j4_nom']}"
            finalizada = m["estado"] == "finalizada"
            marcador = f"{m['puntos_p1']} - {m['puntos_p2']}" if finalizada else "Pendiente"
            estado = str(m["estado"]).replace("_", " ").capitalize()
            self.tabla_mesas.insert(
                "", "end",
                text=marcador if finalizada else "",
                image=self._iconos_marcador_mesas[
                    "finalizado" if finalizada else "pendiente"
                ],
                values=(m["id"], f"Mesa {m['numero_mesa']}", pareja1, pareja2, marcador, estado),
                tags=("finalizada" if finalizada else "en_juego",),
            )
        self._mostrar_vacio(
            self.lbl_vacio_mesas, None if mesas else "No hay mesas en esta ronda."
        )
        self._actualizar_pendientes(mesas, "No hay mesas en esta ronda." if not mesas else None)

    def abrir_hoja_mesa(self) -> None:
        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            messagebox.showwarning("Atención", "Seleccione un torneo válido.")
            return
        ronda = repo.obtener_ronda_activa(torneo_id)
        torneo = repo.obtener_torneo(torneo_id)
        if ronda is None or torneo is None:
            messagebox.showerror("Error", "No se encontró el torneo o su ronda activa.")
            return

        # Número de jugador (orden de ingreso al torneo) y estadísticas acumuladas
        # (PG, PP y EF), tomadas del mismo ranking que muestra la pestaña de Ranking.
        numeros = repo.obtener_numeros_jugadores_torneo(torneo_id)
        estadisticas = {
            fila["cedula"]: fila for fila in repo.obtener_ranking_torneo(torneo_id)
        }

        def jugador_hoja(mesa, posicion: int) -> JugadorHoja:
            cedula = mesa[f"j{posicion}_cedula"]
            fila = estadisticas.get(cedula)
            return JugadorHoja(
                nombre=str(mesa[f"j{posicion}_nom"]),
                numero=numeros.get(cedula),
                ganadas=int(fila["pg"]) if fila is not None else 0,
                perdidas=int(fila["pp"]) if fila is not None else 0,
                eficiencia=int(fila["ef"]) if fila is not None else 0,
            )

        mesas = [
            (
                int(mesa["numero_mesa"]),
                (jugador_hoja(mesa, 1), jugador_hoja(mesa, 2)),
                (jugador_hoja(mesa, 3), jugador_hoja(mesa, 4)),
            )
            for mesa in repo.listar_mesas_de_ronda(ronda["id"])
        ]
        if not mesas:
            messagebox.showwarning(
                "Atención",
                "La ronda activa no tiene mesas para generar hojas.",
            )
            return

        VentanaHojaMesa(
            self,
            str(torneo["nombre"]),
            int(ronda["numero_ronda"]),
            mesas,
        )

    def actualizar_ranking(self) -> None:
        _limpiar_treeview(self.tabla_ranking)

        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            return

        filtro = self.combo_filtro_ranking.get()
        sexo = {"Hombres": "M", "Mujeres": "F"}.get(filtro)
        ranking = repo.obtener_ranking_torneo(torneo_id, sexo=sexo)
        for i, r in enumerate(ranking, start=1):
            self.tabla_ranking.insert("", "end", values=(i, r["cedula"], r["nombre"], r["pg"], r["pp"], r["ef"], r["pf"]))

    def abrir_ranking_club(self) -> None:
        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            messagebox.showwarning("Atención", "Seleccione un torneo válido.")
            return
        VentanaRankingClub(self, torneo_id)

    def generar_ronda(self) -> None:
        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            messagebox.showwarning("Atención", "Seleccione un torneo válido.")
            return

        try:
            # Cuántas rondas existen, para saber cuál función de repository usar.
            count = repo.contar_rondas_torneo(torneo_id)

            modalidades = {
                "Intercalado": "intercalado",
                "Suizo puro": "suizo_puro",
            }
            modalidad_visible = self.combo_modalidad.get()
            modalidad = modalidades.get(modalidad_visible)
            if modalidad is None:
                messagebox.showwarning(
                    "Modalidad inválida",
                    "Seleccione una modalidad válida antes de generar la ronda.",
                    parent=self,
                )
                return

            if count == 0:
                mensaje_confirmacion = (
                    "Se generará la primera ronda con emparejamiento "
                    f"«{modalidad_visible}».\n\n¿Desea continuar?"
                )
                if not messagebox.askyesno(
                    "Confirmar generación de ronda",
                    mensaje_confirmacion,
                    parent=self,
                ):
                    return
                tarea = lambda: repo.generar_emparejamientos(torneo_id, modalidad=modalidad)
                mensaje_exito = "¡Primera ronda generada exitosamente!"
            else:
                if not messagebox.askyesno(
                    "Confirmar generación de ronda",
                    (
                        f"Se generará la ronda {count + 1} con emparejamiento "
                        f"«{modalidad_visible}».\n\n¿Desea continuar?"
                    ),
                    parent=self,
                ):
                    return
                tarea = lambda: repo.generar_siguiente_ronda(torneo_id, modalidad)
                mensaje_exito = f"Nueva ronda generada con emparejamiento {modalidad_visible}."

        except repo.ErrorDatos as e:
            messagebox.showerror("Error al generar ronda", str(e))
            return

        # El emparejamiento (sobre todo el modo "suizo puro", que resuelve
        # conflictos de parejas repetidas) puede tardar con muchos
        # jugadores: se ejecuta fuera del hilo de la interfaz para que la
        # ventana no se congele, y los botones quedan bloqueados mientras
        # tanto para evitar una doble generación por doble clic.
        def _al_terminar(_resultado) -> None:
            messagebox.showinfo("Éxito", mensaje_exito)
            self.actualizar_vista_completa()

        def _al_error(error: BaseException) -> None:
            if isinstance(error, repo.ErrorDatos):
                messagebox.showerror("Error al generar ronda", str(error))
            else:
                raise error

        ejecutar_en_segundo_plano(
            self,
            tarea=tarea,
            al_terminar=_al_terminar,
            al_error=_al_error,
            widgets_a_bloquear=[
                self.btn_iniciar_primera,
                self.btn_generar_ronda,
                self.btn_eliminar_ronda,
            ],
            mensaje_progreso="Generando ronda, un momento...",
        )

    def eliminar_ultima_ronda(self) -> None:
        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            messagebox.showwarning("Atención", "Seleccione un torneo válido.")
            return

        ronda = repo.obtener_ronda_activa(torneo_id)
        torneo = repo.obtener_torneo(torneo_id)
        if ronda is None or torneo is None:
            messagebox.showwarning("Atención", "El torneo no tiene rondas generadas.")
            return

        primera_confirmacion = messagebox.askyesno(
            "Confirmación 1/2",
            f"¿Desea eliminar la ronda {ronda['numero_ronda']} del torneo '{torneo['nombre']}'?",
            parent=self,
        )
        if not primera_confirmacion:
            return

        segunda_confirmacion = messagebox.askyesno(
            "Confirmación 2/2",
            "Esta acción eliminará sus mesas, resultados y byes sin posibilidad de deshacer. ¿Continuar?",
            parent=self,
        )
        if not segunda_confirmacion:
            return

        try:
            numero_ronda = repo.eliminar_ultima_ronda(torneo_id)
            messagebox.showinfo(
                "Éxito",
                f"La ronda {numero_ronda} fue eliminada correctamente.",
                parent=self,
            )
            self.actualizar_vista_completa()
        except repo.ErrorDatos as e:
            messagebox.showerror("Error al eliminar ronda", str(e), parent=self)

    def abrir_anotar_marcador(self) -> None:
        seleccion = self.tabla_mesas.selection()
        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            messagebox.showwarning("Atención", "Seleccione un torneo válido.")
            return
        ronda = repo.obtener_ronda_activa(torneo_id)
        if ronda is None:
            messagebox.showwarning("Atención", "El torneo no tiene una ronda activa.")
            return
        mesas_pendientes = [
            dict(mesa)
            for mesa in repo.listar_mesas_de_ronda(ronda["id"])
            if mesa["estado"] != "finalizada"
        ]
        if not mesas_pendientes:
            messagebox.showinfo(
                "Sin mesas pendientes",
                "Todas las mesas de la ronda ya tienen un resultado.",
                parent=self,
            )
            return

        mesa_id_inicial = None
        if seleccion:
            valores = self.tabla_mesas.item(seleccion[0], "values")
            mesa_id_seleccionada = int(valores[0])
            if any(mesa["id"] == mesa_id_seleccionada for mesa in mesas_pendientes):
                mesa_id_inicial = mesa_id_seleccionada
        if mesa_id_inicial is None:
            mesa_id_inicial = int(mesas_pendientes[0]["id"])

        torneo = dict(repo.obtener_torneo(torneo_id))
        pts_meta = torneo.get("puntaje_meta", 200)

        VentanaRegistrarMesa(
            self,
            mesa_id_inicial,
            "",
            pts_meta,
            self.actualizar_vista_completa,
            mesas_pendientes=mesas_pendientes,
            mesas_ronda=_mesas_ronda_con_numeros(ronda["id"], torneo_id),
        )

    def abrir_mesas_por_numero(self) -> None:
        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            messagebox.showwarning("Atención", "Seleccione un torneo válido.")
            return

        # Mostrar la cubierta y ceder un ciclo al event loop permite que Tk la
        # pinte antes de construir la ventana, que se prepara en el hilo UI.
        overlay, barra = mostrar_overlay_cargando(
            self,
            "Preparando las mesas por número de jugador…",
        )
        self.btn_visualizar_mesas.configure(state="disabled")

        def construir_modal() -> None:
            try:
                modal = VentanaVisualizacionMesasNumeros(self, torneo_id)
            except Exception as exc:
                cerrar_overlay_cargando(overlay, barra)
                self.btn_visualizar_mesas.configure(state="normal")
                messagebox.showerror(
                    "Error al abrir la visualización",
                    f"No fue posible preparar la ventana de mesas.\n\n{exc}",
                    parent=self,
                )
                return

            def esperar_modal_lista(intentos: int = 0) -> None:
                try:
                    if not modal.winfo_exists():
                        cerrar_overlay_cargando(overlay, barra)
                        self.btn_visualizar_mesas.configure(state="normal")
                        return

                    # La Toplevel conserva alpha=0 mientras calcula su layout.
                    # Retirar la cubierta solo después de revelarla evita mostrar
                    # la ventana principal mientras el tablero aún se construye.
                    if getattr(modal, "_revelada", False):
                        cerrar_overlay_cargando(overlay, barra)
                        self.btn_visualizar_mesas.configure(state="normal")
                        modal.habilitar_overlay_redimensionamiento()
                        return

                    if intentos >= 150:  # ~3 segundos como red de seguridad
                        cerrar_overlay_cargando(overlay, barra)
                        self.btn_visualizar_mesas.configure(state="normal")
                        modal.habilitar_overlay_redimensionamiento()
                        return

                    self.after(20, esperar_modal_lista, intentos + 1)
                except tk.TclError:
                    cerrar_overlay_cargando(overlay, barra)
                    self.btn_visualizar_mesas.configure(state="normal")

            esperar_modal_lista()

        # Dar tiempo al event loop para pintar "Cargando" antes del trabajo
        # síncrono evita que la interfaz parezca bloqueada sin explicación.
        self.after(35, construir_modal)

    def abrir_editar_disposicion_mesa(self) -> None:
        seleccion = self.tabla_mesas.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Seleccione una mesa para editar su disposición.")
            return

        torneo_id = self.obtener_torneo_id_sel()
        ronda = repo.obtener_ronda_activa(torneo_id) if torneo_id else None
        if ronda is None:
            messagebox.showwarning("Atención", "No hay una ronda activa seleccionada.")
            return
        mesa_id = int(self.tabla_mesas.item(seleccion[0], "values")[0])
        mesa = next(
            (item for item in repo.listar_mesas_de_ronda(ronda["id"]) if item["id"] == mesa_id),
            None,
        )
        if mesa is None:
            messagebox.showerror("Error", "No se encontró la mesa seleccionada.")
            return
        VentanaEditarDisposicionMesa(
            self,
            dict(mesa),
            self.actualizar_vista_completa,
        )

    def abrir_swap_externo_mesa(self) -> None:
        seleccion = self.tabla_mesas.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Seleccione una mesa de origen.")
            return
        torneo_id = self.obtener_torneo_id_sel()
        ronda = repo.obtener_ronda_activa(torneo_id) if torneo_id else None
        if ronda is None:
            messagebox.showwarning("Atención", "No hay una ronda activa seleccionada.")
            return
        mesas = [dict(mesa) for mesa in repo.listar_mesas_de_ronda(ronda["id"])]
        mesa_id = int(self.tabla_mesas.item(seleccion[0], "values")[0])
        mesa_origen = next((mesa for mesa in mesas if mesa["id"] == mesa_id), None)
        if mesa_origen is None:
            messagebox.showerror("Error", "No se encontró la mesa seleccionada.")
            return
        if len(mesas) < 2:
            messagebox.showwarning("Atención", "No hay otra mesa disponible para el swap externo.")
            return
        VentanaSwapExternoMesa(self, mesa_origen, mesas, self.actualizar_vista_completa)

    def abrir_forfeit(self) -> None:
        seleccion = self.tabla_mesas.selection()
        if not seleccion:
            messagebox.showwarning("Atención", "Seleccione una mesa para declarar forfeit.")
            return

        valores = self.tabla_mesas.item(seleccion[0], "values")
        mesa_id = int(valores[0])
        info = f"{valores[1]}: {valores[2]} VS {valores[3]}"

        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            messagebox.showwarning("Atención", "Seleccione un torneo válido.")
            return
        VentanaForfeitMesa(self, mesa_id, torneo_id, info, self.actualizar_vista_completa)

    def abrir_penalizaciones(self) -> None:
        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            messagebox.showwarning("Atención", "Seleccione un torneo válido.")
            return
        if not repo.listar_jugadores_de_torneo(torneo_id):
            messagebox.showwarning("Atención", "El torneo no tiene jugadores activos.")
            return
        VentanaPenalizaciones(self, torneo_id, self.actualizar_vista_completa)

    def abrir_sustituir(self) -> None:
        torneo_id = self.obtener_torneo_id_sel()
        if not torneo_id:
            messagebox.showwarning("Atención", "Seleccione un torneo válido.")
            return

        VentanaSustituirJugador(
            self,
            torneo_id,
            self.actualizar_vista_completa,
        )

# ==========================================================================
# APLICACIÓN PRINCIPAL
# ==========================================================================

class AplicacionDominotion(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        _aplicar_icono_ventana(self)

        # Cualquier excepción no controlada dentro de un callback (botón,
        # binding de teclado, etc.) queda centralizada acá en vez de
        # imprimirse en una consola que en el build final no existe.
        instalar_manejador_global_de_excepciones(self)

        db.inicializar_bd()
        aplicar_estilo_treeview("Dark")

        self.title("DOMINOTION - Sistema de gestión de torneos de dominó")
        self.centrar_ventana(1150, 720)
        self.minsize(980, 640)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Barra Lateral (Sidebar)
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=COLOR_SIDEBAR)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(6, weight=1)

        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="DOMINOTION",
            text_color=COLOR_TEXTO_ACENTO,
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(24, 28), sticky="w")

        def boton_menu(fila: int, texto: str, comando) -> BotonPlano:
            boton = BotonPlano(
                self.sidebar_frame,
                text=texto,
                estilo="menu",
                height=40,
                anchor="w",
                font=ctk.CTkFont(size=14),
                command=comando,
            )
            boton.grid(row=fila, column=0, padx=14, pady=3, sticky="ew")
            return boton

        self.btn_jugadores = boton_menu(1, "👥\u2002Jugadores", self.mostrar_vista_jugadores)
        self.btn_clubes = boton_menu(2, "🏛\u2002Clubes", self.mostrar_vista_clubes)
        self.btn_torneos = boton_menu(3, "🏆\u2002Torneos", self.mostrar_vista_torneos)
        self.btn_ejecucion = boton_menu(4, "⚔️\u2002En vivo / rondas", self.mostrar_vista_ejecucion)
        for boton, texto in (
            (self.btn_jugadores, "Registro, edición e historial de los jugadores."),
            (self.btn_clubes, "Gestión de clubes y de los jugadores que pertenecen a cada uno."),
            (self.btn_torneos, "Crear y editar torneos, e inscribir a sus participantes."),
            (self.btn_ejecucion, "Ronda en curso: mesas, marcadores, cronómetro y clasificación."),
        ):
            Tooltip(boton, texto)

        self.label_tema = ctk.CTkLabel(
            self.sidebar_frame, text="Tema visual", text_color=COLOR_TEXTO_SECUNDARIO,
            font=ctk.CTkFont(size=12),
        )
        self.label_tema.grid(row=7, column=0, padx=20, pady=(10, 0), sticky="w")
        self.optionmenu_tema = ctk.CTkOptionMenu(
            self.sidebar_frame, values=["Dark", "Light", "System"], command=self.cambiar_tema
        )
        self.optionmenu_tema.grid(row=8, column=0, padx=14, pady=(4, 20), sticky="ew")

        # Contenedor dinámico de vistas (transparente: las tarjetas de cada
        # vista se destacan sobre el fondo de la ventana).
        self.contenedor_vista = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.contenedor_vista.grid(row=0, column=1, padx=22, pady=20, sticky="nsew")
        self.contenedor_vista.grid_rowconfigure(0, weight=1)
        self.contenedor_vista.grid_columnconfigure(0, weight=1)

        self.vista_actual: ctk.CTkFrame | None = None
        self._vistas: dict[type, ctk.CTkFrame] = {}
        self._botones_menu: dict[type, BotonPlano] = {
            VistaJugadores: self.btn_jugadores,
            VistaClubes: self.btn_clubes,
            VistaTorneos: self.btn_torneos,
            VistaEjecucionTorneo: self.btn_ejecucion,
        }
        self.mostrar_vista_jugadores()

    def centrar_ventana(self, ancho: int, alto: int) -> None:
        """Calcula el centro de la pantalla y ubica la ventana allí."""
        self.update_idletasks()
        pantalla_ancho: int = self.winfo_screenwidth()
        pantalla_alto: int = self.winfo_screenheight()
        x: int = (pantalla_ancho // 2) - (ancho // 2)
        y: int = (pantalla_alto // 2) - (alto // 2)
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

    def cambiar_tema(self, nuevo_tema: str) -> None:
        """Cambia el modo visual global y redibuja la interfaz y el Treeview."""
        # customtkinter oculta y vuelve a mostrar cada ventana en Windows para
        # repintar la barra de título (parece que la app se cierra y reabre).
        # Se desactiva esa manipulación durante el cambio y la barra se
        # colorea aparte, sin ocultar nada.
        ventanas = _ventanas_toplevel_abiertas(self)
        for v in ventanas:
            v._deactivate_windows_window_header_manipulation = True

        # Con la vista oculta, customtkinter recolorea todos sus widgets sin
        # tener que pintarlos en pantalla uno por uno: se repinta una sola vez
        # al volver a mostrarla, lo que hace el cambio mucho más inmediato.
        self.contenedor_vista.grid_remove()
        try:
            if nuevo_tema.lower() == "system":
                # Resolver primero el tema actual del SO mantiene sincronizados
                # los widgets CTk y las tablas ttk, que no observan el modo
                # "System" al mismo tiempo. Restaurar "System" conserva cambios
                # automáticos de tema posteriores.
                ctk.set_appearance_mode(_detectar_tema_sistema())
                ctk.set_appearance_mode("System")
            else:
                ctk.set_appearance_mode(nuevo_tema)
        finally:
            for v in ventanas:
                v._deactivate_windows_window_header_manipulation = False
            self.contenedor_vista.grid()

        # Usar el modo efectivo para las barras de título; aquí CTk ya resolvió
        # "System" a "Light" o "Dark".
        modo_efectivo = ctk.get_appearance_mode()

        for v in ventanas:
            _pintar_barra_titulo_windows(v, modo_efectivo)

        # ttk.Style es global; el cambio de paleta no requiere recargar datos.
        aplicar_estilo_treeview(modo_efectivo)

    def _marcar_menu_activo(self, clase_vista: type[ctk.CTkFrame]) -> None:
        """Resalta en la barra lateral el botón de la vista que se muestra."""
        for clase, boton in self._botones_menu.items():
            estilo = "menu_activo" if clase is clase_vista else "menu"
            boton.configure(**ESTILOS_BOTON[estilo])

    def cambiar_vista(self, clase_vista: type[ctk.CTkFrame]) -> None:
        if self.vista_actual is not None:
            ocultar = getattr(self.vista_actual, "al_ocultar", None)
            if callable(ocultar):
                ocultar()
            self.vista_actual.grid_remove()

        vista = self._vistas.get(clase_vista)
        es_nueva = vista is None
        if vista is None:
            vista = clase_vista(self.contenedor_vista)
            self._vistas[clase_vista] = vista
        self.vista_actual = vista
        vista.grid(row=0, column=0, sticky="nsew")

        if not es_nueva:
            mostrar = getattr(vista, "al_mostrar", None)
            if callable(mostrar):
                mostrar()
            if isinstance(vista, VistaJugadores):
                vista.cargar_datos()
            elif isinstance(vista, VistaClubes):
                vista.cargar_datos()
            elif isinstance(vista, VistaTorneos):
                vista.cargar_datos()
            elif isinstance(vista, VistaEjecucionTorneo):
                vista.cargar_torneos_combo(
                    seleccionar_id=vista.obtener_torneo_id_sel(),
                    seleccionar_primero=False,
                )
        self._marcar_menu_activo(clase_vista)

    def mostrar_vista_jugadores(self) -> None:
        self.cambiar_vista(VistaJugadores)

    def mostrar_vista_clubes(self) -> None:
        self.cambiar_vista(VistaClubes)

    def mostrar_vista_torneos(self) -> None:
        self.cambiar_vista(VistaTorneos)

    def mostrar_vista_ejecucion(self) -> None:
        self.cambiar_vista(VistaEjecucionTorneo)


if __name__ == "__main__":
    mostrar_ventana_presentacion()
    app = AplicacionDominotion()
    app.mainloop()