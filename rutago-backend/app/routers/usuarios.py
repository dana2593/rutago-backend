from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.schemas import UserOut, UserUpdateRequest, MetodoPagoCreate, MetodoPagoOut
from app.core.security import get_current_user
from app.core.supabase import get_supabase

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.patch("/perfil", response_model=UserOut)
async def actualizar_perfil(body: UserUpdateRequest, current_user: dict = Depends(get_current_user)):
    """Actualiza nombre y/o teléfono del usuario autenticado."""
    sb = get_supabase()

    updates = {}
    if body.nombre_completo:
        updates["nombre_completo"] = body.nombre_completo
    if body.telefono:
        updates["telefono"] = body.telefono

    if not updates:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")

    result = (
        sb.table("usuarios")
        .update(updates)
        .eq("id", current_user["sub"])
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    u = result.data[0]
    return UserOut(
        id=u["id"],
        nombre_completo=u["nombre_completo"],
        email=u["email"],
        telefono=u.get("telefono"),
        rango=u["rango"],
        viajes_completados=u["viajes_completados"],
        valoracion_promedio=float(u["valoracion_promedio"]),
        es_conductor=u["es_conductor"],
    )


@router.get("/rango")
async def mi_rango(current_user: dict = Depends(get_current_user)):
    """Devuelve el rango actual y progreso hacia el siguiente nivel."""
    sb = get_supabase()
    result = (
        sb.table("usuarios")
        .select("rango, viajes_completados")
        .eq("id", current_user["sub"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    u = result.data
    rango = u["rango"]
    completados = u["viajes_completados"]

    # Calcular viajes necesarios para el siguiente rango
    if rango == "Nuevo":
        siguiente = "Frecuente"
        falta = max(0, 10 - completados)
    elif rango == "Frecuente":
        siguiente = "Elite"
        falta = max(0, 30 - completados)
    else:
        siguiente = None
        falta = 0

    return {
        "rango_actual": rango,
        "viajes_completados": completados,
        "siguiente_rango": siguiente,
        "viajes_para_siguiente": falta,
    }


# ── Métodos de pago ───────────────────────────────────────────────────────────

@router.get("/metodos-pago", response_model=list[MetodoPagoOut])
async def listar_metodos_pago(current_user: dict = Depends(get_current_user)):
    """Lista los métodos de pago guardados del usuario."""
    sb = get_supabase()
    result = (
        sb.table("metodos_pago")
        .select("*")
        .eq("usuario_id", current_user["sub"])
        .order("es_principal", desc=True)
        .execute()
    )
    return [
        MetodoPagoOut(
            id=m["id"],
            banco=m["banco"],
            alias=m.get("alias"),
            es_principal=m["es_principal"],
        )
        for m in result.data
    ]


@router.post("/metodos-pago", response_model=MetodoPagoOut, status_code=status.HTTP_201_CREATED)
async def agregar_metodo_pago(body: MetodoPagoCreate, current_user: dict = Depends(get_current_user)):
    """Agrega un nuevo método de pago al perfil del usuario."""
    sb = get_supabase()

    # Si es el primero, marcarlo como principal
    existing = (
        sb.table("metodos_pago")
        .select("id")
        .eq("usuario_id", current_user["sub"])
        .execute()
    )
    es_principal = len(existing.data) == 0

    result = (
        sb.table("metodos_pago")
        .insert(
            {
                "usuario_id": current_user["sub"],
                "banco": body.banco,
                "alias": body.alias,
                "es_principal": es_principal,
            }
        )
        .execute()
    )
    m = result.data[0]
    return MetodoPagoOut(
        id=m["id"],
        banco=m["banco"],
        alias=m.get("alias"),
        es_principal=m["es_principal"],
    )


@router.patch("/metodos-pago/{metodo_id}/principal")
async def establecer_principal(metodo_id: str, current_user: dict = Depends(get_current_user)):
    """Establece un método de pago como principal."""
    sb = get_supabase()

    # Quitar principal de todos
    sb.table("metodos_pago").update({"es_principal": False}).eq("usuario_id", current_user["sub"]).execute()

    # Establecer el nuevo
    result = (
        sb.table("metodos_pago")
        .update({"es_principal": True})
        .eq("id", metodo_id)
        .eq("usuario_id", current_user["sub"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Método de pago no encontrado")

    return {"mensaje": "Método de pago principal actualizado"}


@router.delete("/metodos-pago/{metodo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_metodo_pago(metodo_id: str, current_user: dict = Depends(get_current_user)):
    """Elimina un método de pago del perfil."""
    sb = get_supabase()
    sb.table("metodos_pago").delete().eq("id", metodo_id).eq("usuario_id", current_user["sub"]).execute()
