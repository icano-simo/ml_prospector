-- ════════════════════════════════════════════════════════════════════════════
-- Esquema PACS-H · para simoOS-prod, esquema `pacs`
-- ════════════════════════════════════════════════════════════════════════════
--
-- Proyecto COMPARTIDO (`simoOS-prod`; la ref esta en .env, no aca). Lo respaldan
-- varias apps independientes y en `public` viven 67 tablas de RRHH y nomina.
-- Nada de esto va en `public`.
--
-- NO ejecuta el paso de `pgrst.db_schemas`: ese va aparte, al final de este
-- archivo, comentado, porque hay que LEER la lista viva antes de reescribirla.
--
-- ── Las cuatro reglas de la skill simologic-supabase, aplicadas ─────────────
--
--   1 · esquema propio, nunca `public`
--   2 · el claim `pacs` en app_metadata.allowed_apps, verificado en las RLS y
--       no solo en la app: PostgREST es alcanzable con un JWT valido sin pasar
--       por el front
--   3 · las tablas de carga son append-only, con upload_batch_id y uploaded_at,
--       y una vista v_*_current que resuelve el lote vivo
--   4 · toda fuente nueva trae una llave que une con lo que ya existe. Los
--       nombres no son llave: licencia estatal para el realtor, NMLS para el
--       loan officer
--
-- ── Y las tres guardias del proyecto PACS ──────────────────────────────────
--
--   denominador       ningun porcentaje se guarda sin numerador y denominador
--   nada por descarte ningun booleano sobre una persona lleva DEFAULT false
--   ECOA              ninguna columna de apellido, etnia u origen

create schema if not exists pacs;
comment on schema pacs is
'Motor de scoring y prospeccion PACS-H. Separado de public, donde vive RRHH.';

-- pgcrypto suele estar ya instalada en el proyecto; se pide en `extensions`
-- para no crear un duplicado en otro esquema.
create extension if not exists pgcrypto with schema extensions;

set search_path = pacs, public, extensions;


-- ════════════════════════════════════════════════════════════════════════════
-- 0 · EL CLAIM · una sola funcion, usada por TODAS las politicas
-- ════════════════════════════════════════════════════════════════════════════
--
-- Se centraliza a proposito: si la comprobacion esta copiada en veinte
-- politicas, la vigesimoprimera se escribe mal y nadie lo nota.
--
-- COALESCE antes del `?` no es decorativo. `raw_app_meta_data -> 'allowed_apps'
-- ? 'x'` devuelve NULL, no false, cuando el usuario todavia no tiene el campo,
-- y cualquier `WHERE NOT (...)` construido sobre eso matchea cero filas en
-- silencio. Es el footgun documentado en la skill.

create or replace function pacs.tiene_acceso()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    (coalesce(
        (select raw_app_meta_data -> 'allowed_apps'
           from auth.users where id = auth.uid()),
        '[]'::jsonb
     ) ? 'pacs'),
    false
  );
$$;

comment on function pacs.tiene_acceso is
'El claim `pacs` en app_metadata.allowed_apps. Se verifica en las RLS y no solo
en la app: PostgREST es alcanzable con un JWT valido sin pasar por el front.';


-- ════════════════════════════════════════════════════════════════════════════
-- 1 · LOTES DE CARGA · el patron append-only
-- ════════════════════════════════════════════════════════════════════════════
--
-- Nada se borra al recargar. Si una captura sale mal se vuelve a la anterior
-- cambiando una fila, no restaurando un backup.

create table if not exists pacs.upload_batch (
    id              uuid primary key default gen_random_uuid(),
    fuente          text not null check (fuente in (
                        'modelmatch', 'instagram', 'mercados', 'libro_v3',
                        'census', 'licencias')),
    archivo         text,
    subido_por      uuid references auth.users(id),
    uploaded_at     timestamptz not null default now(),

    -- El lote vivo de cada fuente. Se apaga al llegar el siguiente, no se
    -- borra: `v_*_current` lee por aca.
    es_vigente      boolean not null default true,
    filas_esperadas integer,
    filas_cargadas  integer,
    nota            text
);

create index if not exists upload_batch_vigente
    on pacs.upload_batch (fuente, es_vigente, uploaded_at desc);

comment on table pacs.upload_batch is
'Un lote por carga. `es_vigente` resuelve cual manda; volver atras es apagar el
nuevo y encender el anterior.';


