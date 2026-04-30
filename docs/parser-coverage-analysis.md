# Parser Coverage Analysis — CENDOJ PDF → XML sintético

**Fecha:** 2026-04-30
**Objetivo:** Mapear qué tipos de resolución judicial parsea actualmente el servidor MCP, qué falla en silencio, y cuántos parsers distintos se necesitarán para cubrir el corpus completo.

---

## 1. Arquitectura del pipeline actual

El servidor expone dos etapas completamente distintas:

```
lookup_by_ecli (tool)
    │
    └─► GET /search/search.action [POST HTML]
         └─► BeautifulSoup scraping
              └─► RulingSections(raw_text=snippet, parse_successful=False, tribunal_scope='other')
                  ← SIEMPRE, sin importar el tribunal

cendoj://{ecli} (resource → get_ruling_text)
    │
    └─► lookup_by_ecli  [para obtener source_url]
         └─► GET contenidos.action?action=contentpdf  [descarga PDF]
              └─► pdfplumber.extract_text()
                   └─► _detect_scope(ecli) → 'ts_tc' | 'other'
                        ├─ 'ts_tc' → split_sections() → regex ANTECEDENTES/FUNDAMENTOS/FALLO
                        └─ 'other' → sin intento, raw_text solo
```

**Conclusión crítica:** `lookup_by_ecli` siempre devuelve `parse_successful=False, tribunal_scope='other'`
porque **nunca descarga el PDF**. El parsing real sólo ocurre al acceder al resource `cendoj://{ecli}`.

---

## 2. ECLIs reales testeados con las herramientas MCP

Los siguientes resultados fueron obtenidos con `lookup_by_ecli` y `check_if_superseded` en producción (30/04/2026):

| ECLI | ROJ | Tipo | Tribunal | `tribunal_scope` (lookup) | `parse_successful` (lookup) | Comportamiento esperado en resource |
|------|-----|------|----------|--------------------------|----------------------------|--------------------------------------|
| `ECLI:ES:TS:2026:1696` | STS 1696/2026 | **Sentencia** | TS Sala Civil | `other`¹ | `false`¹ | `ts_tc` / `true` si estructura canónica ✅ |
| `ECLI:ES:TS:2026:4092A` | ATS 4092/2026 | **Auto** | TS Sala Civil | `other`¹ | `false`¹ | `ts_tc` / `false` ❌ fallo silencioso |
| `ECLI:ES:TS:2026:4075A` | ATS 4075/2026 | **Auto** | TS Contencioso | `other`¹ | `false`¹ | `ts_tc` / `false` ❌ fallo silencioso |
| `ECLI:ES:TS:2026:4099A` | ATS 4099/2026 | **Auto** | TS Contencioso | `other`¹ | `false`¹ | `ts_tc` / `false` ❌ fallo silencioso |
| `ECLI:ES:TS:2026:4111A` | ATS 4111/2026 | **Auto** | TS Sala Penal | `other`¹ | `false`¹ | `ts_tc` / `false` ❌ fallo silencioso |
| `ECLI:ES:TS:2026:1747` | STS 1747/2026 | **Sentencia** | TS Contencioso | `other`¹ | `false`¹ | `ts_tc` / `true` si estructura canónica ✅ |
| `ECLI:ES:TS:2026:1730` | STS 1730/2026 | **Sentencia** | TS Penal | `other`¹ | `false`¹ | `ts_tc` / `true` si estructura canónica ✅ |
| `ECLI:ES:TSJCAT:2026:2934` | STSJ CAT 2934/2026 | **Sentencia** | TSJ Cataluña | `other` | `false` | `other` / `false` — no se intenta ❌ |

> ¹ `lookup_by_ecli` siempre devuelve `other/false` — es el comportamiento esperado (sin PDF).

**Observación importante:** En la muestra del 30/04/2026, aprox. **4 de 7 resoluciones TS eran Autos** (prefijo `ATS`). Esto confirma que el fallo silencioso del parser de Autos afecta a una fracción significativa del corpus TS.

---

## 3. Taxonomía de tribunales CENDOJ

### 3.1 Códigos ECLI de órganos españoles

El formato ECLI es `ECLI:ES:{COURT}:{YEAR}:{ID}`.

