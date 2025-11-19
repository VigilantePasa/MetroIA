# main.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
import heapq
from datetime import datetime

app = FastAPI(title="A* Metro CDMX (subset enunciado)")

# --- CORS para que cualquier GUI/puerto pueda llamar al backend ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ============================================================
# 1) DATOS: líneas y transbordos EXACTOS del enunciado
# ============================================================
# Línea 1 (granate): Observatorio -> Balderas
LINE_1 = [
    "Observatorio", "Tacubaya", "Juanacatlán", "Chapultepec",
    "Sevilla", "Insurgentes", "Cuauhtémoc", "Balderas"
]
# Línea 3 (verde claro): Universidad -> Juárez
LINE_3 = [
    "Universidad", "Copilco", "Miguel Ángel de Quevedo", "Viveros",
    "Coyoacán", "Zapata", "División del Norte", "Eugenia",
    "Etiopía", "Centro Médico", "Hospital General",
    "Niños Héroes", "Balderas", "Juárez"
]
# Línea 7 (naranja): Barranca del Muerto -> Polanco
LINE_7 = [
    "Barranca del Muerto", "Mixcoac", "San Antonio",
    "San Pedro de los Pinos", "Tacubaya",
    "Constituyentes", "Auditorio", "Polanco"
]
# Línea 9 (marrón): Tacubaya -> Lázaro Cárdenas
LINE_9 = ["Tacubaya", "Patriotismo", "Chilpancingo", "Centro Médico", "Lázaro Cárdenas"]
# Línea 12 (verde oscuro): Mixcoac -> Eje Central
LINE_12 = ["Mixcoac", "Insurgentes Sur", "Hospital 20 de Noviembre", "Zapata", "Parque de los Venados", "Eje Central"]

# Intercambios exigidos (5):
TRANSFERS_LIST = [
    {"station": "Mixcoac", "pairs": [("L7", "L12")]},
    {"station": "Zapata", "pairs": [("L3", "L12")]},
    {"station": "Tacubaya", "pairs": [("L1", "L7"), ("L1", "L9"), ("L7", "L9")]},
    {"station": "Centro Médico", "pairs": [("L3", "L9")]},
    {"station": "Balderas", "pairs": [("L1", "L3")]},
]

# Colores (para la futura GUI; aproximados)
LINE_COLORS = {"L1": "#8E1537", "L3": "#6BCB3C", "L7": "#F28C00", "L9": "#8C5A2B", "L12": "#006E4E"}

def chain_to_edges(stations: List[str], line_name: str) -> List[Tuple[str, str, str]]:
    edges = []
    for i in range(len(stations) - 1):
        a, b = stations[i], stations[i+1]
        edges.append((a, b, line_name))
        edges.append((b, a, line_name))
    return edges

EDGES: List[Tuple[str, str, str]] = []
for ln, seq in [("L1", LINE_1), ("L3", LINE_3), ("L7", LINE_7), ("L9", LINE_9), ("L12", LINE_12)]:
    EDGES += chain_to_edges(seq, ln)

# Índices útiles
LINES_BY_STATION: Dict[str, List[str]] = defaultdict(list)
for a, b, ln in EDGES:
    if ln not in LINES_BY_STATION[a]:
        LINES_BY_STATION[a].append(ln)
    if ln not in LINES_BY_STATION[b]:
        LINES_BY_STATION[b].append(ln)

# Transbordos "difíciles" (para PMR, puedes ajustar con tu equipo)
DIFFICULT_TRANSFERS = {
    "Tacubaya": True,
    "Centro Médico": False,
    "Mixcoac": False,
    "Zapata": False,
    "Balderas": False,
}

# Grafo no ponderado (para min hops en la heurística)
def build_unweighted_graph() -> Dict[str, List[str]]:
    g = defaultdict(list)
    for a, b, _ in EDGES:
        g[a].append(b)
    return g

G_UNW = build_unweighted_graph()

# ============================================================
# 2) COSTE g(n) y HEURÍSTICA h(n)
# ============================================================
class CostConfig(BaseModel):
    stop_cost: float = 1.0              # coste por avanzar 1 estación
    transfer_cost: float = 2.0          # penalización por cambio de línea
    steep_transfer_cost: float = 0.0    # penalización extra en transbordos difíciles si accessibility="pmr"
    accessibility: Optional[str] = None # "pmr" para aplicar steep_transfer_cost
    time_of_day: Optional[str] = None   # "rush" => +0.25 por salto
    day_of_week: Optional[str] = None   # {"sat","sun","weekend"} => -0.10 por salto

