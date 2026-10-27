-- =====================================================================
--  Proyecto Final EIF-402 - Configuracion inicial de la base de datos
--  Ejecutar como SYS:   sqlplus / as sysdba @01_configuracion_inicial.sql
--  Crea: usuario administrador de la app, esquemas de demostracion
--        (VENTAS, RRHH), tablespace TS_VENTAS y directorio de respaldos.
-- =====================================================================
SET ECHO OFF FEEDBACK ON SERVEROUTPUT ON
WHENEVER SQLERROR CONTINUE

ALTER SESSION SET CONTAINER = XEPDB1;

-- ---------------------------------------------------------------------
-- Limpieza (permite volver a ejecutar el script)
-- ---------------------------------------------------------------------
BEGIN
  FOR u IN (SELECT username FROM dba_users
             WHERE username IN ('ADMIN_BD','VENTAS','RRHH')) LOOP
    EXECUTE IMMEDIATE 'DROP USER ' || u.username || ' CASCADE';
  END LOOP;
  FOR t IN (SELECT tablespace_name FROM dba_tablespaces
             WHERE tablespace_name = 'TS_VENTAS') LOOP
    EXECUTE IMMEDIATE 'DROP TABLESPACE TS_VENTAS INCLUDING CONTENTS AND DATAFILES';
  END LOOP;
END;
/

-- ---------------------------------------------------------------------
-- Tablespace de la aplicacion de ventas
-- ---------------------------------------------------------------------
CREATE TABLESPACE TS_VENTAS
  DATAFILE 'C:\APP\USUARIO\PRODUCT\21C\ORADATA\XE\XEPDB1\TS_VENTAS01.DBF'
  SIZE 50M AUTOEXTEND ON NEXT 10M MAXSIZE 500M;

-- ---------------------------------------------------------------------
-- Usuario administrador que usa la aplicacion
-- ---------------------------------------------------------------------
CREATE USER ADMIN_BD IDENTIFIED BY "Admin123"
  DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP
  QUOTA UNLIMITED ON USERS;

GRANT DBA TO ADMIN_BD;
GRANT DATAPUMP_EXP_FULL_DATABASE, DATAPUMP_IMP_FULL_DATABASE TO ADMIN_BD;
GRANT AUDIT_ADMIN, AUDIT_VIEWER TO ADMIN_BD;
GRANT SELECT ANY DICTIONARY TO ADMIN_BD;
GRANT EXECUTE ON SYS.DBMS_DATAPUMP TO ADMIN_BD;
GRANT EXECUTE ON SYS.UTL_FILE TO ADMIN_BD;
GRANT EXECUTE ON SYS.DBMS_AUDIT_MGMT TO ADMIN_BD;

-- ---------------------------------------------------------------------
-- Directorio para respaldos
-- ---------------------------------------------------------------------
CREATE OR REPLACE DIRECTORY RESPALDOS_DIR AS 'C:\oracle_respaldos';
GRANT READ, WRITE ON DIRECTORY RESPALDOS_DIR TO ADMIN_BD;
GRANT READ, WRITE ON DIRECTORY DATA_PUMP_DIR TO ADMIN_BD;

-- ---------------------------------------------------------------------
-- Esquema VENTAS (datos de prueba para tuning y respaldos)
-- ---------------------------------------------------------------------
CREATE USER VENTAS IDENTIFIED BY "Ventas123"
  DEFAULT TABLESPACE TS_VENTAS TEMPORARY TABLESPACE TEMP
  QUOTA UNLIMITED ON TS_VENTAS;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE,
      CREATE PROCEDURE TO VENTAS;

CREATE TABLE VENTAS.CLIENTES (
  cliente_id     NUMBER PRIMARY KEY,
  nombre         VARCHAR2(80) NOT NULL,
  email          VARCHAR2(100),
  provincia      VARCHAR2(30),
  fecha_registro DATE
) TABLESPACE TS_VENTAS;

CREATE TABLE VENTAS.PRODUCTOS (
  producto_id NUMBER PRIMARY KEY,
  nombre      VARCHAR2(80) NOT NULL,
  categoria   VARCHAR2(30),
  precio      NUMBER(12,2),
  stock       NUMBER
) TABLESPACE TS_VENTAS;

CREATE TABLE VENTAS.FACTURAS (
  factura_id NUMBER PRIMARY KEY,
  cliente_id NUMBER NOT NULL REFERENCES VENTAS.CLIENTES,
  fecha      DATE,
  estado     VARCHAR2(15),
  total      NUMBER(14,2)
) TABLESPACE TS_VENTAS;

