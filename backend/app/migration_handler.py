"""Temporary Lambda handler for the one-time Supabase PostgreSQL migration."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg import sql


MIGRATIONS = Path(os.environ.get("LAMBDA_TASK_ROOT", "/var/task")) / "migrations"


def _url(name: str) -> str:
    value = os.environ[name]
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def _tables(connection: psycopg.Connection) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute("select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE' order by table_name")
        return [row[0] for row in cursor.fetchall()]


def _columns(connection: psycopg.Connection, table: str) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns where table_schema='public' and table_name=%s and is_generated='NEVER' order by ordinal_position",
            (table,),
        )
        return [row[0] for row in cursor.fetchall()]


def _apply_schema(target: psycopg.Connection) -> None:
    with target.cursor() as cursor:
        cursor.execute("create extension if not exists pgcrypto", prepare=False)
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            cursor.execute(migration.read_text(encoding="utf-8"), prepare=False)
    target.commit()


def _copy_table(source: psycopg.Connection, target: psycopg.Connection, table: str) -> int:
    columns = _columns(source, table)
    names = sql.SQL(", ").join(map(sql.Identifier, columns))
    copy_out = sql.SQL("copy {} ({}) to stdout with (format binary)").format(sql.Identifier(table), names)
    copy_in = sql.SQL("copy {} ({}) from stdin with (format binary)").format(sql.Identifier(table), names)
    with source.cursor() as source_cursor, target.cursor() as target_cursor:
        with source_cursor.copy(copy_out) as reader, target_cursor.copy(copy_in) as writer:
            for block in reader:
                writer.write(block)
        target_cursor.execute(sql.SQL("select count(*) from {}").format(sql.Identifier(table)))
        return int(target_cursor.fetchone()[0])


def handler(_event, _context):
    counts: dict[str, int] = {}
    with psycopg.connect(_url("SOURCE_DATABASE_URL"), connect_timeout=20) as source:
        with psycopg.connect(_url("TARGET_DATABASE_URL"), connect_timeout=20) as target:
            _apply_schema(target)
            source_tables = _tables(source)
            target_tables = set(_tables(target))
            tables = [table for table in source_tables if table in target_tables]
            with target.cursor() as cursor:
                cursor.execute("set session_replication_role = replica")
                identifiers = sql.SQL(", ").join(sql.Identifier(table) for table in sorted(target_tables))
                cursor.execute(sql.SQL("truncate table {} restart identity cascade").format(identifiers))
            for table in tables:
                counts[table] = _copy_table(source, target, table)
            with target.cursor() as cursor:
                cursor.execute("set session_replication_role = origin")
            target.commit()
    return {"tables": len(counts), "rows": sum(counts.values()), "counts": counts}
