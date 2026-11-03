"""Parameterized MySQL access. Keep SQL visible for database coursework."""
import os
from contextlib import contextmanager

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def connect():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "instagram_term_2026"),
        charset="utf8mb4",
    )


@contextmanager
def cursor_for(write=False):
    connection = connect()
    cursor = connection.cursor(dictionary=True)
    try:
        yield cursor
        if write:
            connection.commit()
    except Exception:
        if write:
            connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def one(sql, params=()):
    with cursor_for() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def all_rows(sql, params=()):
    with cursor_for() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def change(sql, params=()):
    with cursor_for(write=True) as cur:
        cur.execute(sql, params)
        return cur.lastrowid
