-- ════════════════════════════════════════════════════════════════════════════
-- Esquema PACS-H · Etapa 1
-- ════════════════════════════════════════════════════════════════════════════
--
-- Un solo motor: el Python. Vercel solo muestra. Nada de logica de scoring en
-- esta base mas alla de las restricciones que hacen imposible guardar algo que
-- el motor no podria haber producido.
--
-- Las tres guardias del proyecto estan puestas donde se pueden hacer cumplir:
--
--   denominador       ninguna tabla guarda un porcentaje sin su numerador y su
--                     denominador al lado. Ver `evaluacion_contrastes`.
--   nada por descarte los booleanos que describen a una persona son NULLABLE y
--                     van con su razon. No hay DEFAULT false en ninguno.
--   ECOA              no existe ninguna columna de apellido, etnia u origen
--                     destinada a inferencia, y hay un comentario en cada tabla
--                     que lo dice para quien vaya a agregar una.

create extension if not exists "pgcrypto";

-- ════════════════════════════════════════════════════════════════════════════
-- 1 · IDENTIDAD
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists realtors (
    id                  uuid primary key default gen_random_uuid(),

    -- La cascada de resolucion, en orden de fuerza. `clave_resolucion` dice
    -- cual de los cuatro niveles resolvio ESTA fila, porque no es lo mismo
    -- haber cruzado por licencia estatal que por nombre y condado.
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
    -- 0 a 1. Va con la clave: una confianza sin decir de que cruce salio no
    -- se puede interpretar.
    match_confidence    numeric not null check (match_confidence between 0 and 1),

    brokerage           text,
    estado              text,
    unidades_ano        numeric,

    -- EXCLUSION DURA. Everett Financial opera como Supreme Lending, NMLS 2129.
    -- Un realtor con originadores de Everett ya es cliente de la casa:
    -- prospectarlo es competirle a un colega.
    es_cliente_de_la_casa      boolean,
    cliente_de_la_casa_motivo  text,

    creado_en           timestamptz not null default now(),
    actualizado_en      timestamptz not null default now(),

    -- Un mismo numero de licencia no puede estar dos veces en el mismo estado.
    unique (licencia_estado, licencia_numero)
);

comment on table realtors is
'Ficha base. NINGUNA columna de apellido, etnia u origen alimenta inferencia:
ECOA Regulation B. El apellido esta dentro de nombre_completo porque hay que
escribirle a la persona, no para deducir nada de el.';

comment on column realtors.es_cliente_de_la_casa is
'Exclusion dura, no un score. NULL = no se verifico, que es distinto de false.';


-- Un contacto por canal y por fuente. NUNCA se sobrescribe: se acumulan.
-- Model Match reporta varios emails con distinta confianza y no siempre
-- coincide con el del lote; el nuestro puede ser el secundario de ellos.
create table if not exists contactos (
    id              uuid primary key default gen_random_uuid(),
    realtor_id      uuid not null references realtors(id) on delete cascade,
    canal           text not null check (canal in ('email', 'telefono',
                                                   'instagram', 'web', 'otro')),
    valor           text not null,
    fuente          text not null,
    confianza       numeric check (confianza between 0 and 1),
    capturado_en    timestamptz not null default now(),
    vigente         boolean,

    -- El mismo valor, del mismo canal y la misma fuente, una sola vez.
    unique (realtor_id, canal, valor, fuente)
);

comment on table contactos is
'Append-only por convencion: no hay UPDATE en el cargador. Un contacto que deja
de servir se marca con vigente=false, no se borra ni se pisa.';


