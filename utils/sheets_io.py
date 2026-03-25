"""
시트 I/O — 로컬 SQLite 모드 (기본) / 구글 시트 모드 (선택)
환경변수 USE_GOOGLE_SHEETS=1 로 설정하면 구글 시트 사용.
기본값은 로컬 SQLite.
"""
import os

if os.getenv('USE_GOOGLE_SHEETS', '').strip() == '1':
    from utils.sheets_io_google import *
    from utils.sheets_io_google import _connect, _spreadsheet, _sheet_cache
else:
    from utils.local_db import *
    from utils.local_db import _sheet_cache
    def _connect(): pass
    class _DummySpreadsheet:
        def worksheets(self):
            from utils.local_db import get_sheet, SHEET_NAMES
            return [get_sheet(i) for i in sorted(SHEET_NAMES.keys())]
    _spreadsheet = _DummySpreadsheet()