-- ════════════════════════════════════════════════════════════════════════════
-- 2 · IDENTIDAD
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists pacs.realtors (
    id                  uuid primary key default gen_random_uuid(),

    -- LA LLAVE. Licencia estatal: es lo unico que une este realtor con
    -- cualquier fuente futura. El nombre no es llave.
    licencia_estado     text,
    licencia_numero     text,

    telefono_e164       text,
    email_principal     text,
    nombre_completo     text not null,
    condado_fips        text,
    rango_volumen       text,

    clave_resolucion    text not null
        check (clave_resolucion in ('licencia', 'telefono', 'email',
                                    'nombre_condado_volumen')),
    match_confidence    numeric not null check (match_confidence between 0 and 1),

    -- Marca las filas que solo se pudieron resolver por nombre. No se
    -- prohiben -- el libro v3 llego asi-- pero quedan contables: es la deuda
    -- que hay que cerrar consiguiendo licencias.
    sin_llave_dura      boolean generated always as (
                            licencia_numero is null
                            and telefono_e164 is null
                            and email_principal is null
                        ) stored,

    brokerage           text,
    estado              text,
    unidades_ano        numeric,

    -- Exclusion dura: Everett Financial opera como Supreme Lending, NMLS 2129.
    -- Un realtor con originadores de Everett ya es cliente de la casa.
    -- NULL = no se verifico, que es distinto de false.
    es_cliente_de_la_casa      boolean,
    cliente_de_la_casa_motivo  text,

    creado_en           timestamptz not null default now(),
    actualizado_en      timestamptz not null default now(),

    unique (licencia_estado, licencia_numero)
);

comment on table pacs.realtors is
'NINGUNA columna de apellido, etnia u origen alimenta inferencia: ECOA
Regulation B. El apellido esta dentro de nombre_completo porque hay que
escribirle a la persona, no para deducir nada de el.';

comment on column pacs.realtors.sin_llave_dura is
'Sin licencia, telefono ni email no hay con que unir esta persona a una fuente
futura. En seis meses son la misma gente bajo cuatro formatos distintos.';


create table if not exists pacs.contactos (
    id              uuid primary key default gen_random_uuid(),
    realtor_id      uuid not null references pacs.realtors(id) on delete cascade,
    canal           text not null check (canal in ('email', 'telefono',
                                                   'instagram', 'web', 'otro')),
    valor           text not null,
    fuente          text not null,
    confianza       numeric check (confianza between 0 and 1),
    upload_batch_id uuid references pacs.upload_batch(id),
    uploaded_at     timestamptz not null default now(),
    vigente         boolean,
    unique (realtor_id, canal, valor, fuente)
);

comment on table pacs.contactos is
'Uno por canal y por fuente. NUNCA se sobrescribe: se acumulan. Model Match
reporta varios emails con distinta confianza y el nuestro puede ser su
secundario.';


-- ════════════════════════════════════════════════════════════════════════════
-- 3 · FUENTES · append-only, con su llave y su vista de lote vivo
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists pacs.capturas_modelmatch (
    id              uuid primary key default gen_random_uuid(),
    upload_batch_id uuid not null references pacs.upload_batch(id),
    uploaded_at     timestamptz not null default now(),

    realtor_id      uuid references pacs.realtors(id) on delete set null,
    -- LA LLAVE, obligatoria para el alcance 'perfil'. Sin licencia no hay con
    -- que unir esta captura a nadie dentro de seis meses.
    licencia_estado text,
    licencia_numero text,

    alcance         text not null check (alcance in ('perfil', 'mercado')),
    condado_fips    text,
    estado          text,

    texto_crudo     text not null,
    parseado        jsonb,
    version_parser  text,

    capturado_en    timestamptz not null default now(),
    rango_desde     date,
    rango_hasta     date,

    -- Regla 4 de la skill, como restriccion y no como costumbre.
    constraint captura_perfil_trae_llave check (
        alcance <> 'perfil' or licencia_numero is not null
    ),
    constraint captura_mercado_trae_geo check (
        alcance <> 'mercado' or condado_fips is not null or estado is not null
    )
);

create index if not exists capturas_mm_lote
    on pacs.capturas_modelmatch (upload_batch_id);

comment on column pacs.capturas_modelmatch.texto_crudo is
'Siempre. El parser va a cambiar y re-parsear es gratis; volver a capturar no,
y la prueba de Model Match vence el 1 de octubre de 2026.';


