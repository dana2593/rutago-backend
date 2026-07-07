# RutaGo — Backend API

Backend distribuido de carpooling para Ecuador.  
**Proyecto integrador ISWZ2105 – Aplicaciones Distribuidas · UDLA**

## Stack tecnológico

| Componente | Herramienta |
|---|---|
| Framework | FastAPI (Python 3.12) |
| Base de datos | Supabase (PostgreSQL) |
| Auth / JWT | Supabase Auth + JWT propio |
| Asistente IA | OpenAI API (GPT-4o) |
| Despliegue | Azure Container Apps |
| CI/CD | GitHub Actions + ACR |

---

## Estructura del proyecto

```
rutago-backend/
├── app/
│   ├── main.py               # Aplicación FastAPI principal
│   ├── core/
│   │   ├── config.py         # Settings con pydantic-settings
│   │   ├── security.py       # JWT helpers y dependencia get_current_user
│   │   └── supabase.py       # Cliente Supabase singleton
│   ├── routers/
│   │   ├── auth.py           # POST /auth/register, /auth/login, /auth/me
│   │   ├── viajes.py         # GET/POST /viajes, /viajes/vehiculos/registrar
│   │   ├── reservas.py       # POST /reservas, PATCH /cancelar, POST /calificar
│   │   ├── usuarios.py       # PATCH /perfil, GET /rango, /metodos-pago
│   │   └── asistente.py      # POST /asistente (GPT-4o)
│   └── schemas/
│       └── schemas.py        # Todos los modelos Pydantic
├── supabase_schema.sql        # Schema completo + seed de datos
├── Dockerfile
├── requirements.txt
└── .github/workflows/deploy.yml
```

---

## Setup local

### 1. Crear proyecto en Supabase

1. Ir a [supabase.com](https://supabase.com) → New Project
2. En el SQL Editor, ejecutar `supabase_schema.sql` completo
3. Copiar las claves desde **Settings → API**

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus claves de Supabase y OpenAI
```

Variables requeridas:
```env
SUPABASE_URL=https://TU_PROJECT_ID.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
JWT_SECRET=TU_JWT_SECRET_DE_SUPABASE   # Settings → API → JWT Secret
OPENAI_API_KEY=sk-...                  # Opcional, activa el asistente IA real
```

### 3. Instalar y ejecutar

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API disponible en: `http://localhost:8000`  
Documentación interactiva: `http://localhost:8000/docs`

---

## Endpoints principales

### Autenticación
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/auth/register` | Crear cuenta nueva |
| POST | `/auth/login` | Iniciar sesión, recibe JWT |
| GET | `/auth/me` | Perfil del usuario autenticado |

### Viajes
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/viajes?destino=Guayas&fecha=2026-07-01&pasajeros=2` | Buscar viajes |
| GET | `/viajes/{id}` | Detalle de un viaje |
| POST | `/viajes` | Publicar viaje (conductor) |
| DELETE | `/viajes/{id}` | Cancelar viaje propio |
| GET | `/viajes/mis-viajes` | Viajes publicados por el conductor |
| POST | `/viajes/vehiculos/registrar` | Registrarse como conductor |

### Reservas
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/reservas` | Crear reserva (con locking optimista) |
| GET | `/reservas` | Mis reservas como pasajero |
| GET | `/reservas/conductor` | Reservas de mis viajes publicados |
| PATCH | `/reservas/{id}/cancelar` | Cancelar una reserva |
| POST | `/reservas/{id}/calificar` | Calificar al conductor (1–5 ⭐) |

### Usuarios
| Método | Ruta | Descripción |
|---|---|---|
| PATCH | `/usuarios/perfil` | Actualizar nombre/teléfono |
| GET | `/usuarios/rango` | Ver rango y progreso |
| GET | `/usuarios/metodos-pago` | Listar métodos de pago |
| POST | `/usuarios/metodos-pago` | Agregar método de pago |
| PATCH | `/usuarios/metodos-pago/{id}/principal` | Cambiar método principal |

### Asistente IA
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/asistente` | Chat con GPT-4o, extrae destino/fecha/pasajeros |

---

## Despliegue en Azure Container Apps

### Secrets necesarios en GitHub

```
ACR_LOGIN_SERVER        → acrrutago.azurecr.io
AZURE_CLIENT_ID         → App Registration Client ID
AZURE_TENANT_ID         → Tenant de tu organización
AZURE_SUBSCRIPTION_ID   → Subscription de Azure
```

### Variables de entorno en Container App

Configurar en Azure Portal → Container App → Secrets + Environment Variables:

```
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
JWT_SECRET
OPENAI_API_KEY
CORS_ORIGINS=https://tu-frontend.azurewebsites.net
```

### Crear el Container App (primera vez)

```bash
az group create --name rg-rutago-prod --location eastus2

az containerapp env create \
  --name env-rutago-prod \
  --resource-group rg-rutago-prod \
  --location eastus2

az containerapp create \
  --name ca-rutago-backend \
  --resource-group rg-rutago-prod \
  --environment env-rutago-prod \
  --image acrrutago.azurecr.io/rutago-backend:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 5
```

---

## Arquitectura distribuida (S5)

- **Locking optimista** en reservas: función SQL `reservar_asientos` con `SELECT ... WHERE asientos_disponibles >= n` + `UPDATE` atómico evita doble reserva del mismo cupo.
- **Realtime**: Supabase Realtime notifica a los clientes cuando cambia `asientos_disponibles` en un viaje.
- **RLS**: Row Level Security en todas las tablas — cada usuario solo accede a sus propios datos.
- **JWT**: Supabase Auth genera el token de autenticación; el backend lo valida sin estado (stateless).
- **Rangos**: Trigger SQL actualiza automáticamente el rango del usuario (`Nuevo → Frecuente → Elite`) al completar viajes.
