-- ════════════════════════════════════════════════════════════════════════════
-- 22 · Las tres tablas de la ficha usan `pacs.tiene_acceso()`, no `true`
-- ════════════════════════════════════════════════════════════════════════════
--
-- Corrige la migración 21, que YA ESTÁ APLICADA. No se edita el 21 por lo
-- mismo que no se editó el 18: editar una migración que corrió hace que el
-- repo mienta sobre lo que hay en la base.
--
-- Qué estaba mal
-- --------------
-- Las políticas de `paquetes_ficha`, `fichas_ia` y `fichas_ia_pendientes`
-- quedaron en `using (true)`. `pacs.tiene_acceso()` existe desde el esquema
-- inicial y ya lo usan `realtors`, `textos_generados` e `ig_clase_perfil`:
-- comprueba el claim `pacs` en `app_metadata.allowed_apps`, y se verifica en
-- la RLS y no solo en la app porque **PostgREST es alcanzable con un JWT
-- válido sin pasar por el front**.
--
-- O sea que tres tablas nuevas --y justo las que llevan el texto redactado y
-- toda la evidencia junta-- quedaron más abiertas que la tabla de realtors.
--
-- Cómo se descubrió
-- -----------------
-- Comprobando que Cowork puede leer los 9 paquetes. La consulta unía
-- `v_paquete_ficha` con `pacs.realtors` y devolvió 0 filas: no por la vista
-- --que devuelve las 9-- sino porque `realtors` SÍ tiene política real y como
-- `authenticated` sin claim no se ve nada.
--
-- El contraste es el hallazgo: una tabla decía que no y la otra que sí.
--
-- Nota para el PR de autenticación (7.2): si el claim pasa de `pacs` a
-- `prospector`, se cambia DENTRO de `tiene_acceso()` y estas tres políticas no
-- se tocan. Por eso van por la función y no con la condición escrita a mano.

drop policy if exists paquete_lectura on pacs.paquetes_ficha;
create policy paquete_lectura on pacs.paquetes_ficha
    for select to authenticated using (pacs.tiene_acceso());

drop policy if exists ficha_ia_lectura on pacs.fichas_ia;
create policy ficha_ia_lectura on pacs.fichas_ia
    for select to authenticated using (pacs.tiene_acceso());

drop policy if exists ficha_pendiente_lectura on pacs.fichas_ia_pendientes;
create policy ficha_pendiente_lectura on pacs.fichas_ia_pendientes
    for select to authenticated using (pacs.tiene_acceso());


-- ── VERIFICACIÓN ───────────────────────────────────────────────────────────
--
-- `python supabase/verificar_migracion_21.py`, que ahora exige que la tabla
-- NO esté vacía antes de dar por buena una lectura.
--
-- Esa es la otra mitad de lo que salió mal hoy: la verificación del 21 probó
-- `select count(*)` con la tabla vacía y lo dio por bueno. Un SELECT que
-- devuelve 0 sobre una tabla sin filas no prueba que se pueda leer -- prueba
-- que no hay nada que leer, que es lo mismo que decía el bug.
