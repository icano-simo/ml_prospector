-- ════════════════════════════════════════════════════════════════════════════
-- 16 · `clase_perfil`: tabla propia, append-only, y la auditoria manda
-- ════════════════════════════════════════════════════════════════════════════
--
-- ⚠ NO APLICADA. Espera el OK de Isabella. Desde el 2026-09-23 las migraciones
--   se aplican a produccion DESPUES del merge.
--
-- REHECHA tras la auditoria de Cowork del 2026-09-23, que encontro dos cosas
-- que la primera version prometia y no hacia:
--
--   · el indice unico sobre (realtor_id, upload_batch_id) NO resolvia la carga
--     parcial. Solo impedia duplicar un realtor DENTRO de un lote. Cargar un
--     lote con 7 handles corregidos y apagar el anterior seguia borrando los
--     291 restantes de la vista;
--   · la clase auditada a mano vivia en la MISMA fila que las señales del
--     scraping, asi que al volver a scrapear entraba una fila nueva con
--     `origen='auto'` y la auditoria quedaba en la fila vieja, fuera de la
--     vista. Pasa justo con los 7 handles corregidos.
--
-- El comentario de la version anterior prometia lo primero. Una promesa en un
-- comentario que el codigo no cumple es peor que no tenerla: alguien la lee y
-- deja de comprobarlo.

-- ── 1 · La clase vive en su propia tabla, append-only ──────────────────────
--
-- Separarla de `ig_senales` es lo que permite que una auditoria manual
-- sobreviva a un re-scraping: son dos hechos de origen distinto y ritmo
-- distinto, y meterlos en la misma fila ata el mas duradero al mas volatil.
create table if not exists pacs.ig_clase_perfil (
    id              uuid primary key default gen_random_uuid(),
    realtor_id      uuid not null references pacs.realtors(id),
    handle          text,
    clase           text not null,
    motivo          text not null,
    origen          text not null default 'auto',
    revisar         boolean not null default false,
    auditada_por    text,
    decidida_en     timestamptz not null default now(),
    version_lexico  text,
    detalle         jsonb,

    -- Las 9 clases y ninguna mas. `clase_perfil` era texto libre, asi que un
    -- typo --«realtor_activa»-- entraba como una clase nueva, y una clase que
    -- nadie declaro cae del lado NO utilizable en el codigo pero nadie se
    -- entera de que existe.
    constraint ig_clase_valida check (clase in (
        'realtor_activo', 'realtor_mixto', 'poca_evidencia', 'otro_perfil',
        'sin_datos', 'persona_equivocada', 're_fuera_eeuu', 'inactivo',
        'personal_sin_re')),
    constraint ig_origen_valido check (origen in ('auto', 'auditoria')),
    -- Una auditoria sin firma no se puede discutir con nadie.
    constraint ig_auditoria_firmada check (
        origen <> 'auditoria' or auditada_por is not null)
);

create index if not exists ig_clase_por_realtor
    on pacs.ig_clase_perfil (realtor_id, decidida_en desc);
create index if not exists ig_clase_por_clase
    on pacs.ig_clase_perfil (clase);

comment on table pacs.ig_clase_perfil is
'Append-only. Una fila por decision de clase, automatica o auditada. La vista
`v_ig_clase_actual` resuelve cual manda: la auditoria manual gana sobre la
automatica SIEMPRE, y entre dos auditorias gana la mas nueva. Un re-scraping
agrega una fila `auto` y NO pisa la auditoria.';

-- ── 2 · La vista que resuelve la prioridad ─────────────────────────────────
--
-- `origen = 'auditoria'` primero, y despues por fecha. Con `distinct on` eso
-- se lee en una sola pasada y el orden ES la regla: no hay un `case` que
-- alguien pueda cambiar sin darse cuenta de que cambia la prioridad.
create or replace view pacs.v_ig_clase_actual as
select distinct on (realtor_id) *
  from pacs.ig_clase_perfil
 order by realtor_id,
          (origen = 'auditoria') desc,   -- la auditoria manda
          decidida_en desc;              -- y entre iguales, la mas nueva

alter view pacs.v_ig_clase_actual set (security_invoker = on);

-- ── 3 · La carga parcial NO puede apagar el lote ───────────────────────────
--
-- `v_ig_senales_current` devolvia todas las filas de los lotes vigentes. Un
-- scraping de 7 handles que apagaba el lote anterior dejaba 7 filas y los 291
-- perfiles restantes desaparecian.
--
-- Ahora devuelve **la fila mas reciente por realtor** entre los lotes vigentes,
-- asi que un lote parcial se suma en vez de reemplazar: los 7 se actualizan y
-- los 291 siguen ahi con su captura anterior. La carga parcial ya no necesita
-- apagar nada -- y si alguien lo apaga igual, los 291 sobreviven mientras su
-- lote siga vigente.
create or replace view pacs.v_ig_senales_current as
select distinct on (s.realtor_id) s.*
  from pacs.ig_senales s
  join pacs.upload_batch b on b.id = s.upload_batch_id
 where b.es_vigente
 order by s.realtor_id, s.capturado_en desc, s.uploaded_at desc;

alter view pacs.v_ig_senales_current set (security_invoker = on);

-- ── RLS · igual que el resto ───────────────────────────────────────────────
alter table pacs.ig_clase_perfil enable row level security;
alter table pacs.ig_clase_perfil force row level security;

drop policy if exists ig_clase_select on pacs.ig_clase_perfil;
create policy ig_clase_select on pacs.ig_clase_perfil
    for select to authenticated using (pacs.tiene_acceso());

-- El GRANT, que la migracion 15 olvido en `textos_generados` y por eso su
-- policy de SELECT quedo inservible: Postgres corta en el GRANT antes de mirar
-- RLS. Aqui va desde el principio.
grant select on pacs.ig_clase_perfil to authenticated;
grant select on pacs.v_ig_clase_actual to authenticated;

-- ── La verificacion ────────────────────────────────────────────────────────
do $$
declare
    n_sen int; n_realtors int; n_policies int; n_grant int;
begin
    -- La vista de señales tiene que devolver UNA fila por realtor.
    select count(*), count(distinct realtor_id) into n_sen, n_realtors
      from pacs.v_ig_senales_current where realtor_id is not null;
    if n_sen <> n_realtors then
        raise exception 'v_ig_senales_current devuelve % filas para % realtors',
            n_sen, n_realtors;
    end if;

    select count(*) into n_policies from pg_policies
     where schemaname='pacs' and tablename='ig_clase_perfil';
    select count(*) into n_grant from information_schema.role_table_grants
     where table_schema='pacs' and grantee='authenticated'
       and table_name in ('ig_clase_perfil', 'v_ig_clase_actual')
       and privilege_type = 'SELECT';
    if n_grant < 2 then
        raise exception 'faltan GRANT SELECT para authenticated (hay %)', n_grant;
    end if;

    raise notice 'ig_clase_perfil creada · % señales para % realtors · '
                 '% policies · % grants', n_sen, n_realtors, n_policies, n_grant;
end $$;
