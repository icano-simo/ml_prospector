-- ════════════════════════════════════════════════════════════════════════════
-- 15 · a `textos_generados` no escribe un usuario: escribe el service role
-- ════════════════════════════════════════════════════════════════════════════
--
-- ⚠ NO APLICADA. Esta migracion espera el OK de Isabella para el merge. Desde
--   el 2026-09-23 las migraciones se aplican a produccion DESPUES del merge y
--   con aprobacion explicita. Las 13 y 14 se aplicaron antes, y eso fue un
--   error mio: quedan descritas en el reporte del PR.
--
-- Que arregla
-- -----------
-- La migracion 10 creo `textos_generados_insert` para `authenticated`. Eso deja
-- un camino de escritura que NO pasa por `supabase/guardar_texto.guardar`, o
-- sea que no pasa por las seis guardas: nunca, vocabulario, promesas de
-- material, folleto, las cifras contra los insumos y las entidades.
--
-- La tabla exige `verificacion` no nulo, pero eso solo obliga a que la columna
-- tenga ALGO. Un cliente con la clave anon puede insertar
-- `verificacion = '{"ok": true}'` a mano y el texto queda indistinguible de uno
-- verificado de verdad. Es el patron del §3 en su peor forma: la comprobacion
-- existe, corre, y el dato que examina lo escribio el mismo que hay que
-- comprobar.
--
-- Al quitar la policy de insert, `authenticated` deja de poder escribir --RLS
-- filtra, no rechaza, asi que un insert sin policy simplemente no entra-- y el
-- unico camino queda el service role, que es el que usa `guardar_texto`.
--
-- El SELECT no se toca: leer los textos sigue estando bien para quien tenga
-- acceso.

drop policy if exists textos_generados_insert on pacs.textos_generados;

comment on table pacs.textos_generados is
'Textos escritos por un modelo. Append-only y SIN policies de insert, update ni
delete para `authenticated`: se escribe solo por service role, desde
`supabase/guardar_texto.guardar`, que corre las seis guardas. Un insert directo
podria poner `verificacion = {"ok": true}` a mano y quedar indistinguible de un
texto verificado.';

-- ── La verificacion, leida de pg_policies DESPUES del cambio ────────────────
-- No alcanza con que el `drop` no diera error: `drop policy if exists` sale con
-- exito tambien cuando no habia nada que borrar, y entonces no prueba nada.
-- Se cuenta lo que quedo.
do $$
declare
    n_insert integer;
    n_update integer;
    n_delete integer;
    n_select integer;
    quedan  text;
begin
    select count(*) into n_insert from pg_policies
     where schemaname='pacs' and tablename='textos_generados' and cmd='INSERT';
    select count(*) into n_update from pg_policies
     where schemaname='pacs' and tablename='textos_generados' and cmd='UPDATE';
    select count(*) into n_delete from pg_policies
     where schemaname='pacs' and tablename='textos_generados' and cmd='DELETE';
    select count(*) into n_select from pg_policies
     where schemaname='pacs' and tablename='textos_generados' and cmd='SELECT';

    select string_agg(policyname || ' [' || cmd || ']', ', ' order by policyname)
      into quedan
      from pg_policies
     where schemaname='pacs' and tablename='textos_generados';

    if n_insert > 0 then
        raise exception
            'siguen habiendo % policies de INSERT en textos_generados: %',
            n_insert, quedan;
    end if;
    if n_update > 0 or n_delete > 0 then
        raise exception 'aparecieron policies de UPDATE (%) o DELETE (%)',
            n_update, n_delete;
    end if;
    if n_select < 1 then
        raise exception
            'se quedo sin policy de SELECT: nadie podria leer los textos';
    end if;

    raise notice 'policies en textos_generados: % · INSERT=% UPDATE=% DELETE=% SELECT=%',
        coalesce(quedan, '(ninguna)'), n_insert, n_update, n_delete, n_select;
    raise notice 'RLS activo=% · forzado=%',
        (select relrowsecurity from pg_class
          where oid = 'pacs.textos_generados'::regclass),
        (select relforcerowsecurity from pg_class
          where oid = 'pacs.textos_generados'::regclass);
end $$;
