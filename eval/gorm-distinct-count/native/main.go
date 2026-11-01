// A native PostgreSQL reproduction of the public GORM issue #6798.
// Keep this verifier outside the production checkout and producer context.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

const sourceCommit = "ead4e04ba7c6a49654649131e587133b1d9f3eca"

type capture struct{ SQL string }

func (l *capture) LogMode(logger.LogLevel) logger.Interface { return l }
func (l *capture) Info(context.Context, string, ...interface{}) {}
func (l *capture) Warn(context.Context, string, ...interface{}) {}
func (l *capture) Error(context.Context, string, ...interface{}) {}
func (l *capture) Trace(_ context.Context, _ time.Time, fc func() (string, int64), _ error) {
	l.SQL, _ = fc()
}

type result struct {
	Name      string `json:"name"`
	Category  string `json:"category"`
	Want      int64  `json:"want"`
	Got       int64  `json:"got"`
	OracleGot int64  `json:"postgres_oracle_got"`
	OracleOK  bool   `json:"postgres_oracle_matches_hand_count"`
	Pass      bool   `json:"pass"`
	SQL       string `json:"observed_gorm_sql"`
	Error     string `json:"error,omitempty"`
}

type receipt struct {
	Issue           string   `json:"public_issue"`
	SourceCommit    string   `json:"gorm_source_commit"`
	DriverVersion   string   `json:"postgres_driver_version"`
	PostgresVersion string   `json:"postgres_version"`
	Cases           []result `json:"cases"`
	PassCount       int      `json:"pass_count"`
	FailureCount    int      `json:"failure_count"`
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(2)
}

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		fail(fmt.Errorf("PG_DSN is required"))
	}
	db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{Logger: &capture{}})
	if err != nil {
		fail(err)
	}
	sqlDB, err := db.DB()
	if err != nil {
		fail(err)
	}
	defer sqlDB.Close()
	sqlDB.SetMaxOpenConns(2)
	if err := sqlDB.PingContext(ctx); err != nil {
		fail(err)
	}
	seed := []string{
		`CREATE TABLE fixture_pairs (id integer PRIMARY KEY, a text NULL, b text NULL, enabled boolean NOT NULL)`,
		`INSERT INTO fixture_pairs (id,a,b,enabled) VALUES
		 (1,'atlas','east',true), (2,'atlas','east',true),
		 (3,'atlas','west',true), (4,'birch','east',true),
		 (5,'birch','east',false), (6,NULL,'east',true),
		 (7,NULL,'east',true), (8,'atlas',NULL,true),
		 (9,NULL,NULL,true), (10,NULL,NULL,false),
		 (11,'cinder','south',false)`,
		`CREATE TABLE fixture_controls (id integer PRIMARY KEY, a text NOT NULL)`,
		`INSERT INTO fixture_controls (id,a) VALUES
		 (1,'ember'), (2,'ember'), (3,'ember'), (4,'flint'), (5,'gale')`,
	}
	for _, statement := range seed {
		if _, err := sqlDB.ExecContext(ctx, statement); err != nil {
			fail(err)
		}
	}
	r := receipt{
		Issue: "https://github.com/go-gorm/gorm/issues/6798",
		SourceCommit: sourceCommit,
		DriverVersion: "gorm.io/driver/postgres@v1.6.0",
	}
	if err := sqlDB.QueryRowContext(ctx, "SHOW server_version").Scan(&r.PostgresVersion); err != nil {
		fail(err)
	}
	cases := []struct {
		name, category, table, mode, where, oracle string
		want                                      int64
	}{
		{"composite_distinct_all", "regression", "fixture_pairs", "pair", "",
			`SELECT COUNT(*) FROM (SELECT DISTINCT a,b FROM fixture_pairs) AS projected_rows`, 7},
		{"composite_distinct_where", "regression", "fixture_pairs", "pair", "enabled = true",
			`SELECT COUNT(*) FROM (SELECT DISTINCT a,b FROM fixture_pairs WHERE enabled = true) AS projected_rows`, 6},
		{"plain_count_public_control", "control", "fixture_controls", "plain", "",
			`SELECT COUNT(*) FROM fixture_controls`, 5},
		{"single_distinct_public_control", "control", "fixture_controls", "single", "",
			`SELECT COUNT(DISTINCT a) FROM fixture_controls`, 3},
	}
	for _, c := range cases {
		log := &capture{}
		query := db.Session(&gorm.Session{Logger: log}).WithContext(ctx).Table(c.table)
		if c.where != "" {
			query = query.Where(c.where)
		}
		v := result{Name: c.name, Category: c.category, Want: c.want}
		switch c.mode {
		case "pair":
			err = query.Distinct("a", "b").Count(&v.Got).Error
		case "single":
			err = query.Distinct("a").Count(&v.Got).Error
		case "plain":
			err = query.Count(&v.Got).Error
		}
		v.SQL = log.SQL
		if err != nil {
			v.Error = err.Error()
		}
		if oracleErr := sqlDB.QueryRowContext(ctx, c.oracle).Scan(&v.OracleGot); oracleErr != nil {
			fail(oracleErr)
		}
		v.OracleOK = v.OracleGot == c.want
		v.Pass = v.Error == "" && v.Got == c.want && v.OracleOK
		if v.Pass {
			r.PassCount++
		} else {
			r.FailureCount++
		}
		r.Cases = append(r.Cases, v)
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(r); err != nil {
		fail(err)
	}
	if r.FailureCount > 0 {
		os.Exit(1)
	}
}
