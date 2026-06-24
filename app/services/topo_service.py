"""
Servicio de topografía usando OpenTopoData (SRTM 30m).
Calcula elevación, pendiente y si el terreno está en valle o cerro.

API pública gratuita: https://api.opentopodata.org
Límite: 100 puntos por request, 1 request/segundo.
"""

import httpx
from dataclasses import dataclass
from math import sqrt


TOPO_URL = "https://api.opentopodata.org/v1/srtm30m"

# Desplazamiento en grados para los 4 puntos cardinales (~150m)
DELTA = 0.0015


@dataclass
class ResultadoTopo:
    elevacion_m: float
    pendiente_pct: float
    elevacion_relativa: str  # "VALLE" o "CERRO"
    error: str = ""


async def consultar_topografia(lat: float, lon: float) -> ResultadoTopo:
    """
    Consulta elevación del punto central + 4 cardinales en un solo request batch.
    Calcula pendiente máxima y determina si está en valle o cerro.
    """
    # 5 puntos en un solo request (centro + N, S, E, O)
    puntos = [
        (lat, lon),               # centro
        (lat + DELTA, lon),       # norte
        (lat - DELTA, lon),       # sur
        (lat, lon + DELTA),       # este
        (lat, lon - DELTA),       # oeste
    ]
    locations = "|".join(f"{la},{lo}" for la, lo in puntos)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                TOPO_URL,
                params={"locations": locations}
            )
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        return ResultadoTopo(
            elevacion_m=0,
            pendiente_pct=0,
            elevacion_relativa="DESCONOCIDO",
            error=f"Error OpenTopoData: {e}"
        )

    resultados = data.get("results", [])
    if len(resultados) < 5:
        return ResultadoTopo(
            elevacion_m=0,
            pendiente_pct=0,
            elevacion_relativa="DESCONOCIDO",
            error="Respuesta incompleta de OpenTopoData"
        )

    elevaciones = [r.get("elevation") or 0 for r in resultados]
    centro, norte, sur, este, oeste = elevaciones

    # Distancia aproximada entre puntos (DELTA grados ≈ 167m en Chile central)
    dist_m = DELTA * 111_000

    # Pendiente máxima entre el centro y cada cardinal
    pendientes = [
        abs(centro - norte) / dist_m * 100,
        abs(centro - sur)   / dist_m * 100,
        abs(centro - este)  / dist_m * 100,
        abs(centro - oeste) / dist_m * 100,
    ]
    pendiente_max = round(max(pendientes), 1)

    # Valle: el centro es más bajo que al menos 2 de los 4 cardinales
    vecinos_mas_altos = sum(1 for v in [norte, sur, este, oeste] if v > centro)
    elevacion_relativa = "VALLE" if vecinos_mas_altos >= 2 else "CERRO"

    return ResultadoTopo(
        elevacion_m=round(centro, 1),
        pendiente_pct=pendiente_max,
        elevacion_relativa=elevacion_relativa,
    )