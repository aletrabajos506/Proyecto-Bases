"""Seguridad: usuarios, roles, privilegios y perfiles."""
import re

import customtkinter as ctk

from db import ident, password
from ui_common import FUENTE_SUB, Formulario, Modulo, Tabla, confirmar, error, info, tabs

PRIVS_SISTEMA = ["CREATE SESSION", "CREATE TABLE", "CREATE VIEW", "CREATE SEQUENCE", "CREATE PROCEDURE",
                 "CREATE TRIGGER", "CREATE SYNONYM", "CREATE ANY TABLE", "ALTER ANY TABLE", "DROP ANY TABLE",
                 "SELECT ANY TABLE", "INSERT ANY TABLE", "UPDATE ANY TABLE", "DELETE ANY TABLE",
                 "CREATE USER", "ALTER USER", "DROP USER", "UNLIMITED TABLESPACE", "SELECT ANY DICTIONARY",
                 "CREATE TABLESPACE", "ALTER SYSTEM", "AUDIT SYSTEM", "CREATE ROLE", "GRANT ANY PRIVILEGE"]
PRIVS_OBJETO = ["SELECT", "INSERT", "UPDATE", "DELETE", "ALTER", "INDEX", "REFERENCES", "EXECUTE",
                "READ", "WRITE", "ALL"]
LIMITES_PERFIL = [
    ("FAILED_LOGIN_ATTEMPTS", "Intentos fallidos antes de bloqueo", "5"),
    ("PASSWORD_LOCK_TIME", "Días de bloqueo", "1"),
    ("PASSWORD_LIFE_TIME", "Vigencia de la contraseña (días)", "90"),
    ("PASSWORD_GRACE_TIME", "Días de gracia", "7"),
    ("PASSWORD_REUSE_MAX", "Cambios antes de reutilizar", "5"),
    ("SESSIONS_PER_USER", "Sesiones simultáneas", "3"),
    ("IDLE_TIME", "Minutos de inactividad", "30"),
    ("CONNECT_TIME", "Minutos de conexión máx.", "UNLIMITED"),
]
_VALOR_LIMITE = re.compile(r"^(UNLIMITED|DEFAULT|\d+(\.\d+)?)$", re.I)


def _limite(v):
    v = v.strip().upper()
    if not _VALOR_LIMITE.match(v):
        raise ValueError(f"Valor de límite inválido: {v}")
    return v


