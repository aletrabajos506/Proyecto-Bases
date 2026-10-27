"""OraAdmin XE - Aplicacion de administracion y respaldos para Oracle 21c XE.
Proyecto Final EIF-402 Administracion de Bases de Datos (UNA).
"""
import datetime
import json
import os
import sys

import customtkinter as ctk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import Conexion  # noqa: E402
from ui_common import aplicar_estilo_tablas, error  # noqa: E402
from modulos import (inicio, tablespaces, tuning, performance, auditoria,  # noqa: E402
                     seguridad, respaldos, recuperacion, archivos)

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

MODULOS = [
    ("Inicio", "🏠", inicio.Inicio),
    ("Tablespaces", "🗄", tablespaces.Tablespaces),
    ("Tuning", "🔧", tuning.Tuning),
    ("Performance", "📈", performance.Performance),
    ("Auditoría", "🔍", auditoria.Auditoria),
    ("Seguridad", "🔐", seguridad.Seguridad),
    ("Respaldos", "💾", respaldos.Respaldos),
    ("Recuperación", "♻", recuperacion.Recuperacion),
    ("Archivos y directorios", "📁", archivos.Archivos),
]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("OraAdmin XE - Administración y Respaldos Oracle 21c")
        self.geometry("1360x820")
        self.minsize(1100, 680)
        self.db = Conexion()
        self.config_app = self._leer_config()
        ctk.set_appearance_mode(self.config_app.get("tema", "Dark"))
        aplicar_estilo_tablas()
        self.pantallas = {}
        self.botones = {}
        self.actual = None
        self._login()

    def report_callback_exception(self, exc, val, tb):
        """Muestra en pantalla cualquier error no controlado de un boton."""
        error(val)

    # ------------------------------------------------------------------ config
    def _leer_config(self):
        try:
            with open(CONFIG, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def guardar_config(self):
        try:
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(self.config_app, f, indent=2)
        except OSError:
            pass

    # ------------------------------------------------------------------ login
    def _login(self):
        for w in self.winfo_children():
            w.destroy()
        c = self.config_app.get("conexion", {})
        marco = ctk.CTkFrame(self, corner_radius=14)
        marco.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(marco, text="OraAdmin XE", font=("Segoe UI", 30, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(28, 0), padx=40)
        ctk.CTkLabel(marco, text="Administración y respaldos · Oracle 21c XE",
                     text_color="gray60").grid(row=1, column=0, columnspan=2, pady=(0, 18))

        campos = [("Servidor", "host", c.get("host", "localhost")),
                  ("Puerto", "puerto", c.get("puerto", "1521")),
                  ("Servicio", "servicio", c.get("servicio", "XEPDB1")),
                  ("Usuario", "usuario", c.get("usuario", "ADMIN_BD")),
                  ("Contraseña", "clave", "")]
        self.ent = {}
        for i, (et, k, v) in enumerate(campos, start=2):
            ctk.CTkLabel(marco, text=et).grid(row=i, column=0, sticky="w", padx=(40, 10), pady=5)
            e = ctk.CTkEntry(marco, width=260, show="*" if k == "clave" else "")
            e.insert(0, v)
            e.grid(row=i, column=1, padx=(0, 40), pady=5)
            self.ent[k] = e
        self.chk_sysdba = ctk.CTkCheckBox(marco, text="Conectar como SYSDBA")
        self.chk_sysdba.grid(row=7, column=1, sticky="w", pady=(6, 2))
        self.chk_local = ctk.CTkCheckBox(
            marco, text="Conexión local (/ as sysdba, sin listener)", command=self._toggle_local)
        self.chk_local.grid(row=8, column=1, sticky="w", pady=2)
        if c.get("local"):
            self.chk_local.select()
            self._toggle_local()
        ctk.CTkButton(marco, text="Conectar", height=38, command=self._conectar).grid(
            row=9, column=0, columnspan=2, sticky="ew", padx=40, pady=(18, 10))
        self.lbl_login = ctk.CTkLabel(marco, text="", text_color="#e5534b", wraplength=360)
        self.lbl_login.grid(row=10, column=0, columnspan=2, pady=(0, 20))
        self.bind("<Return>", lambda e: self._conectar())
        self.ent["clave"].focus_set()

    def _toggle_local(self):
        estado = "disabled" if self.chk_local.get() else "normal"
        for k in ("host", "puerto", "usuario", "clave"):
            self.ent[k].configure(state=estado)

    def _conectar(self):
        v = {k: e.get().strip() for k, e in self.ent.items()}
        local = bool(self.chk_local.get())
        self.lbl_login.configure(text="Conectando...", text_color="gray60")
        self.update_idletasks()
        try:
            self.db.conectar(host=v["host"], puerto=v["puerto"] or 1521,
                             servicio=v["servicio"], usuario=v["usuario"], clave=v["clave"],
                             sysdba=bool(self.chk_sysdba.get()), local=local,
                             pdb=v["servicio"] or "XEPDB1")
        except Exception as e:  # noqa: BLE001
            self.lbl_login.configure(text=str(e).splitlines()[0], text_color="#e5534b")
            return
        self.config_app["conexion"] = {k: v[k] for k in ("host", "puerto", "servicio", "usuario")}
        self.config_app["conexion"]["local"] = local
        self.guardar_config()
        self.unbind("<Return>")
        self._principal()

    # ------------------------------------------------------------------ principal
    def _principal(self):
        for w in self.winfo_children():
            w.destroy()
        self.pantallas.clear()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        menu = ctk.CTkFrame(self, width=230, corner_radius=0)
        menu.grid(row=0, column=0, rowspan=3, sticky="nsw")
        menu.grid_propagate(False)
        ctk.CTkLabel(menu, text="OraAdmin XE", font=("Segoe UI", 22, "bold")).pack(pady=(22, 0))
        ctk.CTkLabel(menu, text="Oracle 21c XE", text_color="gray60").pack(pady=(0, 18))
        for nombre, icono, _ in MODULOS:
            b = ctk.CTkButton(menu, text=f"  {icono}  {nombre}", anchor="w", height=38,
                              fg_color="transparent", text_color=("gray10", "gray90"),
                              hover_color=("gray75", "gray25"),
                              command=lambda n=nombre: self.mostrar(n))
            b.pack(fill="x", padx=10, pady=2)
            self.botones[nombre] = b
        abajo = ctk.CTkFrame(menu, fg_color="transparent")
        abajo.pack(side="bottom", fill="x", padx=10, pady=14)
        self.sw_tema = ctk.CTkSwitch(abajo, text="Modo oscuro", command=self._cambiar_tema)
        if ctk.get_appearance_mode() == "Dark":
            self.sw_tema.select()
        self.sw_tema.pack(anchor="w", pady=6)
        ctk.CTkButton(abajo, text="Desconectar", fg_color="#a23b3b", hover_color="#7d2c2c",
                      command=self._desconectar).pack(fill="x")

        self.contenido = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.contenido.grid(row=0, column=1, sticky="nsew")

        # Bitacora de sentencias ejecutadas
        bit = ctk.CTkFrame(self, height=120, corner_radius=0)
        bit.grid(row=1, column=1, sticky="ew")
        cab = ctk.CTkFrame(bit, fg_color="transparent")
        cab.pack(fill="x", padx=10, pady=(4, 0))
        ctk.CTkLabel(cab, text="Bitácora de sentencias", font=("Segoe UI", 11, "bold")).pack(side="left")
        ctk.CTkButton(cab, text="Limpiar", width=60, height=22,
                      command=lambda: self.txt_bit.delete("1.0", "end")).pack(side="right")
        self.txt_bit = ctk.CTkTextbox(bit, height=90, font=("Consolas", 11))
        self.txt_bit.pack(fill="x", padx=10, pady=(2, 6))
        self.txt_bit.tag_config("err", foreground="#e5534b")
        self.txt_bit.tag_config("ok", foreground="#57ab5a")

        self.lbl_estado = ctk.CTkLabel(self, text="", anchor="w", height=24,
                                       fg_color=("gray85", "gray17"))
        self.lbl_estado.grid(row=2, column=1, sticky="ew")
        self.estado(f"Conectado como {self.db.descripcion}")
        self.mostrar("Inicio")

    def mostrar(self, nombre):
        if self.actual:
            self.pantallas[self.actual].pack_forget()
            self.botones[self.actual].configure(fg_color="transparent")
        if nombre not in self.pantallas:
            clase = next(c for n, _, c in MODULOS if n == nombre)
            try:
                self.pantallas[nombre] = clase(self.contenido, self)
            except Exception as e:  # noqa: BLE001
                error(e)
                return
        self.pantallas[nombre].pack(fill="both", expand=True)
        self.botones[nombre].configure(fg_color=("gray75", "gray25"))
        self.actual = nombre
        self.pantallas[nombre].refrescar_seguro()

    def bitacora(self, sql, ok=True, detalle=""):
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt_bit.insert("end", f"[{hora}] ", "ok" if ok else "err")
        self.txt_bit.insert("end", sql.strip() + ";\n")
        if detalle:
            self.txt_bit.insert("end", "    -> " + detalle.splitlines()[0] + "\n", "err")
        self.txt_bit.see("end")

    def estado(self, texto):
        self.lbl_estado.configure(text="   " + texto)

    def _cambiar_tema(self):
        modo = "Dark" if self.sw_tema.get() else "Light"
        ctk.set_appearance_mode(modo)
        aplicar_estilo_tablas()
        self.config_app["tema"] = modo
        self.guardar_config()
        if self.actual:
            self.pantallas[self.actual].refrescar_seguro()

    def _desconectar(self):
        for p in self.pantallas.values():
            if hasattr(p, "detener"):
                p.detener()
        self.db.cerrar()
        self.actual = None
        self.botones.clear()
        self.grid_columnconfigure(1, weight=0)
        self._login()


if __name__ == "__main__":
    App().mainloop()
