-- ════════════════════════════════════════════════════════════════════════════
-- 21 · `pacs.fichas_ia` y el paquete de evidencia como función
-- ════════════════════════════════════════════════════════════════════════════
--
-- ⚠ NO APLICADA. Se reporta antes, y la aplica Isabella con su OK.
--
-- Qué cambia de enfoque
-- ---------------------
-- Hasta ahora el código intentaba REDACTAR: razones, dolores, mensajes. Cada
-- caso nuevo terminaba en otra regla y la pantalla no llegaba al nivel de la
-- maqueta. A partir de aquí la app captura, decide y muestra; la redacción la
-- hace Cowork y **la app la valida al leer**.
--
-- Lo que NO cambia: una IA nunca decide la exclusión ni el veredicto. Esos
-- llegan calculados en el paquete, con su id, y la ficha solo los muestra.
--
-- Las dos piezas
-- --------------
--   1 · `pacs.paquete_ficha(realtor_id)` -- de solo lectura, para que Cowork
--       lea por SQL todo lo que se sabe del realtor con un id por hecho;
--   2 · `pacs.fichas_ia` -- append-only, donde Cowork escribe la ficha.
--
-- Por qué el paquete es una FUNCIÓN y no una vista materializada
-- --------------------------------------------------------------
-- Porque se arma en Python: `motor/paquete.py` junta Model Match, Instagram,
-- contactos, mercados y las activaciones PACS-H, y aplica la lista blanca de
-- campos. Reimplementar eso en SQL sería tener dos versiones de la misma regla
-- -- y el día que difieran, Cowork leería una cosa y la app validaría contra
-- otra.
--
-- Así que la función es una fachada delgada sobre lo que la app YA calculó y
-- dejó guardado, y el que lo calcula sigue siendo el mismo módulo con pruebas.

create table if not exists pacs.paquetes_ficha (
    id              uuid primary key default gen_random_uuid(),
    realtor_id      uuid not null references pacs.realtors(id),
    generado_en     timestamptz not null default now(),
    version_paquete text not null,
    hash_paquete    text not null,
    paquete         jsonb not null,

    -- La guarda redundante, otra vez. `motor/paquete.py` usa lista blanca y no
    -- mete nada de esto; esto es la segunda vuelta, en la base, y es la que
    -- falla ruidosamente si la primera se rompe.
    constraint paquete_sin_pii check (
        not (paquete::text ilike '%marcadores_culturales%')
        and not (paquete::text ilike '%barrios_mencionados%')
        and not (paquete::text ilike '%"buyers"%')
        and not (paquete::text ilike '%"sellers"%')),

    -- UN PAQUETE POR CONTENIDO, no por vez que alguien corra el generador.
    --
    -- La tabla es append-only, pero «append-only» no quiere decir «guardar lo
    -- mismo otra vez»: el hash ES el contenido, así que dos filas con el mismo
    -- hash son la misma evidencia contada dos veces. Y el conteo importa: la
    -- ficha dice contra qué paquete se escribió, y con duplicados no se sabe
    -- cuál de los dos.
    --
    -- El generador además no llega hasta aquí: comprueba el hash antes y se
    -- salta al realtor, para poder decir «sin cambios» en vez de un 409.
    constraint paquete_uno_por_contenido unique (realtor_id, hash_paquete)
);

create index if not exists paquete_por_realtor
    on pacs.paquetes_ficha (realtor_id, generado_en desc);
create index if not exists paquete_por_hash
    on pacs.paquetes_ficha (hash_paquete);

comment on table pacs.paquetes_ficha is
'Todo lo que se sabe del realtor, con un id estable por hecho. Lo escribe la
app; Cowork lo LEE para redactar la ficha y cita esos ids. Sin nombres de
buyers ni sellers, sin calles, sin marcadores de origen.';


-- ── La ficha redactada ─────────────────────────────────────────────────────
create table if not exists pacs.fichas_ia (
    id              uuid primary key default gen_random_uuid(),
    realtor_id      uuid not null references pacs.realtors(id),
    generada_en     timestamptz not null default now(),
    generada_por    text not null default 'cowork',
    version_prompt  text not null,
    -- Contra QUÉ paquete se escribió. Si el hash actual del realtor ya no
    -- coincide, la pantalla dice «hay datos nuevos: ficha pendiente de
    -- actualizar» y sigue mostrando esta. Una ficha vieja bien marcada es útil;
    -- una ficha vieja sin marcar es una mentira con fecha.
    hash_paquete    text not null,
    json            jsonb not null,
    -- Lo que dio el validador que Cowork corrió ANTES de escribir. No sustituye
    -- a la validación de la app: la app vuelve a validar al leer, porque una
    -- validación que solo corre del lado del que produce el texto es una
    -- promesa, no una guarda.
    validacion      jsonb not null default '[]'::jsonb,

    constraint ficha_solo_campos_ia check (
        not (json ? 'veredicto') and not (json ? 'salesforce')
        and not (json ? 'fuentes')),
    constraint ficha_sin_pii check (
        not (json::text ilike '%marcadores_culturales%')
        and not (json::text ilike '%barrios_mencionados%'))
);

create index if not exists ficha_ia_por_realtor
    on pacs.fichas_ia (realtor_id, generada_en desc);

comment on table pacs.fichas_ia is
'La ficha redactada por Cowork. Append-only. Solo los campos `escribe: ia` del
esquema: el veredicto y la exclusión los calcula el código y la IA no los toca.';

comment on column pacs.fichas_ia.hash_paquete is
'El paquete contra el que se escribió. Si no coincide con el actual, la ficha
se muestra marcada como pendiente de actualizar, no se oculta.';


