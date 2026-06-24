"""
Modelos de base de datos SQLite.
Tablas: remates, comunas_sii, analisis_agua
"""
import os
from pathlib import Path
DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).parent.parent / "tgr_agua.db")))
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "tgr_agua.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea las tablas si no existen."""
    conn = get_connection()
    c = conn.cursor()

    # ── Remates TGR ───────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS remates (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            rol           TEXT,
            rol_formato   TEXT,
            direccion     TEXT,
            comuna        TEXT,
            region        TEXT,
            avaluo        REAL,
            fecha_remate  TEXT,
            fecha_consulta TEXT DEFAULT (datetime('now')),
            -- Coordenadas SII
            lat           REAL,
            lon           REAL,
            ubicacion_sii TEXT,   -- RURAL / URBANO
            destino_sii   TEXT,   -- AGRICOLA, HABITACIONAL, etc.
            -- Estado del análisis
            estado        TEXT DEFAULT 'PENDIENTE'
                              CHECK(estado IN (
                                  'PENDIENTE','COORDENADAS_OK',
                                  'ANALISIS_OK','ERROR_SII','ERROR_DGA'
                              ))
        )
    """)

    # ── Comunas SII (se carga una sola vez) ───────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS comunas_sii (
            codigo TEXT PRIMARY KEY,
            nombre TEXT
        )
    """)

    # ── Análisis de agua por predio ───────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS analisis_agua (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            remate_id           INTEGER REFERENCES remates(id),
            fecha_analisis      TEXT DEFAULT (datetime('now')),

            -- DGA
            pozos_500m          INTEGER DEFAULT 0,
            pozos_2km           INTEGER DEFAULT 0,
            caudal_promedio_ls  REAL    DEFAULT 0,
            profundidad_media_m REAL    DEFAULT 0,
            zona_prohibicion    INTEGER DEFAULT 0,  -- 0/1
            zona_restriccion    INTEGER DEFAULT 0,  -- 0/1
            nombre_zona         TEXT,

            -- Topografía
            elevacion_m         REAL,
            pendiente_pct       REAL,
            elevacion_relativa  TEXT,   -- VALLE / CERRO

            -- Score final
            score               INTEGER,
            nivel               TEXT,   -- ALTO / MEDIO / BAJO
            puede_perforar      INTEGER DEFAULT 1,  -- 0/1
            factores_json       TEXT,   -- JSON con desglose de puntos
            advertencias_json   TEXT    -- JSON con lista de advertencias
        )
    """)

    conn.commit()
    conn.close()
    print(f"✅ Base de datos inicializada en {DB_PATH}")