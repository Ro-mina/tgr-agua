"""
Servicio DGA - Consulta derechos de agua subterránea y zonas de restricción.

Usa la API ArcGIS REST del MOP (actualizada diariamente):
  - SNIA_DerechoAprovechamiento: derechos de agua otorgados (subterráneos y superficiales)
  - Areas_Restriccion_Zonas_prohibicion: zonas donde NO se puede perforar
"""

import httpx
from dataclasses import dataclass, field


# ─── URLs base ────────────────────────────────────────────────────────────────
_BASE = "https://rest-sit.mop.gov.cl/arcgis/rest/services"

DERECHOS_URL   = f"{_BASE}/SNIA/SNIA_DerechoAprovechamiento/MapServer/0/query"
RESTRICCION_URL = f"{_BASE}/DGA/Areas_Restriccion_Zonas_prohibicion/MapServer/0/query"


# ─── Resultado de la consulta ─────────────────────────────────────────────────
@dataclass
class ResultadoDGA:
    # Derechos de agua subterránea
    pozos_500m: int = 0          # cantidad en radio de 500m
    pozos_2km: int = 0           # cantidad en radio de 2km (incluye los de 500m)
    caudal_promedio_ls: float = 0.0   # litros/segundo promedio de los pozos cercanos
    profundidad_media_m: float = 0.0  # profundidad media (cuando está disponible)
    detalle_pozos: list = field(default_factory=list)  # lista de dicts con info cruda

    # Zona de restricción / prohibición
    zona_prohibicion: bool = False
    zona_restriccion: bool = False
    nombre_zona: str = ""

    # Estado del proceso
    error: str = ""


# ─── Función principal ────────────────────────────────────────────────────────
async def consultar_dga(lat: float, lon: float) -> ResultadoDGA:
    """
    Consulta la API ArcGIS del MOP para un punto (lat, lon).
    Retorna un ResultadoDGA con toda la información disponible.
    """
    resultado = ResultadoDGA()

    async with httpx.AsyncClient(timeout=20.0, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://dga.mop.gob.cl/",
        "Accept": "application/json, text/plain, */*"
    }) as client:

        # 1. Derechos de agua en radio de 2km
        await _consultar_derechos(client, lat, lon, resultado)

        # 2. Zona de restricción / prohibición
        await _consultar_restricciones(client, lat, lon, resultado)

    return resultado


# ─── Consulta derechos de agua ────────────────────────────────────────────────
async def _consultar_derechos(
    client: httpx.AsyncClient, lat: float, lon: float, resultado: ResultadoDGA
):
    params = {
        "geometry":     f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR":         "4326",
        "spatialRel":   "esriSpatialRelIntersects",
        "distance":     "2000",          # metros
        "units":        "esriSRUnit_Meter",
        # Campos más relevantes del servicio SNIA
        "outFields":    "TIPO_FUENTE,TIPO_DERECHO,CAUDAL_MEDIO,PROF_POZO,ESTADO,EXPEDIENTE",
        "returnGeometry": "true",        # necesitamos coordenadas para calcular distancia real
        "outSR":        "4326",
        "f":            "json",
    }

    try:
        response = await client.get(DERECHOS_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        resultado.error += f"Error consultando derechos DGA: {e}. "
        return

    features = data.get("features", [])
    if not features:
        return  # No hay derechos registrados en el área → pozos en 0

    caudales = []
    profundidades = []

    for feat in features:
        attrs = feat.get("attributes", {})
        geom  = feat.get("geometry", {})

        # Filtrar solo aguas subterráneas (tipo fuente = "SUBTERRANEA" o similar)
        tipo_fuente = (attrs.get("TIPO_FUENTE") or "").upper()
        if "SUB" not in tipo_fuente and tipo_fuente != "":
            continue  # Ignorar derechos de agua superficial

        # Calcular distancia aproximada al punto
        dist_m = _distancia_metros(lat, lon, geom.get("y"), geom.get("x"))

        if dist_m <= 500:
            resultado.pozos_500m += 1
        resultado.pozos_2km += 1

        # Recopilar caudal y profundidad si existen
        caudal = attrs.get("CAUDAL_MEDIO")
        if caudal and caudal > 0:
            caudales.append(float(caudal))

        prof = attrs.get("PROF_POZO")
        if prof and prof > 0:
            profundidades.append(float(prof))

        resultado.detalle_pozos.append({
            "expediente":   attrs.get("EXPEDIENTE"),
            "tipo_derecho": attrs.get("TIPO_DERECHO"),
            "estado":       attrs.get("ESTADO"),
            "caudal_ls":    caudal,
            "profundidad_m": prof,
            "distancia_m":  round(dist_m),
        })

    if caudales:
        resultado.caudal_promedio_ls = round(sum(caudales) / len(caudales), 2)
    if profundidades:
        resultado.profundidad_media_m = round(sum(profundidades) / len(profundidades), 1)


# ─── Consulta zonas de restricción / prohibición ──────────────────────────────
async def _consultar_restricciones(
    client: httpx.AsyncClient, lat: float, lon: float, resultado: ResultadoDGA
):
    params = {
        "geometry":     f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR":         "4326",
        "spatialRel":   "esriSpatialRelIntersects",
        "outFields":    "TIPO,NOMBREAREA",
        "returnGeometry": "false",
        "f":            "json",
    }

    try:
        response = await client.get(RESTRICCION_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        resultado.error += f"Error consultando restricciones DGA: {e}. "
        return

    features = data.get("features", [])
    if not features:
        return  # Fuera de cualquier zona restringida → bien

    for feat in features:
        attrs = feat.get("attributes", {})
        tipo  = (attrs.get("TIPO") or "").upper()
        nombre = attrs.get("NOMBREAREA") or ""

        if "PROHIBICION" in tipo or "PROHIBICIÓN" in tipo:
            resultado.zona_prohibicion = True
        elif "RESTRICCION" in tipo or "RESTRICCIÓN" in tipo:
            resultado.zona_restriccion = True

        if nombre:
            resultado.nombre_zona = nombre


# ─── Utilidad: distancia aproximada en metros (fórmula de Haversine) ──────────
def _distancia_metros(lat1, lon1, lat2, lon2) -> float:
    """Distancia en metros entre dos puntos (lat/lon en grados decimales)."""
    if lat2 is None or lon2 is None:
        return 9999.0
    from math import radians, sin, cos, sqrt, atan2
    R = 6_371_000  # radio de la Tierra en metros
    φ1, φ2 = radians(lat1), radians(lat2)
    Δφ = radians(lat2 - lat1)
    Δλ = radians(lon2 - lon1)
    a = sin(Δφ/2)**2 + cos(φ1) * cos(φ2) * sin(Δλ/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))