| Código ECLI | Tribunal |
|-------------|----------|
| `TS` | Tribunal Supremo (5 Salas + Especial) |
| `TC` | Tribunal Constitucional |
| `AN` | Audiencia Nacional |
| `TSJAND` | TSJ Andalucía |
| `TSJAR` | TSJ Aragón |
| `TSJAST` | TSJ Asturias |
| `TSJIB` | TSJ Baleares |
| `TSJCAN` | TSJ Canarias |
| `TSJCANT` | TSJ Cantabria |
| `TSJCAT` | TSJ Cataluña |
| `TSJCLM` | TSJ Castilla-La Mancha |
| `TSJCL` | TSJ Castilla y León |
| `TSJCV` | TSJ Comunidad Valenciana |
| `TSJEXT` | TSJ Extremadura |
| `TSJGAL` | TSJ Galicia |
| `TSJLA` | TSJ La Rioja |
| `TSJM` | TSJ Madrid |
| `TSJMUR` | TSJ Murcia |
| `TSJNAV` | TSJ Navarra |
| `TSJPV` | TSJ País Vasco |
| `APM`, `APCO`, `APBA`… | Audiencia Provincial (por provincia) |
| `JPI`, `JI`, `JS`, `JCA`, `JM`, `JP`, `JVM`… | Juzgados unipersonales |
| `CSJM`, `TMT`, `TMC` | Tribunales militares |

### 3.2 Códigos `databasematch` del buscador CENDOJ

El campo `databasematch` en la URL del PDF puede ser:
`TS`, `AN` (usado genéricamente para todos los no-TS), y el código específico de cada TSJ/AP/Juzgado en los atributos HTML de los resultados.

---

## 4. Estructuras de sección encontradas en los documentos

### Estructura A — Sentencia canónica (3 secciones)
**Presente en:** TS Sentencias, TC Sentencias, AN Sentencias, TSJ Sentencias, AP Sentencias

```
[CABECERA DE METADATOS]
  Roj: STS XXXX/YYYY - ECLI:ES:TS:YYYY:NNNN
  Id Cendoj: NNNNNNNNN
  Órgano: Tribunal Supremo. Sala de lo Civil
  Sede: Madrid  |  Sección: 1  |  Fecha: DD/MM/YYYY
  Nº de Recurso: NNN/YYYY  |  Tipo de Resolución: Sentencia
  Ponente: NOMBRE APELLIDO

ANTECEDENTES DE HECHO
  PRIMERO.- ...  SEGUNDO.- ...

FUNDAMENTOS DE DERECHO
  PRIMERO.- ...  SEGUNDO.- ...

FALLO   (o: PARTE DISPOSITIVA)
  1. ...  2. ...
```

**Estado actual:** ✅ Cubierto — pero sólo para `ECLI:ES:TS:*` y `ECLI:ES:TC:*`.
AN, TSJ, AP tienen la misma estructura pero `_detect_scope` los rechaza antes de intentar.

**Fixture:** `tests/fixtures/ts_sentence.txt`

---

### Estructura B — Auto / Providencia
**Presente en:** TS Autos, TC Autos, AN Autos, TSJ Autos
**Identificadores:** ROJ prefijo `ATS`, `AAN`, `ATSJ…`; ECLI sufijo `…:NNNNA`

```
[CABECERA DE METADATOS]
  Roj: ATS XXXX/YYYY - ECLI:ES:TS:YYYY:NNNNA
  ...
  Tipo de Resolución: Auto
  Ponente: NOMBRE APELLIDO

[BLOQUE DE PORTADA — se repite en cada página PDF]
  PIEZA DE MEDIDAS CAUTELARES Num.: XXXX
  Fallo/Acuerdo: Auto no ha lugar ...
  Ponente: Excmo. Sr. D. ...

HECHOS
  PRIMERO.- ...  SEGUNDO.- ...

RAZONAMIENTOS JURÍDICOS
  PRIMERO.- ...

LA SALA ACUERDA:
  [texto del acuerdo]
```

**Estado actual:** ❌ Fallo silencioso — `_detect_scope` devuelve `'ts_tc'` (correcto) pero
`split_sections` no encuentra `ANTECEDENTES DE HECHO/FUNDAMENTOS/FALLO` → `parse_successful=False`.

**Fixture real:** `tests/fixtures/ts_ruling.txt` (`ECLI:ES:TS:2026:3898A`)
**ECLIs reales confirmados:** `ECLI:ES:TS:2026:4092A`, `ECLI:ES:TS:2026:4075A`, `ECLI:ES:TS:2026:4099A`, `ECLI:ES:TS:2026:4111A`

---

### Estructura C — Juzgados unipersonales (vocabulario propio)
**Presente en:** JPI, JS, JCA, JM, JVM, JP, JMe

```
[CABECERA DE METADATOS]
  ...
  Tipo de Resolución: Sentencia

HECHOS PROBADOS   (o: RELACIÓN DE HECHOS, HECHOS DECLARADOS PROBADOS)
  ...

FUNDAMENTOS JURÍDICOS   (o: FUNDAMENTOS DE DERECHO)
  ...

FALLO
  ...
```

