import os, time, gspread
from google.oauth2.service_account import Credentials
from utils.logger import get_logger

log = get_logger('sheets')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/drive']
_gc = None
_spreadsheet = None
_sheet_cache = {}

def _connect() -> None:
    global _gc, _spreadsheet
    if _gc is not None:
        return
    creds = Credentials.from_service_account_file(
        os.getenv('GOOGLE_CRED', 'credentials.json'),
        scopes=SCOPES)
    _gc = gspread.authorize(creds)
    _spreadsheet = _gc.open_by_key(os.getenv('SHEETS_ID'))
    log.info('Sheets 연결 완료')

def get_sheet(sheet_index: int):
    if sheet_index not in _sheet_cache:
        _connect()
        _sheet_cache[sheet_index] = _spreadsheet.get_worksheet(sheet_index)
    return _sheet_cache[sheet_index]

def get_data_rows(ws) -> tuple:
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        return all_values, [], [], 3

    first_row = all_values[0][0] if all_values[0] else ''
    has_guide = any(c in first_row for c in ['📋', '🤖', '✏️', '📊', '📈', '🖼', '✍', '|'])

    if has_guide and len(all_values) >= 2:
        header = all_values[1]
        data   = all_values[2:]
        start  = 3
    else:
        header = all_values[0]
        data   = all_values[1:]
        start  = 2

    return all_values, header, data, start

def upsert_row(ws, key_col, key_value, row_data):
    all_values = ws.get_all_values()
    _, header, data_rows, data_start = get_data_rows(ws)

    key_value_str = str(key_value).strip()

    for i, row in enumerate(data_rows):
        if not row:
            continue
        cell_val = str(row[key_col]).strip() if len(row) > key_col else ''
        if cell_val == key_value_str:
            sheet_row = data_start + i
            ws.update([row_data], f'A{sheet_row}')
            time.sleep(1.1)
            log.info('업데이트: 행%d [%s]', sheet_row, key_value_str)
            return

    ws.append_row(row_data)
    time.sleep(1.1)
    log.info('추가: [%s]', key_value_str)
