# 0016. Full-text publication search (DuckDB FTS over title + abstract)

- Status: accepted
- Date: 2026-06-21

## Context

Users need to find and filter publications ("papers about CAR-T in leukemia",
"this program's open-access output, most-cited first"). Filtering and sorting
over the ~96k-row works table is trivially fast in DuckDB (ADR-0014). The open
question was **search quality**: substring matching on titles is weak, and
researchers expect relevance-ranked results over **abstracts**, not just titles.

OpenAlex stores abstracts as an `abstract_inverted_index` (`{word: [positions]}`)
in the raw layer, not as plain text, and the curated works table did not carry
them.

## Decision

Reconstruct abstract text from the inverted index at **build time** and store it
on the works table (~64% of works have an abstract; ~56 MB after Parquet
compression, read columnar-only when selected). Build a **DuckDB FTS (BM25)
index** over `title + abstract`, **lazily on first search** (~5 s one-time, so
non-search pages and most tests never pay for it).

`search_publications` ranks with **conjunctive (AND) BM25** when a query is
present — "tumor microenvironment immunotherapy" returns the papers containing
all three terms, not the union — and falls back to a title substring match if
the index isn't available. All filters (year, program, OA, collaboration,
inter-institutional, author, journal, citation/RCR thresholds) compose with the
ranked search, and queries are parameterized (injection-safe) with allow-listed
sort columns. Results carry a short abstract **snippet**.

## Consequences

- Ranked relevance over abstracts, entirely **in-process** — no search engine,
  no Postgres, no extra service. Warm searches are ~90 ms.
- Confirms the ADR-0014 boundary: even "good" full-text search does not require
  leaving DuckDB at this scale.
- Abstract coverage is a ceiling (OpenAlex lacks ~36%); those works still match
  on title. The snippet and ranking degrade gracefully for them.
- The build gains a raw-layer scan to reconstruct abstracts (a few seconds);
  paid offline, not at request time.

## Alternatives considered

- **`ILIKE` substring search.** Kept only as the no-index fallback — it is not
  ranked, ignores abstracts, and matches mid-word noise.
- **Postgres full-text (`tsvector`/GIN) or a search engine (Meilisearch /
  Typesense / Elasticsearch).** Rejected for this scale — they add a service to
  operate for a corpus DuckDB FTS handles in milliseconds. Reconsider only if
  search becomes a headline product needing typo-tolerance, instant-as-you-type,
  or synonyms.
- **Disjunctive (OR) BM25.** Rejected as the default — it returns thousands of
  weak single-term matches; AND is what users mean by "papers about X Y Z".