**Estado actual:** ❌ No se intenta — `_detect_scope` devuelve `'other'`, no hay parsing.

---

### Estructura D — Metadatos de cabecera (transversal)
**Presente en:** Absolutamente todos los documentos CENDOJ

```
Roj: [TIPO] NNNN/YYYY - ECLI:ES:XX:YYYY:ID
Id Cendoj: NNNNNNNNNNNNNNNNN
Órgano: [nombre tribunal completo]
Sede: [ciudad]
Sección: [número]
Fecha: DD/MM/YYYY
Nº de Recurso: NNNN/YYYY
Nº de Resolución: [opcional]
Procedimiento: [tipo]
Ponente: NOMBRE APELLIDO (en mayúsculas)
Tipo de Resolución: [Sentencia|Auto|Providencia|Acuerdo]
```

**Estado actual:** ❌ No se extrae — la cabecera se descarta en el `raw_text`.
Estos campos son extraíbles con regex simples y enriquecen enormemente el XML sintético.

---

## 5. Matriz de cobertura actual

| Tipo resolución | Tribunal | ECLI pattern | `tribunal_scope` | `parse_successful` | Causa |
|----------------|----------|-------------|-----------------|-------------------|-------|
| Sentencia | TS, TC | `ECLI:ES:TS/TC:*` (sin sufijo A) | `ts_tc` | ✅ `true` | Parser A implementado |
| Auto | TS, TC | `ECLI:ES:TS/TC:*NNNNA` | `ts_tc` | ❌ `false` | Estructura B no implementada |
| Sentencia | AN | `ECLI:ES:AN:*` | `other` | ❌ `false` | Scope gate rechaza |
| Sentencia | TSJ (17 CCAA) | `ECLI:ES:TSJ*:*` | `other` | ❌ `false` | Scope gate rechaza |
| Sentencia | AP | `ECLI:ES:AP*:*` | `other` | ❌ `false` | Scope gate rechaza |
| Auto | AN, TSJ, AP | `ECLI:ES:AN/TSJ*/AP*:*A` | `other` | ❌ `false` | Scope gate + estructura B |
| Sentencia | Juzgados (JPI/JS/JCA…) | varios | `other` | ❌ `false` | Scope gate + estructura C |
| Metadatos cabecera | Todos | — | — | ❌ nunca | No implementado |

**Cobertura efectiva actual (resource `cendoj://`):** Sentencias TS y TC con estructura canónica — estimado **~15-20% del corpus total CENDOJ**.

---

## 6. Parsers propuestos para el XML sintético

### Parser 0 — Metadatos de cabecera *(alta prioridad, baja complejidad)*

Extrae campos estructurados presentes en **todos** los documentos antes de las secciones de contenido.

```python
_HEADER_RE = re.compile(
    r'Roj:\s*(?P<roj>[^\-]+?)\s*-\s*ECLI:(?P<ecli>[^\n]+)\n'
    r'Id\s+Cendoj:\s*(?P<id_cendoj>\d+)\n'
    r'Órgano:\s*(?P<organo>[^\n]+)\n'
    r'.*?Fecha:\s*(?P<fecha>\d{2}/\d{2}/\d{4})\n'
    r'.*?Tipo\s+de\s+Resolución:\s*(?P<tipo>[^\n]+)',
    re.DOTALL | re.IGNORECASE,
)
```

Produce un bloque XML:
```xml
<metadata>
  <roj>STS 1234/2020</roj>
  <ecli>ECLI:ES:TS:2020:1234</ecli>
  <id_cendoj>28079110012020100001</id_cendoj>
  <organo>Tribunal Supremo. Sala de lo Civil</organo>
  <sede>Madrid</sede>
  <seccion>1</seccion>
  <fecha>2020-06-15</fecha>
  <tipo_resolucion>Sentencia</tipo_resolucion>
  <ponente>NOMBRE APELLIDO</ponente>
  <numero_recurso>1234/2018</numero_recurso>
</metadata>
```

---

### Parser A — Sentencia canónica *(ampliar scope)*

Ya implementado. Cambio mínimo requerido: **eliminar el gate `_detect_scope`** o ampliarlo a todos los tribunales colegiados. La regex `_SECTION_RE` ya detecta correctamente `ANTECEDENTES DE HECHO / FUNDAMENTOS DE DERECHO / FALLO / PARTE DISPOSITIVA` independientemente del tribunal.

Produce:
```xml
<ruling type="sentencia" tribunal_scope="all_collegial">
  <antecedentes_de_hecho>...</antecedentes_de_hecho>
  <fundamentos_de_derecho>...</fundamentos_de_derecho>
  <fallo>...</fallo>
</ruling>
```