-- ════════════════════════════════════════════════════════════════════════════
-- 2 · FUENTES CRUDAS · el crudo se guarda siempre, porque el parser va a cambiar
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists capturas_modelmatch (
    id              uuid primary key default gen_random_uuid(),
    realtor_id      uuid references realtors(id) on delete set null,
    -- Puede no haber realtor todavia: primero se pega el texto, despues se cruza.
    alcance         text not null check (alcance in ('perfil', 'mercado')),
    condado_fips    text,
    estado          text,

    texto_crudo     text not null,
    parseado        jsonb,
    version_parser  text,

    -- Las trampas verificadas del perfil de prueba: los numeros se mueven
    -- dentro de la misma sesion, asi que cada captura lleva su sello y su
    -- rango, y sin eso no se puede comparar con otra.
    capturado_en    timestamptz not null default now(),
    rango_desde     date,
    rango_hasta     date,

    check (alcance <> 'mercado' or condado_fips is not null or estado is not null)
);

comment on column capturas_modelmatch.texto_crudo is
'Siempre. El parser va a cambiar y re-parsear es gratis; volver a capturar no,
y la prueba de Model Match vence.';


create table if not exists ig_crudo (
    id              uuid primary key default gen_random_uuid(),
    realtor_id      uuid references realtors(id) on delete set null,
    handle          text,
    crudo           jsonb not null,
    capturado_en    timestamptz not null,
    via             text,
    estado_perfil   text
);

comment on column ig_crudo.crudo is
'El JSON de ig_raw/ tal cual, sin derivar nada. Hay una prueba en el scraper
que falla si aparece un campo derivado adentro.';


create table if not exists ig_senales (
    id                  uuid primary key default gen_random_uuid(),
    realtor_id          uuid references realtors(id) on delete set null,
    handle              text,

    -- El estado del perfil, con los CUATRO valores nuevos. `privado` solo sale
    -- con evidencia afirmativa: el texto literal de la pagina o el is_private
    -- del JSON. La ausencia de publicaciones NO es privacidad, y creerlo costo
    -- siete perfiles del piloto.
    estado_perfil       text not null check (estado_perfil in (
        'publico_leido', 'privado', 'no_encontrado', 'bloqueado',
        'handle_dudoso', 'muro_de_sesion', 'sin_grid', 'degradado', 'vacio')),
    estado_evidencia    text,
    handle_confianza    text check (handle_confianza in ('alta', 'media', 'baja')),

    -- Las 50 columnas de ig_signals.csv entran aca. Se guardan como jsonb en
    -- vez de 50 columnas porque el contrato del CSV ya cambio tres veces y va
    -- a volver a cambiar; lo que NO cambia es que cada fila lleve su estado y
    -- su denominador, y eso si son columnas.
    senales             jsonb not null,

    captions_n          integer,
    comentarios_n       integer,
    paginacion_truncada boolean,
    capturado_en        timestamptz not null,

    -- El campo mas valioso de la capa: su publico le escribe en español
    -- mientras el publica en ingles. NULL cuando no hay base suficiente de
    -- piezas clasificables de cada lado: un desajuste sobre un comentario no
    -- es una medicion.
    desajuste_idioma    numeric
);

comment on column ig_senales.desajuste_idioma is
'ratio de español en comentarios menos ratio en publicaciones, sobre piezas
CLASIFICABLES. El 26% de los comentarios son solo emoji y no tienen idioma.';


-- ════════════════════════════════════════════════════════════════════════════
-- 3 · MERCADOS · no pertenecen a ningun realtor
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists mercados (
    id              uuid primary key default gen_random_uuid(),
    -- Clave: FIPS del condado, o codigo de estado cuando el dato es estatal.
    condado_fips    text,
    estado          text,
    nivel           text not null check (nivel in ('condado', 'estado')),

    fuente          text not null,
    metricas        jsonb not null,

    -- Envejece. Un benchmark sin fecha no se puede comparar con otro.
    capturado_en    timestamptz not null,
    rango_desde     date,
    rango_hasta     date,

    check (nivel <> 'condado' or condado_fips is not null),
    check (nivel <> 'estado' or estado is not null)
);

