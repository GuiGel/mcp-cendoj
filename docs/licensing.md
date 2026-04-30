# Licensing

## Default license: MIT

`mcp-cendoj` is released under the **MIT License**.

This applies when you install the package with its default dependencies — including `pdfplumber`, which is MIT-licensed.

---

## Optional dependency: PyMuPDF (AGPL)

PyMuPDF (`fitz`) can be installed as an optional dependency to significantly speed up PDF text extraction (5–70× faster, depending on document size). However, PyMuPDF is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)** by Artifex Software.

### Installing PyMuPDF

```bash
uv add pymupdf
# or
pip install pymupdf
```

When `fitz` is importable at runtime, `mcp-cendoj` will use it automatically for PDF extraction. When it is not installed, the default `pdfplumber` backend is used transparently.

### License implications when PyMuPDF is installed

**If you install PyMuPDF, the license of the combined work changes.**

The AGPL-3.0 has a "network use is distribution" clause (section 13). This means:

| Scenario | Obligation |
|---|---|
| Local personal use (MCP server on your own machine, not exposed to others) | No obligation. AGPL does not trigger for private use. |
| Self-hosted, accessible only to you | No obligation. |
| Deployed as a service accessible by others over a network | You **must** make the complete source code (including your modifications) available under AGPL-3.0. |
| Embedding in a proprietary product distributed to third parties | You **must** release the combined work under AGPL-3.0, or obtain a commercial license from Artifex. |

> **Summary**: if you only use `mcp-cendoj` locally as a personal MCP server, installing PyMuPDF has no practical license impact. If you expose it as a public or commercial service, AGPL obligations apply.

### Commercial license

Artifex offers a commercial license for PyMuPDF that removes the AGPL requirement. See [artifex.com/licensing](https://artifex.com/licensing/) for pricing and terms.

---

## Dependency license summary

| Package | License | Notes |
|---|---|---|
| `pdfplumber` | MIT | Default PDF backend |
| `pymupdf` | AGPL-3.0 | Optional fast PDF backend |
| `httpx` | BSD-3-Clause | HTTP client |
| `beautifulsoup4` | MIT | HTML scraping |
| `lxml` | BSD-3-Clause | XML/HTML parser |
| `pydantic` | MIT | Data models |
| `mcp` | MIT | MCP protocol |
| `platformdirs` | MIT | Platform directories |

---

## How to verify which backend is active

```python
import importlib.util
backend = 'pymupdf (AGPL)' if importlib.util.find_spec('fitz') else 'pdfplumber (MIT)'
print(f'PDF backend: {backend}')
```

Or check at runtime from the server logs — the backend is reported on startup when `LOG_LEVEL=DEBUG` is set.
