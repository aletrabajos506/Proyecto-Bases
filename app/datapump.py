"""Respaldos y recuperacion con la API DBMS_DATAPUMP (equivalente a expdp/impdp).

Se usa la API PL/SQL en lugar de los ejecutables para que la aplicacion
funcione con cualquier conexion (local o remota) y sin depender del PATH.
"""
import datetime
import json
import os

import oracledb

from db import ident, literal

HISTORIAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historial_respaldos.json")

_PLSQL = """
DECLARE
  h   NUMBER;
  js  VARCHAR2(30);
  sts ku$_Status;
  le  ku$_LogEntry;
  msg VARCHAR2(4000);
BEGIN
  h := DBMS_DATAPUMP.OPEN(operation => {operacion}, job_mode => {modo}, job_name => {job});
  DBMS_DATAPUMP.ADD_FILE(h, {dump}, {directorio}, reusefile => {reusar});
  DBMS_DATAPUMP.ADD_FILE(h, {log}, {directorio}, filetype => DBMS_DATAPUMP.KU$_FILE_TYPE_LOG_FILE,
                         reusefile => 1);
{extras}
  DBMS_DATAPUMP.START_JOB(h);
  DBMS_DATAPUMP.WAIT_FOR_JOB(h, js);
  :estado := js;
EXCEPTION WHEN OTHERS THEN
  msg := SQLERRM;
  IF h IS NOT NULL THEN
    BEGIN
      DBMS_DATAPUMP.GET_STATUS(h, DBMS_DATAPUMP.KU$_STATUS_JOB_ERROR, 0, js, sts);
      IF sts.error IS NOT NULL THEN
        le := sts.error;
        FOR i IN le.FIRST .. le.LAST LOOP
          msg := SUBSTR(msg || CHR(10) || le(i).LogText, 1, 4000);
        END LOOP;
      END IF;
      DBMS_DATAPUMP.STOP_JOB(h, 1, 0);
    EXCEPTION WHEN OTHERS THEN
      BEGIN DBMS_DATAPUMP.DETACH(h); EXCEPTION WHEN OTHERS THEN NULL; END;
    END;
  END IF;
  :estado := 'ERROR';
  :error := msg;
END;"""


def _lista_in(nombres):
    return "IN (" + ", ".join(literal(ident(n)) for n in nombres) + ")"


def nombre_archivo(tipo, objetos):
    marca = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    sufijo = "_".join(o.replace(".", "-") for o in objetos[:2]) if objetos else ""
    base = f"{tipo.lower()}_{sufijo}_{marca}" if sufijo else f"{tipo.lower()}_{marca}"
    return base[:90].lower()


# ----------------------------------------------------------------------
def plsql_exportar(tipo, directorio, archivo, esquemas=(), tablas=(), contenido="ALL"):
    """tipo: FULL | SCHEMA | TABLE. En modo TABLE: esquemas[0] es el propietario."""
    extras = []
    if tipo == "SCHEMA":
        extras.append(f"  DBMS_DATAPUMP.METADATA_FILTER(h, 'SCHEMA_EXPR', {literal(_lista_in(esquemas))});")
    elif tipo == "TABLE":
        extras.append(f"  DBMS_DATAPUMP.METADATA_FILTER(h, 'SCHEMA_EXPR', {literal(_lista_in(esquemas[:1]))});")
        extras.append(f"  DBMS_DATAPUMP.METADATA_FILTER(h, 'NAME_EXPR', {literal(_lista_in(tablas))});")
    if contenido == "METADATA_ONLY":
        extras.append("  DBMS_DATAPUMP.DATA_FILTER(h, 'INCLUDE_ROWS', 0);")
    elif contenido == "DATA_ONLY":
        extras.append("  DBMS_DATAPUMP.SET_PARAMETER(h, 'INCLUDE_METADATA', 0);")
    return _armar("EXPORT", tipo, directorio, archivo, extras, reusar=1)


def plsql_importar(tipo, directorio, archivo, esquemas=(), tablas=(), remap_esquema=None,
                   remap_tablespace=None, existe="SKIP", remap_tabla=None):
    extras = []
    if tipo == "SCHEMA" and esquemas:
        extras.append(f"  DBMS_DATAPUMP.METADATA_FILTER(h, 'SCHEMA_EXPR', {literal(_lista_in(esquemas))});")
    elif tipo == "TABLE":
        extras.append(f"  DBMS_DATAPUMP.METADATA_FILTER(h, 'SCHEMA_EXPR', {literal(_lista_in(esquemas[:1]))});")
        extras.append(f"  DBMS_DATAPUMP.METADATA_FILTER(h, 'NAME_EXPR', {literal(_lista_in(tablas))});")
    if remap_esquema:
        origen, destino = remap_esquema
        extras.append(f"  DBMS_DATAPUMP.METADATA_REMAP(h, 'REMAP_SCHEMA', {literal(ident(origen))}, "
                      f"{literal(ident(destino))});")
    if remap_tablespace:
        origen, destino = remap_tablespace
        extras.append(f"  DBMS_DATAPUMP.METADATA_REMAP(h, 'REMAP_TABLESPACE', {literal(ident(origen))}, "
                      f"{literal(ident(destino))});")
    if remap_tabla:
        origen, destino = remap_tabla
        extras.append(f"  DBMS_DATAPUMP.METADATA_REMAP(h, 'REMAP_TABLE', {literal(ident(origen))}, "
                      f"{literal(ident(destino))});")
    if existe not in ("SKIP", "APPEND", "TRUNCATE", "REPLACE"):
        raise ValueError("TABLE_EXISTS_ACTION invalido")
    extras.append(f"  DBMS_DATAPUMP.SET_PARAMETER(h, 'TABLE_EXISTS_ACTION', '{existe}');")
    return _armar("IMPORT", tipo, directorio, archivo, extras, reusar=0)


