# GORM multi-column DISTINCT count: native PostgreSQL reproduction

A small database-query repair fixture derived from the public
[GORM issue #6798](https://github.com/go-gorm/gorm/issues/6798).

At GORM commit `ead4e04ba7c6a49654649131e587133b1d9f3eca`,
`Distinct("a", "b").Count(&count)` emits `count(*)`. The physical row count
then replaces the intended count of distinct projected tuples.

[Read the walkthrough](walkthrough.md): the counting unit, NULL-bearing tuples,
and the native four-case check.

## Measured baseline

Native Go + GORM + PostgreSQL 16.15, with fictional records:

| Query | GORM count | PostgreSQL row-set oracle | Result |
|---|---:|---:|---|
| Distinct pair | 11 | 7 | Wrong count |
| Distinct pair, `enabled = true` | 8 | 6 | Wrong count |
| Ordinary count | 5 | 5 | Control passes |
| Single-column distinct count | 3 | 3 | Control passes |

The distinct-pair records include repeated NULL-bearing tuples. The oracle
counts rows from `SELECT DISTINCT a,b`; the hand-counted sets are explained
in [native/oracle.md](native/oracle.md). Acceptance compares returned counts,
without requiring one particular SQL implementation.

[baseline.json](baseline.json) contains the observed SQL and native results.
Exit status **1** is the reproduced baseline bug, **0** means all four cases
pass, and **2** indicates fixture setup or database failure. This is a baseline
reproduction; agent repair runs and production patches are still pending.

## Run against an isolated production checkout

Prerequisites: Go, Git, and an **empty disposable PostgreSQL database**.
The verifier creates two tables; use a fresh database for each run.

From the root of this repository:

```sh
mkdir -p temp/gorm-count-repro
cp -R eval/gorm-distinct-count/native temp/gorm-count-repro/native
git clone https://github.com/go-gorm/gorm.git temp/gorm-count-repro/repo
git -C temp/gorm-count-repro/repo checkout --detach ead4e04ba7c6a49654649131e587133b1d9f3eca
export PG_DSN='host=127.0.0.1 port=5432 user=fixture password=fixture dbname=fixture sslmode=disable'
(cd temp/gorm-count-repro/native && go run .)
```

The local module replacement loads the sibling `repo` checkout. To evaluate
a repair, apply it there and rerun against another empty database. Keep the
verifier and row-set oracle outside the repair agent's input; provide only
the production checkout and task instruction. This four-case fixture covers
composite distinct, a filter, and the two basic controls. Broader ORM behavior
belongs to the upstream regression suite.
