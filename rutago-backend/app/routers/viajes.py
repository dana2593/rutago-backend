import psycopg2
import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query, status
from datetime import date
from pydantic import BaseModel

from app.schemas.schemas import ViajeOut, VehiculoCreate, VehiculoOut
from app.core.security import get_current_user
from app.core.supabase import get_supabase

load_dotenv()
router = APIRouter(prefix="/viajes", tags=["Viajes"])


class ViajePublicarRequest(BaseModel):
    destino: str
    fecha_salida: str
    hora_salida: str
    precio_por_persona: float
    asientos_disponibles: int
    punto_encuentro: str
    duracion_estimada: str = "~7h"


def get_db():
    load_dotenv()
    url = os.environ.get("DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise Exception("DATABASE_URL no configurada")
    conn = psycopg2.connect(url)
    return conn


def _map_row(row) -> ViajeOut:
    return ViajeOut(
        id=str(row[0]),
        conductor_id=str(row[1]),
        conductor_nombre=row[2] or "",
        conductor_valoracion=float(row[3] or 0),
        conductor_viajes=int(row[4] or 0),
        conductor_rango=row[5] or "Nuevo",
        vehiculo_placa=row[6] or "",
        vehiculo_descripcion=f"{row[7] or ''} {row[8] or ''}".strip(),
        destino=row[9],
        fecha_salida=str(row[10]),
        hora_salida=str(row[11])[:5],
        precio_por_persona=float(row[12]),
        asientos_disponibles=int(row[13]),
        punto_encuentro=row[14],
        duracion_estimada=row[15],
    )


VIAJES_QUERY = """
    SELECT v.id, v.conductor_id,
           u.nombre_completo, u.valoracion_promedio, u.viajes_completados, u.rango,
           vh.placa, vh.marca, vh.modelo,
           v.destino, v.fecha_salida, v.hora_salida,
           v.precio_por_persona, v.asientos_disponibles,
           v.punto_encuentro, v.duracion_estimada
    FROM public.viajes v
    LEFT JOIN public.usuarios u ON u.id = v.conductor_id
    LEFT JOIN public.vehiculos vh ON vh.id = v.vehiculo_id
"""


@router.get("", response_model=list[ViajeOut])
async def buscar_viajes(
    destino: str = Query(...),
    fecha: date = Query(...),
    pasajeros: int = Query(1, ge=1, le=4),
    orden: str = Query("precio"),
    _user: dict = Depends(get_current_user),
):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        VIAJES_QUERY + """
        WHERE v.destino ILIKE %s
          AND v.fecha_salida = %s
          AND v.asientos_disponibles >= %s
          AND v.estado = 'activo'
        ORDER BY v.precio_por_persona ASC
        """,
        (f"%{destino}%", str(fecha), pasajeros)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [_map_row(r) for r in rows]


@router.get("/mis-viajes", response_model=list[ViajeOut])
async def mis_viajes_como_conductor(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        VIAJES_QUERY + "WHERE v.conductor_id = %s ORDER BY v.fecha_salida DESC",
        (current_user["sub"],)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [_map_row(r) for r in rows]


@router.get("/{viaje_id}", response_model=ViajeOut)
async def detalle_viaje(viaje_id: str, _user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(VIAJES_QUERY + "WHERE v.id = %s", (viaje_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Viaje no encontrado")
    return _map_row(row)


@router.post("/publicar", response_model=ViajeOut, status_code=status.HTTP_201_CREATED)
async def publicar_viaje(body: ViajePublicarRequest, current_user: dict = Depends(get_current_user)):
    """El conductor publica un nuevo viaje."""
    conn = get_db()
    cur = conn.cursor()

    # Marcar usuario como conductor automáticamente
    cur.execute(
        "UPDATE public.usuarios SET es_conductor = true WHERE id = %s",
        (current_user["sub"],)
    )

    # Obtener vehículo del conductor (si tiene)
    cur.execute(
        "SELECT id FROM public.vehiculos WHERE conductor_id = %s LIMIT 1",
        (current_user["sub"],)
    )
    veh = cur.fetchone()
    vehiculo_id = str(veh[0]) if veh else None

    # Insertar viaje
    cur.execute("""
        INSERT INTO public.viajes
          (conductor_id, vehiculo_id, destino, fecha_salida, hora_salida,
           precio_por_persona, asientos_disponibles, asientos_totales,
           punto_encuentro, duracion_estimada, estado)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'activo')
        RETURNING id
    """, (
        current_user["sub"], vehiculo_id, body.destino,
        body.fecha_salida, body.hora_salida,
        body.precio_por_persona, body.asientos_disponibles, body.asientos_disponibles,
        body.punto_encuentro, body.duracion_estimada
    ))
    viaje_id = cur.fetchone()[0]
    conn.commit()

    # Obtener viaje completo
    cur.execute(VIAJES_QUERY + "WHERE v.id = %s", (str(viaje_id),))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return _map_row(row)


@router.delete("/{viaje_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancelar_viaje(viaje_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE public.viajes SET estado='cancelado' WHERE id=%s AND conductor_id=%s",
        (viaje_id, current_user["sub"])
    )
    conn.commit()
    cur.close()
    conn.close()


@router.post("/vehiculos/registrar", response_model=VehiculoOut, status_code=status.HTTP_201_CREATED)
async def registrar_vehiculo(body: VehiculoCreate, current_user: dict = Depends(get_current_user)):
    sb = get_supabase()
    v_result = sb.table("vehiculos").insert({
        "conductor_id": current_user["sub"],
        "placa": body.placa.upper(),
        "marca": body.marca,
        "modelo": body.modelo,
        "anio": body.anio,
        "asientos_disponibles": body.asientos_disponibles,
        "verificado": False,
    }).execute()
    vehiculo = v_result.data[0]
    sb.table("usuarios").update({"es_conductor": True}).eq("id", current_user["sub"]).execute()
    return VehiculoOut(
        id=vehiculo["id"], placa=vehiculo["placa"], marca=vehiculo["marca"],
        modelo=vehiculo["modelo"], anio=vehiculo["anio"],
        asientos_disponibles=vehiculo["asientos_disponibles"],
        verificado=vehiculo["verificado"],
    )