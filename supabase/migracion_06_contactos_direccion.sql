-- ════════════════════════════════════════════════════════════════════════════
-- 06 · pacs.contactos acepta oficina y direccion
-- ════════════════════════════════════════════════════════════════════════════
--
-- Model Match trae en la cabecera del perfil tres datos de contacto que hoy no
-- tienen canal donde entrar:
--
--   Exp Realty Of California Inc.   el nombre de la oficina
--   2603 Camino Ramon               la calle
--   San Ramon CA 94583              ciudad, estado y codigo postal
--   Office: (888) 584-9427          el telefono, que si tiene canal
--
-- Mandarlos a 'otro' los deja indistinguibles entre si: una consulta que busque
-- la direccion tendria que adivinar cual de los 'otro' lo es. Dos canales
-- nuevos cuestan una linea y evitan eso.
--
-- La acumulacion ya estaba resuelta: `unique (realtor_id, canal, valor,
-- fuente)` incluye la fuente, asi que el telefono de Model Match convive con el
-- del lote en vez de pisarlo. Lo que hace falta del lado del cargador es
-- insertar con `resolution=ignore-duplicates`, porque capturar dos veces el
-- mismo perfil es normal y no deberia devolver un 409.

alter table pacs.contactos
    drop constraint if exists contactos_canal_check;

alter table pacs.contactos
    add constraint contactos_canal_check
    check (canal in ('email', 'telefono', 'instagram', 'web',
                     'oficina', 'direccion', 'otro'));

comment on column pacs.contactos.canal is
'email | telefono | instagram | web | oficina | direccion | otro.
`oficina` es el nombre de la empresa donde opera; `direccion` es la postal.';

-- Verificacion: que el constraint acepte lo nuevo y siga rechazando basura.
do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'pacs.contactos'::regclass
          and conname = 'contactos_canal_check'
          and pg_get_constraintdef(oid) like '%direccion%'
    ) then
        raise exception 'el check de canal no quedo con direccion';
    end if;
end $$;
