"""Conservative publication policy; NEVER manufactures FCC coverage.

FCC processing: completed federal business days, not yesterday unconditionally.
Our bounded availability deadline is noon Puerto Rico on the following calendar
day. No overdue business day may be missing; absolute coverage age <=4 days.
Holiday calendar is reviewed for 2026-2030 only, national OPM holidays.
"""
import datetime as D

PR=D.timezone(D.timedelta(hours=-4))
MAX_AGE_DAYS=4
POLICY='fcc-business-day-noon-pr-v1'

def observed(day):
    return day-D.timedelta(days=1) if day.weekday()==5 else day+D.timedelta(days=1) if day.weekday()==6 else day

def nth(year,month,weekday,n):
    first=D.date(year,month,1)
    return first+D.timedelta(days=(weekday-first.weekday())%7+7*(n-1))

def holidays(year):
    days=set()
    # Adjacent years include New Year's observed on previous December 31.
    for y in (year-1,year,year+1):
        days.update(observed(D.date(y,m,d)) for m,d in ((1,1),(6,19),(7,4),(11,11),(12,25)))
        days.update((nth(y,1,0,3),nth(y,2,0,3),nth(y,9,0,1),nth(y,10,0,2),nth(y,11,3,4)))
        days.add(D.date(y,5,31)-D.timedelta(days=(D.date(y,5,31).weekday()-0)%7))
    return days

def expected_coverage(today,now=None):
    if not 2026<=today.year<=2030:raise ValueError('Holiday calendar needs review')
    if now is None:now=D.datetime.combine(today,D.time(23,59),PR)
    if now.tzinfo is None or now.astimezone(PR).date()!=today:raise ValueError('Invalid PR evaluation time')
    closed=holidays(today.year)
    candidate=today-D.timedelta(days=1)
    while True:
        deadline=D.datetime.combine(candidate+D.timedelta(days=1),D.time(12),PR)
        if candidate.weekday()<5 and candidate not in closed and now>=deadline:return candidate
        candidate-=D.timedelta(days=1)

def assess(through,today,now=None):
    through=D.date.fromisoformat(through)
    expected=expected_coverage(today,now)
    age=(today-through).days
    reason='future_coverage' if age<0 else 'absolute_age_exceeded' if age>MAX_AGE_DAYS else 'overdue_business_day' if through<expected else 'on_schedule'
    return {'policy':POLICY,'expected_through_date':expected.isoformat(),
            'source_through_date':through.isoformat(),'coverage_age_days':age,
            'max_age_days':MAX_AGE_DAYS,'stale':reason!='on_schedule','reason':reason}
