"""Componentes de interfaz reutilizables."""
import datetime
import queue
import threading
from tkinter import messagebox, ttk

import customtkinter as ctk
import oracledb

FUENTE_TITULO = ("Segoe UI", 20, "bold")
FUENTE_SUB = ("Segoe UI", 13, "bold")
FUENTE_MONO = ("Consolas", 12)

COLORES = {
    "Dark": dict(bg="#1d2129", fg="#e4e6eb", head="#2a3040", sel="#1f6aa5", alt="#232833"),
    "Light": dict(bg="#ffffff", fg="#1d2129", head="#e3e7ee", sel="#3b8ed0", alt="#f4f6f9"),
}


def aplicar_estilo_tablas():
    modo = ctk.get_appearance_mode()
    c = COLORES[modo]
    st = ttk.Style()
    st.theme_use("clam")
    st.configure("Treeview", background=c["bg"], fieldbackground=c["bg"],
                 foreground=c["fg"], rowheight=26, borderwidth=0, font=("Segoe UI", 10))
    st.configure("Treeview.Heading", background=c["head"], foreground=c["fg"],
                 relief="flat", font=("Segoe UI", 10, "bold"))
    st.map("Treeview", background=[("selected", c["sel"])],
           foreground=[("selected", "#ffffff")])
    st.map("Treeview.Heading", background=[("active", c["sel"])])
    return c


def error(e, titulo="Error"):
    if isinstance(e, oracledb.Error):
        msg = str(e.args[0].message if hasattr(e.args[0], "message") else e)
    else:
        msg = str(e)
    messagebox.showerror(titulo, msg)


def confirmar(msg, titulo="Confirmar"):
    return messagebox.askyesno(titulo, msg)


def info(msg, titulo="Informacion"):
    messagebox.showinfo(titulo, msg)


# ----------------------------------------------------------------------
class Tabla(ctk.CTkFrame):
    """Treeview con barras de desplazamiento y carga desde (columnas, filas)."""

    def __init__(self, master, alto=10, al_seleccionar=None, al_doble_clic=None,
                 seleccion="browse"):
        super().__init__(master, fg_color="transparent")
        self.tree = ttk.Treeview(self, show="headings", height=alto, selectmode=seleccion)
        sy = ctk.CTkScrollbar(self, command=self.tree.yview)
        sx = ctk.CTkScrollbar(self, orientation="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.columnas = []
        self.filas = []
        if al_seleccionar:
            self.tree.bind("<<TreeviewSelect>>", lambda e: al_seleccionar(self.seleccion()))
        if al_doble_clic:
            self.tree.bind("<Double-1>", lambda e: al_doble_clic(self.seleccion()))

    def cargar(self, columnas, filas):
        c = COLORES[ctk.get_appearance_mode()]
        self.tree.tag_configure("alt", background=c["alt"])
        self.tree.delete(*self.tree.get_children())
        self.columnas = list(columnas)
        self.filas = list(filas)
        self.tree["columns"] = self.columnas
        for col in self.columnas:
            ancho = max(80, min(320, len(str(col)) * 10 + 20))
            for f in self.filas[:50]:
                v = f[self.columnas.index(col)]
                ancho = max(ancho, min(320, len(_fmt(v)) * 8 + 16))
            self.tree.heading(col, text=col, command=lambda c=col: self._ordenar(c, False))
            self.tree.column(col, width=ancho, minwidth=60, stretch=True)
        for i, f in enumerate(self.filas):
            self.tree.insert("", "end", iid=str(i), values=[_fmt(v) for v in f],
                             tags=("alt",) if i % 2 else ())

    def _ordenar(self, col, desc):
        idx = self.columnas.index(col)
        orden = sorted(range(len(self.filas)), reverse=desc,
                       key=lambda i: (self.filas[i][idx] is None, _clave(self.filas[i][idx])))
        for pos, i in enumerate(orden):
            self.tree.move(str(i), "", pos)
        self.tree.heading(col, command=lambda: self._ordenar(col, not desc))

    def seleccion(self):
        """Fila seleccionada como dict {columna: valor} (o None)."""
        sel = self.tree.selection()
        if not sel:
            return None
        return dict(zip(self.columnas, self.filas[int(sel[0])]))

    def selecciones(self):
        return [dict(zip(self.columnas, self.filas[int(i)])) for i in self.tree.selection()]


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def _clave(v):
    if isinstance(v, (int, float)):
        return (0, v, "")
    return (1, 0, str(v))


# ----------------------------------------------------------------------
class Formulario(ctk.CTkToplevel):
    """Dialogo modal generico.
    campos: lista de dicts {clave, etiqueta, tipo, valor, opciones}
    tipo: texto | clave | combo | check | numero | multilinea
    """

    def __init__(self, master, titulo, campos, texto_ok="Aceptar"):
        super().__init__(master)
        self.title(titulo)
        self.resizable(False, False)
        self.resultado = None
        self.campos = campos
        self.widgets = {}
        cont = ctk.CTkFrame(self)
        cont.pack(padx=16, pady=16, fill="both", expand=True)
        ctk.CTkLabel(cont, text=titulo, font=FUENTE_SUB).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(4, 12), padx=8)
        for i, c in enumerate(campos, start=1):
            tipo = c.get("tipo", "texto")
            ctk.CTkLabel(cont, text=c["etiqueta"]).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            if tipo == "combo":
                w = ctk.CTkComboBox(cont, values=[str(o) for o in c.get("opciones", [])], width=280)
                w.set(str(c.get("valor", c["opciones"][0] if c.get("opciones") else "")))
            elif tipo == "check":
                w = ctk.CTkCheckBox(cont, text="")
                if c.get("valor"):
                    w.select()
            elif tipo == "multilinea":
                w = ctk.CTkTextbox(cont, width=280, height=90)
                w.insert("1.0", c.get("valor", ""))
            else:
                w = ctk.CTkEntry(cont, width=280, show="*" if tipo == "clave" else "")
                if c.get("valor") is not None:
                    w.insert(0, str(c.get("valor")))
            w.grid(row=i, column=1, sticky="ew", padx=8, pady=4)
            self.widgets[c["clave"]] = (w, tipo)
        bot = ctk.CTkFrame(cont, fg_color="transparent")
        bot.grid(row=len(campos) + 1, column=0, columnspan=2, sticky="e", pady=(14, 4), padx=8)
        ctk.CTkButton(bot, text="Cancelar", width=100, fg_color="gray40",
                      command=self.destroy).pack(side="right", padx=4)
        ctk.CTkButton(bot, text=texto_ok, width=120, command=self._ok).pack(side="right", padx=4)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(50, self._modal)

    def _modal(self):
        self.lift()
        self.focus_force()
        self.grab_set()

    def _ok(self):
        res = {}
        for clave, (w, tipo) in self.widgets.items():
            if tipo == "check":
                res[clave] = bool(w.get())
            elif tipo == "multilinea":
                res[clave] = w.get("1.0", "end").strip()
            else:
                res[clave] = w.get().strip()
        self.resultado = res
        self.destroy()

    @classmethod
    def pedir(cls, master, titulo, campos, texto_ok="Aceptar"):
        dlg = cls(master, titulo, campos, texto_ok)
        master.wait_window(dlg)
        return dlg.resultado


