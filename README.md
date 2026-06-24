# TGR Agua Subterránea

API REST que analiza propiedades en remate judicial de la TGR de Chile y evalúa la probabilidad de tener agua subterránea.

## 🌐 URL de producción

```
https://tgr-agua-production.up.railway.app
```

Documentación interactiva: [/docs](https://tgr-agua-production.up.railway.app/docs)

---

## ¿Qué hace?

Para cada propiedad en remate:
1. Obtiene coordenadas exactas desde el **SII** usando el rol predial
2. Consulta derechos de agua registrados en la **DGA** (MOP)
3. Calcula elevación y pendiente con **OpenTopoData**
4. Genera un **score 0–100** de probabilidad de agua subterránea

---

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/remates` | Descarga remates activos desde TGR |
| GET | `/remates/{id}/analizar` | Analiza un predio individual |
| GET | `/analisis` | Lista resultados con filtros |

---

## Score de agua (0–100)

| Criterio | Puntos | Fuente |
|----------|--------|--------|
| Pozos DGA en 500m o 2km | 40 | MOP/DGA |
| Caudal promedio | 10 | MOP/DGA |
| Posición en valle | 20 | OpenTopoData |
| Pendiente baja | 10 | OpenTopoData |
| Uso agrícola SII | 20 | SII |

**Niveles:** ALTO ≥ 70 · MEDIO 40–69 · BAJO < 40

> Si el predio está en zona de prohibición DGA, `puede_perforar` = false sin importar el score.

---

## Instalación local

```bash
git clone https://github.com/Ro-mina/tgr-agua.git
cd tgr-agua
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Abre `http://localhost:8000/docs`

---

## Stack

- **FastAPI** + **Uvicorn** — framework y servidor
- **SQLite** — base de datos local
- **httpx** — cliente HTTP async
- **Railway** — deploy en producción

---

## APIs externas

| API | Uso | Estado |
|-----|-----|--------|
| TGR | Remates activos | ✅ Estable |
| SII mapasui | Coordenadas por rol | ⚠️ Rate limiting en volumen |
| MOP/DGA ArcGIS | Derechos de agua | ❌ Intermitente |
| OpenTopoData | Elevación y pendiente | ✅ Estable |

---

Desarrollado por Romina Torres · 2026