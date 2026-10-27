"""Creacion de respaldos con Data Pump: Full, por esquemas y por tablas."""
import datetime
import os
import re
import time

import customtkinter as ctk

import datapump
from ui_common import FUENTE_SUB, Modulo, Tabla, Tarea, error, info

TIPOS = {"Full": "FULL", "Esquemas": "SCHEMA", "Tablas": "TABLE"}
CONTENIDO = {"Estructura y datos": "ALL", "Solo estructura": "METADATA_ONLY", "Solo datos": "DATA_ONLY"}


class ListaChecks(ctk.CTkScrollableFrame):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.checks = {}

    def cargar(self, opciones):
        for w in self.winfo_children():
            w.destroy()
        self.checks = {}
        for o in opciones:
            c = ctk.CTkCheckBox(self, text=o)
            c.pack(anchor="w", pady=2)
            self.checks[o] = c

    def marcados(self):
        return [o for o, c in self.checks.items() if c.get()]

    def todos(self, valor=True):
        for c in self.checks.values():
            c.select() if valor else c.deselect()


class Respaldos(Modulo):
    titulo = "Creación de respaldos"
    subtitulo = ("Genera respaldos lógicos con Oracle Data Pump (DBMS_DATAPUMP, equivalente a expdp): "
                 "base de datos completa, esquemas o tablas.")

    def construir(self):
        self.corriendo = False
        cont = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        cont.pack(fill="both", expand=True)

        # ---------------- formulario
        form = ctk.CTkFrame(cont, width=380)
        form.pack(side="left", fill="y", padx=(0, 10))
        form.pack_propagate(False)
        ctk.CTkLabel(form, text="Tipo de respaldo", font=FUENTE_SUB).pack(anchor="w", padx=14, pady=(12, 4))
        self.seg_tipo = ctk.CTkSegmentedButton(form, values=list(TIPOS), command=lambda _: self._cambiar_tipo())
        self.seg_tipo.set("Esquemas")
        self.seg_tipo.pack(fill="x", padx=14)

        self.marco_obj = ctk.CTkFrame(form, fg_color="transparent")
        self.marco_obj.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        self.lbl_obj = ctk.CTkLabel(self.marco_obj, text="Esquemas a respaldar", anchor="w")
        self.lbl_obj.pack(fill="x")
        self.fila_esq = ctk.CTkFrame(self.marco_obj, fg_color="transparent")
        ctk.CTkLabel(self.fila_esq, text="Esquema:").pack(side="left")
        self.cb_esquema = ctk.CTkComboBox(self.fila_esq, values=[], width=200,
                                          command=lambda _: self._cargar_tablas())
        self.cb_esquema.pack(side="left", padx=6)
        self.lista = ListaChecks(self.marco_obj, height=180)
        self.lista.pack(fill="both", expand=True, pady=4)
        self.sel = ctk.CTkFrame(self.marco_obj, fg_color="transparent")
        self.sel.pack(fill="x")
        ctk.CTkButton(self.sel, text="Todos", width=70, height=24, command=self.lista.todos).pack(side="left")
        ctk.CTkButton(self.sel, text="Ninguno", width=70, height=24,
                      command=lambda: self.lista.todos(False)).pack(side="left", padx=6)
        self.lbl_full = ctk.CTkLabel(self.marco_obj, wraplength=330, justify="left", text=(
            "Se respaldará la base de datos completa (PDB XEPDB1): todos los esquemas, "
            "tablespaces, usuarios, roles y objetos. Puede tardar varios minutos."))

        opc = ctk.CTkFrame(form, fg_color="transparent")
        opc.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(opc, text="Contenido").grid(row=0, column=0, sticky="w", pady=3)
        self.cb_contenido = ctk.CTkComboBox(opc, values=list(CONTENIDO), width=210)
        self.cb_contenido.grid(row=0, column=1, sticky="e", pady=3)
        ctk.CTkLabel(opc, text="Directorio").grid(row=1, column=0, sticky="w", pady=3)
        self.cb_dir = ctk.CTkComboBox(opc, values=[], width=210)
        self.cb_dir.grid(row=1, column=1, sticky="e", pady=3)
        ctk.CTkLabel(opc, text="Archivo .dmp").grid(row=2, column=0, sticky="w", pady=3)
        self.ent_archivo = ctk.CTkEntry(opc, width=210, placeholder_text="(automático)")
        self.ent_archivo.grid(row=2, column=1, sticky="e", pady=3)
        opc.grid_columnconfigure(1, weight=1)

        self.btn = ctk.CTkButton(form, text="💾  Ejecutar respaldo", height=40,
                                 font=("Segoe UI", 14, "bold"), command=self.ejecutar)
        self.btn.pack(fill="x", padx=14, pady=(0, 6))
        self.progreso = ctk.CTkProgressBar(form, mode="indeterminate")
        self.progreso.pack(fill="x", padx=14, pady=(0, 14))
        self.progreso.set(0)

        # ---------------- log + historial
        der = ctk.CTkFrame(cont, fg_color="transparent")
        der.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(der, text="Comando equivalente", font=FUENTE_SUB).pack(anchor="w")
        self.txt_cmd = ctk.CTkTextbox(der, height=46, font=("Consolas", 11))
        self.txt_cmd.pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(der, text="Log del trabajo Data Pump", font=FUENTE_SUB).pack(anchor="w")
        self.txt_log = ctk.CTkTextbox(der, font=("Consolas", 11), wrap="none")
        self.txt_log.pack(fill="both", expand=True, pady=(2, 6))
        cab = ctk.CTkFrame(der, fg_color="transparent")
        cab.pack(fill="x")
        ctk.CTkLabel(cab, text="Historial de respaldos", font=FUENTE_SUB).pack(side="left")
        self.barra(cab, [("Ver log", self.ver_log), ("Restaurar este respaldo", self.restaurar)]).pack(side="right")
        self.tabla_hist = Tabla(der, alto=7)
        self.tabla_hist.pack(fill="both", expand=False, pady=(4, 0))

    # ------------------------------------------------------------------
    def refrescar(self):
        dirs = self.db.lista("SELECT directory_name FROM dba_directories ORDER BY 1")
        self.cb_dir.configure(values=dirs)
        if self.cb_dir.get() not in dirs:
            self.cb_dir.set("RESPALDOS_DIR" if "RESPALDOS_DIR" in dirs else "DATA_PUMP_DIR")
        self.esquemas = self.db.lista(
            "SELECT username FROM dba_users WHERE oracle_maintained = 'N' ORDER BY 1")
        self.cb_esquema.configure(values=self.esquemas)
        if self.cb_esquema.get() not in self.esquemas and self.esquemas:
            self.cb_esquema.set(self.esquemas[0])
        if not self.cb_contenido.get() in CONTENIDO:
            self.cb_contenido.set("Estructura y datos")
        self._cambiar_tipo()
        self.cargar_historial()

    def _cambiar_tipo(self):
        tipo = self.seg_tipo.get()
        for w in (self.fila_esq, self.lbl_full, self.lista, self.sel):
            w.pack_forget()
        if tipo == "Full":
            self.lbl_obj.configure(text="Base de datos completa")
            self.lbl_full.pack(fill="x", pady=8)
            return
        if tipo == "Tablas":
            self.lbl_obj.configure(text="Tablas a respaldar")
            self.fila_esq.pack(fill="x", pady=4)
            self._cargar_tablas()
        else:
            self.lbl_obj.configure(text="Esquemas a respaldar")
            self.lista.cargar(getattr(self, "esquemas", []))
        self.lista.pack(fill="both", expand=True, pady=4)
        self.sel.pack(fill="x")

    def _cargar_tablas(self):
        self.lista.cargar(self.db.lista("SELECT table_name FROM dba_tables WHERE owner = :o ORDER BY 1",
                                        {"o": self.cb_esquema.get()}))

    def cargar_historial(self):
        filas = [(h.get("fecha"), h.get("tipo"), ", ".join(h.get("objetos", [])) or "(toda la BD)",
                  h.get("archivo"), h.get("directorio"), h.get("estado"), h.get("duracion"))
                 for h in datapump.historial() if h.get("operacion", "EXPORT") == "EXPORT"]
        self.tabla_hist.cargar(["FECHA", "TIPO", "OBJETOS", "ARCHIVO", "DIRECTORIO", "ESTADO", "DURACION_S"],
                               filas)

    # ------------------------------------------------------------------
    def ejecutar(self):
        if self.corriendo:
            return
        tipo = TIPOS[self.seg_tipo.get()]
        directorio = self.cb_dir.get()
        objetos = self.lista.marcados() if tipo != "FULL" else []
        if tipo != "FULL" and not objetos:
            info("Seleccione al menos un elemento para respaldar.")
            return
        esquemas = objetos if tipo == "SCHEMA" else [self.cb_esquema.get()] if tipo == "TABLE" else []
        tablas = objetos if tipo == "TABLE" else []
        etiqueta = [f"{esquemas[0]}.{t}" for t in tablas] if tipo == "TABLE" else objetos
        archivo = self.ent_archivo.get().strip() or datapump.nombre_archivo(tipo, etiqueta)
        if not archivo.lower().endswith(".dmp"):
            archivo += ".dmp"
        try:
            plsql, log = datapump.plsql_exportar(tipo, directorio, archivo, esquemas, tablas,
                                                 CONTENIDO[self.cb_contenido.get()])
        except ValueError as e:
            error(e)
            return
        contenido = CONTENIDO[self.cb_contenido.get()]
        self.txt_cmd.delete("1.0", "end")
        self.txt_cmd.insert("1.0", datapump.comando_equivalente(
            "EXPORT", tipo, directorio, archivo, log, esquemas, tablas,
            "" if contenido == "ALL" else f"CONTENT={contenido}"))
        self.txt_log.delete("1.0", "end")
        self.txt_log.insert("1.0", f"Iniciando respaldo {tipo} → {directorio}/{archivo} ...\n")
        self.ruta_log = None
        ruta = datapump.ruta_directorio(self.db, directorio)
        if ruta:
            self.ruta_log = os.path.join(os.path.normpath(ruta), log)
        self._iniciar(True)
        inicio = time.time()
        datos = dict(operacion="EXPORT", fecha=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     tipo=self.seg_tipo.get(), objetos=etiqueta, esquemas=esquemas, tablas=tablas,
                     archivo=archivo, log=log, directorio=directorio)
        self.app.bitacora(f"/* DBMS_DATAPUMP EXPORT {tipo} */ {datapump.comando_equivalente('EXPORT', tipo, directorio, archivo, log, esquemas, tablas)}")

        def correr():
            conn = self.db.nueva()
            try:
                return datapump.ejecutar(conn, plsql)
            finally:
                conn.close()

        def terminado(res):
            estado, err = res
            self._iniciar(False)
            self._leer_log()
            datos.update(estado="ERROR" if estado == "ERROR" else self._estado_log(estado),
                         duracion=round(time.time() - inicio, 1))
            datapump.registrar(datos)
            self.cargar_historial()
            if estado == "ERROR":
                self.txt_log.insert("end", f"\n*** ERROR ***\n{err}\n")
                error(err or "El trabajo falló", "Respaldo fallido")
            else:
                self.app.estado(f"Respaldo terminado: {archivo} ({datos['estado']})")
                info(f"Respaldo terminado ({datos['estado']}).\n\nArchivo: {archivo}\n"
                     f"Directorio: {directorio}\nDuración: {datos['duracion']} s", "Respaldo")

        def fallo(e):
            self._iniciar(False)
            datos.update(estado="ERROR", duracion=round(time.time() - inicio, 1))
            datapump.registrar(datos)
            self.cargar_historial()
            error(e)

        Tarea(self, correr, terminado, fallo)
        self.after(1000, self._seguir_log)

    def _estado_log(self, estado):
        texto = self.txt_log.get("1.0", "end").lower()
        if re.search(r"con \d+ error|completed with \d+ error", texto):
            return "COMPLETADO CON ERRORES"
        return "COMPLETADO" if estado == "COMPLETED" else estado

    def _iniciar(self, si):
        self.corriendo = si
        self.btn.configure(state="disabled" if si else "normal",
                           text="Respaldando..." if si else "💾  Ejecutar respaldo")
        if si:
            self.progreso.start()
        else:
            self.progreso.stop()
            self.progreso.set(1)

    def _leer_log(self):
        if self.ruta_log and os.path.isfile(self.ruta_log):
            with open(self.ruta_log, encoding="latin-1", errors="replace") as f:
                contenido = f.read()
            self.txt_log.delete("1.0", "end")
            self.txt_log.insert("1.0", contenido)
            self.txt_log.see("end")

    def _seguir_log(self):
        if not self.corriendo:
            return
        self._leer_log()
        self.after(1000, self._seguir_log)

    # ------------------------------------------------------------------
    def _hist(self):
        s = self.tabla_hist.seleccion()
        if not s:
            info("Seleccione un respaldo del historial.")
        return s

    def ver_log(self):
        s = self._hist()
        if not s:
            return
        h = next((h for h in datapump.historial() if h.get("archivo") == s["ARCHIVO"]), None)
        try:
            texto = datapump.leer_texto(self.db, s["DIRECTORIO"], h["log"])
        except Exception as e:  # noqa: BLE001
            error(e)
            return
        self.txt_log.delete("1.0", "end")
        self.txt_log.insert("1.0", texto)

    def restaurar(self):
        s = self._hist()
        if s:
            self.app.mostrar("Recuperación")
            self.app.pantallas["Recuperación"].preparar(s["DIRECTORIO"], s["ARCHIVO"])
