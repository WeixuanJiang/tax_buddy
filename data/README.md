# ATO Tax-Return Content Dataset

Extracted from the 4,038 ATO (`ato.gov.au`) links in `../ato_links.json.json`.
Content relevant to **tax returns** for individuals & families — income,
deductions, offsets, CGT, super (incl. SMSF & contributions), Medicare levy,
profession/occupation guides, rental property, crypto, lodging & amending, etc.

## Numbers
- **4,001** pages saved as JSON
- **0** fetch failures
- **35** pages skipped as not tax-return-relevant (glossary term stubs, foreign
  ownership registers, corporate demerger histories) — see `_failures.json`

## Folder layout
Files mirror the ATO URL hierarchy (the common `individuals-and-families/` root
is dropped). For example:

```
output/
  your-tax-return/...
  income-deductions-offsets-and-records/
    deductions-you-can-claim/...
    guides-for-occupations-and-industries/...   # profession-specific guides
  investments-and-assets/capital-gains-tax/...   # CGT
  super-for-individuals-and-families/
    self-managed-super-funds-smsf/...            # SMSF
  ...
```

## Catalogue
`index.json` lists every page with its url, title, category, word count, number
of child links, and relative file path.

## Per-page JSON schema
| field | meaning |
|-------|---------|
| `url` | **source URL** (the page this content came from) |
| `title` | page title |
| `description` | page summary/meta description |
| `nat_number`, `quick_code` | ATO publication / quick codes (when present) |
| `date_updated`, `first_published` | ATO publish dates |
| `keywords` | meta keywords |
| `content_blocks` | structured content: headings, paragraphs, lists, tables |
| `content_text` | full plain-text rendering of the content |
| `child_links` | for hub/landing pages: titles, descriptions & URLs of child pages |
| `word_count` | words in `content_text` |
| `category` | top-level ATO category |
| `source_title`, `source_description` | original values from the link list |

## Regenerating
- `python ../scrape_ato.py` — re-scrape (resumable; skips existing files).
  Optional slice: `python ../scrape_ato.py START END`.
- `python ../build_index.py` — rebuild `index.json` + coverage report.
