# Native PostgreSQL row-set oracle

All values below are fictional. This file and the native verifier stay
outside the producer's context. Acceptance checks returned counts, not a
particular generated SQL spelling.

`fixture_pairs` contains eleven physical rows. The seven distinct `(a,b)`
tuples are `(atlas,east)`, `(atlas,west)`, `(birch,east)`, `(NULL,east)`,
`(atlas,NULL)`, `(NULL,NULL)`, and `(cinder,south)`. Repeated NULL-bearing
tuples collapse under PostgreSQL SELECT DISTINCT row-set semantics.
Count of all distinct projected tuples: **7**.

The `enabled = true` predicate leaves eight physical rows and removes the
last tuple `(cinder,south)`. Six distinct projected tuples remain: **6**.

The five-row public-control pattern uses `ember, ember, ember, flint, gale`.
Ordinary count: **5**. Single-column distinct count: **3**. These preserve
the two behaviors and counts of public GORM `tests/distinct_test.go`.

Each hand count is separately executed against PostgreSQL as a row-set
oracle. The production query remains native GORM Table/Distinct/Count.
