"""Monitoreo de performance de la base de datos."""
import tkinter as tk

import customtkinter as ctk

from ui_common import (COLORES, FUENTE_SUB, Modulo, Tabla, VisorTexto, confirmar,
                       error, info, tabs)

METRICAS = [
    ("Host CPU Utilization (%)", "CPU del servidor", "%"),
    ("Database CPU Time Ratio", "CPU / DB Time", "%"),
    ("Buffer Cache Hit Ratio", "Buffer cache hit", "%"),
    ("Library Cache Hit Ratio", "Library cache hit", "%"),
    ("Average Active Sessions", "Sesiones activas prom.", ""),
    ("Current Logons Count", "Sesiones conectadas", ""),
    ("Executions Per Sec", "Ejecuciones / seg", ""),
    ("User Transaction Per Sec", "Transacciones / seg", ""),
    ("Logical Reads Per Sec", "Lecturas lógicas / seg", ""),
    ("Physical Reads Per Sec", "Lecturas físicas / seg", ""),
    ("SQL Service Response Time", "Tiempo resp. SQL (cs)", ""),
    ("Hard Parse Count Per Sec", "Hard parses / seg", ""),
]


class Performance(Modulo):
    titulo = "Performance de la base de datos"
    subtitulo = "Métricas del sistema, memoria, sesiones, sentencias más costosas, eventos de espera y bloqueos."

    def construir(self):
        fila = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        fila.pack(fill="x", pady=(0, 4))
        self.sw_auto = ctk.CTkSwitch(fila, text="Actualización automática (5 s)", command=self._auto)
        self.sw_auto.pack(side="left")
        self._job = None
        self.historia = {"cpu": [], "aas": []}

        self.tv, (t_ind, t_ses, t_sql, t_esp, t_blo) = tabs(
            self.cuerpo, ["Indicadores", "Sesiones", "Top SQL", "Eventos de espera", "Bloqueos"])

        # ---- Indicadores
        self.tarjetas = {}
        grid = ctk.CTkFrame(t_ind, fg_color="transparent")
        grid.pack(fill="x")
        for i, (metrica, nombre, _) in enumerate(METRICAS):
            t = ctk.CTkFrame(grid, corner_radius=10)
            t.grid(row=i // 6, column=i % 6, sticky="nsew", padx=4, pady=4)
            ctk.CTkLabel(t, text=nombre, text_color="gray60", font=("Segoe UI", 11)).pack(anchor="w", padx=10, pady=(6, 0))
            v = ctk.CTkLabel(t, text="-", font=("Segoe UI", 16, "bold"))
            v.pack(anchor="w", padx=10, pady=(0, 6))
            self.tarjetas[metrica] = v
        for c in range(6):
            grid.grid_columnconfigure(c, weight=1)
        medio = ctk.CTkFrame(t_ind, fg_color="transparent")
        medio.pack(fill="both", expand=True, pady=(8, 0))
        izq = ctk.CTkFrame(medio, fg_color="transparent")
        izq.pack(side="left", fill="both", expand=True, padx=(0, 6))
        ctk.CTkLabel(izq, text="CPU del servidor (%) y sesiones activas — histórico", font=FUENTE_SUB).pack(anchor="w")
        self.canvas = tk.Canvas(izq, height=200, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=4)
        der = ctk.CTkFrame(medio, fg_color="transparent")
        der.pack(side="left", fill="both", expand=True, padx=(6, 0))
        ctk.CTkLabel(der, text="Memoria (SGA / PGA)", font=FUENTE_SUB).pack(anchor="w")
        self.tabla_mem = Tabla(der, alto=8)
        self.tabla_mem.pack(fill="both", expand=True, pady=4)

        # ---- Sesiones
        self.barra(t_ses, [("Ver SQL actual", self.ver_sql_sesion),
                           ("⛔ Terminar sesión", self.matar, "#a23b3b")]).pack(fill="x", pady=(0, 6))
        self.chk_inactivas = ctk.CTkCheckBox(t_ses, text="Incluir sesiones inactivas",
                                             command=self.cargar_sesiones)
        self.chk_inactivas.select()
        self.chk_inactivas.pack(anchor="w", pady=(0, 6))
        self.tabla_ses = Tabla(t_ses, alto=16)
        self.tabla_ses.pack(fill="both", expand=True)

        # ---- Top SQL
        fila = ctk.CTkFrame(t_sql, fg_color="transparent")
        fila.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(fila, text="Ordenar por:").pack(side="left", padx=(0, 6))
        self.cb_orden = ctk.CTkComboBox(fila, width=180, command=lambda _: self.cargar_top_sql(),
                                        values=["Tiempo total", "CPU", "Lecturas lógicas",
                                                "Lecturas físicas", "Ejecuciones"])
        self.cb_orden.pack(side="left", padx=(0, 12))
        self.barra(fila, [("Ver plan de ejecución", self.plan_top_sql),
                          ("Enviar a Tuning", self.enviar_tuning)]).pack(side="left")
        self.tabla_sql = Tabla(t_sql, alto=16)
        self.tabla_sql.pack(fill="both", expand=True)

        # ---- Esperas
        self.tabla_esp = Tabla(t_esp, alto=18)
        self.tabla_esp.pack(fill="both", expand=True)

        # ---- Bloqueos
        ctk.CTkLabel(t_blo, text="Sesiones bloqueadas y la sesión que las bloquea",
                     anchor="w").pack(fill="x", pady=(0, 6))
        self.tabla_blo = Tabla(t_blo, alto=16)
        self.tabla_blo.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    def refrescar(self):
        self.cargar_indicadores()
        self.cargar_sesiones()
        self.cargar_top_sql()
        self.tabla_esp.cargar(*self.db.consultar("""
            SELECT event EVENTO, wait_class CLASE, total_waits ESPERAS,
                   ROUND(time_waited_micro/1e6, 2) SEGUNDOS,
                   ROUND(time_waited_micro/1e3/NULLIF(total_waits,0), 3) PROMEDIO_MS
              FROM v$system_event WHERE wait_class <> 'Idle'
             ORDER BY time_waited_micro DESC FETCH FIRST 30 ROWS ONLY"""))
        self.tabla_blo.cargar(*self.db.consultar("""
            SELECT s.sid SID_BLOQUEADA, s.username USUARIO, s.event EVENTO,
                   s.seconds_in_wait SEGUNDOS, s.blocking_session SID_BLOQUEADOR,
                   b.username USUARIO_BLOQUEADOR, b.machine MAQUINA_BLOQUEADOR,
                   (SELECT o.owner || '.' || o.object_name FROM dba_objects o
                     WHERE o.object_id = s.row_wait_obj#) OBJETO
              FROM v$session s LEFT JOIN v$session b ON b.sid = s.blocking_session
             WHERE s.blocking_session IS NOT NULL"""))

    def cargar_indicadores(self):
        _, filas = self.db.consultar(
            "SELECT metric_name, value FROM v$sysmetric WHERE group_id = 2")
        valores = dict(filas)
        for metrica, _, unidad in METRICAS:
            v = valores.get(metrica)
            self.tarjetas[metrica].configure(text="-" if v is None else f"{v:,.2f}{unidad}")
        self.historia["cpu"] = (self.historia["cpu"] + [valores.get("Host CPU Utilization (%)") or 0])[-60:]
        self.historia["aas"] = (self.historia["aas"] + [valores.get("Average Active Sessions") or 0])[-60:]
        self._dibujar()
        self.tabla_mem.cargar(*self.db.consultar("""
            SELECT name COMPONENTE, ROUND(bytes/1048576, 2) MB, resizeable REDIMENSIONABLE FROM v$sgainfo
            UNION ALL
            SELECT name, ROUND(value/1048576, 2), NULL FROM v$pgastat
             WHERE name IN ('aggregate PGA target parameter', 'total PGA allocated', 'total PGA inuse',
                            'maximum PGA allocated')"""))

    def _dibujar(self):
        c = self.canvas
        col = COLORES[ctk.get_appearance_mode()]
        c.configure(bg=col["bg"])
        c.delete("all")
        w, h = max(c.winfo_width(), 300), max(c.winfo_height(), 160)
        m = 30
        for p in (0, 25, 50, 75, 100):
            y = h - m - (h - 2 * m) * p / 100
            c.create_line(m, y, w - 10, y, fill=col["head"])
            c.create_text(m - 4, y, text=str(p), anchor="e", fill=col["fg"], font=("Segoe UI", 8))
        for serie, color, escala in (("cpu", "#3b8ed0", 1), ("aas", "#d29922", 100 / max(4, max(self.historia["aas"] or [1])))):
            datos = self.historia[serie]
            if len(datos) < 2:
                continue
            paso = (w - m - 10) / 59
            pts = []
            for i, v in enumerate(datos):
                pts += [m + (60 - len(datos) + i) * paso, h - m - (h - 2 * m) * min(v * escala, 100) / 100]
            c.create_line(*pts, fill=color, width=2, smooth=True)
        c.create_text(m + 6, 10, anchor="w", text="■ CPU %", fill="#3b8ed0", font=("Segoe UI", 9, "bold"))
        c.create_text(m + 70, 10, anchor="w", text="■ Sesiones activas (escalado)", fill="#d29922",
                      font=("Segoe UI", 9, "bold"))

    def _auto(self):
        if self.sw_auto.get():
            self._tick()
        else:
            self.detener()

    def _tick(self):
        try:
            self.cargar_indicadores()
            if self.tv.get() == "Sesiones":
                self.cargar_sesiones()
        except Exception as e:  # noqa: BLE001
            self.sw_auto.deselect()
            error(e)
            return
        self._job = self.after(5000, self._tick)

    def detener(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None

    # ------------------------------------------------------------------ sesiones
    def cargar_sesiones(self):
        filtro = "" if self.chk_inactivas.get() else "AND s.status = 'ACTIVE'"
        self.tabla_ses.cargar(*self.db.consultar(f"""
            SELECT s.sid SID, s.serial# SERIAL, s.username USUARIO, s.status ESTADO,
                   s.osuser USUARIO_SO, s.machine MAQUINA, s.program PROGRAMA,
                   s.event EVENTO, s.wait_class CLASE_ESPERA, s.sql_id SQL_ID,
                   s.logon_time CONEXION, s.last_call_et SEG_ULTIMA_LLAMADA
              FROM v$session s WHERE s.type = 'USER' {filtro} ORDER BY s.status, s.username"""))

    def ver_sql_sesion(self):
        s = self.tabla_ses.seleccion()
        if not s:
            info("Seleccione una sesión.")
            return
        if not s["SQL_ID"]:
            info("La sesión no está ejecutando ninguna sentencia.")
            return
        texto = self.db.valor("SELECT sql_fulltext FROM v$sql WHERE sql_id = :i AND ROWNUM = 1",
                              {"i": s["SQL_ID"]})
        VisorTexto(self, f"SQL de la sesión {s['SID']}", texto or "(no disponible)")

    def matar(self):
        s = self.tabla_ses.seleccion()
        if not s:
            info("Seleccione una sesión.")
            return
        if confirmar(f"¿Terminar la sesión {s['SID']},{s['SERIAL']} del usuario {s['USUARIO']}?"):
            self.ddl(f"ALTER SYSTEM KILL SESSION '{int(s['SID'])},{int(s['SERIAL'])}' IMMEDIATE",
                     "Sesión terminada", refrescar=False)
            self.cargar_sesiones()

    # ------------------------------------------------------------------ top sql
    def cargar_top_sql(self):
        orden = {"Tiempo total": "elapsed_time", "CPU": "cpu_time", "Lecturas lógicas": "buffer_gets",
                 "Lecturas físicas": "disk_reads", "Ejecuciones": "executions"}.get(self.cb_orden.get(), "elapsed_time")
        self.tabla_sql.cargar(*self.db.consultar(f"""
            SELECT sql_id SQL_ID, executions EJECUCIONES, ROUND(elapsed_time/1e6, 3) TIEMPO_S,
                   ROUND(cpu_time/1e6, 3) CPU_S,
                   ROUND(elapsed_time/1e3/NULLIF(executions,0), 2) MS_POR_EJEC,
                   buffer_gets LECTURAS_LOGICAS, disk_reads LECTURAS_FISICAS, rows_processed FILAS,
                   SUBSTR(sql_text, 1, 200) SQL
              FROM v$sqlstats
             WHERE sql_text NOT LIKE '%v$sqlstats%'
             ORDER BY {orden} DESC FETCH FIRST 40 ROWS ONLY"""))

    def plan_top_sql(self):
        s = self.tabla_sql.seleccion()
        if not s:
            info("Seleccione una sentencia.")
            return
        lineas = self.db.lista(
            "SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(:i, NULL, 'TYPICAL'))",
            {"i": s["SQL_ID"]})
        VisorTexto(self, f"Plan de {s['SQL_ID']}", "\n".join(lineas))

    def enviar_tuning(self):
        s = self.tabla_sql.seleccion()
        if not s:
            info("Seleccione una sentencia.")
            return
        texto = self.db.valor("SELECT sql_fulltext FROM v$sql WHERE sql_id = :i AND ROWNUM = 1",
                              {"i": s["SQL_ID"]})
        self.app.mostrar("Tuning")
        t = self.app.pantallas["Tuning"]
        t.tv.set("Plan de ejecución")
        t.sql.delete("1.0", "end")
        t.sql.insert("1.0", texto or s["SQL"])
