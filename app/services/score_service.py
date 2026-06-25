"""
Calculador de Score de Agua Subterránea.

Basado en datos reales de la DGA (derechos de agua, zonas de restricción)
más variables topográficas y de uso de suelo.

Escala: 0 – 100
  ≥ 70 → ALTO
  40–69 → MEDIO
  < 40  → BAJO
"""

from dataclasses import dataclass
from app.services.dga_service import ResultadoDGA


@dataclass
class ResultadoScore:
    score: int
    nivel: str           # ALTO / MEDIO / BAJO
    puede_perforar: bool # False si hay zona de prohibición
    factores: dict       # desglose de puntos por criterio
    advertencias: list   # ej: zona de restricción, sin datos topográficos


def calcular_score(
    dga: ResultadoDGA,
    ubicacion_sii: str,     # "RURAL" o "URBANO"
    destino_sii: str,       # ej: "AGRICOLA", "HABITACIONAL", etc.
    pendiente_pct: float,   # pendiente del terreno en %
    elevacion_relativa: str # "VALLE" o "CERRO" (calculado desde DEM)
) -> ResultadoScore:

    puntos = {}
    advertencias = []

    # ── 1. Derechos de agua subterránea DGA (máx 40 pts) ─────────────────────
    if dga.pozos_500m >= 3:
        puntos["pozos_dga"] = 40
    elif dga.pozos_500m >= 1:
        puntos["pozos_dga"] = 30
    elif dga.pozos_2km >= 3:
        puntos["pozos_dga"] = 20
    elif dga.pozos_2km >= 1:
        puntos["pozos_dga"] = 10
    else:
        puntos["pozos_dga"] = 0
        if dga.error:
            advertencias.append(
                "Datos DGA no disponibles — el servidor del MOP no respondió. Los pozos cercanos no pudieron consultarse.")
        else:
            advertencias.append("Sin derechos de agua registrados en 2km según catastro DGA.")

    # ── 2. Caudal promedio de los pozos cercanos (máx 10 pts bonus) ──────────
    if dga.caudal_promedio_ls >= 5:
        puntos["caudal"] = 10
    elif dga.caudal_promedio_ls >= 1:
        puntos["caudal"] = 5
    else:
        puntos["caudal"] = 0

    # ── 3. Posición topográfica (máx 20 pts) ─────────────────────────────────
    if elevacion_relativa == "VALLE":
        puntos["topografia"] = 20
    else:
        puntos["topografia"] = 5  # cerro/ladera = recarga menor

    # ── 4. Pendiente (máx 10 pts) ────────────────────────────────────────────
    # Pendiente baja → agua se infiltra en vez de escurrir
    if pendiente_pct < 3:
        puntos["pendiente"] = 10
    elif pendiente_pct < 8:
        puntos["pendiente"] = 5
    else:
        puntos["pendiente"] = 0

    # ── 5. Uso de suelo SII (máx 20 pts) ─────────────────────────────────────
    destino_upper = (destino_sii or "").upper()
    if "AGRICOLA" in destino_upper or "AGRÍCOLA" in destino_upper:
        puntos["uso_suelo"] = 20
    elif ubicacion_sii == "RURAL":
        puntos["uso_suelo"] = 10
    else:
        puntos["uso_suelo"] = 0

    # ── Suma total (máx teórico = 100) ────────────────────────────────────────
    total_raw = sum(puntos.values())
    score = min(total_raw, 100)  # cap a 100

    # ── Zona de prohibición: bloquea perforación (penalización informativa) ───
    puede_perforar = True
    if dga.zona_prohibicion:
        puede_perforar = False
        advertencias.append(
            f"⚠️ ZONA DE PROHIBICIÓN DGA: {dga.nombre_zona}. "
            "No se pueden constituir nuevos derechos de agua."
        )
    elif dga.zona_restriccion:
        advertencias.append(
            f"⚠️ Zona de restricción DGA: {dga.nombre_zona}. "
            "Se requiere autorización especial para perforar."
        )

    # ── Nivel cualitativo ─────────────────────────────────────────────────────
    if score >= 70:
        nivel = "ALTO"
    elif score >= 40:
        nivel = "MEDIO"
    else:
        nivel = "BAJO"

    return ResultadoScore(
        score=score,
        nivel=nivel,
        puede_perforar=puede_perforar,
        factores=puntos,
        advertencias=advertencias,
    )