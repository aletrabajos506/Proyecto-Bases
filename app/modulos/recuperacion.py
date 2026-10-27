"""Recuperacion de respaldos con Data Pump (equivalente a impdp)."""
import datetime
import os
import time

import customtkinter as ctk

import datapump
from ui_common import FUENTE_SUB, Modulo, Tabla, Tarea, confirmar, error, info

TIPOS = {"Full": "FULL", "Esquemas": "SCHEMA", "Tablas": "TABLE"}
EXISTE = {"Omitir (SKIP)": "SKIP", "Agregar filas (APPEND)": "APPEND",
          "Vaciar y cargar (TRUNCATE)": "TRUNCATE", "Reemplazar (REPLACE)": "REPLACE"}


class Recuperacion(Modulo):
    titulo = "Recuperación de respaldos"
    subtitulo = ("Restaura un archivo de respaldo (.dmp) completo, por esquemas o por tablas. "
                 "Permite restaurar en otro esquema, otro tablespace o con otro nombre de tabla.")

    def construir(self):
        self.corriendo = False
        cont = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        cont.pack(fill="both", expand=True)

        # ---------------- seleccion de archivo
        izq = ctk.CTkFrame(cont, fg_color="transparent")
        izq.pack(side="left", fill="both", expand=True, padx=(0, 10))
        fila = ctk.CTkFrame(izq, fg_color="transparent")
        fila.pack(fill="x")
        ctk.CTkLabel(fila, text="1. Archivo de respaldo", font=FUENTE_SUB).pack(side="left")
        ctk.CTkLabel(fila, text="Directorio:").pack(side="left", padx=(20, 4))
        self.cb_dir = ctk.CTkComboBox(fila, values=[], width=180, command=lambda _: self.cargar_archivos())
        self.cb_dir.pack(side="left")
        self.tabla_arch = Tabla(izq, alto=10, al_seleccionar=lambda s: self._elegir())
        self.tabla_arch.pack(fill="both", expand=True, pady=(6, 6))
        ctk.CTkLabel(izq, text="Log de la restauración", font=FUENTE_SUB).pack(anchor="w")
        self.txt_log = ctk.CTkTextbox(izq, font=("Consolas", 11), wrap="none")
        self.txt_log.pack(fill="both", expand=True, pady=(2, 0))

        # ---------------- opciones
        form = ctk.CTkScrollableFrame(cont, width=380)
        form.pack(side="left", fill="y")
        ctk.CTkLabel(form, text="2. Qué restaurar", font=FUENTE_SUB).pack(anchor="w", pady=(4, 4))
        self.lbl_archivo = ctk.CTkLabel(form, text="Archivo: (ninguno)", wraplength=340, justify="left",
                                        anchor="w")
        self.lbl_archivo.pack(fill="x")
        self.seg_tipo = ctk.CTkSegmentedButton(form, values=list(TIPOS), command=lambda _: self._tipo())
        self.seg_tipo.set("Esquemas")
        self.seg_tipo.pack(fill="x", pady=6)
        self.lbl_esq = ctk.CTkLabel(form, text="Esquemas (coma) — vacío = todos los del archivo", anchor="w")
        self.lbl_esq.pack(fill="x")
        self.ent_esq = ctk.CTkEntry(form)
        self.ent_esq.pack(fill="x", pady=(0, 4))
        self.lbl_tab = ctk.CTkLabel(form, text="Tablas (coma)", anchor="w")
        self.ent_tab = ctk.CTkEntry(form)

        ctk.CTkLabel(form, text="3. Opciones", font=FUENTE_SUB).pack(anchor="w", pady=(10, 4))
        ctk.CTkLabel(form, text="Si la tabla ya existe:", anchor="w").pack(fill="x")
        self.cb_existe = ctk.CTkComboBox(form, values=list(EXISTE))
        self.cb_existe.set("Reemplazar (REPLACE)")
        self.cb_existe.pack(fill="x", pady=(0, 6))
        self.remaps = {}
        for clave, texto in (("esquema", "Restaurar en otro esquema (REMAP_SCHEMA)"),
                             ("tablespace", "Cambiar tablespace (REMAP_TABLESPACE)"),
                             ("tabla", "Renombrar tabla (REMAP_TABLE)")):
            chk = ctk.CTkCheckBox(form, text=texto)
            chk.pack(anchor="w", pady=(6, 2))
            f = ctk.CTkFrame(form, fg_color="transparent")
            f.pack(fill="x")
            o = ctk.CTkEntry(f, width=160, placeholder_text="origen")
            o.pack(side="left")
            ctk.CTkLabel(f, text="→").pack(side="left", padx=4)
            d = ctk.CTkEntry(f, width=160, placeholder_text="destino")
            d.pack(side="left")
            self.remaps[clave] = (chk, o, d)

        self.btn = ctk.CTkButton(form, text="♻  Restaurar respaldo", height=40,
                                 font=("Segoe UI", 14, "bold"), command=self.ejecutar)
        self.btn.pack(fill="x", pady=(16, 6))
        self.progreso = ctk.CTkProgressBar(form, mode="indeterminate")
        self.progreso.pack(fill="x")
        self.progreso.set(0)
        ctk.CTkLabel(form, text="Comando equivalente", anchor="w").pack(fill="x", pady=(10, 0))
        self.txt_cmd = ctk.CTkTextbox(form, height=80, font=("Consolas", 10))
        self.txt_cmd.pack(fill="x")
        self.archivo = None

    # ------------------------------------------------------------------
    def refrescar(self):
        dirs = self.db.lista("SELECT directory_name FROM dba_directories ORDER BY 1")
        self.cb_dir.configure(values=dirs)
        if self.cb_dir.get() not in dirs:
            self.cb_dir.set("RESPALDOS_DIR" if "RESPALDOS_DIR" in dirs else "DATA_PUMP_DIR")
        self.cargar_archivos()
        self._tipo()

    def cargar_archivos(self):
        ruta, filas = datapump.listar_archivos(self.db, self.cb_dir.get())
        if filas is None:
            self.tabla_arch.cargar(["AVISO"], [(f"La ruta {ruta} no es accesible desde esta máquina",)])
            return
        hist = {h["archivo"].upper(): h for h in datapump.historial() if h.get("operacion") == "EXPORT"}
        datos = []
        for nombre, tipo, mb, fecha in filas:
            if tipo != "Respaldo (dump)":
                continue
            h = hist.get(nombre.upper(), {})
            datos.append((nombre, mb, fecha, h.get("tipo", "?"), ", ".join(h.get("objetos", [])) or
                          ("(toda la BD)" if h.get("tipo") == "Full" else "")))
        self.tabla_arch.cargar(["ARCHIVO", "MB", "FECHA", "TIPO", "CONTENIDO"], datos)

    def _elegir(self):
        s = self.tabla_arch.seleccion()
        if not s or "ARCHIVO" not in s:
            return
        self.archivo = s["ARCHIVO"]
        self.lbl_archivo.configure(text=f"Archivo: {self.archivo}")
        h = next((h for h in datapump.historial()
                  if h.get("archivo", "").upper() == self.archivo.upper() and h.get("operacion") == "EXPORT"), None)
        if not h:
            return
        self.seg_tipo.set(h["tipo"])
        self.ent_esq.delete(0, "end")
        self.ent_tab.delete(0, "end")
        self.ent_esq.insert(0, ", ".join(h.get("esquemas", [])))
        self.ent_tab.insert(0, ", ".join(h.get("tablas", [])))
        self._tipo()

    def preparar(self, directorio, archivo):
        """Llamado desde otras pantallas para preseleccionar un respaldo."""
        self.cb_dir.set(directorio)
        self.cargar_archivos()
        for iid, fila in enumerate(self.tabla_arch.filas):
            if fila[0].upper() == archivo.upper():
                self.tabla_arch.tree.selection_set(str(iid))
                self.tabla_arch.tree.see(str(iid))
                break

    def _tipo(self):
        tipo = self.seg_tipo.get()
        self.lbl_tab.pack_forget()
        self.ent_tab.pack_forget()
        if tipo == "Full":
            self.lbl_esq.configure(text="(Se restaurará todo el contenido del archivo)")
            self.ent_esq.configure(state="disabled")
        else:
            self.ent_esq.configure(state="normal")
            if tipo == "Tablas":
                self.lbl_esq.configure(text="Esquema propietario de las tablas")
                self.lbl_tab.pack(fill="x", after=self.ent_esq)
                self.ent_tab.pack(fill="x", pady=(0, 4), after=self.lbl_tab)
            else:
                self.lbl_esq.configure(text="Esquemas (coma) — vacío = todos los del archivo")

    # ------------------------------------------------------------------
    def ejecutar(self):
        if self.corriendo:
            return
        if not self.archivo:
            info("Seleccione un archivo de respaldo (.dmp) de la lista.")
            return
        tipo = TIPOS[self.seg_tipo.get()]
        esquemas = [e.strip().upper() for e in self.ent_esq.get().split(",") if e.strip()]
        tablas = [t.strip().upper() for t in self.ent_tab.get().split(",") if t.strip()]
        if tipo == "TABLE" and (len(esquemas) != 1 or not tablas):
            info("Para restaurar tablas indique un esquema propietario y al menos una tabla.")
            return
        remap = {}
        for clave, (chk, o, d) in self.remaps.items():
            if chk.get():
                if not o.get().strip() or not d.get().strip():
                    info(f"Complete origen y destino del remapeo de {clave}.")
                    return
                remap[clave] = (o.get().strip(), d.get().strip())
        directorio = self.cb_dir.get()
        existe = EXISTE[self.cb_existe.get()]
        try:
            plsql, log = datapump.plsql_importar(
                tipo, directorio, self.archivo, esquemas, tablas, remap.get("esquema"),
                remap.get("tablespace"), existe, remap.get("tabla"))
        except ValueError as e:
            error(e)
            return
        resumen = f"Restaurar {self.seg_tipo.get().lower()} desde {self.archivo}"
        if remap.get("esquema"):
            resumen += f"\nEn el esquema {remap['esquema'][1].upper()}"
        if not confirmar(f"{resumen}\nTablas existentes: {existe}\n\n¿Continuar?"):
            return
        extra = [f"TABLE_EXISTS_ACTION={existe}"]
        nombres = {"esquema": "REMAP_SCHEMA", "tablespace": "REMAP_TABLESPACE", "tabla": "REMAP_TABLE"}
        for clave, (o, d) in remap.items():
            extra.append(f"{nombres[clave]}={o.upper()}:{d.upper()}")
        cmd = datapump.comando_equivalente("IMPORT", tipo, directorio, self.archivo, log,
                                           esquemas, tablas, " ".join(extra))
        self.txt_cmd.delete("1.0", "end")
        self.txt_cmd.insert("1.0", cmd)
        self.app.bitacora(f"/* DBMS_DATAPUMP IMPORT {tipo} */ {cmd}")
        self.txt_log.delete("1.0", "end")
        self.txt_log.insert("1.0", f"Iniciando restauración desde {self.archivo} ...\n")
        ruta = datapump.ruta_directorio(self.db, directorio)
        self.ruta_log = os.path.join(os.path.normpath(ruta), log) if ruta else None
        self._iniciar(True)
        inicio = time.time()
        datos = dict(operacion="IMPORT", fecha=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     tipo=self.seg_tipo.get(), objetos=esquemas + tablas, archivo=self.archivo,
                     log=log, directorio=directorio)

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
            texto = self.txt_log.get("1.0", "end").lower()
            con_errores = " error" in texto and ("error(es)" in texto or "error(s)" in texto)
            datos.update(estado="ERROR" if estado == "ERROR" else
                         "COMPLETADO CON ERRORES" if con_errores else "COMPLETADO",
                         duracion=round(time.time() - inicio, 1))
            datapump.registrar(datos)
            if estado == "ERROR":
                self.txt_log.insert("end", f"\n*** ERROR ***\n{err}\n")
                error(err or "El trabajo falló", "Restauración fallida")
            else:
                self.app.estado(f"Restauración terminada: {datos['estado']}")
                info(f"Restauración terminada: {datos['estado']}\nDuración: {datos['duracion']} s"
                     + ("\n\nRevise el log para ver el detalle de los errores." if con_errores else ""),
                     "Recuperación")

        def fallo(e):
            self._iniciar(False)
            error(e)

        Tarea(self, correr, terminado, fallo)
        self.after(1000, self._seguir_log)

    def _iniciar(self, si):
        self.corriendo = si
        self.btn.configure(state="disabled" if si else "normal",
                           text="Restaurando..." if si else "♻  Restaurar respaldo")
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
        if self.corriendo:
            self._leer_log()
            self.after(1000, self._seguir_log)
