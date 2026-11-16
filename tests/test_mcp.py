"""Protocol-level test of the shipped stdio server, with temporary state."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


class MCPIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_tools_retries_stale_writes_and_timing(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name); state=path/'state'; registry=path/'registry.json'
            subprocess.run([sys.executable,str(ROOT/'scripts/tutor.py'),'--state',str(state),'init'],
                           check=True,capture_output=True)
            registry.write_text(json.dumps({'schema_version':1,'instances':{'test':str(state)}}))
            params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'scripts/mcp_server.py'),'--registry',str(registry)])
            with (path/'server.log').open('w') as log:
                async with stdio_client(params,errlog=log) as streams:
                    async with ClientSession(*streams,read_timeout_seconds=15) as client:
                        await client.initialize()
                        listed=await client.list_tools()
                        self.assertIn('analyze_workload',{t.name for t in listed.tools})
                        async def call(tool,args,ok=True):
                            result=await client.call_tool(tool,args)
                            self.assertEqual(bool(result.is_error),not ok,str(result.content))
                            if not ok:
                                self.assertTrue(any('Stale' in c.text or 'Unknown instance' in c.text or 'already running' in c.text for c in result.content if hasattr(c,'text')),str(result.content))
                            return result.structured_content
                        self.assertEqual((await call('list_instances',{}))['instances'],['test'])
                        ctx=await call('get_context',{'instance':'test'})
                        stale=ctx['state_revision']
                        config={'instance':'test','action':'configure','data':{'timezone':'UTC'},
                                'request_id':'config1','expected_revision':stale}
                        first=await call('tutor_action',config)
                        retry=await call('tutor_action',config)
                        self.assertTrue(retry['replayed'])
                        self.assertEqual(first['result'],retry['result'])
                        await call('tutor_action',{**config,'request_id':'stale','data':{'weekly_hours':6}},ok=False)
                        await call('get_context',{'instance':'../other'},ok=False)
                        timer_args={'instance':'test','action':'start','actor':'agent-A','request_id':'start1','activity':'Actual practice'}
                        timer=(await call('manage_timer',timer_args))['result']
                        repeat=(await call('manage_timer',timer_args))['result']
                        self.assertEqual(timer,repeat)
                        await call('manage_timer',{**timer_args,'actor':'agent-B','request_id':'start2'},ok=False)
                        await asyncio.sleep(0.02)
                        paused=(await call('manage_timer',{'instance':'test','action':'pause','actor':'agent-A',
                                'request_id':'pause1','timer_id':timer['id'],'expected_version':1}))['result']
                        self.assertEqual(paused['status'],'paused')
                        await call('manage_timer',{'instance':'test','action':'stop','actor':'agent-A',
                                   'request_id':'stop1','timer_id':timer['id'],'expected_version':2})
                        now=datetime.now(timezone.utc)
                        manual={'started_at':(now-timedelta(hours=2)).isoformat(),'ended_at':(now-timedelta(hours=1)).isoformat(),'activity':'Earlier practice'}
                        await call('record_time',{'instance':'test','data':manual,'actor':'agent-A','request_id':'log1'})
                        report=await call('get_pace',{'instance':'test','from_date':(now-timedelta(days=1)).date().isoformat(),'to_date':now.date().isoformat()})
                        self.assertGreaterEqual(report['total_logged_hours'],1)
                        goal=json.loads((ROOT/'templates/goal.json').read_text());goal['title']='Learn a test method'
                        ctx=await call('get_context',{'instance':'test'})
                        await call('tutor_action',{'instance':'test','action':'goal_add','data':goal,
                                   'request_id':'goal1','expected_revision':ctx['state_revision']})
                        data={'start_date':now.date().isoformat(),'deadline':(now+timedelta(days=13)).date().isoformat(),
                              'timezone':'UTC','study_days':[0,1,2,3,4], 'weekly_capacity_hours':5,
                              'effort':[{'goal_id':'goal-001','min_hours':10,'max_hours':20,'basis':'Fixture task estimate','source_refs':['fixture:diagnostic']}],
                              'overhead_hours':{'min':0,'max':0,'basis':'Included in task estimate'},'buffer_percent':0}
                        ctx=await call('get_context',{'instance':'test'})
                        result=await call('analyze_workload',{'instance':'test','data':data,'request_id':'workload1','expected_revision':ctx['state_revision']})
                        self.assertEqual(result['result']['recommendation']['weekly_hours_max'],10)
            check=subprocess.run([sys.executable,str(ROOT/'scripts/tutor.py'),'--state',str(state),'check'],capture_output=True,text=True)
            self.assertEqual(check.returncode,0,check.stderr)
            self.assertEqual(len((state/'time-entries.jsonl').read_text().splitlines()),2)


if __name__=='__main__': unittest.main()
