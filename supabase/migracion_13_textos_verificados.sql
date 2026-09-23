-- ════════════════════════════════════════════════════════════════════════════
-- 13 · la vista de textos solo muestra los que pasaron la verificacion
-- ════════════════════════════════════════════════════════════════════════════
--
-- `pacs.textos_generados` es append-only y guarda el veredicto al lado del
-- texto. Pero `v_textos_generados_actual` devolvia TODAS las filas vigentes,
-- pasaran o no -- asi que un texto rechazado seguia siendo legible por
-- cualquiera que consultara la vista, que es el camino normal.
--
-- Hoy `guardar_texto.guardar` levanta `TextoRechazado` antes de insertar, asi
-- que en la practica no hay filas con `ok=false`. Eso no arregla nada: la vista
-- tiene que filtrar por lo que la fila DICE de si misma, no por la confianza en
-- que el unico camino de escritura se respete siempre. Un INSERT directo --que
-- la tabla permite mientras `verificacion` no sea nulo-- volveria a meterlas.
--
-- Idempotente y sin tocar las migraciones anteriores.

-- El filtro va en el WHERE, o sea ANTES del `distinct on`. Si fuera despues,
-- un texto rechazado mas nuevo se llevaria el `distinct on` y taparia al bueno
-- anterior: la vista devolveria cero filas para ese realtor y se leeria como
-- «no hay texto» en vez de «el ultimo intento no pasó».
create or replace view pacs.v_textos_generados_actual as
select distinct on (realtor_id, tipo, coalesce(orden, -1)) *
  from pacs.textos_generados
 where verificacion->>'ok' = 'true'
 order by realtor_id, tipo, coalesce(orden, -1), generado_en desc;

alter view pacs.v_textos_generados_actual set (security_invoker = on);

do $$
declare
    total int; visibles int; sin_veredicto int;
begin
    select count(*) into total from pacs.textos_generados;
    select count(*) into visibles from pacs.v_textos_generados_actual;
    select count(*) into sin_veredicto from pacs.textos_generados
     where verificacion->>'ok' is distinct from 'true';
    raise notice 'textos: % · visibles en la vista: % · sin ok=true: %',
        total, visibles, sin_veredicto;
    -- Las columnas de la tabla tienen que estar TODAS en la vista: `select t.*`
    -- congela la lista al crearla, y esta vista ya se recreo una vez por eso.
    if exists (
        select 1 from information_schema.columns c
         where c.table_schema='pacs' and c.table_name='textos_generados'
           and not exists (
               select 1 from information_schema.columns v
                where v.table_schema='pacs'
                  and v.table_name='v_textos_generados_actual'
                  and v.column_name = c.column_name))
    then
        raise exception 'la vista no tiene todas las columnas de la tabla';
    end if;
end $$;
