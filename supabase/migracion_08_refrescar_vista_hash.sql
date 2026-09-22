-- ════════════════════════════════════════════════════════════════════════════
-- 08 · refrescar la vista tras hash_volcado, y una guarda que lo compruebe
-- ════════════════════════════════════════════════════════════════════════════
--
-- La migracion 04 dejo escrita la regla: **toda migracion que agregue una
-- columna a una tabla con vista tiene que recrear la vista**, porque `select *`
-- se congela al crearla y no hay aviso.
--
-- La migracion 07 agrego `hash_volcado` y NO recreo la vista. Y su guarda paso:
--
--   select 1 from information_schema.columns
--    where table_name = 'capturas_modelmatch' and column_name = 'hash_volcado'
--
-- Eso comprueba LA TABLA. La columna estaba en la tabla, asi que la guarda
-- respondio que si -- mientras la vista seguia sin ella. Es la seccion 3 de
-- `docs/reglas-que-no-cambian.md` otra vez, y esta vez dentro de la guarda que
-- se escribio para evitarla: **una verificacion que mira otro objeto**.
--
-- El sintoma: `column v_capturas_modelmatch_current.hash_volcado does not
-- exist` sobre la vista, con la misma consulta funcionando contra la tabla.

begin;

create or replace view pacs.v_capturas_modelmatch_current as
select c.*
  from pacs.capturas_modelmatch c
  join pacs.upload_batch b on b.id = c.upload_batch_id
 where b.es_vigente;

alter view pacs.v_capturas_modelmatch_current set (security_invoker = on);

-- ── La guarda, esta vez sobre el objeto correcto ────────────────────────────
--
-- No comprueba una columna concreta: comprueba que la vista tenga TODAS las de
-- la tabla. Una guarda con la lista escrita a mano hay que acordarse de
-- ampliarla, y la proxima columna que se agregue no estara en esa lista.
do $$
declare
    faltan text[];
begin
    select array_agg(t.column_name order by t.column_name) into faltan
      from information_schema.columns t
     where t.table_schema = 'pacs'
       and t.table_name = 'capturas_modelmatch'
       and not exists (
           select 1 from information_schema.columns v
            where v.table_schema = 'pacs'
              and v.table_name = 'v_capturas_modelmatch_current'
              and v.column_name = t.column_name
       );

    if faltan is not null then
        raise exception
            'la vista v_capturas_modelmatch_current no tiene estas columnas de '
            'la tabla: %. `select *` se congela al crear la vista.', faltan;
    end if;

    raise notice 'vista al dia: tiene las % columnas de la tabla',
        (select count(*) from information_schema.columns
          where table_schema = 'pacs' and table_name = 'capturas_modelmatch');
end $$;

commit;