create table if not exists pacs.ig_crudo (
    id              uuid primary key default gen_random_uuid(),
    upload_batch_id uuid not null references pacs.upload_batch(id),
    uploaded_at     timestamptz not null default now(),

    realtor_id      uuid references pacs.realtors(id) on delete set null,
    handle          text,
    crudo           jsonb not null,
    capturado_en    timestamptz not null,
    via             text,
    estado_perfil   text
);

create index if not exists ig_crudo_lote on pacs.ig_crudo (upload_batch_id);

comment on column pacs.ig_crudo.crudo is
'El JSON de ig_raw/ tal cual, sin derivar nada. Hay una prueba en el scraper
que falla si aparece un campo derivado adentro.';


create table if not exists pacs.ig_senales (
    id                  uuid primary key default gen_random_uuid(),
    upload_batch_id     uuid not null references pacs.upload_batch(id),
    uploaded_at         timestamptz not null default now(),

    realtor_id          uuid references pacs.realtors(id) on delete set null,
    handle              text,

    -- Los NUEVE estados. `privado` solo con evidencia afirmativa: el texto
    -- literal de la pagina o el is_private del JSON. La ausencia de
    -- publicaciones NO es privacidad, y creerlo costo siete perfiles.
    estado_perfil       text not null check (estado_perfil in (
        'publico_leido', 'privado', 'no_encontrado', 'bloqueado',
        'handle_dudoso', 'muro_de_sesion', 'sin_grid', 'degradado', 'vacio')),
    estado_evidencia    text,
    handle_confianza    text check (handle_confianza in ('alta','media','baja')),

    senales             jsonb not null,
    captions_n          integer,
    comentarios_n       integer,
    paginacion_truncada boolean,
    capturado_en        timestamptz not null,
    desajuste_idioma    numeric
);

create index if not exists ig_senales_lote on pacs.ig_senales (upload_batch_id);

comment on column pacs.ig_senales.desajuste_idioma is
'Ratio de español en comentarios menos ratio en publicaciones, sobre piezas
CLASIFICABLES. El 26% de los comentarios son solo emoji y no tienen idioma.
NULL cuando no hay base de 5 piezas de cada lado.';


create table if not exists pacs.mercados (
    id              uuid primary key default gen_random_uuid(),
    upload_batch_id uuid not null references pacs.upload_batch(id),
    uploaded_at     timestamptz not null default now(),

    condado_fips    text,
    estado          text,
    nivel           text not null check (nivel in ('condado', 'estado')),
    fuente          text not null,
    metricas        jsonb not null,

    capturado_en    timestamptz not null,
    rango_desde     date,
    rango_hasta     date,

    check (nivel <> 'condado' or condado_fips is not null),
    check (nivel <> 'estado' or estado is not null)
);

create index if not exists mercados_lote on pacs.mercados (upload_batch_id);

comment on table pacs.mercados is
'La biblioteca de benchmarks. Un perfil individual de Model Match expira; un
benchmark de condado no. Por eso vive aparte de cualquier realtor.';


-- ── Las vistas de lote vivo ────────────────────────────────────────────────
--
-- Todo lo que consuma la app lee de estas, nunca de la tabla. La tabla tiene
-- el historico entero; la vista tiene lo vigente.

create or replace view pacs.v_capturas_modelmatch_current as
select c.*
  from pacs.capturas_modelmatch c
  join pacs.upload_batch b on b.id = c.upload_batch_id
 where b.es_vigente;

create or replace view pacs.v_ig_senales_current as
select s.*
  from pacs.ig_senales s
  join pacs.upload_batch b on b.id = s.upload_batch_id
 where b.es_vigente;

create or replace view pacs.v_ig_crudo_current as
select c.*
  from pacs.ig_crudo c
  join pacs.upload_batch b on b.id = c.upload_batch_id
 where b.es_vigente;

create or replace view pacs.v_mercados_current as
select m.*
  from pacs.mercados m
  join pacs.upload_batch b on b.id = m.upload_batch_id
 where b.es_vigente;

-- Las vistas heredan las RLS de sus tablas con security_invoker.
alter view pacs.v_capturas_modelmatch_current set (security_invoker = on);
alter view pacs.v_ig_senales_current           set (security_invoker = on);
alter view pacs.v_ig_crudo_current             set (security_invoker = on);
alter view pacs.v_mercados_current             set (security_invoker = on);


