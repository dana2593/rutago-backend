from fastapi import APIRouter, HTTPException, status, Depends
from app.schemas.schemas import RegisterRequest, LoginRequest, TokenResponse, UserOut
from app.core.supabase import get_supabase
from app.core.security import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    """
    Registra un nuevo usuario mediante Supabase Auth y crea
    su perfil en la tabla public.usuarios.
    """
    sb = get_supabase()

    # 1) Crear cuenta en Supabase Auth
    try:
        auth_resp = sb.auth.sign_up(
            {"email": body.email, "password": body.password}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al crear cuenta: {str(e)}")

    if not auth_resp.user:
        raise HTTPException(status_code=400, detail="No se pudo crear el usuario")

    auth_uid = str(auth_resp.user.id)

    # 2) Insertar perfil en tabla usuarios
    try:
        result = (
            sb.table("usuarios")
            .insert(
                {
                    "auth_user_id": auth_uid,
                    "nombre_completo": body.nombre_completo,
                    "email": body.email,
                    "telefono": body.telefono,
                    "rango": "Nuevo",
                    "viajes_completados": 0,
                    "valoracion_promedio": 0.0,
                    "es_conductor": False,
                }
            )
            .execute()
        )
        usuario = result.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar perfil: {str(e)}")

    user_out = UserOut(
        id=usuario["id"],
        nombre_completo=usuario["nombre_completo"],
        email=usuario["email"],
        telefono=usuario.get("telefono"),
        rango=usuario["rango"],
        viajes_completados=usuario["viajes_completados"],
        valoracion_promedio=float(usuario["valoracion_promedio"]),
        es_conductor=usuario["es_conductor"],
    )

    token = create_access_token(
        {"sub": usuario["id"], "email": body.email, "rango": usuario["rango"]}
    )

    return TokenResponse(access_token=token, user=user_out)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """
    Autentica al usuario con Supabase Auth y devuelve el JWT propio.
    """
    sb = get_supabase()

    # 1) Verificar credenciales con Supabase Auth
    try:
        auth_resp = sb.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    if not auth_resp.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    auth_uid = str(auth_resp.user.id)

    # 2) Obtener perfil del usuario
    result = (
        sb.table("usuarios")
        .select("*")
        .eq("auth_user_id", auth_uid)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Perfil de usuario no encontrado")

    usuario = result.data
    user_out = UserOut(
        id=usuario["id"],
        nombre_completo=usuario["nombre_completo"],
        email=usuario["email"],
        telefono=usuario.get("telefono"),
        rango=usuario["rango"],
        viajes_completados=usuario["viajes_completados"],
        valoracion_promedio=float(usuario["valoracion_promedio"]),
        es_conductor=usuario["es_conductor"],
    )

    token = create_access_token(
        {"sub": usuario["id"], "email": body.email, "rango": usuario["rango"]}
    )

    return TokenResponse(access_token=token, user=user_out)


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    """Devuelve el perfil del usuario autenticado."""
    sb = get_supabase()
    result = (
        sb.table("usuarios")
        .select("*")
        .eq("id", current_user["sub"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    u = result.data
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
