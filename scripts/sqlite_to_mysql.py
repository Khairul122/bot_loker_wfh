"""Convert SQLite database (data/app.db) to MySQL and import into MySQL server."""

import sqlite3
import subprocess
from pathlib import Path

SQLITE_DB = Path("data/app.db")
MYSQL_BIN = Path(r"D:\Alternatif_D\laragon\bin\mysql\mysql-8.4.3-winx64\bin\mysql.exe")
DB_NAME = "bot_loker_wfh"

def convert():
    if not SQLITE_DB.exists():
        print(f"Error: {SQLITE_DB} tidak ditemukan!")
        return

    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    tables = [
        row[0]
        for row in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]

    sql_statements = [
        f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
        f"USE `{DB_NAME}`;",
        "SET FOREIGN_KEY_CHECKS = 0;",
    ]

    for table in tables:
        cols_info = cursor.execute(f"PRAGMA table_info(`{table}`)").fetchall()
        col_defs = []
        pk_cols = []
        for col in cols_info:
            c_name = col["name"]
            c_type = col["type"].upper()
            c_pk = col["pk"]
            c_notnull = "NOT NULL" if (col["notnull"] or c_pk) else "NULL"
            c_dflt = col["dflt_value"]

            if "INT" in c_type:
                mysql_type = "BIGINT" if "BIG" in c_type else "INT"
            elif "REAL" in c_type or "FLOAT" in c_type or "DOUBLE" in c_type:
                mysql_type = "DOUBLE"
            elif "BLOB" in c_type:
                mysql_type = "LONGBLOB"
            else:
                if c_pk or c_name in {"id", "host", "status", "source", "role", "mode", "run_id", "application_id", "job_id", "session_id", "created_at", "updated_at", "changed_at", "fetched_at", "notified_at", "submitted_at"}:
                    mysql_type = "VARCHAR(255)"
                else:
                    mysql_type = "LONGTEXT"

            default_clause = ""
            if c_dflt is not None:
                dflt_str = str(c_dflt)
                if "strftime" in dflt_str or "CURRENT_TIMESTAMP" in dflt_str:
                    default_clause = ""
                else:
                    default_clause = f" DEFAULT {dflt_str}"

            col_defs.append(f"  `{c_name}` {mysql_type} {c_notnull}{default_clause}")
            if c_pk:
                pk_cols.append(f"`{c_name}`")

        if pk_cols:
            col_defs.append(f"  PRIMARY KEY ({', '.join(pk_cols)})")

        create_tbl = f"DROP TABLE IF EXISTS `{table}`;\nCREATE TABLE `{table}` (\n" + ",\n".join(col_defs) + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
        sql_statements.append(create_tbl)

        rows = cursor.execute(f"SELECT * FROM `{table}`").fetchall()
        for r in rows:
            cols = [f"`{k}`" for k in r.keys()]
            vals = []
            for v in tuple(r):
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    escaped = str(v).replace("\\", "\\\\").replace("'", "\\'").replace("\0", "")
                    vals.append(f"'{escaped}'")
            ins = f"INSERT INTO `{table}` ({', '.join(cols)}) VALUES ({', '.join(vals)});"
            sql_statements.append(ins)

    sql_statements.append("SET FOREIGN_KEY_CHECKS = 1;")

    out_file = Path("data/mysql_dump.sql")
    out_file.write_text("\n\n".join(sql_statements), encoding="utf-8")
    print(f"Generated {out_file.resolve()} ({len(tables)} tables)")

    # Execute import via mysql CLI
    print(f"Importing into MySQL `{DB_NAME}`...")
    out_path_str = str(out_file.resolve()).replace("\\", "/")
    cmd = [str(MYSQL_BIN), "-u", "root", "--default-character-set=utf8mb4", "-e", f"source {out_path_str};"]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode == 0:
        print(f"Import BERHASIL ke MySQL database '{DB_NAME}'!")
    else:
        print("Import gagal:", res.stderr)

if __name__ == "__main__":
    convert()
