-- ════════════════════════════════════════════════════════════════════════════
-- Migracion 01 · la llave dura: sf_lead_id
-- ════════════════════════════════════════════════════════════════════════════
--
-- El libro v3 entro sin ninguna llave dura: 4.249 de 4.249 sin licencia. El
-- archivo de Salesforce la resuelve con `Lead ID`, que tiene 4.386 valores,
-- 4.386 unicos y cero duplicados -- verificado, no supuesto.
--
-- Solo esta columna. `MMI Agent ID`, `Lead Status`, `Lead Owner`, `Converted` y
-- `Create Date` quedan para una segunda pasada, cuando se decida que hacer con
-- cada uno. En particular `Converted` NO se usa como etiqueta de nada: es la
-- misma columna que dio el 57% de tasa base y los 653 convertidos sin llamadas.

begin;

-- ── 1 · La columna ─────────────────────────────────────────────────────────
alter table pacs.realtors
    add column if not exists sf_lead_id text;

-- UNIQUE aparte del ADD para que sea idempotente y tenga nombre propio.
do $$
begin
  if not exists (
    select 1 from pg_constraint
     where conname = 'realtors_sf_lead_id_key'
       and conrelid = 'pacs.realtors'::regclass
  ) then
    alter table pacs.realtors
      add constraint realtors_sf_lead_id_key unique (sf_lead_id);
  end if;
end $$;

comment on column pacs.realtors.sf_lead_id is
'Lead ID de Salesforce, 15 caracteres. LA llave primaria del modelo: 4.386
valores, 4.386 unicos, cero duplicados (verificado 2026-09-22). Es la unica
fuente que hoy identifica a un realtor sin ambiguedad.';


-- ── 2 · La cascada ─────────────────────────────────────────────────────────
--
-- Lead ID -> licencia -> telefono -> email -> nombre+condado+volumen.
-- El Lead ID va primero porque es el unico con cero duplicados.
alter table pacs.realtors
    drop constraint if exists realtors_clave_resolucion_check;

alter table pacs.realtors
    add constraint realtors_clave_resolucion_check
    check (clave_resolucion in ('sf_lead_id', 'licencia', 'telefono', 'email',
                                'nombre_condado_volumen'));


-- ── 3 · sin_llave_dura, redefinida ─────────────────────────────────────────
--
-- Antes era "ni licencia, ni telefono, ni email" y daba 0 de 4.249, porque el
-- 98,5% tiene email. Eso medía **"no se cruza con nada"**, que es una pregunta
-- legitima -- y cuya respuesta, cero, es buena noticia.
--
-- Pero no es la pregunta de la llave. El telefono y el email son CANALES DE
-- CONTACTO, no llaves: dos personas pueden compartir un telefono de oficina, y
-- un email cambia de empresa. Una llave identifica; un canal alcanza.
--
-- Redefinida como **"no tiene ni sf_lead_id ni licencia"**, la columna vuelve a
-- medir lo que su nombre dice.
--
-- Una columna generada no se puede alterar: se tira y se crea. No hay perdida
-- de datos porque su valor siempre se deriva de las otras.
alter table pacs.realtors drop column if exists sin_llave_dura;

alter table pacs.realtors
    add column sin_llave_dura boolean
    generated always as (
        sf_lead_id is null and licencia_numero is null
    ) stored;

comment on column pacs.realtors.sin_llave_dura is
'No tiene NI sf_lead_id NI licencia estatal: no hay con que identificarlo en
una fuente futura. Telefono y email NO cuentan -- son canales de contacto, no
llaves. Redefinida el 2026-09-22; antes incluia los canales y por eso daba 0.';

commit;


-- ── Verificacion, para correr despues ──────────────────────────────────────
--
-- select count(*) filas,
--        count(sf_lead_id) con_lead_id,
--        count(*) filter (where sin_llave_dura) sin_llave_dura
--   from pacs.realtors;
