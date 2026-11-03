#!/usr/bin/env python3
"""Month-wise belt consumption that does not depend on the SBC pivot (which needs a manual refresh).

1. consumption_log.csv - every replacement / piece addition ever seen in the Daily Report (one line per
   conveyor + type + date). The Daily Report keeps only the LATEST replacement of a belt, so an earlier
   replacement disappears when a belt is replaced again; the log keeps it. Lines are only added, never removed.
2. sbc_monthly.csv - metres per FY / department / conveyor / month. The FY total of each conveyor is always the
   SBC sheet main table (Replacement + Piece Addition FY'xx). Months come from the log; metres the log does not
   explain (old replacements from before the log started) take the months of the frozen pivot copy
   (sbc_month_base.csv, last good pivot of 27-Oct-2026), and only then the month of the latest Daily Report entry.

usage: consumption.py log            (update the log from daily.csv)
       consumption.py monthly        (write sbc_monthly.csv)
"""
import csv, datetime as D, os, re, sys

MONTHS = ['April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'January', 'February', 'March']
LOG_COLS = ['conv', 'type', 'date', 'metres', 'joint', 'vendor', 'first_seen']


def key(s):
    return re.sub(r'\s+', '', str(s or '')).upper()


def num(v):
    try:
        return float(str(v).replace(',', '').strip())
    except ValueError:
        return 0.0


def pdate(v):
    t = str(v or '').strip()
    if re.fullmatch(r'\d{5}(\.\d+)?', t):
        return D.date(1899, 12, 30) + D.timedelta(days=int(float(t)))
    m = re.fullmatch(r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})', t)
    if m:
        try:
            return D.date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            return None
    return None


def fy_of(d):
    return d.year - 2000 + (1 if d.month >= 4 else 0)


def mi_of(d):
    return (d.month + 8) % 12


def read(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    return [{(k or '').replace('_x002e_', '.').replace('_x0027_', "'").strip(): v for k, v in r.items()} for r in rows]


def daily_events(rows):
    out = []
    for r in rows:
        c = key(r.get('Conveyor'))
        if not c or c == '0':
            continue
        d = pdate(r.get('Final Replacement Date'))
        if d and d.year > 2000:
            out.append((c, 'R', d, num(r.get('Cosnumption') or r.get('Consumption')), (r.get('Type of joint') or '').strip(), (r.get('Vendor') or '').strip()))
        for i in range(1, 9):
            d = pdate(r.get(f'Piece Addition date{i}'))
            if d and d.year > 2000:
                out.append((c, 'P', d, num(r.get(f'PA consumption{i}')), (r.get(f'Type of PA Joint{i}') or '').strip(), (r.get(f'PA vendor{i}') or '').strip()))
    return out


def load_log(path):
    return {(r['conv'], r['type'], r['date']): r for r in read(path)}


def save_log(path, log):
    rows = sorted(log.values(), key=lambda r: (r['date'], r['conv'], r['type']))
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=LOG_COLS)
        w.writeheader()
        w.writerows(rows)


def add_to_log(log, events, seen):
    """events = one full Daily Report copy. A date that was corrected in the sheet (same conveyor + type + metres,
    old date gone from the sheet, new date within 10 days) replaces the old line instead of adding a second one."""
    n = 0
    now = {(c, t, d.isoformat()) for c, t, d, m, j, v in events}
    for c, t, d, m, j, v in events:
        k = (c, t, d.isoformat())
        if k not in log:
            for ok, r in list(log.items()):
                if ok[0] == c and ok[1] == t and ok not in now and abs((D.date.fromisoformat(ok[2]) - d).days) <= 10 and abs(num(r['metres']) - m) < 0.01:
                    del log[ok]   # date corrected in the Daily Report
                    n -= 1
                    break
            log[k] = {'conv': c, 'type': t, 'date': d.isoformat(), 'metres': f'{m:g}', 'joint': j, 'vendor': v, 'first_seen': seen}
            n += 1
        elif m > 0 and num(log[k]['metres']) != m:   # metres corrected later in the Daily Report
            log[k]['metres'] = f'{m:g}'
    return n