def per_hop_lower_bound(cfg: CostConfig) -> float:
    rush = 0.25 if cfg.time_of_day == "rush" else 0.0
    weekend = -0.1 if cfg.day_of_week in {"sat", "sun", "weekend"} else 0.0
    # cota inferior por salto: stop_cost + ajustes mínimos que APLICAN con la config actual
    return max(0.0, cfg.stop_cost + rush + weekend)

def min_hops(src: str, dst: str) -> int:
    if src == dst:
        return 0
    q = deque([(src, 0)])
    seen = {src}
    while q:
        u, d = q.popleft()
        for v in G_UNW.get(u, []):
            if v in seen:
                continue
            if v == dst:
                return d + 1
            seen.add(v)
            q.append((v, d + 1))
    return 10**9  # no debería ocurrir

def heuristic(node: str, goal: str, cfg: CostConfig) -> float:
    return float(min_hops(node, goal) * per_hop_lower_bound(cfg))  # admisible y consistente

def neighbors(station: str) -> List[Tuple[str, str]]:
    out = []
    for a, b, ln in EDGES:
        if a == station:
            out.append((b, ln))
    return out

def g_increment(current_station: str, prev_line: Optional[str], next_line: str, cfg: CostConfig):
    """Devuelve (incremento_coste, desglose_dict, did_transfer). El transbordo ocurre en current_station."""
    inc = cfg.stop_cost
    parts = {"stops": cfg.stop_cost, "transfers": 0.0, "steep": 0.0, "rush": 0.0, "weekend": 0.0}
    did_transfer = False

    if prev_line is not None and prev_line != next_line:
        inc += cfg.transfer_cost
        parts["transfers"] = cfg.transfer_cost
        did_transfer = True
        if cfg.accessibility == "pmr" and DIFFICULT_TRANSFERS.get(current_station, False):
            inc += cfg.steep_transfer_cost
            parts["steep"] = cfg.steep_transfer_cost

    if cfg.time_of_day == "rush":
        inc += 0.25
        parts["rush"] = 0.25
    if cfg.day_of_week in {"sat", "sun", "weekend"}:
        inc -= 0.1
        parts["weekend"] = -0.1

    return inc, parts, did_transfer

# ============================================================
# 3) A* y modelos para API
# ============================================================
class PathStep(BaseModel):
    station: str
    line: Optional[str] = None  # línea utilizada para llegar a esta estación (None para origen)

class PathRequest(BaseModel):
    origin: str
    destination: str
    config: CostConfig = CostConfig()

class PathResponse(BaseModel):
    path: List[PathStep]
    total_cost: float
    stops: int
    transfers: int
    cost_breakdown: Dict[str, float]

def astar(origin: str, dest: str, cfg: CostConfig) -> PathResponse:
    if origin not in LINES_BY_STATION or dest not in LINES_BY_STATION:
        raise HTTPException(400, "Estación origen/destino no reconocida en el subconjunto del enunciado.")

    # nodo: (f, g, station, prev_line, path, breakdown, transfers)
    h0 = heuristic(origin, dest, cfg)
    start = (h0, 0.0, origin, None,
             [PathStep(station=origin, line=None)],
             {"stops": 0.0, "transfers": 0.0, "steep": 0.0, "rush": 0.0, "weekend": 0.0},
             0)
    pq = [start]
    best_g: Dict[Tuple[str, Optional[str]], float] = {}

    while pq:
        f, g, u, prev_line, path, parts, transfers = heapq.heappop(pq)

        key = (u, prev_line)
        if g > best_g.get(key, float("inf")):
            continue
        best_g[key] = g

        if u == dest:
            return PathResponse(
                path=path,
                total_cost=round(g, 3),
                stops=max(0, len(path) - 1),
                transfers=transfers,
                cost_breakdown={k: round(v, 3) for k, v in parts.items()},
            )

        for v, ln in neighbors(u):
            inc, inc_parts, did_tr = g_increment(u, prev_line, ln, cfg)
            g2 = g + inc
            key2 = (v, ln)
            if g2 < best_g.get(key2, float("inf")):
                best_g[key2] = g2
                h = heuristic(v, dest, cfg)
                f2 = g2 + h
                path2 = path + [PathStep(station=v, line=ln)]
                parts2 = {
                    "stops": parts["stops"] + inc_parts["stops"],
                    "transfers": parts["transfers"] + inc_parts["transfers"],
                    "steep": parts["steep"] + inc_parts["steep"],
                    "rush": parts["rush"] + inc_parts["rush"],
                    "weekend": parts["weekend"] + inc_parts["weekend"],
                }
                heapq.heappush(pq, (f2, g2, v, ln, path2, parts2, transfers + (1 if did_tr else 0)))

    raise HTTPException(404, "No se encontró ruta.")

