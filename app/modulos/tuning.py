"""Tuning de consultas: planes de ejecucion, estadisticas e indices."""
import time

import customtkinter as ctk

from db import ident, literal
from ui_common import (FUENTE_MONO, FUENTE_SUB, Formulario, Modulo, Tabla, Tarea,
                       confirmar, error, info, tabs)

EJEMPLO_SQL = """SELECT c.nombre, c.provincia, COUNT(*) facturas, SUM(f.total) monto
  FROM clientes c JOIN facturas f ON f.cliente_id = c.cliente_id
 WHERE c.provincia = 'Alajuela'
   AND f.cliente_id = 1234
 GROUP BY c.nombre, c.provincia"""


class Tuning(Modulo):
    titulo = "Tuning de consultas"
    subtitulo = "Analice planes de ejecución, recolecte estadísticas del optimizador y administre índices."

    def construir(self):
        self.tv, (t_plan, t_est, t_idx) = tabs(self.cuerpo, ["Plan de ejecución", "Estadísticas", "Índices"])
        self._tab_plan(t_plan)
        self._tab_estadisticas(t_est)
        self._tab_indices(t_idx)

    def _esquemas(self):
        return self.db.lista("SELECT username FROM dba_users WHERE oracle_maintained='N' ORDER BY 1")

    def refrescar(self):
        esquemas = self._esquemas() or ["SYS"]
        for combo in (self.cb_esq_plan, self.cb_esq_est, self.cb_esq_idx):
            combo.configure(values=esquemas)
            if combo.get() not in esquemas:
                combo.set("VENTAS" if "VENTAS" in esquemas else esquemas[0])
        self.cargar_estadisticas()
        self.cargar_indices()

    # ================================================================== PLAN
    def _tab_plan(self, t):
        fila = ctk.CTkFrame(t, fg_color="transparent")
        fila.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(fila, text="Esquema de análisis:").pack(side="left", padx=(0, 6))
        self.cb_esq_plan = ctk.CTkComboBox(fila, values=[], width=160)
        self.cb_esq_plan.pack(side="left", padx=(0, 12))
        self.barra(fila, [
            ("📋 Explain plan (estimado)", self.explain),
            ("▶ Ejecutar y ver plan real", self.plan_real),
            ("Ver ejemplo", lambda: (self.sql.delete("1.0", "end"), self.sql.insert("1.0", EJEMPLO_SQL))),
        ]).pack(side="left")
        self.sql = ctk.CTkTextbox(t, height=140, font=FUENTE_MONO)
        self.sql.pack(fill="x")
        self.sql.insert("1.0", EJEMPLO_SQL)
        self.lbl_tiempo = ctk.CTkLabel(t, text="", anchor="w")
        self.lbl_tiempo.pack(fill="x", pady=(4, 0))
        self.salida_plan = ctk.CTkTextbox(t, font=("Consolas", 11), wrap="none")
        self.salida_plan.pack(fill="both", expand=True, pady=(4, 0))

    def _texto_sql(self):
        s = self.sql.get("1.0", "end").strip().rstrip(";").strip()
        if not s:
            raise ValueError("Escriba una sentencia SQL.")
        return s

    def _con_esquema(self, funcion):
        esquema = ident(self.cb_esq_plan.get())
        usuario = self.db.valor("SELECT USER FROM dual")
        self.db.ejecutar(f"ALTER SESSION SET CURRENT_SCHEMA = {esquema}")
        try:
            return funcion()
        finally:
            self.db.ejecutar(f"ALTER SESSION SET CURRENT_SCHEMA = {usuario}")

    def _mostrar_plan(self, lineas, encabezado=""):
        self.salida_plan.delete("1.0", "end")
        self.salida_plan.insert("1.0", encabezado + "\n".join(lineas))

    def explain(self):
        try:
            sql = self._texto_sql()
            sid = f"OA{int(time.time())}"

            def correr():
                self.db.ejecutar(f"EXPLAIN PLAN SET STATEMENT_ID = '{sid}' FOR {sql}")
                return self.db.lista(
                    "SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY('PLAN_TABLE', :s, 'TYPICAL'))",
                    {"s": sid})
            lineas = self._con_esquema(correr)
        except Exception as e:  # noqa: BLE001
            error(e)
            return
        self.lbl_tiempo.configure(text="Plan estimado por el optimizador (la consulta no se ejecutó).")
        self._mostrar_plan(lineas)
        self.app.bitacora(f"EXPLAIN PLAN FOR {sql[:80]}...")

    def plan_real(self):
        try:
            sql = self._texto_sql()
            if not sql.upper().lstrip("( ").startswith(("SELECT", "WITH")):
                if not confirmar("La sentencia no es un SELECT y se ejecutará realmente. ¿Continuar?"):
                    return

            def correr():
                self.db.ejecutar("ALTER SESSION SET STATISTICS_LEVEL = ALL")
                with self.db.lock:
                    cur = self.db.conn.cursor()
                    t0 = time.perf_counter()
                    cur.execute(sql)
                    n = len(cur.fetchall()) if cur.description else cur.rowcount
                    seg = time.perf_counter() - t0
                    cur.execute("""SELECT prev_sql_id, prev_child_number FROM v$session
                                    WHERE sid = SYS_CONTEXT('USERENV','SID')""")
                    sql_id, hijo = cur.fetchone()
                lineas = self.db.lista(
                    "SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(:i, :c, 'ALLSTATS LAST'))",
                    {"i": sql_id, "c": hijo})
                self.db.ejecutar("ALTER SESSION SET STATISTICS_LEVEL = TYPICAL")
                return n, seg, lineas
            n, seg, lineas = self._con_esquema(correr)
        except Exception as e:  # noqa: BLE001
            error(e)
            return
        self.lbl_tiempo.configure(text=f"Ejecutada: {n} filas en {seg * 1000:,.1f} ms   "
                                       "(E-Rows = estimadas, A-Rows = reales, Buffers = lecturas lógicas)")
        self._mostrar_plan(lineas)
        self.app.bitacora(f"/* plan real */ {sql[:80]}...")

    # ================================================================== ESTADISTICAS
    def _tab_estadisticas(self, t):
        fila = ctk.CTkFrame(t, fg_color="transparent")
        fila.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(fila, text="Esquema:").pack(side="left", padx=(0, 6))
        self.cb_esq_est = ctk.CTkComboBox(fila, values=[], width=160,
                                          command=lambda _: self.cargar_estadisticas())
        self.cb_esq_est.pack(side="left", padx=(0, 12))
        self.barra(fila, [
            ("Recolectar tabla", self.stats_tabla),
            ("Recolectar esquema completo", self.stats_esquema),
            ("Eliminar estadísticas", self.stats_borrar, "#a23b3b"),
            ("Bloquear / Desbloquear", self.stats_bloqueo),
        ]).pack(side="left")
        self.tabla_est = Tabla(t, alto=9, al_seleccionar=lambda s: self.cargar_columnas())
        self.tabla_est.pack(fill="both", expand=True)
        ctk.CTkLabel(t, text="Estadísticas de columnas", font=FUENTE_SUB).pack(anchor="w", pady=(8, 2))
        self.tabla_col = Tabla(t, alto=6)
        self.tabla_col.pack(fill="both", expand=True)

    def cargar_estadisticas(self):
        esquema = self.cb_esq_est.get()
        self.tabla_est.cargar(*self.db.consultar("""
            SELECT table_name TABLA, num_rows FILAS, blocks BLOQUES, avg_row_len LARGO_PROM,
                   sample_size MUESTRA, last_analyzed ULTIMO_ANALISIS,
                   stale_stats OBSOLETAS, stattype_locked BLOQUEADAS
              FROM dba_tab_statistics
             WHERE owner = :o AND object_type = 'TABLE' ORDER BY table_name""", {"o": esquema}))
        self.tabla_col.cargar([], [])

    def cargar_columnas(self):
        s = self.tabla_est.seleccion()
        if not s:
            return
        self.tabla_col.cargar(*self.db.consultar("""
            SELECT column_name COLUMNA, num_distinct DISTINTOS, num_nulls NULOS,
                   density DENSIDAD, histogram HISTOGRAMA, num_buckets BUCKETS, last_analyzed ANALIZADA
              FROM dba_tab_col_statistics WHERE owner = :o AND table_name = :t
             ORDER BY column_name""", {"o": self.cb_esq_est.get(), "t": s["TABLA"]}))

    def _tabla_est(self):
        s = self.tabla_est.seleccion()
        if not s:
            info("Seleccione una tabla.")
        return s

    def stats_tabla(self):
        s = self._tabla_est()
        if not s:
            return
        r = Formulario.pedir(self, f"Recolectar estadísticas de {s['TABLA']}", [
            dict(clave="pct", etiqueta="Muestra (%) o AUTO", valor="AUTO"),
            dict(clave="hist", etiqueta="Histogramas", tipo="combo",
                 opciones=["FOR ALL COLUMNS SIZE AUTO", "FOR ALL COLUMNS SIZE 1",
                           "FOR ALL INDEXED COLUMNS SIZE AUTO"]),
            dict(clave="cascade", etiqueta="Incluir índices (cascade)", tipo="check", valor=True),
        ], "Recolectar")
        if not r:
            return
        pct = "DBMS_STATS.AUTO_SAMPLE_SIZE" if r["pct"].upper() == "AUTO" else str(float(r["pct"]))
        esquema = ident(self.cb_esq_est.get())
        sql = (f"BEGIN DBMS_STATS.GATHER_TABLE_STATS(ownname => {literal(esquema)}, "
               f"tabname => {literal(s['TABLA'])}, estimate_percent => {pct}, "
               f"method_opt => {literal(r['hist'])}, cascade => {'TRUE' if r['cascade'] else 'FALSE'}); END;")
        self.ddl(sql, f"Estadísticas recolectadas para {s['TABLA']}", refrescar=False)
        self.cargar_estadisticas()

    def stats_esquema(self):
        esquema = ident(self.cb_esq_est.get())
        sql = f"BEGIN DBMS_STATS.GATHER_SCHEMA_STATS(ownname => {literal(esquema)}, cascade => TRUE); END;"
        self.app.estado(f"Recolectando estadísticas del esquema {esquema}...")
        conn = self.db.nueva()

        def correr():
            try:
                conn.cursor().execute(sql)
            finally:
                conn.close()

        def listo(_):
            self.app.bitacora(sql)
            self.app.estado(f"Estadísticas del esquema {esquema} recolectadas")
            self.cargar_estadisticas()
        Tarea(self, correr, listo)

    def stats_borrar(self):
        s = self._tabla_est()
        if s and confirmar(f"¿Eliminar las estadísticas de {s['TABLA']}?"):
            esquema = ident(self.cb_esq_est.get())
            self.ddl(f"BEGIN DBMS_STATS.DELETE_TABLE_STATS({literal(esquema)}, {literal(s['TABLA'])}); END;",
                     "Estadísticas eliminadas", refrescar=False)
            self.cargar_estadisticas()

    def stats_bloqueo(self):
        s = self._tabla_est()
        if not s:
            return
        esquema = ident(self.cb_esq_est.get())
        proc = "UNLOCK_TABLE_STATS" if s["BLOQUEADAS"] else "LOCK_TABLE_STATS"
        self.ddl(f"BEGIN DBMS_STATS.{proc}({literal(esquema)}, {literal(s['TABLA'])}); END;",
                 "Bloqueo de estadísticas actualizado", refrescar=False)
        self.cargar_estadisticas()

    # ================================================================== INDICES
    def _tab_indices(self, t):
        fila = ctk.CTkFrame(t, fg_color="transparent")
        fila.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(fila, text="Esquema:").pack(side="left", padx=(0, 6))
        self.cb_esq_idx = ctk.CTkComboBox(fila, values=[], width=160,
                                          command=lambda _: self.cargar_indices())
        self.cb_esq_idx.pack(side="left", padx=(0, 12))
        self.barra(fila, [
            ("➕ Crear índice", self.crear_indice),
            ("Reconstruir", self.reconstruir),
            ("Visible / Invisible", self.visibilidad),
            ("🗑 Eliminar", self.eliminar_indice, "#a23b3b"),
            ("🔎 Sugerencias", self.sugerencias),
        ]).pack(side="left")
        self.tabla_idx = Tabla(t, alto=12)
        self.tabla_idx.pack(fill="both", expand=True)
        self.lbl_idx = ctk.CTkLabel(t, text="", anchor="w", justify="left")
        self.lbl_idx.pack(fill="x", pady=(4, 0))

    def cargar_indices(self):
        self.tabla_idx.cargar(*self.db.consultar("""
            SELECT i.index_name INDICE, i.table_name TABLA,
                   (SELECT LISTAGG(c.column_name, ', ') WITHIN GROUP (ORDER BY c.column_position)
                      FROM dba_ind_columns c
                     WHERE c.index_owner = i.owner AND c.index_name = i.index_name) COLUMNAS,
                   i.index_type TIPO, i.uniqueness UNICIDAD, i.status ESTADO, i.visibility VISIBILIDAD,
                   i.blevel BLEVEL, i.leaf_blocks HOJAS, i.distinct_keys CLAVES_DISTINTAS,
                   i.clustering_factor CLUSTERING_FACTOR, i.tablespace_name TABLESPACE, i.last_analyzed ANALIZADO
              FROM dba_indexes i WHERE i.owner = :o ORDER BY i.table_name, i.index_name""",
            {"o": self.cb_esq_idx.get()}))
        self.lbl_idx.configure(text="")

    def _indice(self):
        s = self.tabla_idx.seleccion()
        if not s:
            info("Seleccione un índice.")
        return s

    def crear_indice(self):
        esquema = ident(self.cb_esq_idx.get())
        tablas = self.db.lista("SELECT table_name FROM dba_tables WHERE owner=:o ORDER BY 1", {"o": esquema})
        if not tablas:
            info("El esquema no tiene tablas.")
            return
        tss = self.db.lista("SELECT tablespace_name FROM dba_tablespaces WHERE contents='PERMANENT' ORDER BY 1")
        r = Formulario.pedir(self, f"Crear índice en {esquema}", [
            dict(clave="tabla", etiqueta="Tabla", tipo="combo", opciones=tablas),
            dict(clave="cols", etiqueta="Columnas (separadas por coma)"),
            dict(clave="nombre", etiqueta="Nombre del índice (opcional)"),
            dict(clave="tipo", etiqueta="Tipo", tipo="combo", opciones=["NORMAL (B-Tree)", "UNIQUE", "BITMAP"]),
            dict(clave="ts", etiqueta="Tablespace", tipo="combo", opciones=["(por defecto)"] + tss),
        ], "Crear")
        if not r:
            return
        try:
            tabla = ident(r["tabla"])
            cols = [ident(c) for c in r["cols"].split(",") if c.strip()]
            if not cols:
                raise ValueError("Indique al menos una columna.")
            nombre = ident(r["nombre"] or f"IX_{tabla[:15]}_{'_'.join(c[:6] for c in cols)}"[:128])
        except ValueError as e:
            error(e)
            return
        tipo = {"UNIQUE": "UNIQUE ", "BITMAP": "BITMAP "}.get(r["tipo"], "")
        sql = f"CREATE {tipo}INDEX {esquema}.{nombre} ON {esquema}.{tabla} ({', '.join(cols)})"
        if r["ts"] != "(por defecto)":
            sql += f" TABLESPACE {ident(r['ts'])}"
        self.ddl(sql, f"Índice {nombre} creado", refrescar=False)
        self.cargar_indices()

    def reconstruir(self):
        s = self._indice()
        if s and confirmar(f"¿Reconstruir el índice {s['INDICE']} (ONLINE)?"):
            self.ddl(f"ALTER INDEX {ident(self.cb_esq_idx.get())}.{s['INDICE']} REBUILD ONLINE",
                     "Índice reconstruido", refrescar=False)
            self.cargar_indices()

    def visibilidad(self):
        s = self._indice()
        if not s:
            return
        nuevo = "VISIBLE" if s["VISIBILIDAD"] == "INVISIBLE" else "INVISIBLE"
        self.ddl(f"ALTER INDEX {ident(self.cb_esq_idx.get())}.{s['INDICE']} {nuevo}",
                 f"Índice ahora {nuevo}", refrescar=False)
        self.cargar_indices()

    def eliminar_indice(self):
        s = self._indice()
        if s and confirmar(f"¿Eliminar el índice {s['INDICE']}?"):
            self.ddl(f"DROP INDEX {ident(self.cb_esq_idx.get())}.{s['INDICE']}",
                     "Índice eliminado", refrescar=False)
            self.cargar_indices()

    def sugerencias(self):
        """Claves foraneas sin indice y tablas sin estadisticas."""
        esquema = self.cb_esq_idx.get()
        cols, filas = self.db.consultar("""
            SELECT 'FK sin índice' PROBLEMA, c.table_name TABLA, cc.column_name COLUMNA,
                   'CREATE INDEX ' || c.owner || '.IX_' || SUBSTR(c.table_name,1,15) || '_' ||
                   SUBSTR(cc.column_name,1,10) || ' ON ' || c.owner || '.' || c.table_name ||
                   ' (' || cc.column_name || ')' SUGERENCIA
              FROM dba_constraints c JOIN dba_cons_columns cc
                ON cc.owner = c.owner AND cc.constraint_name = c.constraint_name
             WHERE c.owner = :o AND c.constraint_type = 'R'
               AND NOT EXISTS (SELECT 1 FROM dba_ind_columns ic
                                WHERE ic.table_owner = c.owner AND ic.table_name = c.table_name
                                  AND ic.column_name = cc.column_name AND ic.column_position = cc.position)
            UNION ALL
            SELECT 'Sin estadísticas / obsoletas', table_name, NULL,
                   'EXEC DBMS_STATS.GATHER_TABLE_STATS(''' || owner || ''',''' || table_name || ''')'
              FROM dba_tab_statistics
             WHERE owner = :o AND object_type = 'TABLE' AND (last_analyzed IS NULL OR stale_stats = 'YES')""",
            {"o": esquema})
        if not filas:
            info("No se encontraron problemas evidentes en el esquema.")
            return
        self.tabla_idx.cargar(cols, filas)
        self.lbl_idx.configure(text="Mostrando sugerencias. Presione «Refrescar» para volver a la lista de índices.")
