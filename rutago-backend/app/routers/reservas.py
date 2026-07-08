import random
import string
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.schemas import ReservaCreate, ReservaOut, ReservaCancelRequest, CalificacionCreate
from app.core.security import get_current_user
from app.core.supabase import get_supabase

router = APIRouter(prefix="/reservas", tags=["Reservas"])


def _generar_codigo() -> str:
    """Genera un código de reserva tipo RG-XXXXX."""
    return "RG-" + "".join(random.choices(string.digits, k=5))


def _map_reserva(row: dict, viaje: dict, conductor_nombre: str) -> ReservaOut:
    return ReservaOut(
        id=row["id"],
        codigo_reserva=row["codigo_reserva"],
        viaje_id=row["viaje_id"],
        pasajero_id=row["pasajero_id"],
        pasajeros=row["pasajeros"],
        metodo_pago=row["metodo_pago"],
        total=float(row["total"]),
        estado=row["estado"],
        conductor_nombre=conductor_nombre,
        ruta=f"Quito - {viaje['destino']}",
        fecha_hora=f"{viaje['fecha_salida']} · {str(viaje['hora_salida'])[:5]}",
        punto_encuentro=viaje["punto_encuentro"],
    )


@router.post("", response_model=ReservaOut, status_code=status.HTTP_201_CREATED)
async def crear_reserva(body: ReservaCreate, current_user: dict = Depends(get_current_user)):
    """
    Crea una reserva para un viaje.
    Usa la función SQL `reservar_asientos` para el locking optimista
    y evitar doble reserva del mismo cupo (S5).
    """
    sb = get_supabase()

    # 1) Obtener viaje y conductor
    viaje_result = (
        sb.table("viajes")
        .select("*, usuarios(nombre_completo)")
        .eq("id", body.viaje_id)
        .maybe_single()
        .execute()
    )
    if not viaje_result.data:
        raise HTTPException(status_code=404, detail="Viaje no encontrado")

    viaje = viaje_result.data
    conductor_nombre = (viaje.get("usuarios") or {}).get("nombre_completo", "")

    # 2) Verificar que el pasajero no sea el mismo conductor
    if viaje["conductor_id"] == current_user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes reservar tu propio viaje",
        )

    # 3) Calcular total
    total = float(viaje["precio_por_persona"]) * body.pasajeros

    # 4) Descontar asientos con locking optimista vía función SQL
    try:
        sb.rpc("reservar_asientos", {"p_viaje_id": body.viaje_id, "p_pasajeros": body.pasajeros}).execute()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay suficientes asientos disponibles",
        )

    # 5) Insertar reserva
    codigo = _generar_codigo()
    reserva_result = (
        sb.table("reservas")
        .insert(
            {
                "codigo_reserva": codigo,
                "viaje_id": body.viaje_id,
                "pasajero_id": current_user["sub"],
                "pasajeros": body.pasajeros,
                "metodo_pago": body.metodo_pago,
                "total": total,
                "estado": "confirmada",
            }
        )
        .execute()
    )

    reserva = reserva_result.data[0]
    return _map_reserva(reserva, viaje, conductor_nombre)


@router.get("", response_model=list[ReservaOut])
async def mis_reservas(current_user: dict = Depends(get_current_user)):
    """Lista todas las reservas del pasajero autenticado."""
    sb = get_supabase()

    result = (
        sb.table("reservas")
        .select("*, viajes(destino, fecha_salida, hora_salida, punto_encuentro, conductor_id, usuarios(nombre_completo))")
        .eq("pasajero_id", current_user["sub"])
        .order("created_at", desc=True)
        .execute()
    )

    reservas = []
    for row in result.data:
        viaje = row.get("viajes") or {}
        conductor_data = viaje.get("usuarios") or {}
        conductor_nombre = conductor_data.get("nombre_completo", "")
        reservas.append(_map_reserva(row, viaje, conductor_nombre))
    return reservas


