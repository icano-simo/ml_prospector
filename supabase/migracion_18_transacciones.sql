-- ════════════════════════════════════════════════════════════════════════════
-- 18 · `pacs.transacciones`: el grano de la operación
-- ════════════════════════════════════════════════════════════════════════════
--
-- ⚠ NO APLICADA. Espera el OK de Isabella. Desde el 2026-09-23 las migraciones
--   se aplican a producción DESPUÉS del merge.
--
-- Por qué hace falta una tabla y no otro campo del jsonb
-- ------------------------------------------------------
-- El Overview es un resumen, y un resumen no se puede desarmar. Las «9 compras
-- sin originador» de una captura real no eran un dato que faltara: eran
-- compras cash. Sin el grano de la operación no había forma de saberlo, y el
-- veredicto quedaba incompleto sobre una ausencia que no existía.
--
-- Con una fila por cierre, tres cosas dejan de estimarse y pasan a derivarse:
-- cash contra financiadas, el loan mix, y la compuerta de exclusión por lender.
--
-- Lo que esta tabla NO TIENE, y no es un olvido
-- ---------------------------------------------
-- No hay columna para el nombre del comprador ni del vendedor, y no hay
-- columna para la calle. Inferir el origen de los compradores por sus
-- apellidos es ECOA Regulation B, y la única forma de no hacerlo por accidente
-- --hoy, o dentro de un año, por alguien que no leyó esto-- es no tener el
-- dato. El parser los lee para ubicar las demás columnas y los tira antes de
-- devolver nada.
--
-- La dirección se reduce a ciudad y ZIP por lo mismo: la calle identifica una
-- vivienda y una persona, y para lo que el motor hace --saber dónde trabaja--
-- el ZIP alcanza y sobra.
--
-- El check sobre `crudo` es REDUNDANTE A PROPÓSITO. El parser ya no los
-- devuelve y la API ya no los escribe; esto es la tercera vuelta, y falla
-- ruidosamente en la base si alguna vez las dos primeras se rompen a la vez.

create table if not exists pacs.transacciones (
    id              uuid primary key default gen_random_uuid(),
    upload_batch_id uuid not null references pacs.upload_batch(id),
    realtor_id      uuid not null references pacs.realtors(id),
    uploaded_at     timestamptz not null default now(),
    capturado_en    timestamptz not null default now(),

    -- La huella de la operación. NO incluye el monto del préstamo: una compra
    -- cash provisional que después aparece financiada es LA MISMA operación
    -- actualizada, y si el monto entrara sería una fila nueva que dobla el
    -- denominador.
    hash_fila       text not null,

    fecha           date,
    lado            text,
    ciudad          text,
    estado          text,
    zip             text,

    precio          numeric,
    lista           numeric,
    prestamo        numeric,
    enganche        numeric,

    proposito       text,
    tipo            text,
    tasa            numeric,
    plazo           text,

    -- `financiada`, `cash_provisional` o `cash_segun_mm`. Model Match dice:
    -- «Considered Cash until mortgage details are received. Mortgage details
    -- are typically received within 3 to 5 weeks». Así que «Cash» de hace
    -- nueve días y «Cash» de hace un año no son el mismo hecho, y guardarlos
    -- con la misma palabra hace que la ficha afirme que alguien pagó en
    -- efectivo cuando lo único cierto es que todavía no se sabe.
    -- `no_leido` ES UN ESTADO VALIDO, y tiene que poder guardarse.
    --
    -- La primera version del check no lo aceptaba, asi que una sola fila que
    -- el troceado no supo leer hacia fallar el insert de las 25 y la captura
    -- entera se quedaba sin operaciones. La fila que hay que poder auditar
    -- --justamente la que no se leyo-- era la unica que no entraba.
    --
    -- Se guarda para auditoria y NO se cuenta como nada: ni loan ni cash. El
    -- que bloquea es el veredicto, que queda en `pendiente` mientras haya una.
    estado_prestamo text not null,
    dias_desde_cierre   integer,
    recapturar_despues_de date,

    lo_nombre       text,
    lo_nmls         text,
    empleador       text,
    lender          text,
    lender_nmls     text,
    broker          text,
    title           text,
    constructor     text,

    agente_contraparte text,
    de_la_casa      boolean not null default false,
    aviso_suma      text,
    version_parser  text,
    crudo           jsonb,

    constraint tx_lado_valido check (
        lado is null or lado in ('compra', 'venta', 'ambos')),
    constraint tx_estado_prestamo_valido check (
        estado_prestamo in ('financiada', 'cash_provisional', 'cash_segun_mm',
                            'no_leido')),
    -- Una tasa en puntos base --«762.00%»-- pasa por un float perfectamente
    -- válido y sale en la ficha como una tasa. Aquí no entra.
    constraint tx_tasa_es_un_porcentaje check (
        tasa is null or (tasa > 0 and tasa < 20)),
    -- LA GUARDA REDUNDANTE. Ver la cabecera.
    constraint tx_sin_nombres_de_las_partes check (
        crudo is null or not (crudo ?| array[
            'buyers', 'sellers', 'compradores', 'vendedores',
            '_compradores', '_vendedores', 'direccion', 'calle'])),
    -- Dos filas idénticas dentro del mismo pegado son un error de captura, no
    -- dos operaciones. Entre lotes distintos sí se repiten: es una re-captura,
    -- y la vista se queda con la más nueva.
    constraint tx_una_vez_por_lote unique (upload_batch_id, hash_fila)
);