-- ════════════════════════════════════════════════════════════════════════════
-- 4 · GEOGRAFIA
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists pacs.realtor_mercados (
    realtor_id      uuid not null references pacs.realtors(id) on delete cascade,
    condado_fips    text not null,
    unidades        numeric,
    fuente          text not null,
    upload_batch_id uuid references pacs.upload_batch(id),
    uploaded_at     timestamptz not null default now(),
    primary key (realtor_id, condado_fips, fuente)
);

create table if not exists pacs.census_condados (
    condado_fips    text primary key,
    estado          text not null,
    nombre          text,
    variables       jsonb not null,
    anio_acs        integer not null,
    upload_batch_id uuid references pacs.upload_batch(id),
    uploaded_at     timestamptz not null default now()
);

comment on table pacs.census_condados is
'Una fila por condado. Las variables de condado describen DONDE opera, no quien
es: no se usan para clasificar a una persona.';


-- ════════════════════════════════════════════════════════════════════════════
-- 5 · ORIGINADORES Y LENDERS · la llave es el NMLS
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists pacs.lenders (
    id                  uuid primary key default gen_random_uuid(),
    nombre              text not null,
    nmls                text,              -- LA LLAVE
    nombre_comercial    text,
    es_la_casa          boolean not null default false,
    unique (nmls)
);

insert into pacs.lenders (nombre, nmls, nombre_comercial, es_la_casa)
values ('Everett Financial', '2129', 'Supreme Lending', true)
on conflict (nmls) do nothing;

create table if not exists pacs.originadores (
    id              uuid primary key default gen_random_uuid(),
    nombre          text not null,
    nmls            text,                  -- LA LLAVE. Los nombres no lo son.
    lender_id       uuid references pacs.lenders(id) on delete set null,
    empresa_texto   text,
    sin_llave_dura  boolean generated always as (nmls is null) stored,
    unique (nmls)
);

comment on table pacs.originadores is
'Sin columnas de apellido, etnia u origen. ECOA aplica tambien a los loan
officers. `sin_llave_dura` marca los que llegaron sin NMLS: son los que en seis
meses aparecen cuatro veces con cuatro grafias.';

create table if not exists pacs.realtor_originadores (
    realtor_id      uuid not null references pacs.realtors(id) on delete cascade,
    originador_id   uuid not null references pacs.originadores(id) on delete cascade,
    unidades        numeric,
    -- El wallet share solo se calcula sobre buyside: en un agente de listados
    -- el lender que aparece no es su socio, es el del comprador que trajo otro
    -- agente.
    lado            text not null check (lado in ('buyside','listside','desconocido')),
    fuente          text not null,
    upload_batch_id uuid references pacs.upload_batch(id),
    uploaded_at     timestamptz not null default now(),
    primary key (realtor_id, originador_id, lado, fuente)
);


-- ════════════════════════════════════════════════════════════════════════════
-- 6 · REGLAS · proyeccion del catalogo de Python
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists pacs.reglas (
    id              text primary key,
    qualifier       text not null,
    familia         text not null check (familia in ('P','J','G')),
    intensidad      integer not null check (intensidad between 0 and 3),
    grado           text not null check (grado in ('E0','E1','E2','E3')),
    texto           text not null,
    campos          text[] not null,
    -- 'propia': escrita para operar con los nueve campos que da un lote de
    -- Instagram. 'matriz': una de las 124 de la matriz PACS-H, que necesitan
    -- 88 campos. El reemplazo tiene que ser un cambio de datos, no una
    -- reescritura.
    origen          text not null check (origen in ('propia','matriz')),
    referencia      text,
    discrepancia    text,
    gancho          text,
    version         text not null,
    activa          boolean not null default true,
    creada_en       timestamptz not null default now(),
    check (array_length(campos, 1) >= 1)
);

comment on table pacs.reglas is
'El catalogo de Python es la fuente de verdad; esto es su proyeccion. Lo genera
motor/sincronizar_reglas.py, nunca al reves.';


-- ════════════════════════════════════════════════════════════════════════════
-- 7 · EVALUACIONES · append-only, desde el dia uno
-- ════════════════════════════════════════════════════════════════════════════
--
-- No es auditoria: es la infraestructura de la correlacion futura. Dentro de
-- tres meses la pregunta va a ser que diagnostico predijo conversion, y el
-- historico no se puede reconstruir hacia atras.

