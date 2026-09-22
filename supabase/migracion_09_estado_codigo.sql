-- ════════════════════════════════════════════════════════════════════════════
-- 09 · UNA sola representacion del estado: el codigo de dos letras
-- ════════════════════════════════════════════════════════════════════════════
--
-- `pacs.realtors.estado` guardaba `California` y `pacs.census_condados.estado`
-- guarda `CA`. **Ninguna de las 4.249 filas cruzaba con ninguno de los 2.261
-- condados**, y el join no fallaba: devolvia cero, que se lee igual que "este
-- realtor no opera en ningun condado con datos".
--
-- La decision: **el codigo de dos letras manda en las tablas del motor.** El
-- nombre completo es para mostrar, y sale de `captura/estados.py` -- no de una
-- columna, para que no haya dos sitios donde pueda divergir.
--
-- Y el invariante lo impone la BASE, no una convencion. Un `check` que rechace
-- `California` es lo unico que impide que la proxima carga vuelva a meter el
-- nombre largo: una regla escrita en un documento no frena un INSERT.

begin;

-- ── 1 · el mapa, como tabla temporal para no repetirlo tres veces ──────────
create temporary table _estados (nombre text primary key, codigo text not null)
on commit drop;

insert into _estados (nombre, codigo) values
 ('Alabama','AL'),('Alaska','AK'),('Arizona','AZ'),('Arkansas','AR'),
 ('California','CA'),('Colorado','CO'),('Connecticut','CT'),('Delaware','DE'),
 ('District of Columbia','DC'),('Florida','FL'),('Georgia','GA'),('Hawaii','HI'),
 ('Idaho','ID'),('Illinois','IL'),('Indiana','IN'),('Iowa','IA'),
 ('Kansas','KS'),('Kentucky','KY'),('Louisiana','LA'),('Maine','ME'),
 ('Maryland','MD'),('Massachusetts','MA'),('Michigan','MI'),('Minnesota','MN'),
 ('Mississippi','MS'),('Missouri','MO'),('Montana','MT'),('Nebraska','NE'),
 ('Nevada','NV'),('New Hampshire','NH'),('New Jersey','NJ'),('New Mexico','NM'),
 ('New York','NY'),('North Carolina','NC'),('North Dakota','ND'),('Ohio','OH'),
 ('Oklahoma','OK'),('Oregon','OR'),('Pennsylvania','PA'),('Rhode Island','RI'),
 ('South Carolina','SC'),('South Dakota','SD'),('Tennessee','TN'),('Texas','TX'),
 ('Utah','UT'),('Vermont','VT'),('Virginia','VA'),('Washington','WA'),
 ('West Virginia','WV'),('Wisconsin','WI'),('Wyoming','WY'),
 ('Puerto Rico','PR'),('Guam','GU'),('U.S. Virgin Islands','VI');

-- ── 2 · lo que NO se va a poder convertir, ANTES de convertir nada ─────────
do $$
declare
    huerfanos text[];
begin
    select array_agg(distinct r.estado) into huerfanos
      from pacs.realtors r
     where r.estado is not null
       and length(r.estado) <> 2
       and not exists (select 1 from _estados e
                        where lower(e.nombre) = lower(trim(r.estado)));
    if huerfanos is not null then
        raise exception
            'estos valores de `estado` no estan en el mapa y quedarian sin '
            'convertir: %. No se toca nada: media tabla en codigo y media en '
            'nombre es peor que toda en nombre.', huerfanos;
    end if;
end $$;

-- ── 3 · la conversion ──────────────────────────────────────────────────────
update pacs.realtors r
   set estado = e.codigo
  from _estados e
 where lower(e.nombre) = lower(trim(r.estado))
   and r.estado is distinct from e.codigo;

update pacs.realtors set estado = upper(trim(estado))
 where estado is not null and length(trim(estado)) = 2;

-- ── 4 · el invariante, impuesto ────────────────────────────────────────────
alter table pacs.realtors drop constraint if exists realtors_estado_codigo;
alter table pacs.realtors add constraint realtors_estado_codigo
    check (estado is null or estado ~ '^[A-Z]{2}$');

alter table pacs.capturas_modelmatch
    drop constraint if exists capturas_mm_estado_codigo;
alter table pacs.capturas_modelmatch add constraint capturas_mm_estado_codigo
    check (estado is null or estado ~ '^[A-Z]{2}$');

alter table pacs.census_condados
    drop constraint if exists census_condados_estado_codigo;
alter table pacs.census_condados add constraint census_condados_estado_codigo
    check (estado ~ '^[A-Z]{2}$');

comment on column pacs.realtors.estado is
'Codigo de DOS LETRAS, siempre. El nombre completo es para mostrar y sale de
captura/estados.py, no de una columna: dos sitios donde escribirlo son dos
sitios donde puede divergir. El check lo impone.';

-- ── 5 · la comprobacion, sobre el cruce que antes daba cero ────────────────
do $$
declare
    con_census integer;
    total integer;
    largos integer;
begin
    select count(*) into largos from pacs.realtors
     where estado is not null and length(estado) <> 2;
    if largos > 0 then
        raise exception 'quedaron % filas con estado largo', largos;
    end if;

    select count(*) into total from pacs.realtors where estado is not null;
    select count(*) into con_census
      from pacs.realtors r
     where r.estado is not null
       and exists (select 1 from pacs.census_condados c
                    where c.estado = r.estado);

    raise notice 'realtors con estado: % · con Census en su estado: % (%%%)',
        total, con_census, round(100.0 * con_census / nullif(total, 0), 1);

    if con_census = 0 then
        raise exception 'el cruce con census_condados sigue dando CERO';
    end if;
end $$;

commit;
