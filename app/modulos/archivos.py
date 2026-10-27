"""Administracion de directorios Oracle y archivos de respaldo."""
import os

import customtkinter as ctk

import datapump
from db import ident, literal
from ui_common import (FUENTE_SUB, Formulario, Modulo, Tabla, VisorTexto, confirmar,
                       error, etiqueta_valor, info)


class Archivos(Modulo):
    titulo = "Archivos de respaldo y directorios"
    subtitulo = ("Administre los objetos DIRECTORY de Oracle y los archivos de respaldo (.dmp) "
                 "y de log que contienen.")

    def construir(self):
        cab = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        cab.pack(fill="x")
        ctk.CTkLabel(cab, text="Directorios", font=FUENTE_SUB).pack(side="left")
        self.barra(cab, [
            ("➕ Crear directorio", self.crear),
            ("Otorgar acceso", self.otorgar),
            ("Abrir carpeta", self.abrir_carpeta),
            ("🗑 Eliminar directorio", self.eliminar_dir, "#a23b3b"),
        ]).pack(side="right")
        self.chk_todos = ctk.CTkCheckBox(self.cuerpo, text="Mostrar directorios internos de Oracle",
                                         command=self.refrescar_seguro)
        self.chk_todos.pack(anchor="w", pady=(4, 2))
        self.tabla_dir = Tabla(self.cuerpo, alto=6, al_seleccionar=lambda s: self.cargar_archivos())
        self.tabla_dir.pack(fill="both", expand=True)

        cab2 = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        cab2.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(cab2, text="Archivos del directorio", font=FUENTE_SUB).pack(side="left")
        self.barra(cab2, [
            ("Ver contenido", self.ver),
            ("Renombrar", self.renombrar),
            ("Mover a...", self.mover),
            ("Copiar a...", self.copiar),
            ("♻ Restaurar", self.restaurar),
            ("🗑 Eliminar", self.eliminar_archivo, "#a23b3b"),
        ]).pack(side="right")
        resumen = ctk.CTkFrame(self.cuerpo)
        resumen.pack(fill="x", pady=(4, 4))
        self.lbl_ruta = etiqueta_valor(resumen, "Ruta:", 0)
        self.lbl_cant = etiqueta_valor(resumen, "Archivos:", 0, 2)
        self.lbl_tam = etiqueta_valor(resumen, "Espacio usado:", 0, 4)
        self.tabla_arch = Tabla(self.cuerpo, alto=9, seleccion="extended",
                                al_doble_clic=lambda s: self.ver())
        self.tabla_arch.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    def refrescar(self):
        filtro = "" if self.chk_todos.get() else \
            "WHERE origin_con_id > 1 OR directory_name IN ('DATA_PUMP_DIR', 'RESPALDOS_DIR')"
        self.tabla_dir.cargar(*self.db.consultar(f"""
            SELECT d.directory_name DIRECTORIO, d.directory_path RUTA, d.owner PROPIETARIO,
                   (SELECT LISTAGG(p.grantee || ':' || p.privilege, ', ')
                           WITHIN GROUP (ORDER BY p.grantee, p.privilege)
                      FROM dba_tab_privs p WHERE p.table_name = d.directory_name
                       AND p.type = 'DIRECTORY') ACCESOS
              FROM dba_directories d {filtro} ORDER BY 1"""))
        self.tabla_arch.cargar([], [])
        for l in (self.lbl_ruta, self.lbl_cant, self.lbl_tam):
            l.configure(text="-")

    def _dir(self):
        s = self.tabla_dir.seleccion()
        if not s:
            info("Seleccione un directorio.")
            return None
        return s

    def cargar_archivos(self):
        s = self.tabla_dir.seleccion()
        if not s:
            return
        ruta, filas = datapump.listar_archivos(self.db, s["DIRECTORIO"])
        self.lbl_ruta.configure(text=ruta or "-")
        if filas is None:
            self.tabla_arch.cargar(["AVISO"], [("La ruta no existe o no es accesible desde esta máquina",)])
            self.lbl_cant.configure(text="-")
            self.lbl_tam.configure(text="-")
            return
        self.tabla_arch.cargar(["ARCHIVO", "TIPO", "MB", "MODIFICADO"], filas)
        self.lbl_cant.configure(text=str(len(filas)))
        self.lbl_tam.configure(text=f"{sum(f[2] for f in filas):,.2f} MB")

    # ------------------------------------------------------------------ directorios
    def crear(self):
        usuarios = self.db.lista("SELECT username FROM dba_users WHERE oracle_maintained='N' ORDER BY 1")
        r = Formulario.pedir(self, "Crear directorio", [
            dict(clave="nombre", etiqueta="Nombre del directorio", valor="RESPALDOS_"),
            dict(clave="ruta", etiqueta="Ruta en el servidor", valor="C:\\oracle_respaldos\\"),
            dict(clave="crear", etiqueta="Crear la carpeta si no existe", tipo="check", valor=True),
            dict(clave="usuario", etiqueta="Otorgar READ/WRITE a", tipo="combo",
                 opciones=["(nadie)"] + usuarios),
        ], "Crear")
        if not r:
            return
        try:
            nombre = ident(r["nombre"])
        except ValueError as e:
            error(e)
            return
        ruta = r["ruta"].strip()
        if not ruta:
            error("Indique la ruta.")
            return
        if r["crear"]:
            try:
                os.makedirs(ruta, exist_ok=True)
            except OSError as e:
                error(f"No se pudo crear la carpeta: {e}")
                return
        if self.ddl(f"CREATE OR REPLACE DIRECTORY {nombre} AS {literal(ruta)}", f"Directorio {nombre} creado",
                    refrescar=False) and r["usuario"] != "(nadie)":
            self.ddl(f"GRANT READ, WRITE ON DIRECTORY {nombre} TO {ident(r['usuario'])}", refrescar=False)
        self.refrescar_seguro()

    def otorgar(self):
        s = self._dir()
        if not s:
            return
        usuarios = self.db.lista("SELECT username FROM dba_users ORDER BY 1") + \
            self.db.lista("SELECT role FROM dba_roles WHERE oracle_maintained='N' ORDER BY 1")
        r = Formulario.pedir(self, f"Acceso a {s['DIRECTORIO']}", [
            dict(clave="usuario", etiqueta="Usuario o rol", tipo="combo", opciones=usuarios),
            dict(clave="priv", etiqueta="Privilegio", tipo="combo", opciones=["READ, WRITE", "READ", "WRITE"]),
            dict(clave="accion", etiqueta="Acción", tipo="combo", opciones=["Otorgar", "Revocar"]),
        ], "Aplicar")
        if not r:
            return
        priv = {"READ, WRITE": "READ, WRITE", "READ": "READ", "WRITE": "WRITE"}[r["priv"]]
        if r["accion"] == "Otorgar":
            sql = f"GRANT {priv} ON DIRECTORY {ident(s['DIRECTORIO'])} TO {ident(r['usuario'])}"
        else:
            sql = f"REVOKE {priv} ON DIRECTORY {ident(s['DIRECTORIO'])} FROM {ident(r['usuario'])}"
        self.ddl(sql, "Accesos actualizados")

    def abrir_carpeta(self):
        s = self._dir()
        if not s:
            return
        ruta = os.path.normpath(s["RUTA"])
        if os.path.isdir(ruta):
            os.startfile(ruta)
        else:
            info(f"La carpeta {ruta} no existe en esta máquina.")

    def eliminar_dir(self):
        s = self._dir()
        if not s:
            return
        if s["DIRECTORIO"] in ("DATA_PUMP_DIR",):
            info("DATA_PUMP_DIR es el directorio predeterminado de Oracle y no debe eliminarse.")
            return
        if confirmar(f"¿Eliminar el objeto DIRECTORY {s['DIRECTORIO']}?\n"
                     "(Los archivos en disco NO se borran.)"):
            self.ddl(f"DROP DIRECTORY {ident(s['DIRECTORIO'])}", "Directorio eliminado")

    # ------------------------------------------------------------------ archivos
    def _archivos(self):
        sel = [s for s in self.tabla_arch.selecciones() if "ARCHIVO" in s]
        if not sel:
            info("Seleccione uno o más archivos.")
        return sel

    def _otros_directorios(self, actual):
        return [d for d in self.db.lista("SELECT directory_name FROM dba_directories ORDER BY 1") if d != actual]

    def ver(self):
        sel = self._archivos()
        if not sel:
            return
        a = sel[0]
        if a["TIPO"] == "Respaldo (dump)":
            info("Los archivos .dmp son binarios. Use «Restaurar» o vea el .log asociado.")
            return
        try:
            texto = datapump.leer_texto(self.db, self.tabla_dir.seleccion()["DIRECTORIO"], a["ARCHIVO"])
        except Exception as e:  # noqa: BLE001
            error(e)
            return
        VisorTexto(self, a["ARCHIVO"], texto)

    def eliminar_archivo(self):
        sel = self._archivos()
        if not sel:
            return
        d = self.tabla_dir.seleccion()["DIRECTORIO"]
        nombres = "\n".join(a["ARCHIVO"] for a in sel)
        if not confirmar(f"¿Eliminar {len(sel)} archivo(s) del directorio {d}?\n\n{nombres}"):
            return
        for a in sel:
            self.ddl(f"BEGIN UTL_FILE.FREMOVE({literal(d)}, {literal(a['ARCHIVO'])}); END;", refrescar=False)
        self.app.estado(f"{len(sel)} archivo(s) eliminado(s)")
        self.cargar_archivos()

    def renombrar(self):
        sel = self._archivos()
        if not sel:
            return
        d = self.tabla_dir.seleccion()["DIRECTORIO"]
        r = Formulario.pedir(self, "Renombrar archivo", [
            dict(clave="nuevo", etiqueta="Nuevo nombre", valor=sel[0]["ARCHIVO"])], "Renombrar")
        if r and r["nuevo"]:
            self.ddl(f"BEGIN UTL_FILE.FRENAME({literal(d)}, {literal(sel[0]['ARCHIVO'])}, "
                     f"{literal(d)}, {literal(r['nuevo'])}, FALSE); END;", "Archivo renombrado", refrescar=False)
            self.cargar_archivos()

    def _destino(self, titulo):
        d = self.tabla_dir.seleccion()["DIRECTORIO"]
        otros = self._otros_directorios(d)
        if not otros:
            info("No hay otros directorios disponibles.")
            return d, None
        r = Formulario.pedir(self, titulo, [
            dict(clave="destino", etiqueta="Directorio destino", tipo="combo", opciones=otros)], "Aceptar")
        return d, (ident(r["destino"]) if r else None)

    def mover(self):
        sel = self._archivos()
        if not sel:
            return
        d, destino = self._destino("Mover archivos")
        if not destino:
            return
        for a in sel:
            self.ddl(f"BEGIN UTL_FILE.FRENAME({literal(d)}, {literal(a['ARCHIVO'])}, "
                     f"{literal(destino)}, {literal(a['ARCHIVO'])}, FALSE); END;", refrescar=False)
        self.app.estado(f"{len(sel)} archivo(s) movido(s) a {destino}")
        self.cargar_archivos()

    def copiar(self):
        sel = self._archivos()
        if not sel:
            return
        d, destino = self._destino("Copiar archivos")
        if not destino:
            return
        for a in sel:
            self.ddl(f"BEGIN DBMS_FILE_TRANSFER.COPY_FILE({literal(d)}, {literal(a['ARCHIVO'])}, "
                     f"{literal(destino)}, {literal(a['ARCHIVO'])}); END;", refrescar=False)
        self.app.estado(f"Copia a {destino} terminada")

    def restaurar(self):
        sel = self._archivos()
        if not sel:
            return
        if sel[0]["TIPO"] != "Respaldo (dump)":
            info("Seleccione un archivo .dmp.")
            return
        d = self.tabla_dir.seleccion()["DIRECTORIO"]
        self.app.mostrar("Recuperación")
        self.app.pantallas["Recuperación"].preparar(d, sel[0]["ARCHIVO"])