create table if not exists pacs.evaluaciones (
    id                  uuid primary key default gen_random_uuid(),
    realtor_id          uuid not null references pacs.realtors(id) on delete cascade,
    evaluado_en         timestamptz not null default now(),

    version_reglas      text not null,
    -- Detecta un cambio no declarado: si alguien toca una intensidad sin subir
    -- la version, las evaluaciones viejas y las nuevas serian indistinguibles.
    huella_reglas       text not null,

    resultado           jsonb not null,
    dolor_primario      text,
    dolores_secundarios text[],
    moduladores         text[],
    apertura            text,
    gating_qualifier    text,
    gating_intensidad   integer,

    no_evaluadas        jsonb not null default '[]'::jsonb,
    campos_ausentes     text[] not null default '{}',
    confianza           jsonb,
    entrada             jsonb not null
);

create index if not exists evaluaciones_realtor_fecha
    on pacs.evaluaciones (realtor_id, evaluado_en desc);
create index if not exists evaluaciones_primario
    on pacs.evaluaciones (dolor_primario, evaluado_en desc);

comment on table pacs.evaluaciones is
'APPEND-ONLY. No hay politica de UPDATE ni de DELETE, asi que nadie puede
borrar el historico -- mismo patron que uploads.load_log.';


create table if not exists pacs.evaluacion_contrastes (
    id                  uuid primary key default gen_random_uuid(),
    evaluacion_id       uuid not null references pacs.evaluaciones(id) on delete cascade,
    nombre              text not null,

    agente_num          numeric,
    agente_den          numeric,
    mercado_num         numeric,
    mercado_den         numeric,
    distancia           numeric,
    unidad              text,

    -- Cuando un contraste admite mas de una explicacion, se emiten las dos.
    -- Cero FHA en un mercado del 21,5% significa una de dos cosas: sirve a
    -- compradores repetidos, o esta perdiendo a los primerizos.
    ramas               text[],

    fuente_mercado      text,
    mercado_capturado_en timestamptz,

    -- Las guardias, como restricciones.
    check (agente_num is null or agente_den is not null),
    check (mercado_num is null or mercado_den is not null),
    check (nombre <> 'mix_prestamo' or agente_den >= 10)
);

comment on table pacs.evaluacion_contrastes is
'Se guarda el contraste, no solo la conclusion: es lo que permitira medir
despues que contrastes predijeron conversion.';


-- ════════════════════════════════════════════════════════════════════════════
-- 8 · RLS · en TODAS las tablas, verificando el claim
-- ════════════════════════════════════════════════════════════════════════════
--
-- La skill documenta que en este proyecto las RLS NO son uniformes: b2b_metrics
-- aparecio con RLS desactivada en 14 de 15 tablas y `anon` con DELETE y
-- TRUNCATE. Eso es deuda conocida de otra app. Aca se arranca cerrado.
--
-- `anon` no recibe NADA: esto son datos de contacto de personas y inteligencia
-- comercial, no hay caso de uso anonimo.

do $$
declare t text;
begin
  foreach t in array array[
    'upload_batch','realtors','contactos','capturas_modelmatch','ig_crudo',
    'ig_senales','mercados','realtor_mercados','census_condados','lenders',
    'originadores','realtor_originadores','reglas','evaluaciones',
    'evaluacion_contrastes'
  ] loop
    execute format('alter table pacs.%I enable row level security', t);
    execute format('alter table pacs.%I force row level security', t);

    -- Lectura: solo con el claim.
    execute format($f$
      create policy %I on pacs.%I for select to authenticated
      using (pacs.tiene_acceso())
    $f$, t || '_select', t);
  end loop;
end $$;

-- Escritura: solo `service_role`, que es quien corre el motor y los cargadores.
-- Un usuario con el claim lee; no escribe. Las evaluaciones y los lotes no se
-- editan desde el navegador.
do $$
declare t text;
begin
  foreach t in array array[
    'upload_batch','realtors','contactos','capturas_modelmatch','ig_crudo',
    'ig_senales','mercados','realtor_mercados','census_condados','lenders',
    'originadores','realtor_originadores','reglas','evaluaciones',
    'evaluacion_contrastes'
  ] loop
    execute format($f$
      create policy %I on pacs.%I for insert to service_role with check (true)
    $f$, t || '_insert', t);
  end loop;
end $$;

-- UPDATE y DELETE: solo donde tiene sentido. `evaluaciones`,
-- `evaluacion_contrastes`, `capturas_modelmatch`, `ig_crudo` e `ig_senales`
-- quedan SIN politica de update ni de delete: son append-only y nadie puede
-- borrar el historico, ni siquiera service_role a traves de PostgREST.
do $$
declare t text;
begin
  foreach t in array array[
    'upload_batch','realtors','contactos','realtor_mercados','census_condados',
    'lenders','originadores','realtor_originadores','reglas'
  ] loop
    execute format($f$
      create policy %I on pacs.%I for update to service_role
      using (true) with check (true)
    $f$, t || '_update', t);
  end loop;
