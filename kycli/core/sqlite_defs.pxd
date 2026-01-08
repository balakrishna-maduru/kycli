# cython: language_level=3

cdef extern from "sqlite3.h":
    ctypedef struct sqlite3:
        pass
    ctypedef struct sqlite3_stmt:
        pass

    int SQLITE_OK = 0
    int SQLITE_ROW = 100
    int SQLITE_DONE = 101
    
    ctypedef void (*sqlite3_destructor_type)(void*)
    sqlite3_destructor_type SQLITE_TRANSIENT = <sqlite3_destructor_type>-1

    int sqlite3_open(const char *filename, sqlite3 **ppDb)
    int sqlite3_close(sqlite3*)
    int sqlite3_prepare_v2(sqlite3 *db, const char *zSql, int nByte, sqlite3_stmt **ppStmt, const char **pzTail)
    int sqlite3_step(sqlite3_stmt*)
    int sqlite3_finalize(sqlite3_stmt*)
    int sqlite3_exec(sqlite3*, const char *sql, int (*callback)(void*,int,char**,char**), void*, char **errmsg)
    int sqlite3_bind_text(sqlite3_stmt*, int, const char*, int n, sqlite3_destructor_type)
    const unsigned char *sqlite3_column_text(sqlite3_stmt*, int iCol)
    int sqlite3_column_count(sqlite3_stmt *pStmt)
    const char *sqlite3_column_name(sqlite3_stmt*, int N)
    int sqlite3_changes(sqlite3*)
    const char *sqlite3_errmsg(sqlite3*)
    int sqlite3_bind_null(sqlite3_stmt*, int)
