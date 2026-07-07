from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import auth, viajes, reservas, usuarios, asistente

settings = get_settings()

app = FastAPI(
    title="RutaGo API",
    description=(
        "Backend distribuido de carpooling para Ecuador.\n\n"
        "**Stack:** FastAPI · Supabase (PostgreSQL + Auth + Realtime) · Azure Container Apps\n\n"
        "**Proyecto:** ISWZ2105 – Aplicaciones Distribuidas · UDLA"
    ),
    version="1.0.0",
    contact={"name": "Equipo RutaGo", "email": "rutago@udla.edu.ec"},
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(viajes.router)
app.include_router(reservas.router)
app.include_router(usuarios.router)
app.include_router(asistente.router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {
        "app": "RutaGo API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
