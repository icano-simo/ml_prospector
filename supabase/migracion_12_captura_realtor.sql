-- ════════════════════════════════════════════════════════════════════════════
-- 12 · una captura sin dueño no se guarda
-- ════════════════════════════════════════════════════════════════════════════
--
-- `pacs.capturas_modelmatch.realtor_id` existe desde el esquema original y
-- **estuvo NULL en las 60 filas**: `agregar()` en `api/rutas.py` escribia el
-- id dentro de `parseado` y nunca en la columna. Nadie lo noto porque
-- `capturas_que_mandan()` y `/api/capturas` leen `parseado->>realtor_id`, que
-- si estaba lleno. La columna no estaba rota: estaba muerta.
--
-- Una columna muerta no avisa. No hay error, no hay fila vacia que destaque,
-- ningun conteo se ve raro -- y cualquiera que la consulte concluye que las
-- capturas estan huerfanas cuando no lo estan. Eso ya paso.

-- ── 1 · lo que ya estaba en el jsonb ────────────────────────────────────────
-- Solo las que apuntan a un realtor QUE EXISTE. Los ensayos retirados usaron
-- ids sinteticos (`00000000-…-00ff`) que nunca estuvieron en `pacs.realtors`:
-- la clave foranea los rechaza, y hace bien.
update pacs.capturas_modelmatch c
   set realtor_id = (c.parseado->>'realtor_id')::uuid
  from pacs.realtors r
 where c.realtor_id is null
   and c.parseado->>'realtor_id' ~ '^[0-9a-f-]{36}$'
   and r.id = (c.parseado->>'realtor_id')::uuid;

-- ── 2 · las 7 que no lo traen por ningun lado ───────────────────────────────
-- Son el lote `edded21d`, un ENSAYO ya retirado (`es_vigente = false`) de la
-- pantalla vieja. Su crudo nombra a ARMANDO OCHOA y la nota del lote tambien,
-- asi que el dueño no se adivina: se lee. Rellenarlo no lo revive -- sigue
-- apagado a nivel de lote.
update pacs.capturas_modelmatch c
   set realtor_id = r.id
  from pacs.realtors r, pacs.upload_batch b
 where c.realtor_id is null
   and b.id = c.upload_batch_id
   and b.es_vigente = false
   and b.nota ilike '%realtor=Armando Ochoa%'
   and r.nombre_completo = 'ARMANDO OCHOA';

-- ── 3 · que no pueda volver a pasar ─────────────────────────────────────────
-- **NOT VALID a proposito, y no NOT NULL.** Quedan 33 filas de ensayo retirado
-- cuyo `realtor_id` apunta a personas que no existen: no se les puede poner un
-- dueño sin inventarlo, y crear un realtor de mentira para satisfacer una
-- restriccion es exactamente como se ensucia una tabla de identidad.
--
-- `not valid` rige **toda fila que se escriba o se actualice desde ahora** y
-- no toca la historia. Es la semantica que se quiere: la restriccion es sobre
-- lo que el sistema produce, no sobre lo que ya produjo mal. Y que la
-- restriccion figure como no validada deja dicho, en el esquema, que hay
-- historia que no la cumple -- que es mas honesto que un NOT NULL comprado
-- reescribiendo el pasado.
alter table pacs.capturas_modelmatch
    drop constraint if exists capturas_mm_con_dueno;
alter table pacs.capturas_modelmatch
    add constraint capturas_mm_con_dueno check (realtor_id is not null)
    not valid;

create index if not exists capturas_mm_realtor
    on pacs.capturas_modelmatch (realtor_id);

comment on column pacs.capturas_modelmatch.realtor_id is
'De quien es esta captura. Estuvo NULL en las 60 primeras filas porque el
guardado solo escribia el id dentro de `parseado`. Se escribe en los dos sitios
a proposito: la columna lleva la restriccion y el indice, el jsonb es el que ya
leen `capturas_que_mandan` y /api/capturas. La restriccion
`capturas_mm_con_dueno` es NOT VALID porque 33 filas de ensayo retirado apuntan
a realtors sinteticos que nunca existieron.';

do $$
declare
    n int; llenas int; vivas_sin int;
begin
    select count(*), count(realtor_id) into n, llenas
      from pacs.capturas_modelmatch;
    select count(*) into vivas_sin
      from pacs.capturas_modelmatch c
      join pacs.upload_batch b on b.id = c.upload_batch_id
     where c.realtor_id is null and b.es_vigente;
    raise notice 'capturas: % · con dueño: % · sin dueño: % (todas en lotes '
                 'retirados) · capturas VIVAS sin dueño: %',
                 n, llenas, n - llenas, vivas_sin;
    if vivas_sin > 0 then
        raise exception 'hay % capturas vigentes sin realtor_id', vivas_sin;
    end if;
end $$;
