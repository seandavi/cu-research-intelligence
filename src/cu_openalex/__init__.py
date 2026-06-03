"""cu_openalex — mine OpenAlex for CU Anschutz authors and their works.

A Prefect pipeline that discovers University of Colorado Anschutz Medical Campus
authors (active in the last N years) via the OpenAlex API, then pulls every work
by those authors from the OpenAlex S3 snapshot, landing both as Parquet.
"""

__version__ = "0.1.0"
