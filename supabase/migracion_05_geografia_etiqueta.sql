-- ════════════════════════════════════════════════════════════════════════════
-- Migracion 05 · la etiqueta geografica, como columna
-- ════════════════════════════════════════════════════════════════════════════
--
-- La etiqueta de cada bloque de mercado se guardaba SOLO dentro de
-- `parseado->>'etiqueta_geografica'`. Ahi esta y se puede consultar, pero:
--
--   · no es descubrible: quien mire la tabla ve cuatro filas de 'mercado' con
--     `condado_fips` NULL y no tiene forma de saber que son geografias
--     distintas;
--   · no se puede indexar comodo;
--   · y el campo natural, `condado_fips`, esta NULL para todas -- porque
--     todavia no hay crosswalk nombre -> FIPS y meter "Solano" ahi seria poner
--     un nombre en una columna que espera un codigo.
--
-- El riesgo es el que el brief nombro: si dos capturas de Solano y Alameda se
-- ven identicas en la base, la biblioteca no puede saber cual es cual, y ese
-- error no da un solo aviso.
--
-- Se sube a columna de primera clase. `condado_fips` sigue NULL a proposito
-- hasta que exista el crosswalk: son dos cosas distintas y la segunda no se
-- inventa.

begin;

alter table pacs.capturas_modelmatch
    add column if not exists geografia_etiqueta text,
    add column if not exists geografia_nivel    text
        check (geografia_nivel in ('estado', 'condado'));

comment on column pacs.capturas_modelmatch.geografia_etiqueta is
'El nombre de la geografia del bloque, asignado POR POSICION segun el orden del
Overview. NULL en los bloques de perfil. No es un FIPS: el crosswalk todavia no
existe y un nombre no va en `condado_fips`.';

comment on column pacs.capturas_modelmatch.geografia_nivel is
'`estado` para el primer bloque de Market Signals, `condado` para el resto.';

-- Relleno de lo ya capturado, desde el jsonb donde vivia.
update pacs.capturas_modelmatch
   set geografia_etiqueta = parseado->>'etiqueta_geografica',
       geografia_nivel    = parseado->>'nivel'
 where alcance = 'mercado'
   and geografia_etiqueta is null;

-- Un bloque de mercado sin geografia no se puede distinguir de otro, y esa es
-- exactamente la contaminacion silenciosa que hay que impedir.
alter table pacs.capturas_modelmatch
    drop constraint if exists captura_mercado_trae_geografia;

alter table pacs.capturas_modelmatch
    add constraint captura_mercado_trae_geografia check (
        alcance <> 'mercado' or geografia_nivel is not null
    );

create index if not exists capturas_mm_geo
    on pacs.capturas_modelmatch (estado, geografia_nivel, geografia_etiqueta)
 where alcance = 'mercado';

commit;

-- La vista lleva `select *`, que se congela al crearla: hay que recrearla o no
-- va a traer las columnas nuevas. Es la leccion de la migracion 04.
begin;
create or replace view pacs.v_capturas_modelmatch_current as
select c.*
  from pacs.capturas_modelmatch c
  join pacs.upload_batch b on b.id = c.upload_batch_id
 where b.es_vigente;
alter view pacs.v_capturas_modelmatch_current set (security_invoker = on);
grant select on pacs.v_capturas_modelmatch_current to authenticated, service_role;
commit;
