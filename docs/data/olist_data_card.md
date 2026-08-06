# Olist data card

- Canonical source: Olist Brazilian E-Commerce Public Dataset on Kaggle.
- Snapshot: version 2, 9 CSV files, 1,550,922 data rows.
- Archive SHA-256: `967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784`.
- Observed archive size: 42.6 MiB; generated SQLite size: about 175 MiB.
- License metadata: CC BY-NC-SA 4.0; raw data is not redistributed.
- Timestamp timezone: unknown; source values remain timezone-naive.
- Money: source decimal text is retained and exact integer-cent columns are derived with `Decimal`.
- Olist does not contain returns/refunds; canceled/unavailable orders are not returns.

Known anomalies retained and tested:

- 610 products have no category.
- Review IDs contain 814 duplicate occurrences.
- 551 review rows repeat an `order_id` beyond its first row, across 547 multi-review orders.
- Translation input has a UTF-8 BOM and is read with `utf-8-sig`.
- Raw typo fields such as `product_name_lenght` are retained; semantic views provide corrected aliases.

Full file hashes, headers, byte sizes and exact row counts are pinned in
`datasets/olist/source_manifest.yaml`.
