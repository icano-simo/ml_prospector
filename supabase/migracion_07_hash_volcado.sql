-- ════════════════════════════════════════════════════════════════════════════
-- 07 · huella del texto capturado, para detectar el volcado repetido
-- ════════════════════════════════════════════════════════════════════════════
--
-- El mismo perfil entro dos veces con un minuto de diferencia (19:10 y 19:11),
-- identico. Sobre 25 realtors eso no se nota mirando, y cada copia cuenta como
-- una captura mas en la biblioteca de geografias: el conteo de capturas por
-- mercado sale inflado y nadie sabe por cuanto.
--
-- NO lleva unique. Re-capturar el mismo perfil dentro de tres meses es
-- legitimo y la tabla es append-only: lo que hace falta es DETECTARLO y
-- preguntar, no impedirlo. La restriccion la pone el endpoint, que exige
-- `forzar` para guardar un volcado que ya esta.

alter table pacs.capturas_modelmatch
    add column if not exists hash_volcado text;

comment on column pacs.capturas_modelmatch.hash_volcado is
'sha256 del volcado COMPLETO de la captura (no de este bloque). Igual en todas
las filas de una misma captura. Sin unique a proposito: re-capturar es
legitimo, guardarlo sin darse cuenta no.';

create index if not exists capturas_mm_hash_idx
    on pacs.capturas_modelmatch (hash_volcado, realtor_id);

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'pacs' and table_name = 'capturas_modelmatch'
          and column_name = 'hash_volcado'
    ) then
        raise exception 'la columna hash_volcado no quedo';
    end if;
end $$;
