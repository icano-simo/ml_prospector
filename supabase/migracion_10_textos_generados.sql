-- ════════════════════════════════════════════════════════════════════════════
-- 10 · pacs.textos_generados · lo que escribe un modelo, con sus insumos
-- ════════════════════════════════════════════════════════════════════════════
--
-- El motor calcula la logica y un modelo la traduce a algo que un BD entienda
-- sin explicacion. Lo que hace que eso sea auditable y no una caja negra es
-- `insumos`: **el extracto exacto que se uso para escribir el texto**.
--
-- Si una cifra del texto no esta en los insumos, no salio del dato. Esa es la
-- unica comprobacion que atrapa una cifra inventada, y es el modo de fallo que
-- mas importa: un numero equivocado con formato correcto no se ve.
--
-- Append-only, como `evaluaciones`: cada version se guarda y ninguna se pisa.
-- Sin politica de UPDATE ni de DELETE, igual que alli.

create table if not exists pacs.textos_generados (
    id              uuid primary key default gen_random_uuid(),
    realtor_id      uuid not null references pacs.realtors(id) on delete cascade,
    evaluacion_id   uuid references pacs.evaluaciones(id) on delete set null,

    tipo            text not null check (tipo in (
                        'narrativa', 'lectura_contraste', 'toque')),
    -- Solo para los toques. Un toque sin orden no se puede secuenciar.
    orden           integer,

    texto           text not null check (length(btrim(texto)) > 0),
    modelo          text not null,
    generado_en     timestamptz not null default now(),
    version_reglas  text not null,

    -- EL CAMPO QUE HACE AUDITABLE TODO LO DEMAS. No puede venir vacio: un
    -- texto sin insumos es un texto que nadie puede comprobar, y guardarlo
    -- seria guardar una afirmacion sin su fuente.
    insumos         jsonb not null,

    -- Que guardas corrieron y que dijeron. Se guarda el veredicto, no solo el
    -- hecho de que paso: "paso" sin decir cuantas cifras comprobo es la guarda
    -- que pasa porque no tiene nada que verificar.
    verificacion    jsonb not null,

    check (tipo <> 'toque' or orden is not null),
    check (insumos <> '{}'::jsonb and insumos <> '[]'::jsonb)
);

create index if not exists textos_generados_realtor
    on pacs.textos_generados (realtor_id, tipo, generado_en desc);
create index if not exists textos_generados_evaluacion
    on pacs.textos_generados (evaluacion_id);

comment on table pacs.textos_generados is
'Lo que un modelo escribio a partir del diagnostico. Append-only. `insumos` es
el extracto exacto que se le dio: si una cifra del texto no esta ahi, no salio
del dato.';

comment on column pacs.textos_generados.insumos is
'El extracto EXACTO que se uso para escribir. Es lo que permite comprobar que
no se invento nada, y por eso no puede venir vacio.';

comment on column pacs.textos_generados.verificacion is
'El veredicto de cada guarda, con SU DENOMINADOR: cuantas cifras se
comprobaron, no solo si paso. Cero cifras comprobadas no es un aprobado.';

-- ── La vista de lo vigente ──────────────────────────────────────────────────
-- Un texto por realtor, tipo y orden: el ultimo. Nadie consulta la tabla.
create or replace view pacs.v_textos_generados_actual as
select distinct on (realtor_id, tipo, coalesce(orden, -1)) *
  from pacs.textos_generados
 order by realtor_id, tipo, coalesce(orden, -1), generado_en desc;

alter view pacs.v_textos_generados_actual set (security_invoker = on);

-- ── RLS · igual que el resto, y SIN update ni delete ────────────────────────
alter table pacs.textos_generados enable row level security;
alter table pacs.textos_generados force row level security;

drop policy if exists textos_generados_select on pacs.textos_generados;
create policy textos_generados_select on pacs.textos_generados
    for select to authenticated using (pacs.tiene_acceso());

drop policy if exists textos_generados_insert on pacs.textos_generados;
create policy textos_generados_insert on pacs.textos_generados
    for insert to authenticated with check (pacs.tiene_acceso());

do $$
declare
    n_update integer;
    n_delete integer;
begin
    select count(*) into n_update from pg_policies
     where schemaname = 'pacs' and tablename = 'textos_generados'
       and cmd = 'UPDATE';
    select count(*) into n_delete from pg_policies
     where schemaname = 'pacs' and tablename = 'textos_generados'
       and cmd = 'DELETE';
    if n_update > 0 or n_delete > 0 then
        raise exception 'textos_generados tiene % politicas de UPDATE y % de '
            'DELETE. Es append-only: cada version se guarda y ninguna se pisa.',
            n_update, n_delete;
    end if;
    raise notice 'textos_generados creada · append-only, sin UPDATE ni DELETE · '
        'insumos y verificacion obligatorios';
end $$;