comment on table mercados is
'La biblioteca de benchmarks. Un perfil individual de Model Match expira; un
benchmark de condado no. Por eso vive aparte de cualquier realtor y sirve para
todos los que operan ahi.';


create table if not exists realtor_mercados (
    realtor_id      uuid not null references realtors(id) on delete cascade,
    condado_fips    text not null,
    unidades        numeric,
    -- Cual es el dominante se calcula de las unidades, no se declara a mano.
    fuente          text not null,
    capturado_en    timestamptz not null default now(),
    primary key (realtor_id, condado_fips, fuente)
);


create table if not exists census_condados (
    condado_fips    text primary key,
    estado          text not null,
    nombre          text,
    variables       jsonb not null,
    anio_acs        integer not null,
    cargado_en      timestamptz not null default now()
);

comment on table census_condados is
'Una fila por condado. Las variables de tract y de condado describen DONDE
opera, no quien es: no se usan para clasificar a una persona.';


-- ════════════════════════════════════════════════════════════════════════════
-- 4 · ORIGINADORES Y LENDERS
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists lenders (
    id                  uuid primary key default gen_random_uuid(),
    nombre              text not null,
    nmls                text,
    -- Everett Financial opera como Supreme Lending, NMLS 2129.
    nombre_comercial    text,
    es_la_casa          boolean not null default false,
    unique (nmls)
);

insert into lenders (nombre, nmls, nombre_comercial, es_la_casa)
values ('Everett Financial', '2129', 'Supreme Lending', true)
on conflict (nmls) do nothing;


create table if not exists originadores (
    id              uuid primary key default gen_random_uuid(),
    nombre          text not null,
    nmls            text,
    lender_id       uuid references lenders(id) on delete set null,
    empresa_texto   text,
    unique (nmls)
);

comment on table originadores is
'Sin ninguna columna de apellido, etnia u origen para inferencia. La regla ECOA
aplica tambien a los loan officers.';


create table if not exists realtor_originadores (
    realtor_id      uuid not null references realtors(id) on delete cascade,
    originador_id   uuid not null references originadores(id) on delete cascade,
    unidades        numeric,
    -- Solo buyside. En un agente de listados el lender que aparece NO es su
    -- socio: es el del comprador que trajo otro agente.
    lado            text not null check (lado in ('buyside', 'listside',
                                                  'desconocido')),
    fuente          text not null,
    capturado_en    timestamptz not null default now(),
    primary key (realtor_id, originador_id, lado, fuente)
);


-- ════════════════════════════════════════════════════════════════════════════
-- 5 · LAS REGLAS · declaradas, versionadas, con su origen
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists reglas (
    id              text primary key,
    qualifier       text not null,
    familia         text not null check (familia in ('P', 'J', 'G')),
    intensidad      integer not null check (intensidad between 0 and 3),
    grado           text not null check (grado in ('E0', 'E1', 'E2', 'E3')),
    texto           text not null,
    campos          text[] not null,

    -- "propia": escrita a mano para operar con los nueve campos que da un lote
    -- de Instagram. "matriz": una de las 124 reglas de inferencia de la matriz
    -- PACS-H, que necesitan 88 campos del diccionario canonico.
    --
    -- A medida que aparezcan campos, las propias se reemplazan por las de la
    -- matriz, que son mejores. Este campo existe para que ese reemplazo sea un
    -- cambio de datos y no una reescritura.
    origen          text not null check (origen in ('propia', 'matriz')),

    referencia      text,
    discrepancia    text,
    gancho          text,

    version         text not null,
    activa          boolean not null default true,
    creada_en       timestamptz not null default now(),

    check (array_length(campos, 1) >= 1)
);

comment on column reglas.campos is
'Los campos que la condicion lee. Sin esto no se puede verificar contra ECOA ni
saber por que una regla no se pudo evaluar.';

comment on column reglas.discrepancia is
'Anotada cuando el prototipo hace algo distinto de lo documentado. No se
resuelve en el codigo: se declara y se mide.';


