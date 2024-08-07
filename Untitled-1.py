import sqlite3
from cylc.flow.util import serialise_set, deserialise_set

db_file = '/tmp/persistent/db (copy)'
point = '20240404T1400Z'
name = 'forecast'
flow_nums = {2}

params: list[tuple] = [(point, name)]
if not flow_nums:
    stmt = rf'''
        UPDATE OR REPLACE
            task_states
        SET
            flow_nums = "{serialise_set()}"
        WHERE
            cycle = ?
            AND name = ?
    '''
else:
    select_stmt = r'''
        SELECT
            flow_nums
        FROM
            task_states
        WHERE
            cycle = ?
            AND name = ?
    '''
    flow_nums_map = {
        x: deserialise_set(x).difference(flow_nums)
        for x, *_ in
        sqlite3.connect(db_file).execute(select_stmt, params[0])
        if deserialise_set(x).intersection(flow_nums)
    }

    stmt = r'''
        UPDATE OR REPLACE
            task_states
        SET
            flow_nums = ?
        WHERE
            cycle = ?
            AND name = ?
            AND flow_nums = ?
    '''
    params = [
        (serialise_set(new), point, name, old)
        for old, new in flow_nums_map.items()
    ]

conn = sqlite3.connect(db_file)
conn.executemany(stmt, params)
conn.commit()
conn.close()
