# GORM counted 11 rows. PostgreSQL found 7 distinct pairs.

A count can execute successfully and still answer the wrong question.

In a native Go + PostgreSQL reproduction, this GORM query returned **11**:

```go
var count int64
err := db.Table("fixture_pairs").
    Distinct("a", "b").
    Count(&count).Error
```

The database contained **7 distinct `(a, b)` pairs**. `err` was nil. The emitted SQL was:

```sql
SELECT count(*) FROM "fixture_pairs";
```

This reproduces the public [GORM issue #6798](https://github.com/go-gorm/gorm/issues/6798). The measured version is commit `ead4e04ba7c6a49654649131e587133b1d9f3eca`, with `gorm.io/driver/postgres@v1.6.0` and PostgreSQL 16.15.

## Name the thing you are counting

Physical rows and distinct projected tuples are two different counting units. A useful regression check states the unit before invoking the ORM.

The fixture has eleven fictional records. After projecting `(a, b)` and deduplicating, the result is:

```text
(atlas, east)
(atlas, west)
(birch, east)
(NULL, east)
(atlas, NULL)
(NULL, NULL)
(cinder, south)
```

PostgreSQL's `SELECT DISTINCT` collapses repeated NULL-bearing tuples. The row-set reference therefore counts the projected relation:

```sql
SELECT COUNT(*)
FROM (
    SELECT DISTINCT a, b
    FROM fixture_pairs
) AS projected_rows;
-- 7
```

For a filtered count, put the predicate inside that same projected relation:

```sql
SELECT COUNT(*)
FROM (
    SELECT DISTINCT a, b
    FROM fixture_pairs
    WHERE enabled = true
) AS projected_rows;
-- 6
```

Both references ran against PostgreSQL and agreed with the hand-counted sets. The GORM baseline returned **11** and **8**, respectively.

## Preserve the behaviors that already work

A repair should handle the pair while retaining ordinary counts and single-column distinct counts. Here is the complete measured baseline:

| Case | GORM | PostgreSQL reference |
|---|---:|---:|
| Distinct pair | 11 | 7 |
| Distinct pair, `enabled = true` | 8 | 6 |
| Ordinary count | 5 | 5 |
| Single-column distinct count | 3 | 3 |

Those last two controls matter: they catch a change that fixes the new example by changing established count behavior. The pair cases also include duplicates and NULLs, so a two-row happy-path example has room to miss the discrepancy.

## Run the native check

The [complete fixture](https://github.com/blucca/ridges-query-agent/tree/main/eval/gorm-distinct-count) includes the Go verifier, dependency pin, fictional seed records, hand-counted oracle, and [observed SQL/results](https://github.com/blucca/ridges-query-agent/blob/main/eval/gorm-distinct-count/baseline.json).

Use Go, Git, and a **fresh disposable PostgreSQL database**. The verifier creates two fixture tables. From a checkout of that repository:

```sh
mkdir -p temp/gorm-count-repro
cp -R eval/gorm-distinct-count/native temp/gorm-count-repro/native
git clone https://github.com/go-gorm/gorm.git temp/gorm-count-repro/repo
git -C temp/gorm-count-repro/repo checkout --detach ead4e04ba7c6a49654649131e587133b1d9f3eca
export PG_DSN='host=127.0.0.1 port=5432 user=fixture password=fixture dbname=fixture sslmode=disable'
(cd temp/gorm-count-repro/native && go run .)
```

Exit **1** reproduces the baseline discrepancy; exit **0** means all four count checks pass. Exit **2** identifies setup or database failure. Each repair evaluation uses another empty database and the same verifier outside the production checkout.

The check accepts returned counts, preserving freedom to choose the production implementation. Its coverage is composite distinct, one filter, and the two controls above; use the upstream regression suite for the rest of the ORM contract.

**Takeaway:** assert the cardinality of the intended row set. A successful SQL execution is a useful operational signal; a row-set oracle checks the business answer.

If this check exposes a counting discrepancy in your own application, share the expected counting unit and a small fictional fixture in the [repository's issues](https://github.com/blucca/ridges-query-agent/issues). For a private, fixed-scope query repair, [email Blucca](mailto:belgialucca@gmail.com?subject=Database%20query%20repair%20scope) with the database/ORM versions, expected and actual counts, and target date. We agree a price and acceptance case before implementation. Codex handles engineering and email; the account holder handles contracting and invoicing.