CREATE TABLE VENTAS.DETALLE_FACTURA (
  factura_id  NUMBER NOT NULL REFERENCES VENTAS.FACTURAS,
  linea       NUMBER NOT NULL,
  producto_id NUMBER NOT NULL REFERENCES VENTAS.PRODUCTOS,
  cantidad    NUMBER,
  precio      NUMBER(12,2),
  CONSTRAINT pk_detalle PRIMARY KEY (factura_id, linea)
) TABLESPACE TS_VENTAS;

INSERT INTO VENTAS.CLIENTES
SELECT LEVEL,
       'Cliente ' || LEVEL,
       'cliente' || LEVEL || '@correo.com',
       DECODE(MOD(LEVEL,7),0,'San Jose',1,'Alajuela',2,'Heredia',3,'Cartago',
                           4,'Puntarenas',5,'Guanacaste','Limon'),
       DATE '2020-01-01' + MOD(LEVEL * 37, 2000)
  FROM dual CONNECT BY LEVEL <= 5000;

INSERT INTO VENTAS.PRODUCTOS
SELECT LEVEL,
       'Producto ' || LEVEL,
       DECODE(MOD(LEVEL,5),0,'Electronica',1,'Hogar',2,'Ropa',3,'Alimentos','Deportes'),
       ROUND(1000 + MOD(LEVEL * 7919, 99000), 2),
       MOD(LEVEL * 13, 500)
  FROM dual CONNECT BY LEVEL <= 500;

INSERT INTO VENTAS.FACTURAS
SELECT LEVEL,
       MOD(LEVEL * 31, 5000) + 1,
       DATE '2023-01-01' + MOD(LEVEL, 1000),
       DECODE(MOD(LEVEL,10),0,'ANULADA',1,'PENDIENTE','PAGADA'),
       0
  FROM dual CONNECT BY LEVEL <= 50000;

INSERT INTO VENTAS.DETALLE_FACTURA
SELECT f.factura_id, l.linea,
       MOD(f.factura_id * l.linea * 17, 500) + 1,
       MOD(f.factura_id + l.linea, 9) + 1,
       0
  FROM VENTAS.FACTURAS f,
       (SELECT LEVEL linea FROM dual CONNECT BY LEVEL <= 3) l;

UPDATE VENTAS.DETALLE_FACTURA d
   SET precio = (SELECT p.precio FROM VENTAS.PRODUCTOS p WHERE p.producto_id = d.producto_id);

UPDATE VENTAS.FACTURAS f
   SET total = (SELECT SUM(d.cantidad * d.precio) FROM VENTAS.DETALLE_FACTURA d
                 WHERE d.factura_id = f.factura_id);
COMMIT;

-- NOTA: a proposito NO se crea indice sobre FACTURAS.CLIENTE_ID ni
-- CLIENTES.PROVINCIA, para demostrar el modulo de tuning.

-- ---------------------------------------------------------------------
-- Esquema RRHH (esquema pequeno para respaldos por esquema/tabla)
-- ---------------------------------------------------------------------
CREATE USER RRHH IDENTIFIED BY "Rrhh123"
  DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP
  QUOTA UNLIMITED ON USERS;
GRANT CREATE SESSION, CREATE TABLE TO RRHH;

CREATE TABLE RRHH.DEPARTAMENTOS (
  depto_id NUMBER PRIMARY KEY,
  nombre   VARCHAR2(50) NOT NULL
);

CREATE TABLE RRHH.EMPLEADOS (
  empleado_id NUMBER PRIMARY KEY,
  nombre      VARCHAR2(80) NOT NULL,
  depto_id    NUMBER REFERENCES RRHH.DEPARTAMENTOS,
  salario     NUMBER(12,2),
  ingreso     DATE
);

INSERT INTO RRHH.DEPARTAMENTOS VALUES (10, 'Administracion');
INSERT INTO RRHH.DEPARTAMENTOS VALUES (20, 'Tecnologia');
INSERT INTO RRHH.DEPARTAMENTOS VALUES (30, 'Ventas');
INSERT INTO RRHH.DEPARTAMENTOS VALUES (40, 'Recursos Humanos');

INSERT INTO RRHH.EMPLEADOS
SELECT LEVEL, 'Empleado ' || LEVEL, (MOD(LEVEL,4) + 1) * 10,
       ROUND(450000 + MOD(LEVEL * 7717, 1500000), 2),
       DATE '2015-01-01' + MOD(LEVEL * 53, 3500)
  FROM dual CONNECT BY LEVEL <= 200;
COMMIT;

-- ---------------------------------------------------------------------
-- Estadisticas iniciales
-- ---------------------------------------------------------------------
BEGIN
  DBMS_STATS.GATHER_SCHEMA_STATS('VENTAS');
  DBMS_STATS.GATHER_SCHEMA_STATS('RRHH');
END;
/

PROMPT
PROMPT === Configuracion inicial terminada ===
PROMPT Usuario de la aplicacion: ADMIN_BD / Admin123  (servicio XEPDB1)
EXIT