-- ════════════════════════════════════════════════════════════════════════════
-- 6 · EVALUACIONES · append-only, desde el dia uno
-- ════════════════════════════════════════════════════════════════════════════
--
-- Esto no es auditoria. Es la infraestructura de la correlacion futura: dentro
-- de tres meses, con resultados de prospeccion reales, la pregunta va a ser
-- QUE DIAGNOSTICO PREDIJO CONVERSION. Sin el historico de evaluaciones no se
-- puede responder, y el historico no se puede reconstruir hacia atras.
--
-- Por eso la tabla existe hoy aunque todavia no sirva para nada.

create table if not exists evaluaciones (
    id                  uuid primary key default gen_random_uuid(),
    realtor_id          uuid not null references realtors(id) on delete cascade,
    evaluado_en         timestamptz not null default now(),

    -- Con que reglas se produjo. La huella detecta un cambio no declarado: si
    -- alguien toca una intensidad y no sube la version, las evaluaciones
    -- viejas y las nuevas quedarian indistinguibles.
    version_reglas      text not null,
    huella_reglas       text not null,

    -- La evaluacion completa, con la cadena de evidencia de cada activacion.
    resultado           jsonb not null,

    dolor_primario      text,
    dolores_secundarios text[],
    gating_qualifier    text,
    gating_intensidad   integer,

    -- Las reglas que NO se pudieron evaluar, con el campo que faltaba. Una
    -- regla no evaluada no es una regla que no aplica.
    no_evaluadas        jsonb not null default '[]'::jsonb,
    campos_ausentes     text[] not null default '{}',

    -- El snapshot del registro de entrada. Sin esto, dentro de tres meses se
    -- sabe que salio pero no de que entro.
    entrada             jsonb not null
);

create index if not exists evaluaciones_realtor_fecha
    on evaluaciones (realtor_id, evaluado_en desc);
create index if not exists evaluaciones_primario
    on evaluaciones (dolor_primario, evaluado_en desc);

comment on table evaluaciones is
'APPEND-ONLY. No hay UPDATE ni DELETE en el cargador. Una evaluacion corregida
es una evaluacion nueva, y las dos quedan.';


-- Los contrastes, aparte, porque lo que se va a querer correlacionar despues es
-- el CONTRASTE y no la conclusion. "FHA del agente contra FHA del mercado" con
-- sus dos numeros es lo que permite preguntar despues que contraste predijo
-- conversion; "activa P-Q01" no.
create table if not exists evaluacion_contrastes (
    id                  uuid primary key default gen_random_uuid(),
    evaluacion_id       uuid not null references evaluaciones(id) on delete cascade,
    nombre              text not null,

    -- El valor del agente y el de su mercado, con sus denominadores. Un
    -- porcentaje sin denominador no se guarda: el CHECK lo impide.
    agente_num          numeric,
    agente_den          numeric,
    mercado_num         numeric,
    mercado_den         numeric,
    distancia           numeric,
    unidad              text,

    -- Cuando un contraste admite mas de una explicacion, se emiten las dos.
    -- Cero FHA en un mercado del 21,5% significa una de dos cosas: sirve a
    -- compradores repetidos, o esta perdiendo a los primerizos. Esa disyuntiva
    -- es la pregunta del primer mensaje.
    ramas               text[],

    fuente_mercado      text,
    mercado_capturado_en timestamptz,

    -- Sin denominador no hay porcentaje. La guardia, como restriccion.
    check (agente_num is null or agente_den is not null),
    check (mercado_num is null or mercado_den is not null),
    -- Y el denominador minimo del mix de prestamo: menos de 10 operaciones con
    -- tipo identificado no activa ni desactiva nada.
    check (nombre <> 'mix_prestamo' or agente_den >= 10)
);

comment on table evaluacion_contrastes is
'Se guarda el contraste, no solo la conclusion. Es lo que permitira medir
despues que contrastes predijeron conversion.';
