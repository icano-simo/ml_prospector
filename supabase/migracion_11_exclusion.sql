-- ════════════════════════════════════════════════════════════════════════════
-- 11 · la exclusion viaja con la evaluacion
-- ════════════════════════════════════════════════════════════════════════════
--
-- El libro trae `pacs: nivel_de_calificacion` con 135 DESCARTADO, 25 BLOQUEADO
-- POR COBERTURA y 1 RECLASIFICADO POR MMI. **El motor nunca lo leyo.**
--
-- Consecuencia medida: Lisa Munoz salio con dolor primario P-Q10 y confianza
-- MEDIA, y Andrea Saavedra con P-Q09 -- las dos excluidas por metodologia, las
-- dos tratadas como candidatas normales. Que el raspado de Instagram las
-- alcanzara no estorba; que el motor las devuelva como contactables, si.
--
-- Va en COLUMNA y no dentro de `resultado` porque es lo que decide si una
-- persona entra a una cola de contacto. Un dato que gobierna un envio tiene que
-- poder consultarse sin abrir un jsonb.

alter table pacs.evaluaciones
    add column if not exists excluido text,
    add column if not exists excluido_motivo text;

comment on column pacs.evaluaciones.excluido is
'El nivel del libro cuando NO es contactable: DESCARTADO, BLOQUEADO POR
COBERTURA o RECLASIFICADO POR MMI. NULL significa contactable. Se llena del
libro, no se deduce.';

create index if not exists evaluaciones_excluido
    on pacs.evaluaciones (excluido) where excluido is not null;

-- La vista de lo vigente se recrea: `select *` congela la lista de columnas al
-- crearla, y sin esto las dos nuevas no existirian para quien lea la vista.
-- Es la regla de la migracion 04, y la 07 ya la olvido una vez.
create or replace view pacs.v_evaluacion_actual as
select distinct on (realtor_id) *
  from pacs.evaluaciones
 order by realtor_id, evaluado_en desc;

alter view pacs.v_evaluacion_actual set (security_invoker = on);

do $$
declare
    faltan text[];
begin
    select array_agg(t.column_name order by t.column_name) into faltan
      from information_schema.columns t
     where t.table_schema = 'pacs' and t.table_name = 'evaluaciones'
       and not exists (
           select 1 from information_schema.columns v
            where v.table_schema = 'pacs'
              and v.table_name = 'v_evaluacion_actual'
              and v.column_name = t.column_name);
    if faltan is not null then
        raise exception 'v_evaluacion_actual no tiene: %', faltan;
    end if;
    raise notice 'exclusion en columna · vista al dia con las % columnas',
        (select count(*) from information_schema.columns
          where table_schema='pacs' and table_name='evaluaciones');
end $$;
