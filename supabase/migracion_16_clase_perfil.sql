-- ════════════════════════════════════════════════════════════════════════════
-- 16 · `clase_perfil`: la compuerta se persiste, no se recalcula
-- ════════════════════════════════════════════════════════════════════════════
--
-- ⚠ NO APLICADA. Espera el OK de Isabella para el merge. Desde el 2026-09-23
--   las migraciones se aplican a produccion DESPUES del merge.
--
-- Que resuelve
-- ------------
-- `motor/desde_instagram.py` evaluaba Instagram sin compuerta de perfil: 36 de
-- los 39 perfiles no utilizables tenian un dolor primario vigente. La clase se
-- calcula en la INGESTA -- `ingest/instagram/clase_perfil.py` -- y el motor
-- solo la lee; recalcularla en cada consumidor es como dos capas empiezan a
-- discrepar sin que nada avise.
--
-- La auditoria manual MANDA sobre la automatica: `clase_origen = 'auditoria'`
-- gana, y queda registrado quien y cuando. Un clasificador que pisa lo que una
-- persona corrigio a mano hace que nadie vuelva a corregir nada.

alter table pacs.ig_senales
    add column if not exists clase_perfil text,
    add column if not exists clase_motivo text,
    add column if not exists clase_origen text
        default 'auto' check (clase_origen in ('auto', 'auditoria')),
    add column if not exists clase_auditada_por text,
    add column if not exists clase_auditada_en timestamptz,
    add column if not exists clase_revisar boolean default false,
    add column if not exists version_lexico text;

comment on column pacs.ig_senales.clase_perfil is
'realtor_activo | realtor_mixto | poca_evidencia | otro_perfil (UTILIZABLES) ·
sin_datos | persona_equivocada | re_fuera_eeuu | inactivo | personal_sin_re (NO
utilizables). Ninguna señal de Instagram entra al motor sin una clase
utilizable. `otro_perfil` entra solo como fuente de referidos.';

comment on column pacs.ig_senales.clase_origen is
'auto | auditoria. La auditoria manual manda sobre la automatica.';

create index if not exists ig_senales_clase
    on pacs.ig_senales (clase_perfil);

-- ── La carga parcial no puede apagar el lote ───────────────────────────────
-- Un scraping de 7 handles no puede dejar sin señales a los otros 291. Con el
-- modelo de lotes actual, apagar el lote anterior es exactamente eso: la carga
-- nueva trae 7 filas vigentes y las 291 restantes desaparecen de la vista.
--
-- La llave unica por realtor habilita el upsert. **No se crea como constraint
-- de la tabla** porque `ig_senales` es append-only y una fila por lote es lo
-- que permite ver el historico; es un indice UNICO parcial sobre lo vigente.
create unique index if not exists ig_senales_un_realtor_vigente
    on pacs.ig_senales (realtor_id, upload_batch_id)
 where realtor_id is not null;

do $$
declare
    faltan text[];
begin
    select array_agg(c) into faltan from unnest(array[
        'clase_perfil','clase_motivo','clase_origen','clase_auditada_por',
        'clase_auditada_en','clase_revisar','version_lexico']) c
     where not exists (
        select 1 from information_schema.columns
         where table_schema='pacs' and table_name='ig_senales'
           and column_name = c);
    if faltan is not null then
        raise exception 'faltan columnas: %', faltan;
    end if;
    raise notice 'clase_perfil en columna · % filas de ig_senales, % con clase',
        (select count(*) from pacs.ig_senales),
        (select count(clase_perfil) from pacs.ig_senales);
end $$;

-- `select s.*` congela la lista de columnas al crear la vista: sin recrearla,
-- las siete nuevas no existirian para quien lea la vista. Es la regla de la
-- migracion 04 y ya se olvido dos veces.
create or replace view pacs.v_ig_senales_current as
select s.*
  from pacs.ig_senales s
  join pacs.upload_batch b on b.id = s.upload_batch_id
 where b.es_vigente;

alter view pacs.v_ig_senales_current set (security_invoker = on);

do $$
declare faltan text[];
begin
    select array_agg(t.column_name order by t.column_name) into faltan
      from information_schema.columns t
     where t.table_schema='pacs' and t.table_name='ig_senales'
       and not exists (
           select 1 from information_schema.columns v
            where v.table_schema='pacs' and v.table_name='v_ig_senales_current'
              and v.column_name = t.column_name);
    if faltan is not null then
        raise exception 'v_ig_senales_current no tiene: %', faltan;
    end if;
    raise notice 'vista al dia con las % columnas',
        (select count(*) from information_schema.columns
          where table_schema='pacs' and table_name='ig_senales');
end $$;
