-- ════════════════════════════════════════════════════════════════════════════
-- Migracion 03 · las llaves que una captura de perfil SI puede traer
-- ════════════════════════════════════════════════════════════════════════════
--
-- La restriccion `captura_perfil_trae_llave` exigia `licencia_numero` para toda
-- captura de alcance 'perfil'. El espiritu es correcto -- no guardar una
-- captura que despues no se puede pegar a nadie-- y la lista estaba mal: **un
-- perfil de Model Match no trae la licencia estatal.**
--
-- Se descubrio al primer guardado real desde la pantalla, que fallo entero.
-- Fallar fue lo correcto; lo que estaba mal era el conjunto de llaves
-- aceptadas.
--
-- Las llaves que una captura de Model Match SI puede traer:
--
--   mmi_agent_id   esta en el propio perfil. Ya verificado contra un Fast Fact
--                  capturado: el de Lisa Munoz coincide exactamente.
--   sf_lead_id     si quien captura ya sabe a que lead corresponde.
--   licencia       cuando exista.
--
-- La regla no se afloja: sigue haciendo falta AL MENOS UNA. Lo que cambia es
-- que ahora hay alguna que se puede cumplir.

begin;

alter table pacs.capturas_modelmatch
    add column if not exists mmi_agent_id text,
    add column if not exists sf_lead_id   text;

comment on column pacs.capturas_modelmatch.mmi_agent_id is
'La llave natural de una captura de Model Match: esta en el propio perfil.
Verificada contra un Fast Fact capturado.';

alter table pacs.capturas_modelmatch
    drop constraint if exists captura_perfil_trae_llave;

alter table pacs.capturas_modelmatch
    add constraint captura_perfil_trae_llave check (
        alcance <> 'perfil'
        or mmi_agent_id is not null
        or sf_lead_id is not null
        or licencia_numero is not null
    );

create index if not exists capturas_mm_agent
    on pacs.capturas_modelmatch (mmi_agent_id)
 where mmi_agent_id is not null;

commit;