create index if not exists tx_por_realtor
    on pacs.transacciones (realtor_id, fecha desc);
create index if not exists tx_por_lote
    on pacs.transacciones (upload_batch_id);
create index if not exists tx_de_la_casa
    on pacs.transacciones (realtor_id) where de_la_casa;

comment on table pacs.transacciones is
'Una fila por cierre, de la pestaña Transactions de Model Match. Append-only.
SIN nombres de compradores ni vendedores y SIN calle: ECOA Regulation B. La
ausencia de esas columnas es la guarda, no un olvido.';

comment on column pacs.transacciones.estado_prestamo is
'«Cash» en Model Match significa «todavía no hay datos de préstamo», no
«pagó en efectivo». Por debajo de 35 días desde el cierre es cash_provisional
y la ficha no lo afirma. `no_leido` es la celda que no se pudo leer: se guarda
para auditoría, no cuenta como nada, y deja el veredicto en pendiente.';


-- ── La vista de lo vigente ─────────────────────────────────────────────────
--
-- `distinct on (realtor_id, hash_fila)` con la más nueva primero: una
-- re-captura de la misma operación --la que pasa de cash provisional a
-- financiada-- la actualiza en vez de duplicarla.
--
-- Las columnas van UNA POR UNA y no con `select *`: en Postgres un `select *`
-- congela la lista de columnas en el momento de crear la vista, así que una
-- columna nueva en la tabla no aparece nunca y nadie se entera.
create or replace view pacs.v_transacciones_current as
select distinct on (t.realtor_id, t.hash_fila)
    t.id, t.upload_batch_id, t.realtor_id, t.uploaded_at, t.capturado_en,
    t.hash_fila, t.fecha, t.lado, t.ciudad, t.estado, t.zip,
    t.precio, t.lista, t.prestamo, t.enganche,
    t.proposito, t.tipo, t.tasa, t.plazo,
    t.estado_prestamo, t.dias_desde_cierre, t.recapturar_despues_de,
    t.lo_nombre, t.lo_nmls, t.empleador, t.lender, t.lender_nmls, t.broker,
    t.title, t.constructor, t.agente_contraparte, t.de_la_casa,
    t.aviso_suma, t.version_parser
from pacs.transacciones t
join pacs.upload_batch b on b.id = t.upload_batch_id
where b.es_vigente
order by t.realtor_id, t.hash_fila, t.capturado_en desc, t.uploaded_at desc;

comment on view pacs.v_transacciones_current is
'Una fila por operación viva. La re-captura de la misma operación la actualiza
porque el hash no incluye el monto del préstamo.';


-- ── Permisos, igual que el resto de pacs ───────────────────────────────────
grant select on pacs.transacciones to anon, authenticated;
grant select on pacs.v_transacciones_current to anon, authenticated;

alter table pacs.transacciones enable row level security;

-- Lectura sí, escritura no: la escritura entra por la service key desde la
-- función, como todo lo demás. Sin GRANT de insert, Postgres corta ANTES de
-- mirar RLS -- que es justo la confusión de la migración 15.
drop policy if exists tx_lectura on pacs.transacciones;
create policy tx_lectura on pacs.transacciones for select using (true);


-- ── VERIFICACIÓN ───────────────────────────────────────────────────────────
--
-- Las dos mitades, porque una sola no prueba nada: un error de permisos al
-- insertar se ve idéntico esté o no la política de lectura.
--
--   1 · un SELECT como `anon` tiene que FUNCIONAR;
--   2 · un INSERT como `anon` tiene que FALLAR;
--   3 · el check de nombres tiene que RECHAZAR un crudo con `buyers`;
--   4 · el check de tasa tiene que RECHAZAR 762.
--
-- set role anon;
-- select count(*) from pacs.v_transacciones_current;                  -- ok
-- insert into pacs.transacciones (upload_batch_id, realtor_id, hash_fila,
--     estado_prestamo) values (gen_random_uuid(), gen_random_uuid(), 'x',
--     'financiada');                                                  -- falla
-- reset role;
-- insert into pacs.transacciones (upload_batch_id, realtor_id, hash_fila,
--     estado_prestamo, crudo)
--   select b.id, r.id, 'prueba-ecoa', 'financiada', '{"buyers": "X"}'::jsonb
--   from pacs.upload_batch b, pacs.realtors r limit 1;  -- falla por el check
-- insert into pacs.transacciones (upload_batch_id, realtor_id, hash_fila,
--     estado_prestamo, tasa)
--   select b.id, r.id, 'prueba-tasa', 'financiada', 762
--   from pacs.upload_batch b, pacs.realtors r limit 1;  -- falla por el check
