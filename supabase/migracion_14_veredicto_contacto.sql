-- ════════════════════════════════════════════════════════════════════════════
-- 14 · el veredicto de contacto viaja con la evaluacion
-- ════════════════════════════════════════════════════════════════════════════
--
-- `motor.veredicto.puede_contactarse` es la compuerta unica: devuelve
-- `excluido`, `pendiente_modelmatch` u `ok`, con su motivo y su evidencia.
-- La migracion 11 ya guardo `excluido` --el nivel del libro-- pero eso es solo
-- una de las tres razones por las que alguien no es contactable. Faltaban las
-- otras dos:
--
--   · ya trabaja con originadores de la casa (exclusion por no-canibalizacion,
--     umbral > 0 operaciones buyside por unidades);
--   · no hay captura de Model Match, o la hay y no se pudo leer el reparto.
--
-- Va en jsonb y no en tres columnas porque el veredicto se guarda ENTERO: el
-- estado sin su evidencia --que originadores, cuantas unidades, sobre que
-- total y de que fecha-- obliga a recalcularlo para poder discutirlo, y
-- recalcularlo contra un perfil que ya cambio da otro resultado.

alter table pacs.evaluaciones
    add column if not exists veredicto_contacto jsonb;

comment on column pacs.evaluaciones.veredicto_contacto is
'El veredicto de `motor.veredicto.puede_contactarse`: {estado, motivo,
evidencia}. `estado` es excluido | pendiente_modelmatch | ok. Es la misma
compuerta que usan /api/dossier, /api/extracto y guardar_texto -- una sola, para
que el mismo realtor no salga contactable por un camino e inviable por otro.';

create index if not exists evaluaciones_veredicto_estado
    on pacs.evaluaciones ((veredicto_contacto->>'estado'));

-- `select *` congela la lista de columnas al crear la vista. Es la regla de la
-- migracion 04 y ya se olvido dos veces.
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
    raise notice 'veredicto_contacto en columna · vista al dia con % columnas',
        (select count(*) from information_schema.columns
          where table_schema='pacs' and table_name='evaluaciones');
end $$;
