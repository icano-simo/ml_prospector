-- ════════════════════════════════════════════════════════════════════════════
-- 20 · `pacs.transacciones`: el GRANT va a `authenticated`, no a `anon`
-- ════════════════════════════════════════════════════════════════════════════
--
-- Corrige la migración 18, que YA ESTÁ APLICADA. No se edita el archivo 18:
-- editar una migración que corrió hace que el repo mienta sobre lo que hay en
-- la base, y la próxima persona que lea el 18 va a creer que eso fue lo que se
-- aplicó.
--
-- Qué estaba mal
-- --------------
-- La 18 hacía `grant select ... to anon, authenticated`. Las otras dieciséis
-- tablas de `pacs` conceden SELECT solo a `authenticated`, y **`anon` no tiene
-- USAGE sobre el esquema `pacs`** -- el esquema entero está cerrado para él.
--
-- O sea que el GRANT a `anon` no abría nada: Postgres corta en el esquema
-- antes de mirar la tabla. Pero dejaba escrita una intención que contradice la
-- postura del proyecto, y una intención escrita se termina cumpliendo el día
-- que alguien abra el esquema por otro motivo.
--
-- Cómo se descubrió, que es la parte que importa
-- ----------------------------------------------
-- La verificación al pie del 18 hace un SELECT como `anon` que TIENE que
-- funcionar. Falló con `permission denied for schema pacs`, y de paso dejó ver
-- que el INSERT de la línea siguiente --el que «tiene que fallar»-- estaba
-- fallando por el esquema y no por la falta de GRANT de insert.
--
-- Es exactamente la confusión de la migración 15: **un permiso denegado no
-- dice CUÁL permiso.** Por eso la verificación pide siempre las dos mitades, y
-- por eso la de abajo corre como `authenticated`.

revoke select on pacs.transacciones from anon;
revoke select on pacs.v_transacciones_current from anon;

-- Y explícito, aunque la 18 ya lo hizo: esta migración tiene que poder leerse
-- sola y decir en qué estado deja la tabla.
grant select on pacs.transacciones to authenticated;
grant select on pacs.v_transacciones_current to authenticated;

comment on table pacs.transacciones is
'Una fila por cierre, de la pestaña Transactions de Model Match. Append-only.
SIN nombres de compradores ni vendedores y SIN calle: ECOA Regulation B. La
ausencia de esas columnas es la guarda, no un olvido.
Lectura: `authenticated`, como el resto de pacs. La escritura entra por la
service key desde la función.';


-- ── VERIFICACIÓN ───────────────────────────────────────────────────────────
--
-- `python supabase/verificar_migracion_18.py`, que corre las dos mitades como
-- `authenticated` y revierte todo. No se deja como SQL comentado: un bloque
-- comentado se lee y se cree.
