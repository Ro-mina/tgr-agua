import httpx
from dataclasses import dataclass
from app.services.comunas_sii import obtener_codigo_comuna


SII_URL = "https://www4.sii.cl/mapasui/services/data/mapasFacadeService/getPredioNacional"

@dataclass
class ResultadoGeo:
    lat: float
    lon: float
    ubicacion: str = ""
    destino: str = ""
    error: str = ""

async def geocodificar_por_rol(rol_formato: str) -> ResultadoGeo:
    """
    rol_formato viene como "CURICO-00531-037" o "RETIRO-00317-059"
    Parsea comuna, manzana y predio directamente.
    """
    try:
        partes = rol_formato.split("-")
        nombre_comuna = partes[0].strip()
        manzana = int(partes[1])
        predio  = int(partes[2])
    except Exception:
        return ResultadoGeo(lat=0, lon=0, error=f"rolFormato con formato inesperado: {rol_formato}")

    codigo_comuna = obtener_codigo_comuna(nombre_comuna)
    if not codigo_comuna:
        return ResultadoGeo(lat=0, lon=0, error=f"Comuna no encontrada en diccionario: {nombre_comuna}")

    payload = {
        "metaData": {
            "namespace": "cl.sii.sdi.lob.bbrr.mapas.data.api.interfaces.MapasFacadeService/getPredioNacional",
            "conversationId": "UNAUTHENTICATED-CALL",
            "transactionId": "tgr-agua-app-001",
        },
        "data": {
            "predio": {
                "comuna": str(codigo_comuna),
                "manzana": str(manzana).zfill(5),  # rellena con ceros: 317 → "00317"
                "predio": str(predio).zfill(3),  # rellena con ceros: 59 → "059"
            },
            "servicios": []
        }
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Referer":    "https://www4.sii.cl/mapasui/internet/",
        "Origin":     "https://www4.sii.cl",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(SII_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return ResultadoGeo(lat=0, lon=0, error=f"Error SII: {e}")

    predio_data = data.get("data") if data else None
    if not predio_data:
        return ResultadoGeo(lat=0, lon=0, error=f"SII no devolvió datos para: {rol_formato}")

    if not predio_data.get("existePredio"):
        return ResultadoGeo(lat=0, lon=0, error=f"Predio no encontrado en SII: {rol_formato}")

    lat = predio_data.get("ubicacionX")
    lon = predio_data.get("ubicacionY")

    if not lat or not lon:
        return ResultadoGeo(lat=0, lon=0, error=f"SII no devolvió coordenadas para: {rol_formato}")

    return ResultadoGeo(
        lat=float(lat),
        lon=float(lon),
        ubicacion=predio_data.get("ubicacion", ""),
        destino=predio_data.get("destinoDescripcion", ""),
    )
