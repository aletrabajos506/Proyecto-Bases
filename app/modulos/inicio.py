"""Pantalla de inicio: resumen general de la base de datos."""
import customtkinter as ctk

from ui_common import FUENTE_SUB, Modulo, Tabla


class Inicio(Modulo):
    titulo = "Resumen de la base de datos"
    subtitulo = "Información general de la instancia, la PDB y el uso de espacio."

    def construir(self):
        self.tarjetas = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        self.tarjetas.pack(fill="x")
        self.valores = {}
        nombres = ["Base de datos", "Contenedor", "Versión", "Instancia activa desde",
                   "Tamaño datafiles", "Sesiones de usuario", "Modo de archivado", "Usuario conectado"]
        for i, n in enumerate(nombres):
            t = ctk.CTkFrame(self.tarjetas, corner_radius=10)
            t.grid(row=i // 4, column=i % 4, sticky="nsew", padx=5, pady=5)
            ctk.CTkLabel(t, text=n, text_color="gray60").pack(anchor="w", padx=14, pady=(10, 0))
            v = ctk.CTkLabel(t, text="-", font=("Segoe UI", 17, "bold"))
            v.pack(anchor="w", padx=14, pady=(0, 10))
            self.valores[n] = v
        for c in range(4):
            self.tarjetas.grid_columnconfigure(c, weight=1)

        ctk.CTkLabel(self.cuerpo, text="Uso de tablespaces", font=FUENTE_SUB).pack(anchor="w", pady=(14, 4))
        self.barras = ctk.CTkScrollableFrame(self.cuerpo, height=200)
        self.barras.pack(fill="x")
        ctk.CTkLabel(self.cuerpo, text="Esquemas de usuario", font=FUENTE_SUB).pack(anchor="w", pady=(14, 4))
        self.tabla = Tabla(self.cuerpo, alto=6)
        self.tabla.pack(fill="both", expand=True)

    def refrescar(self):
        db = self.db
        _, f = db.consultar("""SELECT d.name, i.version_full, i.instance_name,
                                      TO_CHAR(i.startup_time,'DD/MM/YYYY HH24:MI'), d.log_mode
                                 FROM v$database d, v$instance i""")
        nombre, version, inst, inicio, log_mode = f[0]
        con = db.valor("SELECT SYS_CONTEXT('USERENV','CON_NAME') FROM dual")
        usuario = db.valor("SELECT USER FROM dual")
        tam = db.valor("SELECT ROUND(SUM(bytes)/1024/1024) FROM dba_data_files")
        ses = db.valor("SELECT COUNT(*) FROM v$session WHERE type='USER'")
        datos = {"Base de datos": f"{nombre} ({inst})", "Contenedor": con, "Versión": version,
                 "Instancia activa desde": inicio, "Tamaño datafiles": f"{tam:,} MB",
                 "Sesiones de usuario": ses, "Modo de archivado": log_mode,
                 "Usuario conectado": usuario}
        for k, v in datos.items():
            self.valores[k].configure(text=str(v))

        for w in self.barras.winfo_children():
            w.destroy()
        _, filas = db.consultar(USO_TABLESPACES + " ORDER BY pct DESC")
        for i, (ts, total, usado, pct) in enumerate(filas):
            ctk.CTkLabel(self.barras, text=ts, width=140, anchor="w").grid(row=i, column=0, padx=6, pady=3)
            b = ctk.CTkProgressBar(self.barras, width=500, height=14)
            b.set(min(float(pct or 0) / 100, 1))
            color = "#e5534b" if pct >= 90 else "#d29922" if pct >= 75 else "#57ab5a"
            b.configure(progress_color=color)
            b.grid(row=i, column=1, padx=6, pady=3, sticky="ew")
            ctk.CTkLabel(self.barras, text=f"{usado:,.1f} / {total:,.1f} MB  ({pct:.1f}%)",
                         anchor="w").grid(row=i, column=2, padx=6, sticky="w")
        self.barras.grid_columnconfigure(1, weight=1)

        self.tabla.cargar(*db.consultar("""
            SELECT u.username ESQUEMA, u.account_status ESTADO, u.default_tablespace TABLESPACE,
                   (SELECT COUNT(*) FROM dba_objects o WHERE o.owner=u.username) OBJETOS,
                   (SELECT ROUND(NVL(SUM(bytes),0)/1024/1024,2) FROM dba_segments s
                     WHERE s.owner=u.username) MB,
                   u.created CREADO
              FROM dba_users u WHERE u.oracle_maintained='N' ORDER BY 1"""))


# Uso de tablespaces permanentes, temporales y undo (MB)
USO_TABLESPACES = """
SELECT * FROM (
  SELECT df.tablespace_name ts,
         ROUND(df.total/1048576, 2) total,
         ROUND((df.total - NVL(fs.libre,0))/1048576, 2) usado,
         ROUND((df.total - NVL(fs.libre,0)) * 100 / df.total, 2) pct
    FROM (SELECT tablespace_name, SUM(bytes) total FROM dba_data_files GROUP BY tablespace_name) df
    LEFT JOIN (SELECT tablespace_name, SUM(bytes) libre FROM dba_free_space GROUP BY tablespace_name) fs
      ON fs.tablespace_name = df.tablespace_name
  UNION ALL
  SELECT tf.tablespace_name, ROUND(tf.total/1048576, 2),
         ROUND(NVL(tu.usado,0)/1048576, 2), ROUND(NVL(tu.usado,0) * 100 / tf.total, 2)
    FROM (SELECT tablespace_name, SUM(bytes) total FROM dba_temp_files GROUP BY tablespace_name) tf
    LEFT JOIN (SELECT tablespace, SUM(blocks) * 8192 usado FROM v$tempseg_usage GROUP BY tablespace) tu
      ON tu.tablespace = tf.tablespace_name
)"""
