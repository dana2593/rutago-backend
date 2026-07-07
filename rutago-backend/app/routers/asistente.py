from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI
import json
from datetime import date, timedelta

from app.schemas.schemas import ChatMessage, ChatResponse
from app.core.security import get_current_user
from app.core.config import get_settings

router = APIRouter(prefix="/asistente", tags=["Asistente IA"])

SYSTEM_PROMPT = """Eres el asistente de RutaGo, una app de carpooling en Ecuador.
Tu rol es ayudar a los usuarios a buscar viajes en lenguaje natural.

Cuando el usuario mencione un viaje, extrae:
- destino: ciudad de destino (Guayas, Cuenca, Manta, UDLA, etc.)
- fecha: fecha de salida en formato YYYY-MM-DD (si dice "hoy", "mañana", "este viernes", etc., calcula la fecha)
- pasajeros: número de personas (default 1)

Responde SIEMPRE en JSON con esta estructura exacta:
{
  "respuesta": "mensaje amigable para el usuario",
  "accion": "buscar_viaje" o null,
  "params": {"destino": "...", "fecha": "YYYY-MM-DD", "pasajeros": 1} o null
}

Si el usuario no menciona un viaje concreto (saluda, pregunta otra cosa), pon accion: null y params: null.
Sé conciso, amigable y en español.
Hoy es: """ + str(date.today())


@router.post("", response_model=ChatResponse)
async def chat_asistente(body: ChatMessage, current_user: dict = Depends(get_current_user)):
    """
    Asistente conversacional con GPT-4o.
    Interpreta la solicitud del usuario en lenguaje natural,
    extrae destino/fecha/pasajeros y devuelve la acción a ejecutar en el frontend.
    """
    settings = get_settings()

    if not settings.openai_api_key:
        # Fallback sin OpenAI: respuesta por palabras clave
        return _fallback_reply(body.mensaje)

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        completion = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": body.mensaje},
            ],
            max_tokens=300,
            temperature=0.3,
        )

        raw = completion.choices[0].message.content
        data = json.loads(raw)

        return ChatResponse(
            respuesta=data.get("respuesta", ""),
            accion=data.get("accion"),
            params=data.get("params"),
        )

    except Exception as e:
        # Si falla OpenAI, usar fallback
        return _fallback_reply(body.mensaje)


def _fallback_reply(mensaje: str) -> ChatResponse:
    """
    Respuesta por palabras clave cuando OpenAI no está disponible.
    Replica la lógica del prototipo HTML.
    """
    m = mensaje.lower()
    today = date.today()
    tomorrow = today + timedelta(days=1)

    DESTINOS = {
        "guayaquil": "Guayas",
        "guayas": "Guayas",
        "cuenca": "Cuenca",
        "manta": "Manta",
        "udla": "UDLA Park",
        "universidad": "UDLA Park",
        "ambato": "Ambato",
        "esmeraldas": "Esmeraldas",
        "loja": "Loja",
    }

    destino_encontrado = None
    for kw, dest in DESTINOS.items():
        if kw in m:
            destino_encontrado = dest
            break

    # Detectar fecha
    fecha = str(tomorrow)
    if "hoy" in m:
        fecha = str(today)
    elif "mañana" in m:
        fecha = str(tomorrow)

    # Detectar pasajeros
    pasajeros = 1
    for n, w in [(2, "dos"), (3, "tres"), (4, "cuatro"), (2, "2"), (3, "3"), (4, "4")]:
        if w in m:
            pasajeros = n
            break

    if destino_encontrado:
        return ChatResponse(
            respuesta=f"¡Perfecto! Busco viajes a *{destino_encontrado}* para {pasajeros} pasajero(s) el {fecha}. ¿Lo muestro?",
            accion="buscar_viaje",
            params={"destino": destino_encontrado, "fecha": fecha, "pasajeros": pasajeros},
        )

    if any(w in m for w in ["hola", "buenas", "hey", "buen"]):
        return ChatResponse(
            respuesta="¡Hola! Soy tu asistente RutaGo 🚗 ¿A dónde necesitas viajar? Por ejemplo: *necesito ir a Guayaquil mañana para 2 personas*",
            accion=None,
            params=None,
        )

    if any(w in m for w in ["barato", "económico", "precio", "más barato"]):
        return ChatResponse(
            respuesta="Los viajes más económicos de hoy:\n• Guayas: desde $9\n• UDLA Park: desde $3\n• Cuenca: desde $15\n\n¿A cuál te dirijo?",
            accion=None,
            params=None,
        )

    return ChatResponse(
        respuesta=f"No encontré un destino específico en tu mensaje. ¿Puedes decirme a dónde quieres viajar? Por ejemplo: *quiero ir a Cuenca este viernes*",
        accion=None,
        params=None,
    )
