import json
import httpx
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager

from app.models.database import init_db, get_connection
from app.services.dga_service import consultar_dga
from app.services.topo_service import consultar_topografia
from app.services.score_service import calcular_score

TGR_URL = "https://remates.tgr.cl/v1/getListaRematesActivos"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="TGR Agua Subterránea",
    description="Analiza propiedades en remate TGR para detectar probabilidad de agua subterránea",
    version="1.0.0",
    lifespan=lifespan,
)


def _actualizar_estado(remate_id: int, estado: str):
    conn = get_connection()
    conn.execute("UPDATE remates SET estado = ? WHERE id = ?", (estado, remate_id))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# GET /remates
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/remates", summary="Obtener y guardar remates activos desde TGR")
async def obtener_remates():
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(TGR_URL)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise HTTPException(502, f"Error consultando TGR: {e}")

    items = data if isinstance(data, list) else data.get("data", [])

    conn = get_connection()
    c = conn.cursor()
    guardados = 0

    for item in items:
        rol = item.get("rol") or ""
        if not rol:
            continue

        existe = c.execute("SELECT id FROM remates WHERE rol = ?", (rol,)).fetchone()
        if existe:
            continue

        c.execute("""
            INSERT INTO remates (rol, rol_formato, direccion, comuna, region, avaluo, fecha_remate)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            rol,
            item.get("rolFormato") or "",
            item.get("direccionRol") or "",
            item.get("comunaJuzgado") or "",
            item.get("tipoDeuda") or "",
            item.get("avaluo") or item.get("tasacion") or 0,
            item.get("fechaRemate") or "",
        ))
        guardados += 1

    conn.commit()
    conn.close()

    return {"mensaje": f"{guardados} remates nuevos guardados", "total_recibidos": len(items)}


# ─────────────────────────────────────────────────────────────────────────────
# GET /remates/{id}/analizar
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/remates/{remate_id}/analizar", summary="Analizar probabilidad de agua subterránea")
async def analizar_remate(remate_id: int):
    conn = get_connection()
    remate = conn.execute("SELECT * FROM remates WHERE id = ?", (remate_id,)).fetchone()
    conn.close()

    if not remate:
        raise HTTPException(404, "Remate no encontrado")

    remate = dict(remate)

    from app.services.geo_service import geocodificar_por_rol

    rol_formato = remate.get("rol_formato") or ""
    if not rol_formato:
        _actualizar_estado(remate_id, "ERROR_SII")
        raise HTTPException(422, f"Remate sin rolFormato: id={remate_id}")

    geo = await geocodificar_por_rol(rol_formato)
    if geo.error:
        _actualizar_estado(remate_id, "ERROR_SII")
        raise HTTPException(422, geo.error)

    lat           = geo.lat
    lon           = geo.lon
    ubicacion_sii = geo.ubicacion
    destino_sii   = geo.destino

    conn = get_connection()
    conn.execute("""
        UPDATE remates
        SET lat = ?, lon = ?, ubicacion_sii = ?, destino_sii = ?, estado = 'COORDENADAS_OK'
        WHERE id = ?
    """, (lat, lon, ubicacion_sii, destino_sii, remate_id))
    conn.commit()
    conn.close()

    dga = await consultar_dga(lat, lon)
    if dga.error:
        _actualizar_estado(remate_id, "ERROR_DGA")

    topo = await consultar_topografia(lat, lon)

    score_result = calcular_score(
        dga=dga,
        ubicacion_sii=ubicacion_sii,
        destino_sii=destino_sii,
        pendiente_pct=topo.pendiente_pct,
        elevacion_relativa=topo.elevacion_relativa,
    )

    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO analisis_agua (
            remate_id, pozos_500m, pozos_2km, caudal_promedio_ls,
            profundidad_media_m, zona_prohibicion, zona_restriccion, nombre_zona,
            elevacion_m, pendiente_pct, elevacion_relativa,
            score, nivel, puede_perforar, factores_json, advertencias_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        remate_id,
        dga.pozos_500m, dga.pozos_2km, dga.caudal_promedio_ls,
        dga.profundidad_media_m,
        int(dga.zona_prohibicion), int(dga.zona_restriccion), dga.nombre_zona,
        topo.elevacion_m, topo.pendiente_pct, topo.elevacion_relativa,
        score_result.score, score_result.nivel,
        int(score_result.puede_perforar),
        json.dumps(score_result.factores),
        json.dumps(score_result.advertencias),
    ))
    conn.execute("UPDATE remates SET estado = 'ANALISIS_OK' WHERE id = ?", (remate_id,))
    conn.commit()
    conn.close()

    return {
        "remate_id":     remate_id,
        "rol":           remate["rol"],
        "rol_formato":   rol_formato,
        "comuna":        remate["comuna"],
        "direccion":     remate["direccion"],
        "coordenadas":   {"lat": lat, "lon": lon},
        "ubicacion_sii": ubicacion_sii,
        "destino_sii":   destino_sii,
        "dga": {
            "pozos_500m":          dga.pozos_500m,
            "pozos_2km":           dga.pozos_2km,
            "caudal_promedio_ls":  dga.caudal_promedio_ls,
            "profundidad_media_m": dga.profundidad_media_m,
            "zona_prohibicion":    dga.zona_prohibicion,
            "zona_restriccion":    dga.zona_restriccion,
            "nombre_zona":         dga.nombre_zona,
        },
        "topografia": {
            "elevacion_m":        topo.elevacion_m,
            "pendiente_pct":      topo.pendiente_pct,
            "elevacion_relativa": topo.elevacion_relativa,
        },
        "score_agua": {
            "score":          score_result.score,
            "nivel":          score_result.nivel,
            "puede_perforar": score_result.puede_perforar,
            "factores":       score_result.factores,
            "advertencias":   score_result.advertencias,
        }
    }

# ─────────────────────────────────────────────────────────────────────────────
# GET /analisis
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/analisis", summary="Listar análisis con score de agua")
async def listar_analisis(
    score_min:      int  = 0,
    nivel:          str  = "",
    solo_rural:     bool = False,
    puede_perforar: bool = False,
):
    conn = get_connection()

    query = """
        SELECT r.id, r.rol, r.rol_formato, r.comuna, r.region, r.direccion, r.avaluo,
               r.ubicacion_sii, r.destino_sii,
               a.score, a.nivel, a.puede_perforar,
               a.pozos_2km, a.caudal_promedio_ls, a.zona_prohibicion,
               a.elevacion_relativa, a.pendiente_pct
        FROM remates r
        JOIN analisis_agua a ON a.remate_id = r.id
        WHERE a.score >= ?
    """
    params = [score_min]

    if nivel:
        query += " AND a.nivel = ?"
        params.append(nivel.upper())
    if solo_rural:
        query += " AND r.ubicacion_sii = 'RURAL'"
    if puede_perforar:
        query += " AND a.puede_perforar = 1"

    query += " ORDER BY a.score DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [dict(r) for r in rows]

@app.get("/remates/por-rol/{rol_formato}", summary="Analizar por rolFormato")
async def analizar_por_rol(rol_formato: str):
    """Busca o crea el remate por rolFormato y lo analiza."""
    conn = get_connection()
    remate = conn.execute(
        "SELECT * FROM remates WHERE rol_formato = ?", (rol_formato,)
    ).fetchone()
    conn.close()

    if not remate:
        raise HTTPException(404, f"Remate no encontrado: {rol_formato}")

    return await analizar_remate(remate["id"])