# ============================================================
# 4) ENDPOINTS
# ============================================================
@app.get("/health")
def health():
    return {"status": "ok", "datetime": datetime.now().isoformat()}

@app.get("/lines")
def lines():
    return {
        "lines": {
            "L1": LINE_1, "L3": LINE_3, "L7": LINE_7, "L9": LINE_9, "L12": LINE_12
        },
        "transfers": TRANSFERS_LIST,
        "colors": LINE_COLORS
    }

@app.get("/stations")
def stations():
    all_st = sorted(set(LINES_BY_STATION.keys()))
    return {"stations": all_st}

@app.get("/graph")
def graph():
    """Útil para la GUI: nodos, aristas y colores de línea."""
    nodes = sorted(set([a for a, _, _ in EDGES] + [b for _, b, _ in EDGES]))
    edges = [{"from": a, "to": b, "line": ln} for a, b, ln in EDGES]
    return {"nodes": nodes, "edges": edges, "colors": LINE_COLORS}

@app.post("/path", response_model=PathResponse)
def get_path(req: PathRequest):
    return astar(req.origin, req.destination, req.config)

@app.get("/path_q", response_model=PathResponse)
def get_path_q(
    origin: str = Query(..., description="Estación origen"),
    destination: str = Query(..., description="Estación destino"),
    stop_cost: float = 1.0,
    transfer_cost: float = 2.0,
    steep_transfer_cost: float = 0.0,
    accessibility: Optional[str] = None,
    time_of_day: Optional[str] = None,
    day_of_week: Optional[str] = None,
):
    cfg = CostConfig(
        stop_cost=stop_cost, transfer_cost=transfer_cost,
        steep_transfer_cost=steep_transfer_cost,
        accessibility=accessibility, time_of_day=time_of_day, day_of_week=day_of_week
    )
    return astar(origin, destination, cfg)

# (Opcional) /explain para didáctica: primeros N pasos de expansión
class ExplainRequest(BaseModel):
    origin: str
    destination: str
    config: CostConfig = CostConfig()
    max_steps: int = 40

@app.post("/explain")
def explain(req: ExplainRequest):
    cfg = req.config
    origin, dest, max_steps = req.origin, req.destination, req.max_steps
    if origin not in LINES_BY_STATION or dest not in LINES_BY_STATION:
        raise HTTPException(400, "Estación origen/destino no reconocida.")

    pq = []
    h0 = heuristic(origin, dest, cfg)
    heapq.heappush(pq, (h0, 0.0, origin, None, [PathStep(station=origin, line=None)]))
    seen: Dict[Tuple[str, Optional[str]], float] = {}
    steps = []

    step = 0
    while pq and step < max_steps:
        f, g, u, prev_line, path = heapq.heappop(pq)
        step += 1
        entry = {"current": u, "prev_line": prev_line, "g": round(g, 3), "h": round(heuristic(u, dest, cfg), 3), "f": round(f, 3), "pushed": []}

        for v, ln in neighbors(u):
            inc, _, _ = g_increment(u, prev_line, ln, cfg)
            g2 = g + inc
            key = (v, ln)
            if g2 < seen.get(key, float("inf")):
                seen[key] = g2
                h = heuristic(v, dest, cfg)
                f2 = g2 + h
                heapq.heappush(pq, (f2, g2, v, ln, path + [PathStep(station=v, line=ln)]))
                entry["pushed"].append({"to": v, "line": ln, "g": round(g2, 3), "h": round(h, 3), "f": round(f2, 3)})
        steps.append(entry)

        if u == dest:
            break

    return {"steps": steps, "note": "Solo para explicación/GUI; el trayecto óptimo úsalo con /path."}
