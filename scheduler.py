"""GA exam scheduling and deterministic room/invigilator allocation.

A chromosome is a list of slot indices in the same order as subjects.csv.
The GA minimizes weighted student clashes and multi-room resource shortages.
"""
from collections import Counter, defaultdict
from functools import lru_cache
from datetime import datetime
import random
import pandas as pd

REQUIRED = {
    'subjects': ['SubjectID', 'SubjectName'],
    'students': ['StudentID', 'StudentName'],
    'registrations': ['StudentID', 'SubjectID'],
    'rooms': ['RoomID', 'Capacity'],
    'invigilators': ['InvigilatorID', 'InvigilatorName'],
    'slots': ['SlotID', 'Date', 'Session', 'StartTime', 'EndTime'],
}


def validate_inputs(data):
    issues = []
    for name, cols in REQUIRED.items():
        if name not in data:
            issues.append(f'Missing dataset: {name}.csv')
            continue
        df = data[name]
        missing = set(cols) - set(df.columns)
        if missing:
            issues.append(f'{name}.csv missing columns: {", ".join(sorted(missing))}')
            continue
        if df.empty:
            issues.append(f'{name}.csv must contain at least one row')
        if df[cols].isna().any().any():
            issues.append(f'{name}.csv contains blank required values')
    if issues:
        return issues
    for name, col in [('subjects','SubjectID'), ('students','StudentID'), ('rooms','RoomID'), ('invigilators','InvigilatorID'), ('slots','SlotID')]:
        if data[name][col].astype(str).duplicated().any():
            issues.append(f'Duplicate {col} values in {name}.csv')
    for name, col, parent, parent_col in [('registrations','StudentID','students','StudentID'), ('registrations','SubjectID','subjects','SubjectID')]:
        unknown = set(data[name][col].astype(str)) - set(data[parent][parent_col].astype(str))
        if unknown:
            issues.append(f'Unknown {col} in {name}.csv: {sorted(unknown)}')
    if data['registrations'][['StudentID','SubjectID']].duplicated().any():
        issues.append('Duplicate student-subject registrations')
    capacities = pd.to_numeric(data['rooms']['Capacity'], errors='coerce')
    if capacities.isna().any() or (capacities <= 0).any() or (capacities % 1 != 0).any():
        issues.append('Room capacities must be positive whole numbers')
    for _, r in data['rooms'].iterrows():
        status = str(r.get('Status', 'Available')).strip().lower()
        if status not in ('available', 'unavailable'):
            issues.append(f"Invalid room status for {r.RoomID}")
        blocked = blocked_slots(r)
        if blocked - set(data['slots']['SlotID'].astype(str)):
            issues.append(f"Unknown unavailable slot for {r.RoomID}")
    slots = data['slots']
    intervals = []
    for _, row in slots.iterrows():
        try:
            start = datetime.fromisoformat(f'{row.Date} {row.StartTime}')
            end = datetime.fromisoformat(f'{row.Date} {row.EndTime}')
            if end <= start:
                raise ValueError('end must be later than start')
            intervals.append((str(row.SlotID), start, end))
        except (ValueError, TypeError):
            issues.append(f'Invalid date/time for slot {row.SlotID}; use YYYY-MM-DD and HH:MM')
    # The current algorithm treats each SlotID as a unique period and assumes non-overlapping periods.
    for i, (id1, a, b) in enumerate(intervals):
        for id2, c, d in intervals[i+1:]:
            if a < d and c < b:
                issues.append(f'Slots {id1} and {id2} overlap in time; use non-overlapping slots')
    return issues


