"""Auditoria de la base de datos (Unified Auditing)."""
import re

import customtkinter as ctk

from db import ident
from ui_common import (FUENTE_SUB, Formulario, Modulo, Tabla, VisorTexto, confirmar,
                       error, etiqueta_valor, info, tabs)

_ACCION = re.compile(r"^[A-Za-z ]+$")


def _acciones(texto):
    lista = [a.strip().upper() for a in texto.split(",") if a.strip()]
    if not lista or not all(_ACCION.match(a) for a in lista):
        raise ValueError("Indique acciones válidas separadas por coma (ej: SELECT, UPDATE, DELETE)")
    return lista


class Auditoria(Modulo):
    titulo = "Auditoría de la base de datos"
    subtitulo = "Administre políticas de auditoría unificada (Unified Auditing) y consulte el registro de auditoría."

    def construir(self):
        self.tv, (t_reg, t_pol, t_log) = tabs(self.cuerpo, ["Registro de auditoría", "Políticas", "Inicios de sesión"])

        # ---- Registro
        f = ctk.CTkFrame(t_reg, fg_color="transparent")
        f.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(f, text="Usuario:").pack(side="left")
        self.f_usuario = ctk.CTkEntry(f, width=110)
        self.f_usuario.pack(side="left", padx=(4, 10))
        ctk.CTkLabel(f, text="Acción:").pack(side="left")
        self.f_accion = ctk.CTkEntry(f, width=110)
        self.f_accion.pack(side="left", padx=(4, 10))
        ctk.CTkLabel(f, text="Objeto:").pack(side="left")
        self.f_objeto = ctk.CTkEntry(f, width=110)
        self.f_objeto.pack(side="left", padx=(4, 10))
        ctk.CTkLabel(f, text="Últimas:").pack(side="left")
        self.f_horas = ctk.CTkComboBox(f, width=110, values=["1 hora", "24 horas", "7 días", "30 días", "Todo"])
        self.f_horas.set("24 horas")
        self.f_horas.pack(side="left", padx=(4, 10))
        self.barra(f, [("Buscar", self.cargar_registro),
                       ("Ver detalle", self.ver_detalle),
                       ("🗑 Purgar registro", self.purgar, "#a23b3b")]).pack(side="left")
        self.tabla_reg = Tabla(t_reg, alto=18, al_doble_clic=lambda s: self.ver_detalle())
        self.tabla_reg.pack(fill="both", expand=True)

        # ---- Politicas
        self.barra(t_pol, [
            ("➕ Crear política", self.crear_politica),
            ("✔ Habilitar", self.habilitar),
            ("✖ Deshabilitar", self.deshabilitar),
            ("🗑 Eliminar", self.eliminar_politica, "#a23b3b"),
        ]).pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(t_pol, text="Políticas definidas", font=FUENTE_SUB).pack(anchor="w")
        self.tabla_pol = Tabla(t_pol, alto=8, al_seleccionar=lambda s: self.cargar_opciones())
        self.tabla_pol.pack(fill="both", expand=True)
        ctk.CTkLabel(t_pol, text="Opciones auditadas por la política seleccionada", font=FUENTE_SUB).pack(anchor="w", pady=(8, 0))
        self.tabla_opc = Tabla(t_pol, alto=6)
        self.tabla_opc.pack(fill="both", expand=True)

        # ---- Inicios de sesion
        cfg = ctk.CTkFrame(t_log)
        cfg.pack(fill="x", pady=(0, 8))
        self.lbl_unificada = etiqueta_valor(cfg, "Auditoría unificada pura:", 0)
        self.lbl_trail = etiqueta_valor(cfg, "Parámetro audit_trail:", 0, 2)
        self.lbl_total = etiqueta_valor(cfg, "Registros en el trail:", 0, 4)
        ctk.CTkLabel(t_log, text="Conexiones fallidas y exitosas recientes", font=FUENTE_SUB).pack(anchor="w")
        self.tabla_log = Tabla(t_log, alto=16)
        self.tabla_log.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    def refrescar(self):
        self.cargar_registro()
        self.cargar_politicas()
        self.cargar_logins()

    def cargar_registro(self):
        horas = {"1 hora": 1, "24 horas": 24, "7 días": 168, "30 días": 720}.get(self.f_horas.get())
        cond, p = [], {}
        if horas:
            cond.append("event_timestamp > SYSTIMESTAMP - NUMTODSINTERVAL(:h, 'HOUR')")
            p["h"] = horas
        for campo, entry, col in (("u", self.f_usuario, "dbusername"), ("a", self.f_accion, "action_name"),
                                  ("o", self.f_objeto, "object_name")):
            if entry.get().strip():
                cond.append(f"UPPER({col}) LIKE :{campo}")
                p[campo] = "%" + entry.get().strip().upper() + "%"
        where = ("WHERE " + " AND ".join(cond)) if cond else ""
        self.tabla_reg.cargar(*self.db.consultar(f"""
            SELECT CAST(event_timestamp AS DATE) FECHA, dbusername USUARIO, action_name ACCION,
                   object_schema ESQUEMA, object_name OBJETO, return_code CODIGO,
                   unified_audit_policies POLITICA, os_username USUARIO_SO, userhost EQUIPO,
                   client_program_name PROGRAMA, SUBSTR(sql_text, 1, 300) SQL
              FROM unified_audit_trail {where}
             ORDER BY event_timestamp DESC FETCH FIRST 1000 ROWS ONLY""", p))

    def ver_detalle(self):
        s = self.tabla_reg.seleccion()
        if not s:
            info("Seleccione un registro.")
            return
        texto = "\n".join(f"{k:<12}: {'' if v is None else v}" for k, v in s.items())
        VisorTexto(self, "Detalle del registro de auditoría", texto)

    def purgar(self):
        if not confirmar("¿Purgar TODOS los registros del trail de auditoría unificada?\n"
                         "Esta acción no se puede deshacer."):
            return
        self.ddl("""BEGIN
  DBMS_AUDIT_MGMT.CLEAN_AUDIT_TRAIL(
    audit_trail_type        => DBMS_AUDIT_MGMT.AUDIT_TRAIL_UNIFIED,
    use_last_arch_timestamp => FALSE);
END;""", "Registro de auditoría purgado")

    # ------------------------------------------------------------------ politicas
    def cargar_politicas(self):
        self.tabla_pol.cargar(*self.db.consultar("""
            SELECT p.policy_name POLITICA, COUNT(*) OPCIONES,
                   MAX(p.common) COMUN,
                   NVL((SELECT LISTAGG(e.entity_name || ' (' ||
                                 DECODE(e.success,'YES','OK','') ||
                                 DECODE(e.success||e.failure,'YESYES','/','') ||
                                 DECODE(e.failure,'YES','FALLO','') || ')', ', ')
                              WITHIN GROUP (ORDER BY e.entity_name)
                          FROM audit_unified_enabled_policies e WHERE e.policy_name = p.policy_name),
                       '— deshabilitada —') HABILITADA_PARA
              FROM audit_unified_policies p
             GROUP BY p.policy_name ORDER BY 1"""))
        self.tabla_opc.cargar([], [])

    def cargar_opciones(self):
        s = self.tabla_pol.seleccion()
        if not s:
            return
        self.tabla_opc.cargar(*self.db.consultar("""
            SELECT audit_option OPCION, audit_option_type TIPO, object_schema ESQUEMA,
                   object_name OBJETO, object_type TIPO_OBJETO, audit_condition CONDICION
              FROM audit_unified_policies WHERE policy_name = :p ORDER BY 2, 1""",
            {"p": s["POLITICA"]}))

    def crear_politica(self):
        esquemas = self.db.lista("SELECT username FROM dba_users WHERE oracle_maintained='N' ORDER BY 1")
        r = Formulario.pedir(self, "Crear política de auditoría", [
            dict(clave="nombre", etiqueta="Nombre de la política", valor="AUD_"),
            dict(clave="tipo", etiqueta="Tipo", tipo="combo",
                 opciones=["Acciones sobre un objeto", "Acciones de sistema", "Privilegios de sistema"]),
            dict(clave="acciones", etiqueta="Acciones / privilegios", valor="SELECT, INSERT, UPDATE, DELETE"),
            dict(clave="esquema", etiqueta="Esquema (solo objeto)", tipo="combo", opciones=esquemas or [""]),
            dict(clave="objeto", etiqueta="Objeto (solo objeto)", valor="CLIENTES"),
        ], "Crear")
        if not r:
            return
        try:
            nombre = ident(r["nombre"])
            acciones = _acciones(r["acciones"])
            if r["tipo"] == "Acciones sobre un objeto":
                obj = f"{ident(r['esquema'])}.{ident(r['objeto'])}"
                cuerpo = "ACTIONS " + ", ".join(f"{a} ON {obj}" for a in acciones)
            elif r["tipo"] == "Acciones de sistema":
                cuerpo = "ACTIONS " + ", ".join(acciones)
            else:
                cuerpo = "PRIVILEGES " + ", ".join(acciones)
        except ValueError as e:
            error(e)
            return
        self.ddl(f"CREATE AUDIT POLICY {nombre} {cuerpo}", f"Política {nombre} creada", refrescar=False)
        self.cargar_politicas()

    def _politica(self):
        s = self.tabla_pol.seleccion()
        if not s:
            info("Seleccione una política.")
        return s

    def habilitar(self):
        s = self._politica()
        if not s:
            return
        usuarios = self.db.lista("SELECT username FROM dba_users ORDER BY 1")
        r = Formulario.pedir(self, f"Habilitar {s['POLITICA']}", [
            dict(clave="alcance", etiqueta="Aplicar a", tipo="combo",
                 opciones=["Todos los usuarios", "Solo el usuario", "Todos excepto el usuario"]),
            dict(clave="usuario", etiqueta="Usuario", tipo="combo", opciones=usuarios),
            dict(clave="cuando", etiqueta="Registrar", tipo="combo",
                 opciones=["Exitosas y fallidas", "Solo exitosas", "Solo fallidas"]),
        ], "Habilitar")
        if not r:
            return
        sql = f"AUDIT POLICY {ident(s['POLITICA'])}"
        if r["alcance"] == "Solo el usuario":
            sql += f" BY {ident(r['usuario'])}"
        elif r["alcance"] == "Todos excepto el usuario":
            sql += f" EXCEPT {ident(r['usuario'])}"
        sql += {"Solo exitosas": " WHENEVER SUCCESSFUL",
                "Solo fallidas": " WHENEVER NOT SUCCESSFUL"}.get(r["cuando"], "")
        self.ddl(sql, "Política habilitada", refrescar=False)
        self.cargar_politicas()

    def deshabilitar(self):
        s = self._politica()
        if not s:
            return
        _, filas = self.db.consultar(
            "SELECT entity_name, enabled_option FROM audit_unified_enabled_policies WHERE policy_name = :p",
            {"p": s["POLITICA"]})
        if not filas:
            info("La política no está habilitada.")
            return
        for entidad, opcion in filas:
            sql = f"NOAUDIT POLICY {ident(s['POLITICA'])}"
            if opcion == "BY USER" and entidad != "ALL USERS":
                sql += f" BY {ident(entidad)}"
            self.ddl(sql, "Política deshabilitada", refrescar=False)
        self.cargar_politicas()

    def eliminar_politica(self):
        s = self._politica()
        if not s:
            return
        if s["POLITICA"].startswith("ORA_"):
            info("Las políticas predefinidas de Oracle (ORA_*) no se pueden eliminar.")
            return
        if s["HABILITADA_PARA"] != "— deshabilitada —":
            info("Deshabilite la política antes de eliminarla.")
            return
        if confirmar(f"¿Eliminar la política {s['POLITICA']}?"):
            self.ddl(f"DROP AUDIT POLICY {ident(s['POLITICA'])}", "Política eliminada", refrescar=False)
            self.cargar_politicas()

    # ------------------------------------------------------------------ logins
    def cargar_logins(self):
        pura = self.db.valor("SELECT value FROM v$option WHERE parameter = 'Unified Auditing'")
        self.lbl_unificada.configure(text="Sí" if pura == "TRUE" else "No (modo mixto)")
        self.lbl_trail.configure(text=self.db.valor("SELECT value FROM v$parameter WHERE name='audit_trail'"))
        self.lbl_total.configure(text=f"{self.db.valor('SELECT COUNT(*) FROM unified_audit_trail'):,}")
        self.tabla_log.cargar(*self.db.consultar("""
            SELECT CAST(event_timestamp AS DATE) FECHA, dbusername USUARIO, action_name ACCION,
                   CASE WHEN return_code = 0 THEN 'EXITOSO' ELSE 'FALLIDO (ORA-' || return_code || ')' END RESULTADO,
                   os_username USUARIO_SO, userhost EQUIPO, client_program_name PROGRAMA,
                   authentication_type AUTENTICACION
              FROM unified_audit_trail
             WHERE action_name IN ('LOGON', 'LOGOFF', 'LOGOFF BY CLEANUP')
             ORDER BY event_timestamp DESC FETCH FIRST 300 ROWS ONLY"""))
