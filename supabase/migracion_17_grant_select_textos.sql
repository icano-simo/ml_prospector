-- ════════════════════════════════════════════════════════════════════════════
-- 17 · el GRANT SELECT que la migracion 15 dejo faltando
-- ════════════════════════════════════════════════════════════════════════════
--
-- ⚠ NO APLICADA. Va con el PR de autenticacion, segun la recomendacion de la
--   auditoria de Cowork del 2026-09-23.
--
-- Que paso
-- --------
-- La migracion 15 quito `textos_generados_insert` y dejo escrito en su propio
-- comentario: «El SELECT no se toca: leer los textos sigue estando bien para
-- quien tenga acceso». **No era asi.** `authenticated` no tiene NINGUN grant
-- sobre `pacs.textos_generados` ni sobre `pacs.v_textos_generados_actual`; las
-- otras 22 tablas y vistas de `pacs` si lo tienen.
--
-- La policy de SELECT existe y no sirve, porque **Postgres corta en el GRANT
-- antes de mirar RLS**.
--
-- Y algo peor, que es lo que esta migracion tambien viene a arreglar: la
-- verificacion que yo pegue como prueba de que la policy funcionaba era un
-- INSERT que devolvia `permission denied for table textos_generados`. Ese es el
-- corte por GRANT. Un SELECT del mismo usuario daba EXACTAMENTE el mismo error,
-- asi que mi prueba no distinguia «la policy rechaza» de «el rol no llega a la
-- tabla». Es el §3 del libro de reglas otra vez, en mi propia verificacion.
--
-- Hoy no se nota porque la API usa `service_role`, que salta GRANTs y RLS. Se
-- rompe el dia que la app lea con el JWT del usuario.

grant select on pacs.textos_generados            to authenticated;
grant select on pacs.v_textos_generados_actual   to authenticated;

comment on table pacs.textos_generados is
'Textos escritos por un modelo. Append-only, SIN policies de insert, update ni
delete para `authenticated`: se escribe solo por service role, desde
`supabase/guardar_texto.guardar`, que corre las seis guardas. LEER si esta
permitido: GRANT SELECT desde la migracion 17, que la 15 olvido.';

-- ── La verificacion que la 15 debio hacer ──────────────────────────────────
--
-- Dos comprobaciones, y hacen falta las dos:
--   1 · un SELECT como `authenticated` tiene que PODER correr -- si falla, el
--       GRANT sigue sin estar y la policy sigue siendo decorativa;
--   2 · un INSERT tiene que fallar **por RLS**, no por permisos. Si falla por
--       GRANT, no prueba nada sobre la policy.
do $$
declare
    n_grant int;
    fallo   text;
begin
    select count(*) into n_grant
      from information_schema.role_table_grants
     where table_schema='pacs' and grantee='authenticated'
       and table_name in ('textos_generados','v_textos_generados_actual')
       and privilege_type='SELECT';
    if n_grant < 2 then
        raise exception 'faltan GRANT SELECT: hay % de 2', n_grant;
    end if;

    -- 1 · leer tiene que poder.
    begin
        set local role authenticated;
        perform 1 from pacs.textos_generados limit 1;
        reset role;
    exception when insufficient_privilege then
        reset role;
        raise exception 'un authenticated NO puede leer: el GRANT no sirvio';
    end;

    -- 2 · escribir tiene que fallar, y por RLS.
    begin
        set local role authenticated;
        begin
            insert into pacs.textos_generados
                (realtor_id, tipo, texto, modelo, insumos, verificacion)
            select r.id, 'narrativa', 'prueba de la migracion 17', 'm',
                   '{"a":1}'::jsonb, '{"ok": true}'::jsonb
              from pacs.realtors r limit 1;
            reset role;
            raise exception 'un authenticated PUDO insertar: falta la policy';
        exception
            when insufficient_privilege then
                reset role;
                fallo := 'GRANT';
            when others then
                reset role;
                fallo := sqlstate;
        end;
    end;

    if fallo = 'GRANT' then
        raise exception
            'el INSERT fallo por GRANT y no por RLS: no prueba la policy';
    end if;
    raise notice 'SELECT permitido para authenticated · INSERT rechazado por '
                 'RLS (sqlstate %) · grants: %', fallo, n_grant;
end $$;
