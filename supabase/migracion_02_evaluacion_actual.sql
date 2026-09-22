-- ════════════════════════════════════════════════════════════════════════════
-- Migracion 02 · la vista del diagnostico vigente
-- ════════════════════════════════════════════════════════════════════════════
--
-- `pacs.evaluaciones` es append-only a proposito: el historico es la
-- infraestructura de la correlacion futura. Pero eso significa que
-- `select count(*) from pacs.evaluaciones` cuenta CORRIDAS, no realtors, y esa
-- confusion ya paso: la segunda corrida del motor reporto 8.374 evaluaciones y
-- un 34,8% sin dolor primario que mezclaba las dos pasadas.
--
-- El numero correcto era 40,4%. La consulta estaba mal, no el dato.
--
-- Nadie deberia tener que acordarse de escribir el DISTINCT ON.

begin;

create or replace view pacs.v_evaluacion_actual as
select distinct on (realtor_id) *
  from pacs.evaluaciones
 order by realtor_id, evaluado_en desc;

alter view pacs.v_evaluacion_actual set (security_invoker = on);

comment on view pacs.v_evaluacion_actual is
'La ULTIMA evaluacion de cada realtor. Todo lo que quiera saber "cual es el
diagnostico de hoy" lee de aca; `pacs.evaluaciones` es el historico y contarlo
cuenta corridas, no personas.';

grant select on pacs.v_evaluacion_actual to authenticated, service_role;

commit;
