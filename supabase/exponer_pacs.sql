-- ════════════════════════════════════════════════════════════════════════════
-- Exponer `pacs` en PostgREST · TRES pasos, en orden, sin saltarse el primero
-- ════════════════════════════════════════════════════════════════════════════
--
-- `pgrst.db_schemas` se reescribe ENTERO. No hay forma de agregar un esquema:
-- se pone la lista completa o se pierde lo que no se puso.
--
-- Y la lista se reseteo sola dos veces, tumbando apps que funcionaban. Cuando
-- eso pasa el sintoma es `permission denied for schema X` en una app que nadie
-- toco, que es de los errores mas caros de diagnosticar porque el cambio no
-- esta en el repositorio de nadie.
--
-- Por eso este archivo NO trae la lista escrita. La ultima verificada, el
-- 2026-09-22, eran trece esquemas -- cuatro mas que cinco semanas antes-- y
-- esta anotada en el comentario final de `esquema.sql` como REFERENCIA. Si se
-- usa esa lista en vez de leer, se pierde lo que haya aparecido desde entonces.


-- ── PASO 1 · LEER. No se saltea ────────────────────────────────────────────

select setconfig
  from pg_db_role_setting drs
  join pg_roles r on r.oid = drs.setrole
 where r.rolname = 'authenticator';

-- Devuelve algo como:
--   {pgrst.db_schemas=public,b2b_metrics,...,comp,statement_timeout=8s,...}
--
-- Interesa SOLO el valor de `pgrst.db_schemas`. Los otros settings del rol
-- (statement_timeout, lock_timeout, safeupdate) se dejan como estan: el ALTER
-- del paso 2 toca un unico setting y no los pisa.


-- ── PASO 2 · REESCRIBIR, con la lista del paso 1 + pacs ────────────────────
--
-- Reemplazar <PEGAR_AQUI_LO_QUE_DEVOLVIO_EL_PASO_1> por la lista literal,
-- separada por comas y sin espacios, y con `,pacs` al final.
--
-- Si la lista del paso 1 NO tiene trece o mas esquemas, parar: algo cambio y
-- hay que entender que antes de escribir.

-- ALTER ROLE authenticator
--   SET pgrst.db_schemas = '<PEGAR_AQUI_LO_QUE_DEVOLVIO_EL_PASO_1>,pacs';
--
-- NOTIFY pgrst, 'reload config';


-- ── PASO 3 · VOLVER A LEER y confirmar que estan TODAS ─────────────────────
--
-- No alcanza con ver `pacs`. Hay que contar que no falte ninguno de los que
-- estaban: el modo de fallo es perder uno, no no-agregar el nuevo.

-- select setconfig
--   from pg_db_role_setting drs
--   join pg_roles r on r.oid = drs.setrole
--  where r.rolname = 'authenticator';

-- Y la comprobacion util, que cuenta en vez de mirar:
--
--   select count(*) as n_esquemas
--     from unnest(string_to_array(
--            (select split_part(unnest, '=', 2)
--               from pg_db_role_setting drs
--               join pg_roles r on r.oid = drs.setrole,
--                    unnest(drs.setconfig)
--              where r.rolname = 'authenticator'
--                and unnest like 'pgrst.db_schemas=%'),
--          ',')) ;
--
-- Tiene que dar el numero del paso 1 mas uno. Si da menos, se perdio alguno y
-- hay que reponerlo AHORA, no cuando alguien reporte que su app dejo de andar.