def _armar(operacion, tipo, directorio, archivo, extras, reusar):
    if tipo not in ("FULL", "SCHEMA", "TABLE"):
        raise ValueError("Tipo de respaldo invalido")
    if not archivo or any(c in archivo for c in "\\/:*?\"<>|'"):
        raise ValueError("Nombre de archivo invalido")
    base = archivo[:-4] if archivo.lower().endswith(".dmp") else archivo
    sufijo = "exp" if operacion == "EXPORT" else "imp_" + datetime.datetime.now().strftime("%H%M%S")
    log = f"{base}_{sufijo}.log"
    job = f"OA_{operacion[:3]}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    sql = _PLSQL.format(operacion=literal(operacion), modo=literal(tipo), job=literal(job),
                        dump=literal(archivo), log=literal(log), directorio=literal(ident(directorio)),
                        reusar=reusar, extras="\n".join(extras))
    return sql, log


def comando_equivalente(operacion, tipo, directorio, archivo, log, esquemas=(), tablas=(), extra=""):
    exe = "expdp" if operacion == "EXPORT" else "impdp"
    partes = [exe, "ADMIN_BD/******@localhost:1521/XEPDB1", f"DIRECTORY={directorio}",
              f"DUMPFILE={archivo}", f"LOGFILE={log}"]
    if tipo == "FULL":
        partes.append("FULL=Y")
    elif tipo == "SCHEMA" and esquemas:
        partes.append("SCHEMAS=" + ",".join(esquemas))
    elif tipo == "TABLE":
        partes.append("TABLES=" + ",".join(f"{esquemas[0]}.{t}" for t in tablas))
    if extra:
        partes.append(extra)
    return " ".join(partes)


def ejecutar(conn, plsql):
    """Ejecuta el bloque en la conexion dada (bloqueante). Devuelve (estado, error)."""
    cur = conn.cursor()
    estado = cur.var(str)
    err = cur.var(str, 4000)
    cur.execute(plsql, estado=estado, error=err)
    return estado.getvalue(), err.getvalue()


# ----------------------------------------------------------------------
def ruta_directorio(db, directorio):
    return db.valor("SELECT directory_path FROM dba_directories WHERE directory_name = :d",
                    {"d": directorio})


def leer_archivo(db, directorio, archivo, max_lineas=5000):
    """Lee un archivo de texto del servidor mediante UTL_FILE."""
    with db.lock:
        cur = db.conn.cursor()
        salida = cur.var(oracledb.DB_TYPE_CLOB)
        cur.execute("""
            DECLARE
              f UTL_FILE.FILE_TYPE;
              l VARCHAR2(32767);
              r CLOB;
              n PLS_INTEGER := 0;
            BEGIN
              DBMS_LOB.CREATETEMPORARY(r, TRUE);
              f := UTL_FILE.FOPEN(:d, :a, 'r', 32767);
              LOOP
                BEGIN
                  UTL_FILE.GET_LINE(f, l);
                EXCEPTION WHEN NO_DATA_FOUND THEN EXIT;
                END;
                DBMS_LOB.APPEND(r, l || CHR(10));
                n := n + 1;
                EXIT WHEN n >= :m;
              END LOOP;
              UTL_FILE.FCLOSE(f);
              :s := r;
            END;""", d=directorio, a=archivo, m=max_lineas, s=salida)
        lob = salida.getvalue()
        return lob.read() if lob else ""


def leer_texto(db, directorio, archivo):
    """Intenta leer el archivo localmente; si no es accesible, via UTL_FILE."""
    ruta = ruta_directorio(db, directorio)
    if ruta:
        local = os.path.join(os.path.normpath(ruta), archivo)
        if os.path.isfile(local):
            with open(local, encoding="latin-1", errors="replace") as f:
                return f.read()
    return leer_archivo(db, directorio, archivo)


def listar_archivos(db, directorio):
    """Lista archivos del directorio (debe ser accesible desde esta maquina)."""
    ruta = ruta_directorio(db, directorio)
    if not ruta:
        return None, []
    ruta = os.path.normpath(ruta)
    if not os.path.isdir(ruta):
        return ruta, None
    filas = []
    for nombre in os.listdir(ruta):
        completo = os.path.join(ruta, nombre)
        if os.path.isfile(completo):
            st = os.stat(completo)
            ext = os.path.splitext(nombre)[1].lower()
            tipo = {".dmp": "Respaldo (dump)", ".log": "Log"}.get(ext, "Otro")
            filas.append((nombre, tipo, round(st.st_size / 1048576, 3),
                          datetime.datetime.fromtimestamp(st.st_mtime)))
    filas.sort(key=lambda f: f[3], reverse=True)
    return ruta, filas


# ----------------------------------------------------------------------
def historial():
    try:
        with open(HISTORIAL, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def registrar(entrada):
    datos = historial()
    datos.insert(0, entrada)
    try:
        with open(HISTORIAL, "w", encoding="utf-8") as f:
            json.dump(datos[:500], f, indent=2, ensure_ascii=False, default=str)
    except OSError:
        pass
