"""Capa de acceso a Oracle 21c XE (python-oracledb)."""
import os
import re
import shutil
import threading

import oracledb

_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")
_thick_iniciado = False


def ident(nombre):
    """Valida un identificador Oracle y lo devuelve en mayusculas.
    Evita inyeccion SQL al construir sentencias DDL dinamicas."""
    nombre = (nombre or "").strip()
    if not _IDENT.match(nombre):
        raise ValueError(f"Nombre invalido: '{nombre}'")
    return nombre.upper()


def literal(texto):
    """Escapa un texto para usarlo como literal SQL entre comillas simples."""
    return "'" + str(texto).replace("'", "''") + "'"


def password(texto):
    if not texto or '"' in texto:
        raise ValueError("La contrasena no puede estar vacia ni contener comillas dobles")
    return '"' + texto + '"'


def detectar_oracle_home():
    if os.environ.get("ORACLE_HOME"):
        return os.environ["ORACLE_HOME"]
    exe = shutil.which("sqlplus")
    if exe:
        return os.path.dirname(os.path.dirname(exe))
    return r"C:\app\usuario\product\21c\dbhomeXE"


class Conexion:
    """Mantiene la conexion principal y sabe crear conexiones nuevas
    (para trabajos largos en segundo plano, como Data Pump)."""

    def __init__(self):
        self.params = None
        self.conn = None
        self.lock = threading.RLock()

    # ------------------------------------------------------------------
    def conectar(self, host="localhost", puerto=1521, servicio="XEPDB1",
                 usuario="", clave="", sysdba=False, local=False,
                 sid="XE", pdb="XEPDB1"):
        self.params = dict(host=host, puerto=int(puerto), servicio=servicio,
                           usuario=usuario, clave=clave, sysdba=sysdba,
                           local=local, sid=sid, pdb=pdb)
        self.conn = self.nueva()
        return self.conn

    def nueva(self):
        p = self.params
        if p["local"]:
            # Conexion local "/ as sysdba" sin listener (modo thick / bequeath)
            global _thick_iniciado
            if not _thick_iniciado:
                home = detectar_oracle_home()
                oracledb.init_oracle_client(lib_dir=os.path.join(home, "bin"))
                _thick_iniciado = True
            os.environ["ORACLE_SID"] = p["sid"]
            conn = oracledb.connect(mode=oracledb.AUTH_MODE_SYSDBA)
            conn.cursor().execute(f"ALTER SESSION SET CONTAINER = {ident(p['pdb'])}")
        else:
            dsn = oracledb.makedsn(p["host"], p["puerto"], service_name=p["servicio"])
            modo = oracledb.AUTH_MODE_SYSDBA if p["sysdba"] else oracledb.AUTH_MODE_DEFAULT
            conn = oracledb.connect(user=p["usuario"], password=p["clave"],
                                    dsn=dsn, mode=modo)
        conn.autocommit = True
        return conn

    def cerrar(self):
        if self.conn:
            try:
                self.conn.close()
            except oracledb.Error:
                pass
        self.conn = None

    @property
    def descripcion(self):
        p = self.params or {}
        if p.get("local"):
            return f"SYS (local) @ {p['sid']}/{p['pdb']}"
        return f"{p.get('usuario', '').upper()} @ {p.get('host')}:{p.get('puerto')}/{p.get('servicio')}"

    # ------------------------------------------------------------------
    def consultar(self, sql, params=None, max_filas=None):
        """Devuelve (columnas, filas)."""
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(sql, params or {})
            cols = [d[0] for d in cur.description] if cur.description else []
            filas = cur.fetchmany(max_filas) if max_filas else cur.fetchall()
            return cols, [tuple(_texto(v) for v in f) for f in filas]

    def valor(self, sql, params=None):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(sql, params or {})
            fila = cur.fetchone()
            return _texto(fila[0]) if fila else None

    def ejecutar(self, sql, params=None):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(sql, params or {})
            return cur

    def lista(self, sql, params=None):
        """Primera columna de una consulta como lista."""
        return [f[0] for f in self.consultar(sql, params)[1]]


def _texto(v):
    if isinstance(v, oracledb.LOB):
        return v.read()
    return v