def generate_schedule(data, population_size=80, generations=120, seed=42):
    errors = validate_inputs(data)
    if errors:
        raise ValueError('\n'.join(errors))
    rng = random.Random(seed)
    subjects = data['subjects']['SubjectID'].astype(str).tolist()
    slots = data['slots']['SlotID'].astype(str).tolist()
    subject_index = {s:i for i,s in enumerate(subjects)}
    pairs = Counter()
    for _, group in data['registrations'].groupby('StudentID'):
        ids = sorted(set(group['SubjectID'].astype(str)))
        for i, a in enumerate(ids):
            for b in ids[i+1:]:
                pairs[(subject_index[a], subject_index[b])] += 1
    enrollment = data['registrations'].groupby('SubjectID')['StudentID'].nunique().to_dict()
    enrollment = {str(k): v for k,v in enrollment.items()}
    room_lists = [available_rooms(data, slot) for slot in slots]
    staff_count = len(data['invigilators'])

    @lru_cache(maxsize=50000)
    def resource_cost(slot_idx, counts):
        plan = room_plan(counts, room_lists[slot_idx], staff_count)
        return sum(100 + missing for _, _, missing in plan if missing)

    @lru_cache(maxsize=100000)
    def cached_penalty(chrom):
        clashes = sum(weight for (i,j), weight in pairs.items() if chrom[i] == chrom[j])
        by_slot = defaultdict(list)
        for i, slot_idx in enumerate(chrom):
            count = int(enrollment.get(subjects[i], 0))
            if count: by_slot[slot_idx].append(count)
        return clashes * 1000 + sum(resource_cost(k, tuple(sorted(v, reverse=True))) for k,v in by_slot.items())

    def penalty(chrom):
        return cached_penalty(tuple(chrom))

    def tournament(pop):
        candidates = rng.sample(pop, k=min(3, len(pop)))
        return min(candidates, key=penalty)

    pop = [[rng.randrange(len(slots)) for _ in subjects] for _ in range(population_size)]
    # Seed with round-robin chromosomes, useful when slots >= subjects.
    for shift in range(min(population_size, len(slots))):
        pop[shift] = [(i+shift) % len(slots) for i in range(len(subjects))]
    history = []
    best = min(pop, key=penalty)[:]
    for generation in range(generations+1):
        current = min(pop, key=penalty)
        if penalty(current) < penalty(best):
            best = current[:]
        history.append({'Generation': generation, 'Penalty': penalty(best), 'Fitness': round(1/(1+penalty(best)), 6)})
        if penalty(best) == 0:
            break
        next_pop = [best[:]]
        while len(next_pop) < population_size:
            a, b = tournament(pop), tournament(pop)
            cut = rng.randrange(1, len(subjects)) if len(subjects) > 1 else 1
            child = a[:cut] + b[cut:]
            for i in range(len(child)):
                if rng.random() < 0.12:
                    child[i] = rng.randrange(len(slots))
            next_pop.append(child)
        pop = next_pop

    schedule = data['subjects'].copy().reset_index(drop=True)
    schedule['SlotID'] = [slots[i] for i in best]
    schedule = schedule.merge(data['slots'], on='SlotID', how='left')
    schedule['StudentCount'] = schedule['SubjectID'].astype(str).map(enrollment).fillna(0).astype(int)
    schedule = schedule.sort_values(['Date','StartTime','SubjectID']).reset_index(drop=True)
    allocated, allocation_issues = allocate(schedule, data)
    issues = audit(allocated, data) + allocation_issues
    return allocated, pd.DataFrame(history), issues


def blocked_slots(room):
    value = room.get('UnavailableSlots', '')
    return set() if pd.isna(value) else {x.strip() for x in str(value).split(';') if x.strip()}


def available_rooms(data, slot):
    return sorted([(str(r.RoomID), int(r.Capacity)) for _, r in data['rooms'].iterrows()
                   if str(r.get('Status', 'Available')).strip().lower() == 'available'
                   and str(slot) not in blocked_slots(r)], key=lambda x: (-x[1], x[0]))


def room_plan(counts, rooms, staff_count):
    # Exclusive room per exam; one invigilator per occupied room.
    remaining = list(rooms)
    result = []
    for count in counts:
        needed = count
        assigned = []
        while needed and remaining and staff_count:
            fits = [r for r in remaining if r[1] >= needed]
            room = min(fits, key=lambda r: (r[1], r[0])) if fits else remaining[0]
            remaining.remove(room)
            occupied = min(needed, room[1])
            assigned.append((room[0], room[1], occupied))
            needed -= occupied
            staff_count -= 1
        result.append((count, assigned, needed))
    return result