def monthly(sbc_path, log_path, base_path, out_path):
    sbc = read(sbc_path)
    log = load_log(log_path)
    base = read(base_path)
    fys = sorted({int(m.group(1)) for k in (sbc[0].keys() if sbc else []) for m in [re.match(r"Replacement FY'(\d+)", k)] if m})
    main, dept = {}, {}
    for r in sbc:
        c = key(r.get('Conveyor'))
        if not c or c == '0':
            continue
        dept.setdefault(c, (r.get('Department') or '').strip())
        for fy in fys:
            for t, col in (('R', f"Replacement FY'{fy}"), ('P', f"Piece Addition FY'{fy}")):
                v = num(r.get(col))
                if v:
                    main[(fy, c, t)] = main.get((fy, c, t), 0) + v
    bm = {}
    for r in base:
        k = (int(r['fy']), r['conv'])
        bm.setdefault(k, [0.0] * 12)[int(r['mi'])] += num(r['m'])
        dept.setdefault(r['conv'], r.get('dept', ''))
    ev = {}
    for r in log.values():
        d = D.date.fromisoformat(r['date'])
        ev.setdefault((fy_of(d), r['conv'], r['type']), []).append((d, num(r['metres'])))
    out = []
    for fy in fys:
        convs = sorted({c for (f, c, t) in main if f == fy})
        for c in convs:
            months = [0.0] * 12
            src = [''] * 12
            gap_total = 0.0
            last_d = None
            for t in ('R', 'P'):
                tot = main.get((fy, c, t), 0)
                if tot <= 0.01:
                    continue
                evs = sorted(ev.get((fy, c, t), []), key=lambda x: x[0], reverse=True)   # newest first
                for d, m in evs:
                    last_d = max(last_d, d) if last_d else d
                    if tot <= 0.01 or m <= 0:
                        continue
                    take = min(tot, m)
                    months[mi_of(d)] += take
                    src[mi_of(d)] = 'daily report log'
                    tot -= take
                gap_total += max(0.0, tot)
            # metres the log cannot explain: months of the frozen pivot copy, beyond what the log already placed
            b = bm.get((fy, c))
            if gap_total > 0.01 and b:
                for i in range(12):
                    room = max(0.0, b[i] - months[i])
                    take = min(room, gap_total)
                    if take > 0.01:
                        months[i] += take
                        src[i] = (src[i] + ' + ' if src[i] else '') + 'pivot copy 27-Oct-2026'
                        gap_total -= take
            if gap_total > 0.01:   # still unknown: month of the latest entry (or today) - flagged
                d = last_d or D.date.today()
                if fy_of(d) != fy:
                    d = D.date(2000 + fy, 3, 1)
                months[mi_of(d)] += gap_total
                src[mi_of(d)] = (src[mi_of(d)] + ' + ' if src[mi_of(d)] else '') + 'no date - month of latest entry'
            for i in range(12):
                if months[i] > 0.01:
                    out.append({'fy': fy, 'dept': dept.get(c, ''), 'conv': c, 'mi': i, 'month': MONTHS[i], 'metres': f'{months[i]:g}', 'source': src[i]})
    with open(out_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['fy', 'dept', 'conv', 'mi', 'month', 'metres', 'source'])
        w.writeheader()
        w.writerows(out)
    return out


if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    P = lambda n: os.path.join(root, n)
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd in ('log', 'all'):
        log = load_log(P('consumption_log.csv'))
        n = add_to_log(log, daily_events(read(P('daily.csv'))), D.date.today().isoformat())
        save_log(P('consumption_log.csv'), log)
        print('log: +', n, 'new, total', len(log))
    if cmd in ('monthly', 'all'):
        o = monthly(P('sbc.csv'), P('consumption_log.csv'), P('sbc_month_base.csv'), P('sbc_monthly.csv'))
        print('monthly rows', len(o))
