import duckdb
import pandas as pd
import pytest

from sql_analytics import SQLValidationError, execute_sql_query, validate_sql


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "t.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE cleaned_data AS SELECT * FROM (VALUES (1,'a',10.5),(2,'b',20.0),(3,'a',5.0)) t(id,grp,amt)")
    con.close()
    return path


def test_basic_select_accuracy(db):
    df = execute_sql_query("SELECT grp, SUM(amt) AS total FROM cleaned_data GROUP BY grp ORDER BY grp", db)
    assert df.to_dict("records") == [{"grp": "a", "total": 15.5}, {"grp": "b", "total": 20.0}]


@pytest.mark.parametrize("q", [
    "WITH x AS (SELECT * FROM cleaned_data) SELECT COUNT(*) AS n FROM x",
    "DESCRIBE cleaned_data", "SHOW TABLES", "SUMMARIZE cleaned_data",
    "EXPLAIN SELECT * FROM cleaned_data", "FROM cleaned_data", "SELECT 'a;b' AS s",
    "SELECT 1;", "/* c */ select 1 -- tail",
])
def test_allowed(db, q):
    assert isinstance(execute_sql_query(q, db), pd.DataFrame)


@pytest.mark.parametrize("q", [
    "DROP TABLE cleaned_data", "DELETE FROM cleaned_data", "UPDATE cleaned_data SET amt=0",
    "INSERT INTO cleaned_data VALUES (9,'z',1)", "CREATE TABLE x AS SELECT 1",
    "ALTER TABLE cleaned_data ADD COLUMN z INT", "TRUNCATE cleaned_data",
    "COPY cleaned_data TO 'out.csv'", "ATTACH 'other.db'", "INSTALL httpfs", "LOAD httpfs",
    "PRAGMA database_list", "SET threads=1", "CALL pragma_version()",
    "EXPORT DATABASE 'dump'", "SELECT 1; DROP TABLE cleaned_data",
    "-- hi\nDROP TABLE cleaned_data", "/* x */ DELETE FROM cleaned_data",
    "dRoP tAbLe cleaned_data", "", "   ;  ", "SELEC broken",
])
def test_rejected(db, q):
    with pytest.raises(SQLValidationError):
        execute_sql_query(q, db)


@pytest.mark.parametrize("q", [
    "SELECT * FROM read_csv('/etc/passwd')", "SELECT * FROM read_text('/etc/hostname')",
    "SELECT * FROM glob('/*')", "SELECT * FROM read_parquet('http://example.com/x.parquet')",
])
def test_file_and_network_access_blocked(db, q):
    with pytest.raises(duckdb.Error):
        execute_sql_query(q, db)


def test_data_unchanged_after_attacks(db):
    for q in ["DROP TABLE cleaned_data", "DELETE FROM cleaned_data"]:
        with pytest.raises(SQLValidationError):
            execute_sql_query(q, db)
    assert execute_sql_query("SELECT COUNT(*) AS n FROM cleaned_data", db)["n"][0] == 3


def test_row_cap(db):
    df = execute_sql_query("SELECT * FROM range(50000)", db, max_rows=1000)
    assert len(df) == 1000 and df.attrs["truncated"] is True
    assert execute_sql_query("SELECT 1", db).attrs["truncated"] is False


def test_timeout(db):
    with pytest.raises(TimeoutError):
        execute_sql_query("SELECT COUNT(*) FROM range(10000000000)", db, timeout_seconds=1)


def test_missing_database(tmp_path):
    with pytest.raises(FileNotFoundError):
        execute_sql_query("SELECT 1", tmp_path / "nope.duckdb")


def test_validate_sql_no_db_needed():
    assert validate_sql("select 1;") == "select 1"
