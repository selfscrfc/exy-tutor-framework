"""Public CLI checks for recommendations, focus timing, and pace."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

import test_workflow as fixtures
DAY = fixtures.DAY


class TimeAndWorkloadTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.PilotWorkflow(methodName='runTest')
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.session = self.h.setup_pilot()

    def analyze_input(self):
        return {'start_date': DAY, 'deadline': '2030-01-20', 'timezone': 'UTC', 'study_days': [0,1,2,3,4],
                'unavailable_dates': [], 'weekly_capacity_hours': 10, 'daily_capacity_hours': [2,2,2,2,2,0,0],
                'effort': [{'goal_id': goal, 'min_hours':4, 'max_hours':6, 'basis':'Diagnostic task and curriculum breakdown',
                            'source_refs':['fixture:diagnostic', 'fixture:syllabus']} for goal in ['goal-001','goal-002']],
                'overhead_hours': {'min':2,'max':4,'basis':'Review and assessment time excluded from leaf estimates'}, 'buffer_percent':25}

    def test_recommendation_uses_scope_deadline_and_capacity_without_committing(self):
        data=self.analyze_input()
        result=self.h.cli('workload','analyze','--file',self.h.file(data))
        self.assertEqual(result['recommendation']['total_hours_max'],20)
        self.assertEqual(result['recommendation']['weekly_hours_max'],10)
        self.assertEqual(result['recommendation']['hours_per_study_day_max'],2)
        self.assertEqual(result['recommendation']['feasibility'],'fits_estimate_range')
        self.assertEqual(self.h.read('objective.json')['weekly_hours'],6)
        self.assertFalse(result['is_user_commitment'])
        data.update(weekly_capacity_hours=5,daily_capacity_hours=[1,1,1,1,1,0,0])
        conflict=self.h.cli('workload','analyze','--file',self.h.file(data))
        self.assertEqual(conflict['recommendation']['feasibility'],'scope_deadline_conflict')
        self.assertEqual(conflict['recommendation']['upper_estimate_shortfall_hours'],10)

    def test_impossible_daily_requirement_is_reported_even_without_capacity(self):
        data=self.analyze_input()
        data.update(deadline=DAY,weekly_capacity_hours=None,daily_capacity_hours=None)
        for effort in data['effort']:
            effort.update(min_hours=100,max_hours=200)
        result=self.h.cli('workload','analyze','--file',self.h.file(data))
        self.assertEqual(result['recommendation']['feasibility'],'scope_deadline_conflict')

    def test_missing_estimates_do_not_become_a_fabricated_recommendation(self):
        data=self.analyze_input(); data['effort'].pop()
        result=self.h.cli('workload','analyze','--file',self.h.file(data))
        self.assertEqual(result['status'],'insufficient_evidence')
        self.assertIsNone(result['recommendation'])
        data['effort'][0]['source_refs']=[]
        self.h.cli('workload','analyze','--file',self.h.file(data),ok=False)

    def test_timer_pause_restart_retry_and_session_totals(self):
        timer=self.h.cli('time','start','--actor','tutor','--request-id','start-1','--session',self.session,
                         '--goal','goal-001','--activity','Independent exercise')
        paused=self.h.cli('time','pause','--actor','tutor','--request-id','pause-1','--timer',timer['id'],
                          '--version','1',at=DAY+'T10:25:00+00:00')
        retry=self.h.cli('time','pause','--actor','tutor','--request-id','pause-1','--timer',timer['id'],
                         '--version','1',at=DAY+'T10:30:00+00:00')
        self.assertEqual(paused,retry)
        self.assertEqual(len(self.h.read('time-entries.jsonl')),1)
        self.h.cli('time','resume','--actor','tutor','--request-id','resume-1','--timer',timer['id'],
                   '--version','2',at=DAY+'T10:40:00+00:00')
        self.h.cli('time','stop','--actor','tutor','--request-id','stop-1','--timer',timer['id'],
                   '--version','3',at=DAY+'T11:00:00+00:00')
        session=self.h.cli('session','end','--note','Continue tomorrow',at=DAY+'T11:00:00+00:00')
        self.assertEqual(session['actual_minutes'],45)
        report=self.h.cli('pace','--from-date',DAY,'--to-date',DAY,at=DAY+'T11:00:00+00:00')
        self.assertEqual(report['total_logged_hours'],0.75)
        self.assertEqual(report['legacy_session_minutes_not_allocated_to_days'],0)
        self.assertEqual(report['completed_goal_effort_samples'],[])

    def test_session_cannot_end_before_first_running_timer_is_saved(self):
        timer=self.h.cli('time','start','--actor','tutor','--request-id','start-first',
                         '--session',self.session,'--activity','Practice')
        error=self.h.cli('session','end','--note','Continue tomorrow','--minutes','0',
                         at=DAY+'T10:20:00+00:00',ok=False)
        self.assertIn('Pause or stop',error)
        self.assertIsNone(self.h.read('sessions.json')[0]['ended_at'])
        self.h.cli('time','stop','--actor','tutor','--request-id','stop-first',
                   '--timer',timer['id'],'--version','1',at=DAY+'T10:20:00+00:00')
        ended=self.h.cli('session','end','--note','Continue tomorrow',at=DAY+'T10:20:00+00:00')
        self.assertEqual(ended['actual_minutes'],20)

    def test_other_actor_stale_version_and_parallel_timer_are_rejected(self):
        t=self.h.cli('time','start','--actor','first','--request-id','start','--activity','Study')
        self.h.cli('time','start','--actor','second','--request-id','start2','--activity','Other task',ok=False)
        self.h.cli('time','pause','--actor','second','--request-id','pause2','--timer',t['id'],'--version','1',ok=False)
        self.h.cli('time','pause','--actor','first','--request-id','pause','--timer',t['id'],'--version','2',ok=False)
        self.assertEqual(self.h.cli('time','status')[0]['version'],1)

    def test_long_timer_requires_explicit_confirmation(self):
        t=self.h.cli('time','start','--actor','tutor','--request-id','start','--activity','Study')
        args=('time','stop','--actor','tutor','--request-id','stop','--timer',t['id'],'--version','1')
        self.h.cli(*args,at=DAY+'T16:00:00+00:00',ok=False)
        self.assertEqual(self.h.read('time-entries.jsonl'),[])
        self.h.cli(*args,'--confirm-long',at=DAY+'T16:00:00+00:00')
        self.assertEqual(len(self.h.read('time-entries.jsonl')),1)

    def test_overlap_and_correction_do_not_double_count(self):
        data={'started_at':DAY+'T10:00:00+00:00','ended_at':DAY+'T11:00:00+00:00',
              'activity':'Practice','goal_id':'goal-001','session_id':None}
        first=self.h.cli('time','log','--actor','tutor','--request-id','manual1','--file',self.h.file(data),at=DAY+'T12:00:00+00:00')
        self.h.cli('time','log','--actor','other','--request-id','manual2','--file',self.h.file(data),at=DAY+'T12:00:00+00:00',ok=False)
        data.update(ended_at=DAY+'T10:30:00+00:00',supersedes=first['id'],reason='Corrected actual finish time')
        self.h.cli('time','log','--actor','tutor','--request-id','correct','--file',self.h.file(data),at=DAY+'T12:00:00+00:00')
        report=self.h.cli('pace','--from-date',DAY,'--to-date',DAY)
        self.assertEqual(report['total_logged_hours'],0.5)
        self.assertEqual(len(self.h.read('time-entries.jsonl')),2)

    def test_daily_budget_validation_carryover_and_adherence(self):
        plan=self.h.read(f'plans/{DAY}.r1.json')
        plan.update(change_reason='Allocate the agreed hours across the week',
                    daily_hours={f'2030-01-{day:02d}':1 if day<13 else 0 for day in range(7,14)})
        self.h.cli('plan','save','--file',self.h.file(plan))
        bad=deepcopy(plan); bad['daily_hours'][DAY]=10
        self.h.cli('plan','save','--file',self.h.file(bad),ok=False)
        carry=self.h.cli('plan','carry','--from-week',DAY,'--to-week','2030-01-14')
        self.assertIn('2030-01-14',carry['daily_hours'])
        self.assertNotIn(DAY,carry['daily_hours'])
        data={'started_at':DAY+'T10:00:00+00:00','ended_at':DAY+'T11:00:00+00:00','activity':'Practice'}
        self.h.cli('time','log','--actor','tutor','--request-id','log','--file',self.h.file(data),at=DAY+'T12:00:00+00:00')
        report=self.h.cli('pace','--from-date',DAY,'--to-date','2030-01-13',at='2030-01-14T10:00:00+00:00')
        self.assertAlmostEqual(report['past_day_adherence_ratio'],1/6)

    def test_pace_uses_known_draft_timezone_without_confirming_it(self):
        foundation=self.h.read('foundation.json')
        foundation.update(status='draft',timezone='Europe/Moscow')
        self.h.cli('foundation','save','--file',self.h.file(foundation))
        self.h.cli('configure','--file',self.h.file({'timezone':None}))
        report=self.h.cli('pace','--from-date',DAY,'--to-date',DAY)
        self.assertEqual(report['timezone'],'Europe/Moscow')
        self.assertEqual(report['timezone_source'],'draft_foundation')
        self.assertEqual(self.h.read('foundation.json')['status'],'draft')
        self.assertIsNone(self.h.read('objective.json')['timezone'])

    def test_timezone_split_respects_dst(self):
        # Runtime uses instance settings; a draft foundation permits choosing another zone.
        foundation=self.h.read('foundation.json');foundation['status']='draft'
        self.h.cli('foundation','save','--file',self.h.file(foundation))
        self.h.cli('configure','--file',self.h.file({'timezone':'America/New_York'}))
        data={'started_at':'2030-03-10T04:30:00+00:00','ended_at':'2030-03-10T08:30:00+00:00','activity':'Actual interval'}
        self.h.cli('time','log','--actor','tutor','--request-id','dst','--file',self.h.file(data),at='2030-03-10T09:00:00+00:00')
        report=self.h.cli('pace','--from-date','2030-03-09','--to-date','2030-03-10',at='2030-03-11T09:00:00+00:00')
        self.assertEqual(report['total_logged_hours'],4)
        self.assertEqual(report['daily_logged_hours']['2030-03-09'],0.5)
        self.assertEqual(report['daily_logged_hours']['2030-03-10'],3.5)


if __name__=='__main__': unittest.main()