class VisorTexto(ctk.CTkToplevel):
    def __init__(self, master, titulo, texto):
        super().__init__(master)
        self.title(titulo)
        self.geometry("900x560")
        caja = ctk.CTkTextbox(self, font=FUENTE_MONO, wrap="none")
        caja.pack(fill="both", expand=True, padx=10, pady=10)
        caja.insert("1.0", texto)
        caja.configure(state="disabled")
        self.after(50, self.lift)


# ----------------------------------------------------------------------
class Modulo(ctk.CTkFrame):
    """Clase base de cada pantalla de administracion."""
    titulo = ""
    subtitulo = ""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.db = app.db
        enc = ctk.CTkFrame(self, fg_color="transparent")
        enc.pack(fill="x", padx=20, pady=(16, 6))
        ctk.CTkLabel(enc, text=self.titulo, font=FUENTE_TITULO).pack(side="left")
        ctk.CTkButton(enc, text="⟳ Refrescar", width=110,
                      command=self.refrescar_seguro).pack(side="right")
        if self.subtitulo:
            ctk.CTkLabel(self, text=self.subtitulo, text_color="gray60", anchor="w",
                         justify="left").pack(fill="x", padx=20, pady=(0, 8))
        self.cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        self.cuerpo.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self.construir()

    def construir(self):
        pass

    def refrescar(self):
        pass

    def refrescar_seguro(self):
        try:
            self.refrescar()
        except Exception as e:  # noqa: BLE001 - se muestra al usuario
            error(e)

    def ddl(self, sql, mensaje=None, refrescar=True):
        """Ejecuta una sentencia, la registra en la bitacora y refresca."""
        try:
            self.db.ejecutar(sql)
        except Exception as e:  # noqa: BLE001
            self.app.bitacora(sql, ok=False, detalle=str(e))
            error(e)
            return False
        self.app.bitacora(sql)
        if mensaje:
            self.app.estado(mensaje)
        if refrescar:
            self.refrescar_seguro()
        return True

    def barra(self, master, botones):
        """Crea una fila de botones [(texto, comando, color?)]."""
        f = ctk.CTkFrame(master, fg_color="transparent")
        for b in botones:
            texto, cmd = b[0], b[1]
            color = b[2] if len(b) > 2 else None
            kw = {"fg_color": color} if color else {}
            ctk.CTkButton(f, text=texto, command=cmd, width=10, **kw).pack(side="left", padx=(0, 6))
        return f


class Tarea:
    """Ejecuta una funcion en un hilo y entrega el resultado en el hilo de Tk."""

    def __init__(self, widget, funcion, al_terminar, al_fallar=None):
        self.q = queue.Queue()
        self.widget = widget
        self.al_terminar = al_terminar
        self.al_fallar = al_fallar or error
        threading.Thread(target=self._correr, args=(funcion,), daemon=True).start()
        widget.after(200, self._revisar)

    def _correr(self, funcion):
        try:
            self.q.put(("ok", funcion()))
        except Exception as e:  # noqa: BLE001
            self.q.put(("err", e))

    def _revisar(self):
        try:
            tipo, valor = self.q.get_nowait()
        except queue.Empty:
            self.widget.after(200, self._revisar)
            return
        (self.al_terminar if tipo == "ok" else self.al_fallar)(valor)


def tabs(master, nombres):
    tv = ctk.CTkTabview(master)
    tv.pack(fill="both", expand=True)
    return tv, [tv.add(n) for n in nombres]


def etiqueta_valor(master, texto, fila, col=0):
    ctk.CTkLabel(master, text=texto, text_color="gray60").grid(row=fila, column=col, sticky="w", padx=6, pady=2)
    v = ctk.CTkLabel(master, text="-", font=("Segoe UI", 12, "bold"))
    v.grid(row=fila, column=col + 1, sticky="w", padx=6, pady=2)
    return v
