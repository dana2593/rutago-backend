from __future__ import annotations
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Literal
from datetime import date, time
from uuid import UUID


# ─────────────────────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    nombre_completo: str
    email: EmailStr
    telefono: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ─────────────────────────────────────────────────────────────
#  USUARIOS
# ─────────────────────────────────────────────────────────────
class UserOut(BaseModel):
    id: str
    nombre_completo: str
    email: str
    telefono: Optional[str] = None
    rango: str = "Nuevo"
    viajes_completados: int = 0
    valoracion_promedio: float = 0.0
    es_conductor: bool = False


class UserUpdateRequest(BaseModel):
    nombre_completo: Optional[str] = None
    telefono: Optional[str] = None


# ─────────────────────────────────────────────────────────────
#  VEHÍCULOS
# ─────────────────────────────────────────────────────────────
class VehiculoCreate(BaseModel):
    placa: str
    marca: str
    modelo: str
    anio: int
    asientos_disponibles: int
    rutas: list[str]  # destinos que cubre el conductor


class VehiculoOut(BaseModel):
    id: str
    placa: str
    marca: str
    modelo: str
    anio: int
    asientos_disponibles: int
    verificado: bool


# ─────────────────────────────────────────────────────────────
#  VIAJES
# ─────────────────────────────────────────────────────────────
class ViajeCreate(BaseModel):
    destino: str
    fecha_salida: date
    hora_salida: str          # "06:00"
    precio_por_persona: float
    asientos_disponibles: int
    punto_encuentro: str
    duracion_estimada: str    # "~7h"


class ViajeOut(BaseModel):
    id: str
    conductor_id: str
    conductor_nombre: str
    conductor_valoracion: float
    conductor_viajes: int
    conductor_rango: Optional[str]
    vehiculo_placa: str
    vehiculo_descripcion: str   # "Kia Picanto"
    destino: str
    fecha_salida: str
    hora_salida: str
    precio_por_persona: float
    asientos_disponibles: int
    punto_encuentro: str
    duracion_estimada: str


class ViajeSearchParams(BaseModel):
    destino: str
    fecha: date
    pasajeros: int = 1
    orden: Literal["precio", "hora", "valoracion"] = "precio"


# ─────────────────────────────────────────────────────────────
#  RESERVAS
# ─────────────────────────────────────────────────────────────
class ReservaCreate(BaseModel):
    viaje_id: str
    pasajeros: int
    metodo_pago: Literal["pichincha", "produbanco", "guayaquil", "efectivo"]


class ReservaOut(BaseModel):
    id: str
    codigo_reserva: str      # RG-XXXXX
    viaje_id: str
    pasajero_id: str
    pasajeros: int
    metodo_pago: str
    total: float
    estado: str              # confirmada | cancelada
    conductor_nombre: str
    ruta: str
    fecha_hora: str
    punto_encuentro: str


class ReservaCancelRequest(BaseModel):
    motivo: Optional[str] = None


# ─────────────────────────────────────────────────────────────
#  CALIFICACIONES
# ─────────────────────────────────────────────────────────────
class CalificacionCreate(BaseModel):
    reserva_id: str
    puntuacion: int           # 1–5
    comentario: Optional[str] = None

    @field_validator("puntuacion")
    @classmethod
    def puntuacion_rango(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("La puntuación debe estar entre 1 y 5")
        return v


# ─────────────────────────────────────────────────────────────
#  MÉTODOS DE PAGO
# ─────────────────────────────────────────────────────────────
class MetodoPagoCreate(BaseModel):
    banco: str
    alias: Optional[str] = None


class MetodoPagoOut(BaseModel):
    id: str
    banco: str
    alias: Optional[str]
    es_principal: bool


# ─────────────────────────────────────────────────────────────
#  ASISTENTE IA
# ─────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    mensaje: str


class ChatResponse(BaseModel):
    respuesta: str
    accion: Optional[str] = None          # "buscar_viaje" | None
    params: Optional[dict] = None         # destino, fecha, pasajeros extraídos
