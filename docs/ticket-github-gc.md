# Ticket para GitHub Support · garbage-collect de objetos huérfanos

**Estado: NO ENVIADO.** Es una comunicación externa; la abre una persona.

## Por qué hace falta

El 2026-09-21 se reescribió el historial de `icano-simo/ml_prospector` con
`git-filter-repo` para sacar cinco archivos con datos personales, y se hizo
force-push a `master`. El repo también se pasó a privado.

La reescritura **no borra los objetos del servidor**. Verificado con la API
después del force-push:

```
GET /repos/icano-simo/ml_prospector/commits/ee462bb79b94ab565f983f263ca5d4e11331f7a5
    → 200, devuelve el commit

GET /repos/icano-simo/ml_prospector/git/blobs/99119c07fcdb74cd4fa88a49e2dda856a61f6451
    → 200, size 237042   (Calls.xlsx)
```

Mientras esos objetos existan, cualquiera con acceso al repo —y cualquiera, si
el repo volviera a ser público— puede recuperarlos con la URL del SHA.

## Blobs a purgar

| SHA | Archivo | Bytes |
|---|---|---|
| `99119c07fcdb74cd4fa88a49e2dda856a61f6451` | `latino_re_engine/Calls.xlsx` | 237.042 |
| `b8a9d8a1ee2f979b95d5b067ab106194cb12e4d4` | `latino_re_engine/Historico Realtors.xlsx` | 1.154.174 |
| `1c144b3eb039dad519a7cbcad77276f3394e3a4a` | `latino_re_engine/MMI Data.xlsx` | 355.863 |
| `16256422ce80eedeb636fca419e85b22ed294956` | `data/realtors.csv` | 1.583.280 |
| `dcb69298dd3d552320a3ad844819f542c6bf941a` | `realtor_scraper/output/model/historico_scored.csv` | 2.888.092 |

Commit previo al force-push: `ee462bb79b94ab565f983f263ca5d4e11331f7a5`
Commit actual: `d1e66ec4d0260cddb564f5fc82c6cfba0135a977`

## Texto sugerido

> Subject: Request garbage collection of unreachable objects after history
> rewrite (sensitive data)
>
> Repository: icano-simo/ml_prospector
>
> On 2026-09-21 we rewrote this repository's history with git-filter-repo to
> remove five files that contained personal contact data (names, email
> addresses, phone numbers) for approximately 33,000 individuals, and
> force-pushed to master. We also switched the repository to private.
>
> The rewritten history no longer references those files, but the original
> objects remain reachable on your servers by SHA. For example,
> GET /repos/icano-simo/ml_prospector/git/blobs/99119c07fcdb74cd4fa88a49e2dda856a61f6451
> still returns 200 with size 237042.
>
> Could you please:
>
> 1. Run garbage collection on this repository to permanently remove
>    unreachable objects. The pre-rewrite tip was
>    ee462bb79b94ab565f983f263ca5d4e11331f7a5; the current tip is
>    d1e66ec4d0260cddb564f5fc82c6cfba0135a977.
>
> 2. Confirm whether any clone, fetch or raw-file traffic against this
>    repository was recorded while it was public, and if so, share whatever
>    detail you can. We need to assess whether the data was actually
>    retrieved. The repository was public from its first commit until
>    2026-09-21; the last push before the rewrite was 2026-06-20.
>
> 3. Confirm that no forks exist. The API reports forkCount: 0, but we would
>    like that confirmed on your side, since a fork would keep the objects
>    alive independently.
>
> Thank you.

## Después de que respondan

Volver a correr la verificación de los cinco SHA. Si siguen dando 200, el
ticket no se cerró aunque diga que sí.