def allocate(schedule, data):
    staff = sorted(data['invigilators']['InvigilatorID'].astype(str))
    duty = Counter()
    results, issues = [], []
    for slot, group in schedule.groupby('SlotID', sort=False):
        rows = list(group.sort_values(['StudentCount','SubjectID'], ascending=[False,True]).itertuples(index=False))
        plans = room_plan([int(r.StudentCount) for r in rows], available_rooms(data, slot), len(staff))
        free = set(staff)
        for row, (_, assignments, missing) in zip(rows, plans):
            base = row._asdict()
            for room, cap, occupied in assignments:
                teacher = min(free, key=lambda x: (duty[x], x))
                free.remove(teacher); duty[teacher] += 1
                results.append(dict(base, RoomID=room, InvigilatorID=teacher, RoomCapacity=cap, AllocatedStudents=occupied, UnallocatedStudents=0))
            if missing or not assignments:
                results.append(dict(base, RoomID='', InvigilatorID='', RoomCapacity=0, AllocatedStudents=0, UnallocatedStudents=missing))
            if missing:
                issues.append(f'{row.SubjectID} in {slot}: {missing} students without seats (room or staff shortage)')
    return pd.DataFrame(results), issues


def seating_table(schedule, data):
    records = []
    students = data['students'].set_index('StudentID')['StudentName'].to_dict()
    for subject, group in schedule.groupby('SubjectID', sort=False):
        ids = sorted(data['registrations'].loc[data['registrations']['SubjectID'].astype(str)==str(subject), 'StudentID'].astype(str))
        offset = 0
        for row in group.itertuples(index=False):
            count = int(row.AllocatedStudents or row.UnallocatedStudents)
            for seat, student in enumerate(ids[offset:offset+count], 1):
                records.append(dict(StudentID=student, StudentName=students.get(student, ''), SubjectName=row.SubjectName, SubjectID=subject, Date=row.Date, Session=row.Session, StartTime=row.StartTime, EndTime=row.EndTime, SlotID=row.SlotID, RoomID=row.RoomID or 'UNASSIGNED', SeatNo=seat if row.RoomID else 'UNASSIGNED'))
            offset += count
    return pd.DataFrame(records, columns=['StudentID','StudentName','SubjectName','SubjectID','Date','Session','StartTime','EndTime','SlotID','RoomID','SeatNo'])


def audit(schedule, data):
    issues = []
    master = schedule[['SubjectID','SlotID']].drop_duplicates()
    if master['SubjectID'].duplicated().any() or set(master.SubjectID) != set(data['subjects'].SubjectID):
        issues.append('Subject timetable coverage error')
    joined = data['registrations'].merge(master, on='SubjectID')
    clashes = joined.duplicated(['StudentID','SlotID'], keep=False)
    if clashes.any(): issues.append(f'{int(clashes.sum())} student registrations have overlapping exams')
    active = schedule[schedule.AllocatedStudents > 0]
    for col in ['RoomID','InvigilatorID']:
        if active[col].eq('').any() or active.duplicated(['SlotID',col]).any(): issues.append(f'Missing or double-booked {col}')
    for row in active.itertuples(index=False):
        if dict(available_rooms(data,row.SlotID)).get(row.RoomID,0) < row.AllocatedStudents:
            issues.append(f'Room capacity or availability violation: {row.RoomID} / {row.SlotID}')
    seats = seating_table(schedule,data)
    if len(seats) != len(data['registrations']) or seats.duplicated(['StudentID','SubjectID']).any(): issues.append('Student seating coverage error')
    if seats.RoomID.eq('UNASSIGNED').any(): issues.append('Some students have no assigned seat')
    if seats[seats.RoomID.ne('UNASSIGNED')].duplicated(['SlotID','RoomID','SeatNo']).any(): issues.append('Duplicate seat assignment')
    return sorted(set(issues))
