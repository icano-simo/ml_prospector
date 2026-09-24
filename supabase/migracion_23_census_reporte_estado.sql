-- ════════════════════════════════════════════════════════════════════════════
-- 23 · `pacs.census_reporte_estado`: el Census del ESTADO, para citarlo
-- ════════════════════════════════════════════════════════════════════════════
--
-- ⚠ NO APLICADA. Se reporta antes, y la aplica Isabella con su OK.
--
-- Qué guarda, y por qué en una tabla
-- -----------------------------------
-- El reporte del mercado latino por estado --ACS 2024 5-Year, promedio
-- 2020-2024-- es un TEXTO por estado que las fichas citan por id
-- (`CENSUS-RPT-IL`). Hoy no está en ninguna parte: Cowork lo escribió en las
-- fichas y el validador de la app lo rechaza, porque el id no existe en el
-- paquete. Entre 7 y 23 problemas por ficha, todos por eso.
--
-- Va en una tabla y no en un archivo del repo por tres razones:
--   · el paquete se arma leyendo la base, no el sistema de archivos --en
--     Vercel el repo entero no viaja--;
--   · es append-only y fechado: cuando salga el ACS siguiente, el texto viejo
--     sigue explicando las fichas que se escribieron con él;
--   · y así el id que cita la ficha existe en la base, que es lo que el
--     validador comprueba.
--
-- Lo que NO es
-- ------------
-- **No describe a la persona.** Es el mercado del estado: cuántos latinos
-- viven allí, qué proporción es propietaria, cuántos hogares hablan español.
-- De «en Illinois el 18,8 % son latinos» a «sus buyers son latinos» hay un
-- salto que nadie midió, y el grado máximo que sostiene esta evidencia es
-- **Hipótesis** -- igual que `MM-MK-*` y por el mismo motivo. El validador lo
-- impone: `CENSUS-RPT` no está en `_GRADO_POR_FUENTE`, así que no sostiene un
-- «Dato».
--
-- Y no lleva PII: son agregados de estado publicados por el Census Bureau.

create table if not exists pacs.census_reporte_estado (
    id              uuid primary key default gen_random_uuid(),
    -- El código de dos letras, en mayúsculas. Es la llave con la que el
    -- paquete busca: `realtors.estado` -> `CENSUS-RPT-<ST>`.
    estado          text not null check (estado ~ '^[A-Z]{2}$'),
    -- El id que la ficha cita, literal. Se guarda en vez de componerse para
    -- que sea imposible que el de la tabla y el del paquete difieran: si un
    -- día el formato cambia, cambia AQUÍ y no en dos sitios.
    id_evidencia    text not null,
    texto           text not null,
    fuente          text not null,
    cargado_en      timestamptz not null default now(),

    -- Append-only con sentido: dos filas con el mismo texto para el mismo
    -- estado son el mismo hecho contado dos veces, y el paquete tendría que
    -- elegir. Se permite un texto NUEVO (otra edición del ACS) y se rechaza el
    -- mismo repetido.
    constraint census_rpt_uno_por_texto unique (estado, texto),

    -- La guarda redundante, como en `paquetes_ficha`. Este texto se copia
    -- dentro del paquete, que es lo que lee Cowork: si algún día alguien pega
    -- aquí un recorte con un nombre o un barrio, falla ruidosamente en vez de
    -- viajar.
    constraint census_rpt_sin_pii check (
        not (texto ilike '%marcadores_culturales%')
        and not (texto ilike '%barrios_mencionados%')
        and not (texto ilike '%@%'))
);

create index if not exists census_rpt_por_estado
    on pacs.census_reporte_estado (estado, cargado_en desc);

comment on table pacs.census_reporte_estado is
'El reporte de mercado latino por ESTADO (ACS 2024 5-Year). Describe el
mercado, nunca a la persona: grado máximo Hipótesis. Append-only; el paquete
toma la fila más reciente del estado del realtor.';

comment on column pacs.census_reporte_estado.id_evidencia is
'El id que la ficha cita, literal (CENSUS-RPT-IL). Se guarda, no se compone.';


-- ── Lo vigente por estado ──────────────────────────────────────────────────
--
-- Columnas una por una y no `select *`: un `select *` congela la lista al
-- crear la vista, así que una columna nueva no aparece nunca.
--
-- `security_invoker = true`, igual que las de la migración 21: por defecto una
-- vista corre con los permisos de su OWNER y se salta la RLS de las tablas que
-- lee. Hoy no cambia nada; el día que las tablas se cierren con
-- `allowed_apps ? 'prospector'`, una vista sin esto es una ventana abierta al
-- lado de una puerta cerrada.
create or replace view pacs.v_census_reporte_actual
with (security_invoker = true) as
select distinct on (c.estado)
    c.id, c.estado, c.id_evidencia, c.texto, c.fuente, c.cargado_en
from pacs.census_reporte_estado c
order by c.estado, c.cargado_en desc;

comment on view pacs.v_census_reporte_actual is
'El reporte más reciente por estado. Es lo que el paquete mete como
CENSUS-RPT-<ST>.';


-- ── Permisos ───────────────────────────────────────────────────────────────
--
-- `authenticated` lee, como el resto de pacs. **NO se concede a `anon`**: no
-- tiene USAGE sobre el esquema (ver migración 20, donde eso se corrigió
-- después de que la 18 lo hiciera mal).
grant select on pacs.census_reporte_estado   to authenticated;
grant select on pacs.v_census_reporte_actual to authenticated;

alter table pacs.census_reporte_estado enable row level security;

drop policy if exists census_rpt_lectura on pacs.census_reporte_estado;
create policy census_rpt_lectura on pacs.census_reporte_estado
    for select to authenticated using (pacs.tiene_acceso());


-- ── VERIFICACIÓN ───────────────────────────────────────────────────────────
--
-- `python supabase/verificar_migracion_23.py`, que corre las dos mitades sobre
-- datos de prueba y revierte. Comprueba:
--   · que `authenticated` puede leer y NO insertar;
--   · que el check de PII rechaza un texto con un correo dentro;
--   · que el unique rechaza el mismo texto repetido para el estado -- con los
--     dos inserts en la MISMA transacción, que es el error que ya cometí una
--     vez: en dos casos con rollback en medio no chocan nunca, y la prueba
--     decía que el unique no funcionaba cuando lo que no funcionaba era la
--     prueba;
--   · y que `v_census_reporte_actual` devuelve UNA fila por estado, la más
--     reciente, con dos cargas del mismo estado.