end $$;


-- ════════════════════════════════════════════════════════════════════════════
-- 9 · GRANTS · por tabla, nunca por esquema entero
-- ════════════════════════════════════════════════════════════════════════════
--
-- La skill: "Grants are given per table, never per schema wholesale". Y el
-- caso real que lo motivo: service_role tenia USAGE solo en b2b_metrics, por
-- eso cinco tablas funcionaban y la sexta no.

grant usage on schema pacs to authenticated, service_role;
revoke all on schema pacs from anon;

do $$
declare t text;
begin
  foreach t in array array[
    'upload_batch','realtors','contactos','capturas_modelmatch','ig_crudo',
    'ig_senales','mercados','realtor_mercados','census_condados','lenders',
    'originadores','realtor_originadores','reglas','evaluaciones',
    'evaluacion_contrastes'
  ] loop
    execute format('grant select on pacs.%I to authenticated', t);
    execute format('grant select, insert on pacs.%I to service_role', t);
    execute format('revoke all on pacs.%I from anon', t);
  end loop;
end $$;

-- UPDATE solo en las que no son append-only.
do $$
declare t text;
begin
  foreach t in array array[
    'upload_batch','realtors','contactos','realtor_mercados','census_condados',
    'lenders','originadores','realtor_originadores','reglas'
  ] loop
    execute format('grant update on pacs.%I to service_role', t);
  end loop;
end $$;

grant select on pacs.v_capturas_modelmatch_current,
                pacs.v_ig_senales_current,
                pacs.v_ig_crudo_current,
                pacs.v_mercados_current
      to authenticated, service_role;


-- ════════════════════════════════════════════════════════════════════════════
-- 10 · LO QUE NO VA EN ESTE ARCHIVO
-- ════════════════════════════════════════════════════════════════════════════
--
-- ── A · exponer el esquema en PostgREST ────────────────────────────────────
--
-- NO se hace aca a proposito: hay que LEER la lista viva primero. Se reseteo
-- sola dos veces y tumbo apps que funcionaban, asi que nunca se asume cual era.
--
-- Paso 1 · leer:
--
--   SELECT setconfig FROM pg_db_role_setting drs
--     JOIN pg_roles r ON r.oid = drs.setrole
--    WHERE r.rolname = 'authenticator';
--
-- Paso 2 · tomar la lista COMPLETA que devuelva, agregarle `pacs` al final, y
-- reescribirla entera. La lista conocida al 2026-08-17 era
--   public, b2b_metrics, activity_report, pipeline_forecast, finance_pl,
--   hr_us_payroll, finance_division, org, business_plan
-- pero `org` y `business_plan` aparecieron despues de la comprobacion anterior,
-- asi que esa lista es una referencia, NO la fuente. La fuente es el paso 1.
--
--   ALTER ROLE authenticator SET pgrst.db_schemas = '<lo que devolvio>,pacs';
--   NOTIFY pgrst, 'reload config';
--
-- Paso 3 · volver a leer y confirmar que estan TODAS, no solo `pacs`.
--
-- ── B · el claim a los usuarios ────────────────────────────────────────────
--
-- `pacs` en app_metadata.allowed_apps. Va por script con service_role, y el
-- script tiene que RELEER la fila despues de escribir: un script que reporta
-- exito porque la llamada no dio error ya mintio en este proyecto.
--
-- Y nunca reescribir el app_metadata entero: `provider` y `providers` son
-- claims reservados de GoTrue y respetarlos de vuelta puede hacer que la
-- escritura se descarte en silencio. jsonb_set sobre la clave sola.
--
-- ── C · rotar la service_role ──────────────────────────────────────────────
--
-- Estuvo en .env.example y paso por un canal de chat. Abre la nomina.
-- Despues de rotar hay que actualizarla en dos lugares por app: el .env.local
-- y las tres variables de entorno de Vercel, y redesplegar.
--
-- ── D · el timeout ────────────────────────────────────────────────────────
--
-- `authenticator` lleva statement_timeout=8s y lock_timeout=8s. Toda carga por
-- PostgREST va en lotes: 500 filas por upsert es comodo. Los 4.249 realtors del
-- libro v3 son nueve lotes.
