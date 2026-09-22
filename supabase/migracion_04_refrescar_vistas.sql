-- ════════════════════════════════════════════════════════════════════════════
-- Migracion 04 · refrescar las vistas despues de agregar columnas
-- ════════════════════════════════════════════════════════════════════════════
--
-- **`select *` en una vista se congela al crearla.**
--
-- `v_capturas_modelmatch_current` se creo con `select c.*` cuando
-- `capturas_modelmatch` todavia no tenia `mmi_agent_id` ni `sf_lead_id`.
-- Postgres expande el `*` en ese momento y guarda la lista de columnas; agregar
-- una columna a la tabla NO la agrega a la vista.
--
-- El sintoma fue una consulta contra la vista fallando con
--
--   column "mmi_agent_id" does not exist
--
-- mientras la misma consulta contra la tabla funcionaba. La vista parece seguir
-- a la tabla y no la sigue.
--
-- Es la misma familia que todo lo demas de estos dias: **algo que se ve como si
-- se derivara solo y en realidad quedo fijado en un momento del pasado.**
--
-- Regla que sale de aca: **toda migracion que agregue una columna a una tabla
-- con vista tiene que recrear la vista.** No hay aviso.

begin;

create or replace view pacs.v_capturas_modelmatch_current as
select c.*
  from pacs.capturas_modelmatch c
  join pacs.upload_batch b on b.id = c.upload_batch_id
 where b.es_vigente;

create or replace view pacs.v_ig_senales_current as
select s.*
  from pacs.ig_senales s
  join pacs.upload_batch b on b.id = s.upload_batch_id
 where b.es_vigente;

create or replace view pacs.v_ig_crudo_current as
select c.*
  from pacs.ig_crudo c
  join pacs.upload_batch b on b.id = c.upload_batch_id
 where b.es_vigente;

create or replace view pacs.v_mercados_current as
select m.*
  from pacs.mercados m
  join pacs.upload_batch b on b.id = m.upload_batch_id
 where b.es_vigente;

-- `realtors` gano `sf_lead_id` en la 01, asi que esta tambien estaba fijada.
create or replace view pacs.v_evaluacion_actual as
select distinct on (realtor_id) *
  from pacs.evaluaciones
 order by realtor_id, evaluado_en desc;

alter view pacs.v_capturas_modelmatch_current set (security_invoker = on);
alter view pacs.v_ig_senales_current           set (security_invoker = on);
alter view pacs.v_ig_crudo_current             set (security_invoker = on);
alter view pacs.v_mercados_current             set (security_invoker = on);
alter view pacs.v_evaluacion_actual            set (security_invoker = on);

grant select on pacs.v_capturas_modelmatch_current,
                pacs.v_ig_senales_current,
                pacs.v_ig_crudo_current,
                pacs.v_mercados_current,
                pacs.v_evaluacion_actual
      to authenticated, service_role;

commit;

-- Verificacion:
--
--   select column_name from information_schema.columns
--    where table_schema='pacs' and table_name='v_capturas_modelmatch_current'
--      and column_name in ('mmi_agent_id','sf_lead_id');
--
-- Tiene que devolver las dos.
