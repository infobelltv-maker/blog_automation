"""
로컬 SQLite 기반 시트 대체 모듈.
블로그 자동화용 — 3개 시트 (상품, 발행로그, SEO데이터)
"""

import sqlite3
import json
import os
import re
from pathlib import Path
from utils.logger import get_logger

log = get_logger('local_db')

DB_PATH = Path(os.getenv('LOCAL_DB', 'data/blog_automation.db'))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_conn = None

SHEET_NAMES = {
    0: 'sheet1_products',
    1: 'sheet2_publish_log',
    2: 'sheet3_seo_data',
}


def _get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _init_tables()
        log.info('로컬 DB 연결: %s', DB_PATH)
    return _conn


def _init_tables():
    conn = _conn
    for idx, name in SHEET_NAMES.items():
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {name} (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sheet_meta (
            sheet_idx INTEGER PRIMARY KEY,
            guide_row TEXT DEFAULT '',
            header_row TEXT DEFAULT ''
        )
    """)
    conn.commit()


class LocalSheet:
    """gspread Worksheet를 모방하는 로컬 시트 객체."""

    def __init__(self, sheet_index: int):
        self.index = sheet_index
        self.table = SHEET_NAMES.get(sheet_index, f'sheet{sheet_index+1}')
        self.id = sheet_index
        self.title = self.table
        _get_conn()

    def get_all_values(self) -> list:
        conn = _get_conn()
        meta = conn.execute(
            "SELECT guide_row, header_row FROM sheet_meta WHERE sheet_idx=?",
            (self.index,)
        ).fetchone()

        result = []
        if meta and meta[0]:
            result.append(json.loads(meta[0]))
        else:
            result.append([f'📊 시트{self.index+1} 데이터'])
        if meta and meta[1]:
            result.append(json.loads(meta[1]))
        else:
            result.append([])
        rows = conn.execute(
            f"SELECT data FROM {self.table} ORDER BY row_id"
        ).fetchall()
        for (data_json,) in rows:
            result.append(json.loads(data_json))

        return result

    def append_row(self, row_data: list):
        conn = _get_conn()
        str_data = [str(v) if v is not None else '' for v in row_data]
        data_json = json.dumps(str_data, ensure_ascii=False)
        conn.execute(f"INSERT INTO {self.table} (data) VALUES (?)", (data_json,))
        conn.commit()

    def update(self, values: list, cell_range: str = 'A1'):
        conn = _get_conn()
        if cell_range.upper() == 'A1' and values:
            guide = json.dumps(values[0] if isinstance(values[0], list) else values, ensure_ascii=False)
            conn.execute(
                "INSERT OR REPLACE INTO sheet_meta (sheet_idx, guide_row, header_row) "
                "VALUES (?, ?, COALESCE((SELECT header_row FROM sheet_meta WHERE sheet_idx=?), ''))",
                (self.index, guide, self.index)
            )
            conn.commit()
            return
        if cell_range.upper() == 'A2' and values:
            header = json.dumps(values[0] if isinstance(values[0], list) else values, ensure_ascii=False)
            conn.execute(
                "INSERT OR REPLACE INTO sheet_meta (sheet_idx, guide_row, header_row) "
                "VALUES (?, COALESCE((SELECT guide_row FROM sheet_meta WHERE sheet_idx=?), ''), ?)",
                (self.index, self.index, header)
            )
            conn.commit()
            return

        m = re.match(r'[A-Z]+(\d+)', cell_range.upper())
        if m:
            sheet_row = int(m.group(1))
            data_row_idx = sheet_row - 3
            if data_row_idx >= 0:
                rows = conn.execute(
                    f"SELECT row_id FROM {self.table} ORDER BY row_id"
                ).fetchall()
                if data_row_idx < len(rows):
                    row_id = rows[data_row_idx][0]
                    row_data = values[0] if isinstance(values[0], list) else values
                    conn.execute(
                        f"UPDATE {self.table} SET data=?, updated_at=CURRENT_TIMESTAMP WHERE row_id=?",
                        (json.dumps(row_data, ensure_ascii=False), row_id)
                    )
                    conn.commit()

    def update_acell(self, cell: str, value):
        m = re.match(r'([A-Z]+)(\d+)', cell.upper())
        if not m:
            return
        col_str, row_num = m.group(1), int(m.group(2))
        col_idx = 0
        for ch in col_str:
            col_idx = col_idx * 26 + (ord(ch) - 64)
        col_idx -= 1

        data_row_idx = row_num - 3
        if data_row_idx < 0:
            return

        conn = _get_conn()
        rows = conn.execute(
            f"SELECT row_id, data FROM {self.table} ORDER BY row_id"
        ).fetchall()
        if data_row_idx < len(rows):
            row_id, data_json = rows[data_row_idx]
            row_data = json.loads(data_json)
            while len(row_data) <= col_idx:
                row_data.append('')
            row_data[col_idx] = value
            conn.execute(
                f"UPDATE {self.table} SET data=?, updated_at=CURRENT_TIMESTAMP WHERE row_id=?",
                (json.dumps(row_data, ensure_ascii=False), row_id)
            )
            conn.commit()

    def delete_rows(self, start: int, end: int = None):
        conn = _get_conn()
        if start <= 2:
            conn.execute(f"DELETE FROM {self.table}")
            conn.commit()
            return

        data_start_idx = start - 3
        rows = conn.execute(
            f"SELECT row_id FROM {self.table} ORDER BY row_id"
        ).fetchall()

        if end is None:
            if data_start_idx < len(rows):
                conn.execute(f"DELETE FROM {self.table} WHERE row_id=?", (rows[data_start_idx][0],))
        else:
            ids_to_delete = [rows[i][0] for i in range(data_start_idx, len(rows))]
            if ids_to_delete:
                placeholders = ','.join('?' * len(ids_to_delete))
                conn.execute(f"DELETE FROM {self.table} WHERE row_id IN ({placeholders})", ids_to_delete)
        conn.commit()

    def format(self, cell_range: str, fmt: dict):
        pass

    def clear(self):
        conn = _get_conn()
        conn.execute(f"DELETE FROM {self.table}")
        conn.execute("DELETE FROM sheet_meta WHERE sheet_idx=?", (self.index,))
        conn.commit()


_sheet_cache = {}


def get_sheet(sheet_index: int) -> LocalSheet:
    if sheet_index not in _sheet_cache:
        _sheet_cache[sheet_index] = LocalSheet(sheet_index)
    return _sheet_cache[sheet_index]


def get_data_rows(ws) -> tuple:
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        return all_values, [], [], 3

    first_row = all_values[0][0] if all_values[0] else ''
    has_guide = any(c in first_row for c in ['📋', '🤖', '✏️', '📊', '📈', '🖼', '✍', '|'])

    if has_guide and len(all_values) >= 2:
        header = all_values[1]
        data = all_values[2:]
        start = 3
    else:
        header = all_values[0]
        data = all_values[1:]
        start = 2

    return all_values, header, data, start


def upsert_row(ws, key_col: int, key_value, row_data: list):
    conn = _get_conn()
    table = ws.table
    key_value_str = str(key_value).strip()
    str_data = [str(v) if v is not None else '' for v in row_data]

    rows = conn.execute(
        f"SELECT row_id, data FROM {table} ORDER BY row_id"
    ).fetchall()

    for row_id, data_json in rows:
        existing = json.loads(data_json)
        cell_val = str(existing[key_col]).strip() if len(existing) > key_col else ''
        if cell_val == key_value_str:
            conn.execute(
                f"UPDATE {table} SET data=?, updated_at=CURRENT_TIMESTAMP WHERE row_id=?",
                (json.dumps(str_data, ensure_ascii=False), row_id)
            )
            conn.commit()
            log.info('업데이트: [%s]', key_value_str)
            return

    ws.append_row(str_data)
    log.info('추가: [%s]', key_value_str)
