#!/usr/bin/env python3
"""Keep a day-wise history of the Next CBM date of every conveyor.

The thickness sheet (data.csv) only holds the latest CBM date. This script
compares it with the last saved value in cbm_history.csv and appends a row
only for belts whose CBM date, last thickness date or minimum thickness has
changed. The dashboard uses this file to show "CBM was X, now it is Y".

Usage:  python3 tools/cbm_history.py data.csv cbm_history.csv [YYYY-MM-DD]
"""
import csv
import datetime
import io
import os
import sys

FIELDS = ['Date', 'Conveyor', 'Dept', 'NextCBM', 'LastThicknessDate', 'MinThickness', 'Criticality']


def to_date(v):
    v = (v or '').strip()
    if not v:
        return ''
    try:
        f = float(v)
        if 20000 < f < 80000:
            # same as the dashboard: Excel serial (UTC) shown in India time (IST)
            return (datetime.datetime(1899, 12, 30) + datetime.timedelta(days=f, hours=5, minutes=30)).date().isoformat()
    except ValueError:
        pass
    for fm in ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%b-%Y', '%d-%b-%y'):
        try:
            return datetime.datetime.strptime(v.split(' ')[0], fm).date().isoformat()
        except ValueError:
            pass
    return ''


def read_thickness(text):
    rows = list(csv.DictReader(io.StringIO(text.lstrip('﻿'))))
    if not rows:
        return {}
    keys = list(rows[0].keys())
    k_cbm = next((k for k in keys if k and k.replace('\n', ' ').startswith('Next Prediction') and 'CBM' in k), None)
    if not k_cbm:
        return {}
    out = {}
    for r in rows:
        c = (r.get('Conveyor') or '').strip()
        if not c or c.startswith('#'):
            continue
        out[c.upper()] = {
            'Conveyor': c,
            'Dept': (r.get('DEPT') or '').strip(),
            'NextCBM': to_date(r.get(k_cbm)),
            'LastThicknessDate': to_date(r.get('Last Thickness Date')),
            'MinThickness': (r.get('MIN THICKNESS') or '').strip(),
            'Criticality': (r.get('Criticality') or '').strip(),
        }
    return out


def last_saved(path):
    last = {}
    if os.path.exists(path):
        with open(path, newline='', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                last[r['Conveyor'].strip().upper()] = r
    return last


def update(text, path, day):
    now = read_thickness(text)
    if not now:
        return 0
    last = last_saved(path)
    new = []
    for c, r in now.items():
        p = last.get(c)
        if not r['NextCBM']:
            continue
        if p and (p['NextCBM'], p['LastThicknessDate'], p['MinThickness']) == (r['NextCBM'], r['LastThicknessDate'], r['MinThickness']):
            continue
        new.append(dict(r, Date=day))
    if new:
        exists = os.path.exists(path)
        with open(path, 'a', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if not exists:
                w.writeheader()
            for r in sorted(new, key=lambda x: x['Conveyor']):
                w.writerow({k: r.get(k, '') for k in FIELDS})
    return len(new)


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    day = sys.argv[3] if len(sys.argv) > 3 else ist.date().isoformat()
    with open(src, encoding='utf-8', errors='replace') as f:
        n = update(f.read(), dst, day)
    print(f'cbm_history: {n} belt(s) changed on {day}')