class Seguridad(Modulo):
    titulo = "Seguridad de usuarios"
    subtitulo = "Administre usuarios, roles, privilegios de sistema y de objeto, y perfiles de contraseña/recursos."

    def construir(self):
        self.tv, (t_usr, t_rol, t_per) = tabs(self.cuerpo, ["Usuarios", "Roles", "Perfiles"])

        # ---- Usuarios
        self.barra(t_usr, [
            ("➕ Crear usuario", self.crear_usuario),
            ("Contraseña", self.cambiar_clave),
            ("Bloquear / Desbloquear", self.bloquear),
            ("Expirar contraseña", self.expirar),
            ("Tablespace y cuota", self.cuota),
            ("Asignar perfil", self.asignar_perfil),
            ("🗑 Eliminar", self.eliminar_usuario, "#a23b3b"),
        ]).pack(fill="x", pady=(0, 4))
        self.chk_sistema = ctk.CTkCheckBox(t_usr, text="Mostrar usuarios internos de Oracle",
                                           command=self.cargar_usuarios)
        self.chk_sistema.pack(anchor="w", pady=(0, 4))
        self.tabla_usr = Tabla(t_usr, alto=8, al_seleccionar=lambda s: self.cargar_privs_usuario())
        self.tabla_usr.pack(fill="both", expand=True)
        cab = ctk.CTkFrame(t_usr, fg_color="transparent")
        cab.pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(cab, text="Roles y privilegios del usuario", font=FUENTE_SUB).pack(side="left")
        self.barra(cab, [
            ("Otorgar rol", lambda: self.otorgar_rol(self._usuario())),
            ("Otorgar priv. sistema", lambda: self.otorgar_sistema(self._usuario())),
            ("Otorgar priv. objeto", lambda: self.otorgar_objeto(self._usuario())),
            ("Revocar", lambda: self.revocar(self._usuario(), self.tabla_priv), "#a23b3b"),
        ]).pack(side="right")
        self.tabla_priv = Tabla(t_usr, alto=6)
        self.tabla_priv.pack(fill="both", expand=True)

        # ---- Roles
        self.barra(t_rol, [
            ("➕ Crear rol", self.crear_rol),
            ("🗑 Eliminar rol", self.eliminar_rol, "#a23b3b"),
            ("Otorgar rol", lambda: self.otorgar_rol(self._rol())),
            ("Otorgar priv. sistema", lambda: self.otorgar_sistema(self._rol())),
            ("Otorgar priv. objeto", lambda: self.otorgar_objeto(self._rol())),
            ("Revocar", lambda: self.revocar(self._rol(), self.tabla_rol_priv), "#a23b3b"),
        ]).pack(fill="x", pady=(0, 4))
        self.chk_roles_sistema = ctk.CTkCheckBox(t_rol, text="Mostrar roles predefinidos de Oracle",
                                                 command=self.cargar_roles)
        self.chk_roles_sistema.pack(anchor="w", pady=(0, 4))
        self.tabla_rol = Tabla(t_rol, alto=8, al_seleccionar=lambda s: self.cargar_privs_rol())
        self.tabla_rol.pack(fill="both", expand=True)
        ctk.CTkLabel(t_rol, text="Privilegios y usuarios del rol", font=FUENTE_SUB).pack(anchor="w", pady=(8, 2))
        self.tabla_rol_priv = Tabla(t_rol, alto=6)
        self.tabla_rol_priv.pack(fill="both", expand=True)

        # ---- Perfiles
        self.barra(t_per, [
            ("➕ Crear perfil", self.crear_perfil),
            ("Modificar límite", self.modificar_limite),
            ("🗑 Eliminar perfil", self.eliminar_perfil, "#a23b3b"),
        ]).pack(fill="x", pady=(0, 6))
        self.tabla_per = Tabla(t_per, alto=6, al_seleccionar=lambda s: self.cargar_limites())
        self.tabla_per.pack(fill="both", expand=True)
        ctk.CTkLabel(t_per, text="Límites del perfil", font=FUENTE_SUB).pack(anchor="w", pady=(8, 2))
        self.tabla_lim = Tabla(t_per, alto=10)
        self.tabla_lim.pack(fill="both", expand=True)

    def refrescar(self):
        self.cargar_usuarios()
        self.cargar_roles()
        self.cargar_perfiles()

    # ================================================================== usuarios
    def cargar_usuarios(self):
        filtro = "" if self.chk_sistema.get() else "WHERE oracle_maintained = 'N'"
        self.tabla_usr.cargar(*self.db.consultar(f"""
            SELECT username USUARIO, account_status ESTADO, default_tablespace TABLESPACE,
                   temporary_tablespace TEMPORAL, profile PERFIL, created CREADO,
                   expiry_date EXPIRA, lock_date BLOQUEADO_EL, last_login ULTIMO_LOGIN
              FROM dba_users {filtro} ORDER BY username"""))
        self.tabla_priv.cargar([], [])

    def _usuario(self):
        s = self.tabla_usr.seleccion()
        if not s:
            info("Seleccione un usuario.")
            return None
        return s["USUARIO"]

    def cargar_privs_usuario(self):
        s = self.tabla_usr.seleccion()
        if s:
            self.tabla_priv.cargar(*self._privilegios(s["USUARIO"]))

    def _privilegios(self, grantee):
        return self.db.consultar("""
            SELECT 'ROL' TIPO, granted_role PRIVILEGIO, NULL OBJETO, admin_option CON_ADMIN
              FROM dba_role_privs WHERE grantee = :g
            UNION ALL
            SELECT 'SISTEMA', privilege, NULL, admin_option FROM dba_sys_privs WHERE grantee = :g
            UNION ALL
            SELECT 'OBJETO', privilege, owner || '.' || table_name, grantable
              FROM dba_tab_privs WHERE grantee = :g
            UNION ALL
            SELECT 'CUOTA', 'QUOTA ' || DECODE(max_bytes, -1, 'UNLIMITED', ROUND(max_bytes/1048576) || 'M'),
                   tablespace_name, NULL FROM dba_ts_quotas WHERE username = :g
             ORDER BY 1, 2""", {"g": grantee})

    def _tablespaces(self, contenido="PERMANENT"):
        return self.db.lista("SELECT tablespace_name FROM dba_tablespaces WHERE contents = :c ORDER BY 1",
                             {"c": contenido})

    def _perfiles(self):
        return self.db.lista("SELECT DISTINCT profile FROM dba_profiles ORDER BY 1")

    def crear_usuario(self):
        ts = self._tablespaces()
        r = Formulario.pedir(self, "Crear usuario", [
            dict(clave="nombre", etiqueta="Usuario"),
            dict(clave="clave", etiqueta="Contraseña", tipo="clave"),
            dict(clave="ts", etiqueta="Tablespace por defecto", tipo="combo", opciones=ts,
                 valor="USERS" if "USERS" in ts else ts[0]),
            dict(clave="temp", etiqueta="Tablespace temporal", tipo="combo", opciones=self._tablespaces("TEMPORARY")),
            dict(clave="cuota", etiqueta="Cuota (MB o UNLIMITED)", valor="UNLIMITED"),
            dict(clave="perfil", etiqueta="Perfil", tipo="combo", opciones=self._perfiles(), valor="DEFAULT"),
            dict(clave="sesion", etiqueta="Otorgar CREATE SESSION", tipo="check", valor=True),
            dict(clave="expirar", etiqueta="Expirar contraseña (cambio en 1er login)", tipo="check"),
        ], "Crear")
        if not r:
            return
        try:
            nombre, ts_def = ident(r["nombre"]), ident(r["ts"])
            cuota = "UNLIMITED" if r["cuota"].upper() == "UNLIMITED" else f"{int(r['cuota'])}M"
            sql = (f"CREATE USER {nombre} IDENTIFIED BY {password(r['clave'])} "
                   f"DEFAULT TABLESPACE {ts_def} TEMPORARY TABLESPACE {ident(r['temp'])} "
                   f"QUOTA {cuota} ON {ts_def} PROFILE {ident(r['perfil'])}")
        except ValueError as e:
            error(e)
            return
        if r["expirar"]:
            sql += " PASSWORD EXPIRE"
        if self.ddl(sql, f"Usuario {nombre} creado", refrescar=False) and r["sesion"]:
            self.ddl(f"GRANT CREATE SESSION TO {nombre}", refrescar=False)
        self.cargar_usuarios()

    def cambiar_clave(self):
        u = self._usuario()
        if not u:
            return
        r = Formulario.pedir(self, f"Cambiar contraseña de {u}", [
            dict(clave="c1", etiqueta="Nueva contraseña", tipo="clave"),
            dict(clave="c2", etiqueta="Confirmar", tipo="clave"),
        ], "Cambiar")
        if not r:
            return
        if r["c1"] != r["c2"]:
            error("Las contraseñas no coinciden.")
            return
        try:
            sql = f"ALTER USER {ident(u)} IDENTIFIED BY {password(r['c1'])}"
        except ValueError as e:
            error(e)
            return
        if self._ddl_silencioso(sql):
            self.app.estado(f"Contraseña de {u} cambiada")

    def _ddl_silencioso(self, sql):
        """Ejecuta sin escribir la contrasena en la bitacora."""
        try:
            self.db.ejecutar(sql)
        except Exception as e:  # noqa: BLE001
            error(e)
            return False
        self.app.bitacora(re.sub(r'IDENTIFIED BY "[^"]*"', 'IDENTIFIED BY "********"', sql))
        self.cargar_usuarios()
        return True

    def bloquear(self):
        s = self.tabla_usr.seleccion()
        if not s:
            info("Seleccione un usuario.")
            return
        accion = "UNLOCK" if "LOCKED" in s["ESTADO"] else "LOCK"
        if confirmar(f"¿{'Desbloquear' if accion == 'UNLOCK' else 'Bloquear'} la cuenta {s['USUARIO']}?"):
            self.ddl(f"ALTER USER {ident(s['USUARIO'])} ACCOUNT {accion}", "Cuenta actualizada", refrescar=False)
            self.cargar_usuarios()

    def expirar(self):
        u = self._usuario()
        if u and confirmar(f"¿Expirar la contraseña de {u}? Deberá cambiarla en el próximo inicio de sesión."):
            self.ddl(f"ALTER USER {ident(u)} PASSWORD EXPIRE", "Contraseña expirada", refrescar=False)
            self.cargar_usuarios()

    def cuota(self):
        s = self.tabla_usr.seleccion()
        if not s:
            info("Seleccione un usuario.")
            return
        ts = self._tablespaces()
        r = Formulario.pedir(self, f"Tablespace y cuota de {s['USUARIO']}", [
            dict(clave="ts", etiqueta="Tablespace", tipo="combo", opciones=ts, valor=s["TABLESPACE"]),
            dict(clave="cuota", etiqueta="Cuota (MB, UNLIMITED o 0)", valor="UNLIMITED"),
            dict(clave="defecto", etiqueta="Usar como tablespace por defecto", tipo="check"),
        ], "Aplicar")
        if not r:
            return
        u, t = ident(s["USUARIO"]), ident(r["ts"])
        cuota = "UNLIMITED" if r["cuota"].upper() == "UNLIMITED" else f"{int(r['cuota'])}M"
        sql = f"ALTER USER {u} QUOTA {cuota} ON {t}"
        if r["defecto"]:
            sql += f" DEFAULT TABLESPACE {t}"
        self.ddl(sql, "Cuota actualizada", refrescar=False)
        self.cargar_usuarios()

    def asignar_perfil(self):
        u = self._usuario()
        if not u:
            return
        r = Formulario.pedir(self, f"Asignar perfil a {u}", [
            dict(clave="perfil", etiqueta="Perfil", tipo="combo", opciones=self._perfiles())], "Asignar")
        if r:
            self.ddl(f"ALTER USER {ident(u)} PROFILE {ident(r['perfil'])}", "Perfil asignado", refrescar=False)
            self.cargar_usuarios()

    def eliminar_usuario(self):
        u = self._usuario()
        if u and confirmar(f"¿Eliminar el usuario {u} y TODOS sus objetos (CASCADE)?\nNo se puede deshacer."):
            self.ddl(f"DROP USER {ident(u)} CASCADE", f"Usuario {u} eliminado", refrescar=False)
            self.cargar_usuarios()

    # ================================================================== otorgar / revocar
    def otorgar_rol(self, grantee):
        if not grantee:
            return
        roles = self.db.lista("SELECT role FROM dba_roles ORDER BY 1")
        r = Formulario.pedir(self, f"Otorgar rol a {grantee}", [
            dict(clave="rol", etiqueta="Rol", tipo="combo", opciones=roles,
                 valor="CONNECT" if "CONNECT" in roles else roles[0]),
            dict(clave="admin", etiqueta="WITH ADMIN OPTION", tipo="check"),
        ], "Otorgar")
        if r:
            sql = f"GRANT {ident(r['rol'])} TO {ident(grantee)}" + (" WITH ADMIN OPTION" if r["admin"] else "")
            self.ddl(sql, "Rol otorgado", refrescar=False)
            self._refrescar_privs()

    def otorgar_sistema(self, grantee):
        if not grantee:
            return
        r = Formulario.pedir(self, f"Otorgar privilegio de sistema a {grantee}", [
            dict(clave="priv", etiqueta="Privilegio", tipo="combo", opciones=PRIVS_SISTEMA),
            dict(clave="admin", etiqueta="WITH ADMIN OPTION", tipo="check"),
        ], "Otorgar")
        if not r:
            return
        priv = r["priv"].upper()
        if not re.match(r"^[A-Z ]+$", priv):
            error("Privilegio inválido.")
            return
        self.ddl(f"GRANT {priv} TO {ident(grantee)}" + (" WITH ADMIN OPTION" if r["admin"] else ""),
                 "Privilegio otorgado", refrescar=False)
        self._refrescar_privs()

    def otorgar_objeto(self, grantee):
        if not grantee:
            return
        esquemas = self.db.lista("SELECT username FROM dba_users WHERE oracle_maintained='N' ORDER BY 1")
        r = Formulario.pedir(self, f"Otorgar privilegio de objeto a {grantee}", [
            dict(clave="privs", etiqueta="Privilegios (coma)", valor="SELECT"),
            dict(clave="esquema", etiqueta="Esquema", tipo="combo", opciones=esquemas),
            dict(clave="objeto", etiqueta="Objeto (tabla, vista...)"),
            dict(clave="grant", etiqueta="WITH GRANT OPTION", tipo="check"),
        ], "Otorgar")
        if not r:
            return
        try:
            privs = [p.strip().upper() for p in r["privs"].split(",") if p.strip()]
            if not privs or any(p not in PRIVS_OBJETO for p in privs):
                raise ValueError("Privilegios válidos: " + ", ".join(PRIVS_OBJETO))
            obj = f"{ident(r['esquema'])}.{ident(r['objeto'])}"
        except ValueError as e:
            error(e)
            return
        self.ddl(f"GRANT {', '.join(privs)} ON {obj} TO {ident(grantee)}" +
                 (" WITH GRANT OPTION" if r["grant"] else ""), "Privilegio otorgado", refrescar=False)
        self._refrescar_privs()

    def revocar(self, grantee, tabla):
        if not grantee:
            return
        s = tabla.seleccion()
        if not s or s.get("TIPO") not in ("ROL", "SISTEMA", "OBJETO"):
            info("Seleccione un rol o privilegio en la tabla inferior.")
            return
        if s["TIPO"] == "OBJETO":
            sql = f"REVOKE {s['PRIVILEGIO']} ON {s['OBJETO']} FROM {ident(grantee)}"
        else:
            sql = f"REVOKE {s['PRIVILEGIO']} FROM {ident(grantee)}"
        if confirmar(f"¿Ejecutar?\n\n{sql}"):
            self.ddl(sql, "Privilegio revocado", refrescar=False)
            self._refrescar_privs()

    def _refrescar_privs(self):
        self.cargar_privs_usuario()
        self.cargar_privs_rol()

    # ================================================================== roles
    def cargar_roles(self):
        filtro = "" if self.chk_roles_sistema.get() else "WHERE r.oracle_maintained = 'N'"
        self.tabla_rol.cargar(*self.db.consultar(f"""
            SELECT r.role ROL, r.authentication_type AUTENTICACION,
                   (SELECT COUNT(*) FROM dba_sys_privs p WHERE p.grantee = r.role) PRIV_SISTEMA,
                   (SELECT COUNT(*) FROM dba_tab_privs p WHERE p.grantee = r.role) PRIV_OBJETO,
                   (SELECT COUNT(*) FROM dba_role_privs p WHERE p.granted_role = r.role) OTORGADO_A
              FROM dba_roles r {filtro} ORDER BY 1"""))
        self.tabla_rol_priv.cargar([], [])

    def _rol(self):
        s = self.tabla_rol.seleccion()
        if not s:
            info("Seleccione un rol.")
            return None
        return s["ROL"]

    def cargar_privs_rol(self):
        s = self.tabla_rol.seleccion()
        if not s:
            return
        cols, filas = self._privilegios(s["ROL"])
        _, usuarios = self.db.consultar(
            "SELECT 'OTORGADO A', grantee, NULL, admin_option FROM dba_role_privs WHERE granted_role = :r",
            {"r": s["ROL"]})
        self.tabla_rol_priv.cargar(cols, filas + usuarios)

    def crear_rol(self):
        r = Formulario.pedir(self, "Crear rol", [dict(clave="nombre", etiqueta="Nombre del rol")], "Crear")
        if r:
            try:
                nombre = ident(r["nombre"])
            except ValueError as e:
                error(e)
                return
            self.ddl(f"CREATE ROLE {nombre}", f"Rol {nombre} creado", refrescar=False)
            self.cargar_roles()

    def eliminar_rol(self):
        rol = self._rol()
        if rol and confirmar(f"¿Eliminar el rol {rol}?"):
            self.ddl(f"DROP ROLE {ident(rol)}", "Rol eliminado", refrescar=False)
            self.cargar_roles()

    # ================================================================== perfiles
    def cargar_perfiles(self):
        self.tabla_per.cargar(*self.db.consultar("""
            SELECT p.profile PERFIL,
                   MAX(DECODE(resource_name,'FAILED_LOGIN_ATTEMPTS',limit)) INTENTOS_FALLIDOS,
                   MAX(DECODE(resource_name,'PASSWORD_LIFE_TIME',limit)) VIGENCIA_CLAVE,
                   MAX(DECODE(resource_name,'SESSIONS_PER_USER',limit)) SESIONES,
                   MAX(DECODE(resource_name,'IDLE_TIME',limit)) INACTIVIDAD,
                   (SELECT COUNT(*) FROM dba_users u WHERE u.profile = p.profile) USUARIOS
              FROM dba_profiles p GROUP BY p.profile ORDER BY 1"""))
        self.tabla_lim.cargar([], [])

    def cargar_limites(self):
        s = self.tabla_per.seleccion()
        if s:
            self.tabla_lim.cargar(*self.db.consultar("""
                SELECT resource_name RECURSO, resource_type TIPO, limit LIMITE
                  FROM dba_profiles WHERE profile = :p ORDER BY 2, 1""", {"p": s["PERFIL"]}))

    def crear_perfil(self):
        campos = [dict(clave="nombre", etiqueta="Nombre del perfil", valor="PERFIL_")]
        campos += [dict(clave=k, etiqueta=e, valor=v) for k, e, v in LIMITES_PERFIL]
        r = Formulario.pedir(self, "Crear perfil", campos, "Crear")
        if not r:
            return
        try:
            nombre = ident(r["nombre"])
            limites = " ".join(f"{k} {_limite(r[k])}" for k, _, _ in LIMITES_PERFIL if r[k])
        except ValueError as e:
            error(e)
            return
        self.ddl(f"CREATE PROFILE {nombre} LIMIT {limites}", f"Perfil {nombre} creado", refrescar=False)
        self.cargar_perfiles()

    def modificar_limite(self):
        s = self.tabla_per.seleccion()
        lim = self.tabla_lim.seleccion()
        if not s or not lim:
            info("Seleccione un perfil y luego un límite en la tabla inferior.")
            return
        r = Formulario.pedir(self, f"{s['PERFIL']}: {lim['RECURSO']}", [
            dict(clave="valor", etiqueta="Nuevo valor (número, UNLIMITED, DEFAULT)", valor=lim["LIMITE"])],
            "Aplicar")
        if not r:
            return
        try:
            valor = _limite(r["valor"])
        except ValueError as e:
            error(e)
            return
        self.ddl(f"ALTER PROFILE {ident(s['PERFIL'])} LIMIT {ident(lim['RECURSO'])} {valor}",
                 "Límite actualizado", refrescar=False)
        self.cargar_perfiles()

    def eliminar_perfil(self):
        s = self.tabla_per.seleccion()
        if not s:
            info("Seleccione un perfil.")
            return
        if s["PERFIL"] == "DEFAULT":
            info("El perfil DEFAULT no se puede eliminar.")
            return
        if confirmar(f"¿Eliminar el perfil {s['PERFIL']}? Los usuarios que lo usen pasarán a DEFAULT."):
            self.ddl(f"DROP PROFILE {ident(s['PERFIL'])} CASCADE", "Perfil eliminado", refrescar=False)
            self.cargar_perfiles()
