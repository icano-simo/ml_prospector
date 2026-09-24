-- ════════════════════════════════════════════════════════════════════════════
-- 19 · `pacs.sf_lead_estado`: el Lead de Salesforce, con su dueño y su actividad
-- ════════════════════════════════════════════════════════════════════════════
--
-- ⚠ NO APLICADA. Se reporta antes de aplicarla, como pidió la revisión.
--
-- Qué contesta, y por qué no se puede contestar desde el prospector
-- -----------------------------------------------------------------
-- «¿Este realtor ya tiene dueño en Salesforce?» y «¿ya lo contactó alguien?».
-- Las dos deciden si el BD escribe o no escribe, y las dos viven en BigQuery.
--
-- El sync lo hace `simo-sync`, que es otro repo y otro despliegue. Aquí solo
-- está la tabla de destino: append-only, con `capturado_en`, y una vista que
-- se queda con la lectura más nueva por lead.
--
-- Por qué la llave es de 15 caracteres
-- ------------------------------------
-- `pacs.realtors.sf_lead_id` los tiene de 15 y Salesforce devuelve 18. Los tres
-- últimos son un checksum de mayúsculas, así que `LEFT(Id,15)` es la misma
-- llave sin perder nada. Guardar el de 18 obligaría a recortar en cada join, y
-- un join que recorta en un lado y no en el otro devuelve cero filas sin error.
--
-- Lo que NO se guarda
-- -------------------
-- **El Subject de las Tasks, crudo, nunca.** Trae el cuerpo del SMS de campaña
-- y los nombres de quien contestó. Se guarda el `origen` derivado --tres
-- valores-- y la fecha. Derivar y tirar es la única forma de que no aparezca
-- después en una exportación que nadie revisó.

create table if not exists pacs.sf_lead_estado (
    id              uuid primary key default gen_random_uuid(),
    capturado_en    timestamptz not null default now(),
    uploaded_at     timestamptz not null default now(),
    upload_batch_id uuid references pacs.upload_batch(id),

    -- `LEFT(Lead.Id,15)`. Es la llave contra `pacs.realtors.sf_lead_id`.
    sf_lead_id      text not null,
    realtor_id      uuid references pacs.realtors(id),

    status          text,
    lead_source     text,
    creado_en       timestamptz,
    es_convertido   boolean,
    ultima_actividad date,

    owner_id        text,
    owner_nombre    text,
    owner_activo    boolean,
    -- La conclusión, ya tomada: `owner_es_integracion` sale de una lista
    -- EXPLÍCITA de Ids, no de `IsActive`. `sf integrations` tiene IsActive =
    -- true, así que la condición de actividad lo clasificaría como un BD y la
    -- ficha diría «ya tiene dueño» sobre todos los leads sin dueño.
    owner_es_integracion boolean not null default false,
    -- El área del owner, cuando es una persona. Decide el TEXTO del sello, no
    -- si hay dueño: `Recruiting` sigue siendo un dueño.
    --
    -- Maria Guerrero (005Qg000009lvyfIAA) es el caso que lo motiva: posee
    -- 47.553 leads, más que `sf integrations`, y por volumen parecía un
    -- usuario de enrutamiento. Es Recruiter Manager, Corporate; sus leads son
    -- de reclutamiento (MMI 30.551, Recruitment Base Digital 6.322) y ninguno
    -- es `Realtors Base Digital`. NO es de integración.
    --
    -- Si aparece como dueña de un lead de realtor, el sello va en ámbar y dice
    -- «ya tiene dueño: Maria Guerrero (Recruiting)»: es un dueño real, y el BD
    -- tiene que saber que viene de reclutamiento y no de prospección.
    owner_area      text,

    -- Las últimas 5 Tasks, ya derivadas. Sin Subject.
    -- [{"fecha": "2026-07-31", "subtipo": "Task", "origen": "sms_campana"}]
    actividades     jsonb not null default '[]'::jsonb,

    constraint sf_lead_id_es_de_15 check (length(sf_lead_id) = 15),
    -- La guarda redundante: ninguna actividad puede traer el texto del SMS.
    -- El sync ya no lo manda y la vista de BigQuery ya no lo selecciona; esto
    -- es la tercera vuelta, y es la que falla ruidosamente.
    constraint sf_sin_subject_crudo check (
        not (actividades::text ilike '%"subject"%')
        and not (actividades::text ilike '%"description"%')
        and not (actividades::text ilike '%3019536182%'))
);

create index if not exists sf_lead_por_lead
    on pacs.sf_lead_estado (sf_lead_id, capturado_en desc);
create index if not exists sf_lead_por_realtor
    on pacs.sf_lead_estado (realtor_id, capturado_en desc);

comment on table pacs.sf_lead_estado is
'Estado del Lead de Salesforce, sincronizado desde BigQuery por simo-sync.
Append-only. SIN el Subject de las Tasks: trae el cuerpo del SMS de campaña.';


-- ── La lectura más nueva por lead ──────────────────────────────────────────
--
-- Columnas una por una y no `select *`: en Postgres un `select *` congela la
-- lista de columnas al crear la vista, así que una columna nueva no aparece
-- nunca y nadie se entera.
create or replace view pacs.v_sf_lead_actual as
select distinct on (s.sf_lead_id)
    s.id, s.capturado_en, s.sf_lead_id, s.realtor_id,
    s.status, s.lead_source, s.creado_en, s.es_convertido, s.ultima_actividad,
    s.owner_id, s.owner_nombre, s.owner_activo, s.owner_es_integracion,
    s.owner_area, s.actividades
from pacs.sf_lead_estado s
order by s.sf_lead_id, s.capturado_en desc, s.uploaded_at desc;

comment on view pacs.v_sf_lead_actual is
'Una fila por lead, la más nueva. El sello de la ficha se lee de aquí.';


grant select on pacs.sf_lead_estado to anon, authenticated;
grant select on pacs.v_sf_lead_actual to anon, authenticated;

alter table pacs.sf_lead_estado enable row level security;
drop policy if exists sf_lead_lectura on pacs.sf_lead_estado;
create policy sf_lead_lectura on pacs.sf_lead_estado for select using (true);


-- ── VERIFICACIÓN ───────────────────────────────────────────────────────────
--
-- Las cuatro, y la de lectura primero: sin GRANT de select, un INSERT que
-- falla se ve idéntico esté o no la política, y eso ya confundió una vez.
--
-- set role anon;
-- select count(*) from pacs.v_sf_lead_actual;                          -- ok
-- insert into pacs.sf_lead_estado (sf_lead_id) values ('00QQg00000cgy'); -- falla
-- reset role;
-- insert into pacs.sf_lead_estado (sf_lead_id) values ('00QQg00000cgylTMAQ');
--   -- falla: son 18 caracteres, la llave es de 15
-- insert into pacs.sf_lead_estado (sf_lead_id, actividades)
--   values ('00QQg00000cgylT', '[{"subject": "SMS de +13019536182"}]'::jsonb);
--   -- falla por el check: el Subject crudo no entra
-- insert into pacs.sf_lead_estado (sf_lead_id, actividades)
--   values ('00QQg00000cgylT',
--           '[{"fecha":"2026-07-31","subtipo":"Task","origen":"sms_campana"}]');
--   -- entra