---

### Parser B — Auto / Providencia *(nueva implementación, alta prioridad)*

Nuevas variantes de heading a detectar:

| Sección | Variantes conocidas |
|---------|-------------------|
| Hechos | `HECHOS`, `ANTECEDENTES` |
| Razonamientos | `RAZONAMIENTOS JURÍDICOS`, `FUNDAMENTOS JURÍDICOS`, `RAZONAMIENTOS` |
| Parte dispositiva | `LA SALA ACUERDA:`, `ACUERDA:`, `SE ACUERDA:`, `PARTE DISPOSITIVA` |

```python
_AUTO_SECTION_RE = re.compile(
    r'(HECHOS|RAZONAMIENTOS\s+JUR[IÍ]DICOS|RAZONAMIENTOS|'
    r'LA\s+SALA\s+ACUERDA\s*:|ACUERDA\s*:|SE\s+ACUERDA\s*:)',
    re.IGNORECASE,
)
```

Produce:
```xml
<ruling type="auto">
  <hechos>...</hechos>
  <razonamientos_juridicos>...</razonamientos_juridicos>
  <acuerdo>...</acuerdo>
</ruling>
```

**Fixture de prueba disponible:** `tests/fixtures/ts_ruling.txt`

---

### Parser C — Juzgados unipersonales *(prioridad media)*

Headings específicos de órganos de primera instancia:

| Sección | Variantes |
|---------|-----------|
| Hechos | `HECHOS PROBADOS`, `RELACIÓN DE HECHOS`, `HECHOS DECLARADOS PROBADOS`, `HECHOS` |
| Fundamentos | `FUNDAMENTOS JURÍDICOS`, `FUNDAMENTOS DE DERECHO` |
| Fallo | `FALLO` |

Produce el mismo XML que Parser A con `type="sentencia_unipersonal"`.

---

## 7. Plan de implementación sugerido

| Fase | Parser | Impacto estimado | Complejidad |
|------|--------|-----------------|------------|
| 1 | **Parser 0** (metadatos cabecera) | Enriquece el 100% de documentos con ponente, fecha exacta, tipo | Baja |
| 2 | **Parser A ampliado** (quitar scope gate) | Añade TSJ + AN + AP Sentencias (>50% del corpus) | Mínima |
| 3 | **Parser B** (Autos) | Fix silencioso TS Autos (~30% de resoluciones TS) | Media |
| 4 | **Parser C** (Juzgados) | Cubre órganos unipersonales | Media-Alta |

> La fase 2 es de mayor impacto con menor esfuerzo: las sentencias de TSJ, AN y AP ya tienen exactamente la misma estructura canónica que las TS — la regex actual ya funcionaría, solo hay que quitar el filtro de scope.

---

## 8. Formato XML sintético objetivo

Inspirado en la estructura CENDOJ pero adaptado para consumo por LLMs:

```xml
<court_document source="cendoj" version="2">
  <metadata>
    <ecli>ECLI:ES:TS:2026:1696</ecli>
    <roj>STS 1696/2026</roj>
    <id_cendoj>11704809</id_cendoj>
    <organo>Tribunal Supremo. Sala de lo Civil</organo>
    <sede>Madrid</sede>
    <fecha>2026-04-27</fecha>
    <tipo_resolucion>Sentencia</tipo_resolucion>
    <ponente>NOMBRE APELLIDO</ponente>
    <numero_recurso>XXXX/YYYY</numero_recurso>
  </metadata>
  <contenido tipo="sentencia">
    <antecedentes_de_hecho>
      <item numero="PRIMERO">...</item>
      <item numero="SEGUNDO">...</item>
    </antecedentes_de_hecho>
    <fundamentos_de_derecho>
      <item numero="PRIMERO">...</item>
    </fundamentos_de_derecho>
    <fallo>...</fallo>
  </contenido>
</court_document>
```

---

## Referencias

- `src/mcp_cendoj/parser.py` — parser actual
- `src/mcp_cendoj/models.py` — modelos `RulingSections`, `Ruling`
- `tests/fixtures/ts_sentence.txt` — ejemplo Sentencia TS (Estructura A)
- `tests/fixtures/ts_ruling.txt` — ejemplo Auto TS (Estructura B) — `ECLI:ES:TS:2026:3898A`
- `tests/fixtures/tsj_ruling.txt` — ejemplo Sentencia TSJ (stub)
- [Página CENDOJ Jurisprudencia](https://www.poderjudicial.es/cgpj/es/Temas/Centro-de-Documentacion-Judicial--CENDOJ-/Jurisprudencia/)
