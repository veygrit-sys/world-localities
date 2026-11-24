# Uruguay — Direcciones Geográficas del Uruguay

Infraestructura de Datos Espaciales (IDE), based on information from Correo Uruguayo. [Dataset and 19 departmental exports](https://catalogodatos.gub.uy/dataset/ide-direcciones-geograficas-del-uruguay), published 2026-10-01 and retrieved 2026-11-24. [Licencia de Datos Abiertos – Uruguay, versión 0.1](https://www.gub.uy/agencia-gobierno-electronico-sociedad-informacion-conocimiento/sites/agencia-gobierno-electronico-sociedad-informacion-conocimiento/files/documentos/publicaciones/licencia_de_datos_abiertos_0.pdf).

World Localities selected the postcode, census locality, street and door number from each source row, retained interpretable door suffixes after a space, and discarded incomplete or unparsed addresses. A point must have its own five-digit postcode. The receipt identifies the department and the CSV line in the snapshot pinned in [source.json](source.json). It is a version-specific locator. A department is verified against the `state` component. Geometries, residents, door access and delivery status are outside the projection.

The complete 19 downloadable files contain 1,059,256 rows. The index includes 1,024,802 published point observations under 121 distinct postcodes. IDE includes both officially assigned and informally observed addresses. Repeated published observations can be ambiguous; the quantity is a row count. Skipped rows include 25,991 unidentified streets (including internal designations), 1,642 unconfirmed number-marker rows, 4,604 unparsed door suffixes, 2,132 missing or unspecified numbers, 83 missing localities or streets and 2 kilometre-qualified entries. Counts are assigned to the first applicable exclusion.

Example: `65000 → FRAY BENTOS → ESPAÑA → 111` identifies row 2 of the Río Negro CSV. The provider supplies the four fields on that same row.

Reproduce the projection from the exact exports named and hashed in `source.json`:

```sh
python scripts/project_uy_addresses.py --manifest localities/open_reference/uy/source.json --raw-dir /path/to/pinned-csv --output /path/to/new-uy
```
