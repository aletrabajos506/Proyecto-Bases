# OraAdmin XE

Aplicación de escritorio para la administración y respaldos de **Oracle 21c XE**
(Proyecto Final EIF-402 Administración de Bases de Datos, UNA).

Módulos: Tablespaces · Tuning (planes, estadísticas, índices) · Performance · Auditoría ·
Seguridad · Respaldos (Full / Esquemas / Tablas) · Recuperación · Archivos y directorios.

## Ejecución

```
pip install -r requirements.txt
sqlplus / as sysdba @sql\01_configuracion_inicial.sql   # una sola vez
python app\main.py                                       # o doble clic en Ejecutar_OraAdmin.bat
```

Usuario de la aplicación: `ADMIN_BD / Admin123` · servicio `XEPDB1` en `localhost:1521`.

Documentación: `Manual_de_Usuario_OraAdminXE.docx` y `Guia_Demo_OraAdminXE.pdf`.