@router.get("/conductor", response_model=list[ReservaOut])
async def reservas_de_mis_viajes(current_user: dict = Depends(get_current_user)):
    """Lista todas las reservas de los viajes publicados por el conductor."""
    sb = get_supabase()

    # Obtener IDs de viajes del conductor
    viajes_result = (
        sb.table("viajes")
        .select("id, destino, fecha_salida, hora_salida, punto_encuentro, conductor_id")
        .eq("conductor_id", current_user["sub"])
        .execute()
    )
    viaje_ids = [v["id"] for v in viajes_result.data]
    viaje_map = {v["id"]: v for v in viajes_result.data}

    if not viaje_ids:
        return []

    reservas_result = (
        sb.table("reservas")
        .select("*, usuarios(nombre_completo)")
        .in_("viaje_id", viaje_ids)
        .order("created_at", desc=True)
        .execute()
    )

    return [
        _map_reserva(row, viaje_map.get(row["viaje_id"], {}), current_user.get("sub", ""))
        for row in reservas_result.data
    ]


@router.get("/{reserva_id}", response_model=ReservaOut)
async def detalle_reserva(reserva_id: str, current_user: dict = Depends(get_current_user)):
    sb = get_supabase()
    result = (
        sb.table("reservas")
        .select("*, viajes(destino, fecha_salida, hora_salida, punto_encuentro, usuarios(nombre_completo))")
        .eq("id", reserva_id)
        .eq("pasajero_id", current_user["sub"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    row = result.data
    viaje = row.get("viajes") or {}
    conductor_nombre = (viaje.get("usuarios") or {}).get("nombre_completo", "")
    return _map_reserva(row, viaje, conductor_nombre)


@router.patch("/{reserva_id}/cancelar", response_model=ReservaOut)
async def cancelar_reserva(
    reserva_id: str,
    body: ReservaCancelRequest,
    current_user: dict = Depends(get_current_user),
):
    """Cancela una reserva y devuelve los asientos al viaje."""
    sb = get_supabase()

    # Obtener la reserva
    result = (
        sb.table("reservas")
        .select("*, viajes(destino, fecha_salida, hora_salida, punto_encuentro, usuarios(nombre_completo))")
        .eq("id", reserva_id)
        .eq("pasajero_id", current_user["sub"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    reserva = result.data
    if reserva["estado"] != "confirmada":
        raise HTTPException(status_code=400, detail="Solo se pueden cancelar reservas confirmadas")

    # Devolver asientos al viaje
    sb.table("viajes").update(
        {"asientos_disponibles": sb.table("viajes").select("asientos_disponibles")
         .eq("id", reserva["viaje_id"]).single().execute().data["asientos_disponibles"] + reserva["pasajeros"]}
    ).eq("id", reserva["viaje_id"]).execute()

    # Cancelar reserva
    upd = (
        sb.table("reservas")
        .update({"estado": "cancelada"})
        .eq("id", reserva_id)
        .execute()
    )

    viaje = reserva.get("viajes") or {}
    conductor_nombre = (viaje.get("usuarios") or {}).get("nombre_completo", "")
    return _map_reserva(upd.data[0], viaje, conductor_nombre)


@router.post("/{reserva_id}/calificar", status_code=status.HTTP_201_CREATED)
async def calificar_conductor(
    reserva_id: str,
    body: CalificacionCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    El pasajero califica al conductor después de completar el viaje.
    Dispara el trigger que recalcula la valoración promedio del conductor.
    """
    sb = get_supabase()

    # Verificar que la reserva pertenece al usuario y está completada
    reserva = (
        sb.table("reservas")
        .select("*, viajes(conductor_id)")
        .eq("id", reserva_id)
        .eq("pasajero_id", current_user["sub"])
        .single()
        .execute()
    )
    if not reserva.data:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    if reserva.data["estado"] != "completada":
        raise HTTPException(status_code=400, detail="Solo puedes calificar viajes completados")

    conductor_id = reserva.data["viajes"]["conductor_id"]

    try:
        sb.table("calificaciones").insert(
            {
                "reserva_id": reserva_id,
                "calificador": current_user["sub"],
                "calificado": conductor_id,
                "puntuacion": body.puntuacion,
                "comentario": body.comentario,
            }
        ).execute()
    except Exception:
        raise HTTPException(status_code=400, detail="Ya calificaste este viaje")

    return {"mensaje": "Calificación registrada correctamente"}