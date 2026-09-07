#!/usr/bin/env python3
"""Read-only native-client probe. Requires explicit existing record ID.

Uses the caller's configured credentials; never prints them or record bodies.
Does not register hooks, install plugins, or write Reqall records.
"""
from pathlib import Path
import json
import sys

if len(sys.argv) != 2 or not sys.argv[1].isdigit():
    raise SystemExit('usage: probe_readback.py EXISTING_RECORD_ID')
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reqall import client

rid = int(sys.argv[1])
result = client.mcp_call('get_record', {'id': rid})
data = result.get('data')
verified = result.get('ok') is True and isinstance(data, dict) and data.get('id') == rid
print(json.dumps({'ok': bool(verified), 'record_id': data.get('id') if isinstance(data, dict) else None,
                  'project_id': data.get('project_id') if isinstance(data, dict) else None,
                  'kind': data.get('kind') if isinstance(data, dict) else None,
                  'data_type': type(data).__name__, 'error': result.get('error'),
                  'operation': 'get_record', 'read_only': True}))
raise SystemExit(not verified)
