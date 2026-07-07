-- ================================================================
-- RutaGo — Schema SQL para Supabase (PostgreSQL)
-- Ejecutar en el SQL Editor de tu proyecto Supabase
-- ================================================================

-- Extensión para UUIDs
create extension if not exists "uuid-ossp";

-- ────────────────────────────────────────────────────────────────
-- 1. USUARIOS
-- ────────────────────────────────────────────────────────────────
create table if not exists public.usuarios (
  id                   uuid primary key default uuid_generate_v4(),
  auth_user_id         uuid unique,             -- referencia al auth.users de Supabase
  nombre_completo      text not null,
  email                text unique not null,
  telefono             text,
  rango                text not null default 'Nuevo'
                         check (rango in ('Nuevo', 'Frecuente', 'Elite')),
  viajes_completados   int  not null default 0,
  valoracion_promedio  numeric(3,2) not null default 0.00,
  es_conductor         boolean not null default false,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);

-- ────────────────────────────────────────────────────────────────
-- 2. VEHÍCULOS
-- ────────────────────────────────────────────────────────────────
create table if not exists public.vehiculos (
  id                   uuid primary key default uuid_generate_v4(),
  conductor_id         uuid not null references public.usuarios(id) on delete cascade,
  placa                text not null,
  marca                text not null,
  modelo               text not null,
  anio                 int  not null,
  asientos_disponibles int  not null default 3 check (asientos_disponibles between 1 and 6),
  verificado           boolean not null default false,
  created_at           timestamptz not null default now()
);

-- ────────────────────────────────────────────────────────────────
-- 3. RUTAS DEL CONDUCTOR (destinos que cubre)
-- ────────────────────────────────────────────────────────────────
create table if not exists public.conductor_rutas (
  id           uuid primary key default uuid_generate_v4(),
  conductor_id uuid not null references public.usuarios(id) on delete cascade,
  destino      text not null
);

-- ────────────────────────────────────────────────────────────────
-- 4. VIAJES
-- ────────────────────────────────────────────────────────────────
create table if not exists public.viajes (
  id                   uuid primary key default uuid_generate_v4(),
  conductor_id         uuid not null references public.usuarios(id),
  vehiculo_id          uuid references public.vehiculos(id),
  destino              text not null,
  fecha_salida         date not null,
  hora_salida          time not null,
  precio_por_persona   numeric(8,2) not null check (precio_por_persona > 0),
  asientos_disponibles int  not null check (asientos_disponibles >= 0),
  asientos_totales     int  not null,
  punto_encuentro      text not null,
  duracion_estimada    text not null,          -- "~7h"
  estado               text not null default 'activo'
                         check (estado in ('activo', 'completo', 'cancelado')),
  created_at           timestamptz not null default now()
);

