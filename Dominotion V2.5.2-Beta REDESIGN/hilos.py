"""Ejecución de tareas largas y reporte de errores de la interfaz.

(Hay que optimizar esto)
Los cálculos y operaciones de datos pueden ejecutarse en un hilo de trabajo,
pero solo el hilo principal debe acceder a widgets de Tkinter. Una cola lleva
el resultado o la excepción de vuelta al hilo de la interfaz mediante
``after``. Mientras tanto, este módulo puede bloquear los controles que
iniciaron la operación y mostrar una barra de progreso. También centraliza la
presentación y el registro de excepciones no controladas de callbacks.

Uso típico dentro de una vista/ventana de CustomTkinter::

    from hilos import ejecutar_en_segundo_plano

    def generar_ronda(self):
        ...
        ejecutar_en_segundo_plano(
            self,
            tarea=lambda: repo.generar_siguiente_ronda(torneo_id, modalidad),
            al_terminar=lambda resultado: self.actualizar_vista_completa(),
            al_error=lambda error: messagebox.showerror("Error", str(error)),
            widgets_a_bloquear=[self.btn_generar_ronda],
            mensaje_progreso="Generando ronda...",
        )
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from typing import Callable

import customtkinter as ctk


def ejecutar_en_segundo_plano(
    widget_maestro,
    tarea: Callable[[], object],
    al_terminar: Callable[[object], None] | None = None,
    al_error: Callable[[BaseException], None] | None = None,
    widgets_a_bloquear: list | None = None,
    mensaje_progreso: str | None = None,
    intervalo_sondeo_ms: int = 60,
) -> None:
    """Corre ``tarea`` en un hilo aparte y entrega el resultado en el hilo
    de la interfaz.

    - ``tarea`` NO debe tocar ningún widget; solo debe llamar a funciones
      de ``repository``/``db`` y devolver un valor (o lanzar una excepción).
    - ``al_terminar(resultado)`` y ``al_error(excepcion)`` sí corren en el
      hilo principal y pueden actualizar la interfaz con seguridad.
    - ``widgets_a_bloquear``: botones/entries que se deshabilitan mientras
      la tarea corre (evita doble clic/Enter) y se reactivan al terminar,
      incluso si la operación falla.
    """
    resultados: "queue.Queue[tuple[bool, object]]" = queue.Queue()
    widgets_a_bloquear = widgets_a_bloquear or []

    estados_previos = []
    for w in widgets_a_bloquear:
        try:
            estados_previos.append(w.cget("state"))
            w.configure(state="disabled")
        except Exception:
            estados_previos.append(None)

    overlay = (
        _OverlayProgreso(widget_maestro.winfo_toplevel(), widget_maestro, mensaje_progreso)
        if mensaje_progreso
        else None
    )

    def _correr() -> None:
        try:
            valor = tarea()
            resultados.put((True, valor))
        except BaseException as error:  # noqa: BLE001 - se reporta, no se silencia
            resultados.put((False, error))

    hilo = threading.Thread(target=_correr, daemon=True)
    hilo.start()

    def _revisar_cola() -> None:
        try:
            if not widget_maestro.winfo_exists():
                if overlay is not None:
                    overlay.cerrar()
                return
        except tk.TclError:
            if overlay is not None:
                overlay.cerrar()
            return

        try:
            ok, valor = resultados.get_nowait()
        except queue.Empty:
            try:
                widget_maestro.after(intervalo_sondeo_ms, _revisar_cola)
            except tk.TclError:
                if overlay is not None:
                    overlay.cerrar()
            return

        for w, estado_previo in zip(widgets_a_bloquear, estados_previos):
            try:
                w.configure(state=estado_previo or "normal")
            except Exception:
                pass
        if overlay is not None:
            overlay.cerrar()

        if ok:
            if al_terminar is not None:
                al_terminar(valor)
        else:
            if al_error is not None:
                al_error(valor)
            else:
                raise valor

    widget_maestro.after(intervalo_sondeo_ms, _revisar_cola)


class _OverlayProgreso(ctk.CTkToplevel):
    """Ventanita modal simple con una barra de progreso indeterminada,
    para operaciones que tardan más de un instante (generar ronda,
    calcular un ranking grande, etc.)."""

    # Evita que CustomTkinter programe un focus_set sobre esta ventana tras
    # ocultarla brevemente para cambiar el color de la barra de título.
    _deactivate_windows_window_header_manipulation = True

    def __init__(self, parent, widget_ancla, mensaje: str) -> None:
        super().__init__(parent)
        self._widget_ancla = widget_ancla
        self._cerrando = False
        self.title("Procesando")
        self.geometry("320x110")
        self.resizable(False, False)
        self.transient(parent)
        # La operación no se puede cancelar desde esta ventana de progreso.
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        ctk.CTkLabel(self, text=mensaje, wraplength=280).pack(padx=16, pady=(20, 10))
        barra = ctk.CTkProgressBar(self, mode="indeterminate", width=260)
        barra.pack(padx=16, pady=(0, 16))
        barra.start()
        self._barra = barra

        self._ancla_bind_id = widget_ancla.bind(
            "<Destroy>", self._al_destruir_ancla, add="+"
        )
        self.after(10, self._centrar_sobre_ancla)
        self.after(50, self._vigilar_ancla)
        self.grab_set()

    def _al_destruir_ancla(self, evento) -> None:
        if evento.widget is self._widget_ancla:
            self.cerrar()

    def _centrar_sobre_ancla(self) -> None:
        try:
            if not self.winfo_exists() or not self._widget_ancla.winfo_exists():
                self.cerrar()
                return
            self.update_idletasks()
            ancla = self._widget_ancla
            x = ancla.winfo_rootx() + (ancla.winfo_width() // 2) - (self.winfo_width() // 2)
            y = ancla.winfo_rooty() + (ancla.winfo_height() // 2) - (self.winfo_height() // 2)
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            self.cerrar()

    def _vigilar_ancla(self) -> None:
        try:
            if not self.winfo_exists():
                return
            if not self._widget_ancla.winfo_exists():
                self.cerrar()
                return
            self.after(50, self._vigilar_ancla)
        except tk.TclError:
            self.cerrar()

    def cerrar(self) -> None:
        if self._cerrando:
            return
        self._cerrando = True
        if self._ancla_bind_id:
            try:
                self._widget_ancla.unbind("<Destroy>", self._ancla_bind_id)
            except (tk.TclError, AttributeError):
                pass
        try:
            if self._barra.winfo_exists():
                self._barra.stop()
        except (tk.TclError, AttributeError):
            pass
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            if self.winfo_exists():
                self.destroy()
        except tk.TclError:
            pass


def instalar_manejador_global_de_excepciones(app: ctk.CTk) -> None:
    """Centraliza el reporte de excepciones inesperadas de callbacks.

    Por defecto, si un ``command=`` de un botón o un binding de evento
    lanza una excepción no controlada, Tkinter la imprime en la consola
    (invisible para el usuario final en el build sin consola) y sigue
    funcionando, a veces en un estado inconsistente. Esto la intercepta,
    muestra un mensaje entendible y deja registro del detalle técnico en
    el archivo de log, sin cerrar la aplicación.
    """
    import logging
    import traceback

    logger = logging.getLogger("dominotion")

    def _al_ocurrir_excepcion(exc_type, exc_value, exc_traceback) -> None:
        detalle = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logger.error("Excepción no controlada en un callback:\n%s", detalle)
        try:
            from tkinter import messagebox

            messagebox.showerror(
                "Error inesperado",
                "Ocurrió un error inesperado y la operación no se completó.\n\n"
                "La aplicación sigue funcionando; si el problema persiste, "
                "revise el archivo de registro o contacte soporte.\n\n"
                f"Detalle técnico: {exc_type.__name__}: {exc_value}",
            )
        except Exception:
            pass

    app.report_callback_exception = _al_ocurrir_excepcion
