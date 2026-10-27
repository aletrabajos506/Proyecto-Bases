"""Administracion de tablespaces y datafiles."""
import ntpath

import customtkinter as ctk

from db import ident, literal
from modulos.inicio import USO_TABLESPACES
from ui_common import FUENTE_SUB, Formulario, Modulo, Tabla, confirmar, info


class Tablespaces(Modulo):
    titulo = "Administración de tablespaces"
    subtitulo = ("Cree, amplíe y administre tablespaces y sus datafiles. "
                 "Seleccione un tablespace para ver sus archivos y segmentos.")

    def construir(self):
        self.barra(self.cuerpo, [
            ("➕ Crear tablespace", self.crear),
            ("Agregar datafile", self.agregar_datafile),
            ("Online / Offline", self.online_offline),
            ("Read only / Read write", self.solo_lectura),
            ("Tablespace por defecto", self.por_defecto),
            ("🗑 Eliminar", self.eliminar, "#a23b3b"),
        ]).pack(fill="x", pady=(0, 8))
        self.tabla = Tabla(self.cuerpo, alto=8, al_seleccionar=lambda s: self.cargar_detalle())
        self.tabla.pack(fill="both", expand=True)

        abajo = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        abajo.pack(fill="both", expand=True, pady=(10, 0))
        izq = ctk.CTkFrame(abajo, fg_color="transparent")
        izq.pack(side="left", fill="both", expand=True, padx=(0, 6))
        cab = ctk.CTkFrame(izq, fg_color="transparent")
        cab.pack(fill="x")
        ctk.CTkLabel(cab, text="Datafiles", font=FUENTE_SUB).pack(side="left")
        self.barra(cab, [("Redimensionar", self.redimensionar),
                         ("Autoextend", self.autoextend)]).pack(side="right")
        self.tabla_df = Tabla(izq, alto=6)
        self.tabla_df.pack(fill="both", expand=True, pady=(4, 0))
        der = ctk.CTkFrame(abajo, fg_color="transparent")
        der.pack(side="left", fill="both", expand=True, padx=(6, 0))
        ctk.CTkLabel(der, text="Segmentos más grandes", font=FUENTE_SUB).pack(anchor="w", pady=(2, 0))
        self.tabla_seg = Tabla(der, alto=6)
        self.tabla_seg.pack(fill="both", expand=True, pady=(4, 0))

    # ------------------------------------------------------------------
    def refrescar(self):
        self.tabla.cargar(*self.db.consultar(f"""
            SELECT t.tablespace_name TABLESPACE, t.status ESTADO, t.contents TIPO,
                   u.total TOTAL_MB, u.usado USADO_MB, ROUND(u.total-u.usado,2) LIBRE_MB,
                   u.pct PCT_USO, t.extent_management EXTENTS,
                   t.segment_space_management SEGMENTOS, t.bigfile BIGFILE,
                   (SELECT COUNT(*) FROM dba_data_files d WHERE d.tablespace_name=t.tablespace_name) +
                   (SELECT COUNT(*) FROM dba_temp_files d WHERE d.tablespace_name=t.tablespace_name) ARCHIVOS
              FROM dba_tablespaces t LEFT JOIN ({USO_TABLESPACES}) u ON u.ts = t.tablespace_name
             ORDER BY 1"""))
        self.tabla_df.cargar([], [])
        self.tabla_seg.cargar([], [])

    def cargar_detalle(self):
        ts = self._ts(avisar=False)
        if not ts:
            return
        self.tabla_df.cargar(*self.db.consultar("""
            SELECT file_id ID, file_name ARCHIVO, ROUND(bytes/1048576,2) MB, status ESTADO,
                   autoextensible AUTOEXT, ROUND(increment_by*8192/1048576,2) SIGUIENTE_MB,
                   ROUND(maxbytes/1048576,2) MAX_MB
              FROM dba_data_files WHERE tablespace_name = :ts
            UNION ALL
            SELECT file_id, file_name, ROUND(bytes/1048576,2), status, autoextensible,
                   ROUND(increment_by*8192/1048576,2), ROUND(maxbytes/1048576,2)
              FROM dba_temp_files WHERE tablespace_name = :ts ORDER BY 1""", {"ts": ts}))
        self.tabla_seg.cargar(*self.db.consultar("""
            SELECT owner PROPIETARIO, segment_name SEGMENTO, segment_type TIPO,
                   ROUND(bytes/1048576,2) MB, extents EXTENTS
              FROM dba_segments WHERE tablespace_name = :ts
             ORDER BY bytes DESC FETCH FIRST 30 ROWS ONLY""", {"ts": ts}))

    def _ts(self, avisar=True):
        s = self.tabla.seleccion()
        if not s:
            if avisar:
                info("Seleccione un tablespace de la lista.")
            return None
        return s["TABLESPACE"]

    def _ruta_datafiles(self):
        f = self.db.valor("SELECT file_name FROM dba_data_files WHERE ROWNUM = 1")
        return ntpath.dirname(f) if f else ""

    # ------------------------------------------------------------------ acciones
    def crear(self):
        r = Formulario.pedir(self, "Crear tablespace", [
            dict(clave="nombre", etiqueta="Nombre"),
            dict(clave="tipo", etiqueta="Tipo", tipo="combo",
                 opciones=["PERMANENTE", "TEMPORAL", "UNDO"]),
            dict(clave="archivo", etiqueta="Datafile (vacío = automático)", valor=""),
            dict(clave="tam", etiqueta="Tamaño inicial (MB)", valor="100"),
            dict(clave="auto", etiqueta="Autoextend", tipo="check", valor=True),
            dict(clave="next", etiqueta="Incremento (MB)", valor="10"),
            dict(clave="max", etiqueta="Tamaño máximo (MB o UNLIMITED)", valor="1024"),
            dict(clave="bigfile", etiqueta="Bigfile", tipo="check", valor=False),
        ], "Crear")
        if not r:
            return
        nombre = ident(r["nombre"])
        archivo = r["archivo"] or ntpath.join(self._ruta_datafiles(), f"{nombre}01.DBF")
        tipo = {"PERMANENTE": "", "TEMPORAL": "TEMPORARY ", "UNDO": "UNDO "}[r["tipo"]]
        clausula = "TEMPFILE" if tipo == "TEMPORARY " else "DATAFILE"
        big = "BIGFILE " if r["bigfile"] else ""
        sql = (f"CREATE {big}{tipo}TABLESPACE {nombre} {clausula} {literal(archivo)} "
               f"SIZE {int(r['tam'])}M")
        sql += self._clausula_auto(r)
        self.ddl(sql, f"Tablespace {nombre} creado")

    def _clausula_auto(self, r):
        if not r["auto"]:
            return " AUTOEXTEND OFF"
        maximo = r["max"].upper()
        maximo = "UNLIMITED" if maximo == "UNLIMITED" else f"{int(maximo)}M"
        return f" AUTOEXTEND ON NEXT {int(r['next'])}M MAXSIZE {maximo}"

    def agregar_datafile(self):
        ts = self._ts()
        if not ts:
            return
        tipo = self.tabla.seleccion()["TIPO"]
        n = int(self.db.valor("SELECT COUNT(*) FROM dba_data_files WHERE tablespace_name=:t", {"t": ts})) + \
            int(self.db.valor("SELECT COUNT(*) FROM dba_temp_files WHERE tablespace_name=:t", {"t": ts}))
        r = Formulario.pedir(self, f"Agregar archivo a {ts}", [
            dict(clave="archivo", etiqueta="Archivo",
                 valor=ntpath.join(self._ruta_datafiles(), f"{ts}{n + 1:02d}.DBF")),
            dict(clave="tam", etiqueta="Tamaño (MB)", valor="100"),
            dict(clave="auto", etiqueta="Autoextend", tipo="check", valor=True),
            dict(clave="next", etiqueta="Incremento (MB)", valor="10"),
            dict(clave="max", etiqueta="Tamaño máximo (MB o UNLIMITED)", valor="1024"),
        ], "Agregar")
        if not r:
            return
        clausula = "TEMPFILE" if tipo == "TEMPORARY" else "DATAFILE"
        sql = (f"ALTER TABLESPACE {ts} ADD {clausula} {literal(r['archivo'])} "
               f"SIZE {int(r['tam'])}M" + self._clausula_auto(r))
        self.ddl(sql, f"Archivo agregado a {ts}")

    def _datafile(self):
        s = self.tabla_df.seleccion()
        if not s:
            info("Seleccione un datafile en la tabla de datafiles.")
            return None, None
        temp = self.tabla.seleccion()["TIPO"] == "TEMPORARY"
        return s, ("TEMPFILE" if temp else "DATAFILE")

    def redimensionar(self):
        s, clase = self._datafile()
        if not s:
            return
        r = Formulario.pedir(self, "Redimensionar datafile", [
            dict(clave="tam", etiqueta=f"Nuevo tamaño (MB) — actual {s['MB']}", valor=str(int(s["MB"]))),
        ], "Redimensionar")
        if r:
            self.ddl(f"ALTER DATABASE {clase} {literal(s['ARCHIVO'])} RESIZE {int(r['tam'])}M",
                     "Datafile redimensionado")

    def autoextend(self):
        s, clase = self._datafile()
        if not s:
            return
        r = Formulario.pedir(self, "Configurar autoextend", [
            dict(clave="auto", etiqueta="Autoextend", tipo="check", valor=s["AUTOEXT"] == "YES"),
            dict(clave="next", etiqueta="Incremento (MB)", valor="10"),
            dict(clave="max", etiqueta="Tamaño máximo (MB o UNLIMITED)", valor="UNLIMITED"),
        ], "Aplicar")
        if r:
            self.ddl(f"ALTER DATABASE {clase} {literal(s['ARCHIVO'])}" + self._clausula_auto(r),
                     "Autoextend actualizado")

    def online_offline(self):
        ts = self._ts()
        if not ts:
            return
        nuevo = "ONLINE" if self.tabla.seleccion()["ESTADO"] == "OFFLINE" else "OFFLINE"
        if confirmar(f"¿Poner el tablespace {ts} en {nuevo}?"):
            self.ddl(f"ALTER TABLESPACE {ts} {nuevo}", f"{ts} ahora está {nuevo}")

    def solo_lectura(self):
        ts = self._ts()
        if not ts:
            return
        nuevo = "READ WRITE" if self.tabla.seleccion()["ESTADO"] == "READ ONLY" else "READ ONLY"
        if confirmar(f"¿Cambiar el tablespace {ts} a {nuevo}?"):
            self.ddl(f"ALTER TABLESPACE {ts} {nuevo}", f"{ts} ahora está {nuevo}")

    def por_defecto(self):
        ts = self._ts()
        if not ts:
            return
        tipo = self.tabla.seleccion()["TIPO"]
        if tipo == "UNDO":
            info("Un tablespace UNDO no puede ser el tablespace por defecto.")
            return
        clase = "DEFAULT TEMPORARY TABLESPACE" if tipo == "TEMPORARY" else "DEFAULT TABLESPACE"
        if confirmar(f"¿Establecer {ts} como {clase.lower()} de la base de datos?"):
            self.ddl(f"ALTER DATABASE {clase} {ts}", f"{ts} es ahora el tablespace por defecto")

    def eliminar(self):
        ts = self._ts()
        if not ts:
            return
        if ts in ("SYSTEM", "SYSAUX", "UNDOTBS1", "TEMP"):
            info(f"{ts} es un tablespace del sistema y no se puede eliminar desde aquí.")
            return
        if confirmar(f"¿Eliminar el tablespace {ts} INCLUDING CONTENTS AND DATAFILES?\n"
                     "Esta acción no se puede deshacer."):
            self.ddl(f"DROP TABLESPACE {ts} INCLUDING CONTENTS AND DATAFILES CASCADE CONSTRAINTS",
                     f"Tablespace {ts} eliminado")