-- ────────────────────────────────────────────────────────────────
-- 5. RESERVAS
-- ────────────────────────────────────────────────────────────────
create table if not exists public.reservas (
  id              uuid primary key default uuid_generate_v4(),
  codigo_reserva  text unique not null,          -- RG-XXXXX
  viaje_id        uuid not null references public.viajes(id),
  pasajero_id     uuid not null references public.usuarios(id),
  pasajeros       int  not null default 1 check (pasajeros between 1 and 4),
  metodo_pago     text not null
                    check (metodo_pago in ('pichincha','produbanco','guayaquil','efectivo')),
  total           numeric(8,2) not null,
  estado          text not null default 'confirmada'
                    check (estado in ('confirmada','cancelada','completada')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- ────────────────────────────────────────────────────────────────
-- 6. CALIFICACIONES
-- ────────────────────────────────────────────────────────────────
create table if not exists public.calificaciones (
  id           uuid primary key default uuid_generate_v4(),
  reserva_id   uuid not null unique references public.reservas(id),
  calificador  uuid not null references public.usuarios(id),   -- pasajero
  calificado   uuid not null references public.usuarios(id),   -- conductor
  puntuacion   int  not null check (puntuacion between 1 and 5),
  comentario   text,
  created_at   timestamptz not null default now()
);

-- ────────────────────────────────────────────────────────────────
-- 7. MÉTODOS DE PAGO (favoritos del usuario)
-- ────────────────────────────────────────────────────────────────
create table if not exists public.metodos_pago (
  id           uuid primary key default uuid_generate_v4(),
  usuario_id   uuid not null references public.usuarios(id) on delete cascade,
  banco        text not null,
  alias        text,
  es_principal boolean not null default false,
  created_at   timestamptz not null default now()
);

-- ────────────────────────────────────────────────────────────────
-- 8. TRIGGER — actualizar updated_at automáticamente
-- ────────────────────────────────────────────────────────────────
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace trigger usuarios_updated_at
  before update on public.usuarios
  for each row execute function public.set_updated_at();

create or replace trigger reservas_updated_at
  before update on public.reservas
  for each row execute function public.set_updated_at();

-- ────────────────────────────────────────────────────────────────
-- 9. FUNCIÓN — descuento de asientos con locking optimista
--    Evita doble reserva del mismo cupo (control de concurrencia S5)
-- ────────────────────────────────────────────────────────────────
create or replace function public.reservar_asientos(
  p_viaje_id  uuid,
  p_pasajeros int
)
returns void language plpgsql as $$
begin
  update public.viajes
  set    asientos_disponibles = asientos_disponibles - p_pasajeros
  where  id = p_viaje_id
    and  asientos_disponibles >= p_pasajeros
    and  estado = 'activo';

  if not found then
    raise exception 'Sin asientos disponibles o viaje no activo';
  end if;
end;
$$;

-- ────────────────────────────────────────────────────────────────
-- 10. FUNCIÓN — recalcular valoración promedio del conductor
-- ────────────────────────────────────────────────────────────────
create or replace function public.recalcular_valoracion()
returns trigger language plpgsql as $$
begin
  update public.usuarios
  set    valoracion_promedio = (
           select round(avg(puntuacion)::numeric, 2)
           from   public.calificaciones
           where  calificado = new.calificado
         )
  where  id = new.calificado;
  return new;
end;
$$;

create or replace trigger after_calificacion
  after insert on public.calificaciones
  for each row execute function public.recalcular_valoracion();

-- ────────────────────────────────────────────────────────────────
-- 11. FUNCIÓN — actualizar rango según viajes completados
-- ────────────────────────────────────────────────────────────────
create or replace function public.actualizar_rango()
returns trigger language plpgsql as $$
begin
  update public.usuarios
  set rango = case
    when viajes_completados >= 30 then 'Elite'
    when viajes_completados >= 10 then 'Frecuente'
    else 'Nuevo'
  end
  where id = new.pasajero_id;
  return new;
end;
$$;

create or replace trigger after_reserva_completada
  after update of estado on public.reservas
  for each row
  when (new.estado = 'completada' and old.estado != 'completada')
  execute function public.actualizar_rango();

-- ────────────────────────────────────────────────────────────────
-- 12. ROW LEVEL SECURITY (básico)
-- ────────────────────────────────────────────────────────────────
alter table public.usuarios enable row level security;
alter table public.viajes   enable row level security;
alter table public.reservas enable row level security;
alter table public.calificaciones enable row level security;
alter table public.metodos_pago enable row level security;
alter table public.vehiculos enable row level security;

-- Usuarios: cada uno ve su propio registro
create policy "usuario_propio" on public.usuarios
  for all using (auth.uid() = auth_user_id);

-- Viajes: todos los usuarios autenticados pueden ver viajes activos
create policy "viajes_lectura" on public.viajes
  for select using (auth.role() = 'authenticated');

-- Conductores gestionan sus propios viajes
create policy "viajes_conductor" on public.viajes
  for all using (
    conductor_id in (
      select id from public.usuarios where auth_user_id = auth.uid()
    )
  );

-- Reservas: el pasajero ve las suyas
create policy "reservas_pasajero" on public.reservas
  for all using (
    pasajero_id in (
      select id from public.usuarios where auth_user_id = auth.uid()
    )
  );

-- El conductor puede ver reservas de sus viajes
create policy "reservas_conductor" on public.reservas
  for select using (
    viaje_id in (
      select v.id from public.viajes v
      join public.usuarios u on u.id = v.conductor_id
      where u.auth_user_id = auth.uid()
    )
  );

-- ────────────────────────────────────────────────────────────────
-- 13. DATOS DE PRUEBA (seed)
-- ────────────────────────────────────────────────────────────────
-- Insertar conductores de ejemplo (sin auth_user_id para seed)
insert into public.usuarios (nombre_completo, email, rango, viajes_completados, valoracion_promedio, es_conductor)
values
  ('Gallardo Ruales',  'gallardo@rutago.ec',  'Elite',      38, 4.90, true),
  ('Ricardo Vásquez',  'ricardo@rutago.ec',   'Frecuente',  21, 4.70, true),
  ('Marco Delgado',    'marco@rutago.ec',     'Elite',      55, 4.80, true),
  ('Sofía Andrade',    'sofia@rutago.ec',     'Elite',      72, 5.00, true),
  ('Carlos Méndez',    'carlos@rutago.ec',    'Frecuente',  18, 4.60, true)
on conflict (email) do nothing;

-- Vehículos de los conductores seed
insert into public.vehiculos (conductor_id, placa, marca, modelo, anio, asientos_disponibles, verificado)
select id, 'ABC-1234', 'Kia', 'Picanto', 2022, 3, true
from public.usuarios where email = 'gallardo@rutago.ec'
on conflict do nothing;

insert into public.vehiculos (conductor_id, placa, marca, modelo, anio, asientos_disponibles, verificado)
select id, 'XYZ-5678', 'Chevrolet', 'Aveo', 2021, 3, true
from public.usuarios where email = 'ricardo@rutago.ec'
on conflict do nothing;

insert into public.vehiculos (conductor_id, placa, marca, modelo, anio, asientos_disponibles, verificado)
select id, 'GHI-9012', 'Hyundai', 'i10', 2023, 4, true
from public.usuarios where email = 'marco@rutago.ec'
on conflict do nothing;

-- Viajes de ejemplo (fecha dinámica: mañana)
insert into public.viajes
  (conductor_id, vehiculo_id, destino, fecha_salida, hora_salida,
   precio_por_persona, asientos_disponibles, asientos_totales, punto_encuentro, duracion_estimada)
select
  u.id, v.id, 'Guayas', current_date + 1, '06:00',
  10.00, 2, 3, 'Parqueadero UDLA Park', '~7h'
from public.usuarios u
join public.vehiculos v on v.conductor_id = u.id
where u.email = 'gallardo@rutago.ec'
on conflict do nothing;

insert into public.viajes
  (conductor_id, vehiculo_id, destino, fecha_salida, hora_salida,
   precio_por_persona, asientos_disponibles, asientos_totales, punto_encuentro, duracion_estimada)
select
  u.id, v.id, 'Guayas', current_date + 1, '07:30',
  12.00, 3, 3, 'Av. América y Naciones Unidas', '~7h'
from public.usuarios u
join public.vehiculos v on v.conductor_id = u.id
where u.email = 'ricardo@rutago.ec'
on conflict do nothing;

insert into public.viajes
  (conductor_id, vehiculo_id, destino, fecha_salida, hora_salida,
   precio_por_persona, asientos_disponibles, asientos_totales, punto_encuentro, duracion_estimada)
select
  u.id, v.id, 'Cuenca', current_date + 1, '05:00',
  15.00, 3, 4, 'La Y - Quito Norte', '~4h'
from public.usuarios u
join public.vehiculos v on v.conductor_id = u.id
where u.email = 'marco@rutago.ec'
on conflict do nothing;