-- ── La cola de lo que hay que redactar ─────────────────────────────────────
--
-- El botón «Pedir actualización» de la pantalla escribe aquí. Es una cola y no
-- una columna en `realtors` porque se pide varias veces y hay que poder ver
-- quién lo pidió y cuándo.
create table if not exists pacs.fichas_ia_pendientes (
    id              uuid primary key default gen_random_uuid(),
    realtor_id      uuid not null references pacs.realtors(id),
    pedida_en       timestamptz not null default now(),
    pedida_por      text,
    motivo          text,
    hash_paquete    text,
    atendida_en     timestamptz
);

create index if not exists ficha_pendiente_abierta
    on pacs.fichas_ia_pendientes (realtor_id) where atendida_en is null;

comment on table pacs.fichas_ia_pendientes is
'Cola de realtors a los que hay que (re)escribirles la ficha. La llena el botón
«Pedir actualización»; Cowork la lee y marca `atendida_en`.';


-- ── Las vistas de lo vigente ───────────────────────────────────────────────
--
-- Columnas una por una y no `select *`: en Postgres un `select *` congela la
-- lista de columnas al crear la vista, así que una columna nueva no aparece
-- nunca y nadie se entera.
--
-- `security_invoker = true` EN LAS DOS, y es la parte que importa
-- --------------------------------------------------------------
-- Por defecto una vista corre con los permisos de su OWNER, así que se salta
-- la RLS de las tablas que lee. Hoy no cambia nada --las políticas son
-- `using (true)`-- pero el día que se cierren con `allowed_apps ? 'prospector'`
-- (PR de autenticación, migración 17) las tablas quedarían cerradas y las
-- vistas seguirían abiertas: una puerta cerrada al lado de una ventana.
--
-- Y sería una ventana invisible, porque la verificación de la migración de
-- auth va a probar las TABLAS. Se pone ahora, que es cuando se ve.
create or replace view pacs.v_ficha_ia_actual
with (security_invoker = true) as
select distinct on (f.realtor_id)
    f.id, f.realtor_id, f.generada_en, f.generada_por, f.version_prompt,
    f.hash_paquete, f.json, f.validacion
from pacs.fichas_ia f
order by f.realtor_id, f.generada_en desc;

create or replace view pacs.v_paquete_ficha
with (security_invoker = true) as
select distinct on (p.realtor_id)
    p.id, p.realtor_id, p.generado_en, p.version_paquete, p.hash_paquete,
    p.paquete
from pacs.paquetes_ficha p
order by p.realtor_id, p.generado_en desc;

comment on view pacs.v_paquete_ficha is
'El paquete más nuevo por realtor. Es lo que Cowork lee para redactar.';


-- `pacs.paquete_ficha(realtor_id)`: la fachada para leer por SQL sin conocer
-- la vista. Devuelve el jsonb, o null si la app todavía no lo generó -- y null
-- es la respuesta correcta: significa «este realtor no está listo para
-- redactar», no «no tiene datos».
-- `security invoker` explícito aunque sea el valor por defecto de las
-- funciones: al lado de dos vistas donde SÍ hay que declararlo, el silencio se
-- lee como olvido.
create or replace function pacs.paquete_ficha(p_realtor_id uuid)
returns jsonb
language sql
stable
security invoker
as $$
    select v.paquete from pacs.v_paquete_ficha v
     where v.realtor_id = p_realtor_id
$$;

comment on function pacs.paquete_ficha(uuid) is
'El paquete de evidencia del realtor, con un id por hecho. Solo lectura.';


-- ── Permisos ───────────────────────────────────────────────────────────────
--
-- `authenticated` lee, como el resto de pacs. **NO se concede a `anon`**: no
-- tiene USAGE sobre el esquema y ninguna otra tabla se lo da. Ver la
-- migración 20, donde eso se corrigió después de que la 18 lo hiciera mal.
grant select on pacs.paquetes_ficha        to authenticated;
grant select on pacs.fichas_ia             to authenticated;
grant select on pacs.fichas_ia_pendientes  to authenticated;
grant select on pacs.v_ficha_ia_actual     to authenticated;
grant select on pacs.v_paquete_ficha       to authenticated;
grant execute on function pacs.paquete_ficha(uuid) to authenticated;

alter table pacs.paquetes_ficha        enable row level security;
alter table pacs.fichas_ia             enable row level security;
alter table pacs.fichas_ia_pendientes  enable row level security;

drop policy if exists paquete_lectura on pacs.paquetes_ficha;
create policy paquete_lectura on pacs.paquetes_ficha for select using (true);
drop policy if exists ficha_ia_lectura on pacs.fichas_ia;
create policy ficha_ia_lectura on pacs.fichas_ia for select using (true);
drop policy if exists ficha_pendiente_lectura on pacs.fichas_ia_pendientes;
create policy ficha_pendiente_lectura on pacs.fichas_ia_pendientes
    for select using (true);


-- ── VERIFICACIÓN ───────────────────────────────────────────────────────────
--
-- `python supabase/verificar_migracion_21.py`, que corre las dos mitades y
-- revierte todo. No se deja como SQL comentado: un bloque comentado se lee y
-- se cree.
--
-- Comprueba, entre otras: que `authenticated` puede leer y no insertar; que
-- el check de PII rechaza un paquete con `marcadores_culturales`; que
-- `fichas_ia` rechaza un json que traiga `veredicto`; y que
-- `pacs.paquete_ficha()` devuelve el paquete guardado.
