"""Failure/restart regression tests. No external services or development data.

Run: .venv/bin/python -m unittest -v test_reliability
"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from docx import Document
from fastapi.testclient import TestClient

import config
from core import accounts, analyzer, delivery, inbox, reporter, workwechat_routing
from core.accounts import db
from core.dates import day_bounds
from core.models import ChatMessage, ImportantItem
from core.pipeline import Pipeline
from core.storage import Storage
from main import _collect_instances, _ingest_message, _sync_daily_jobs
from platforms.workwechat import WorkWechatAdapter
from web.routers import workwechat
from web.server import app
from web.wxmsgcrypt import WXBizMsgCrypt


class IsolatedTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        # Windows 下 SQLite 连接未及时释放时无法删除已打开的文件，
        # 允许清理失败（仅影响临时目录回收，不影响断言结果）
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(ignore_cleanup_errors=True)))
        for name in ('DATA_DIR', 'CONFIGS_DIR', 'LOGS_DIR', 'REPORTS_DIR'):
            path = self.root / name.lower()
            path.mkdir()
            self.stack.enter_context(patch.object(config, name, path))
        self.stack.enter_context(patch.object(db, '_db_path', self.root / 'accounts.db'))
        self.stack.enter_context(patch('core.pipeline.DATA_DIR', config.DATA_DIR))
        self.stack.enter_context(patch('core.keywords._KEYWORDS_FILE', self.root / 'keywords.json'))
        (self.root / 'keywords.json').write_text('{"测试": ["紧急"]}', encoding='utf-8')
        self.storage = Storage(self.root / 'messages.db')

    def message(self, msg_id='m1', content='紧急求助', **kwargs):
        return ChatMessage(msg_id=msg_id, platform='qq', content=content, **kwargs)

    def pipeline(self, **cfg):
        pipeline = Pipeline(self.storage, cfg, 'qq')
        pipeline._match = lambda text: bool(text)
        return pipeline


class DeliveryTests(IsolatedTest):
    def raw(self, agent='1'):
        return dict(msg_id='ww_1', corpid='corp', agent_id=agent,
                    chat_id='group', content='hello', media_ids=[], ts=1000)

    def test_each_app_and_subscriber_receives_own_copy(self):
        delivery.enqueue('workwechat', self.raw(), ['alice', 'bob'])
        delivery.enqueue('workwechat', self.raw('2'), ['claire'])
        self.assertIsNone(delivery.claim('workwechat', 'corp', '2', 'alice'))
        for agent, username in [('1', 'alice'), ('1', 'bob'), ('2', 'claire')]:
            item = delivery.claim('workwechat', 'corp', agent, username)
            self.assertEqual(item['message']['agent_id'], agent)
            self.assertTrue(delivery.acknowledge(item['receipt']))

    def test_callback_replay_does_not_recreate_acknowledged_delivery(self):
        delivery.enqueue('workwechat', self.raw(), ['alice'])
        item = delivery.claim('workwechat', 'corp', '1', 'alice')
        self.assertTrue(delivery.acknowledge(item['receipt']))
        delivery.enqueue('workwechat', self.raw(), ['alice'])
        self.assertIsNone(delivery.claim('workwechat', 'corp', '1', 'alice'))

    def test_expired_worker_lease_is_recovered_and_old_ack_rejected(self):
        delivery.enqueue('workwechat', self.raw(), ['alice'])
        abandoned = delivery.claim('workwechat', 'corp', '1', 'alice', lease_seconds=-1)
        recovered = delivery.claim('workwechat', 'corp', '1', 'alice')
        self.assertEqual(abandoned['message'], recovered['message'])
        self.assertFalse(delivery.acknowledge(abandoned['receipt']))
        self.assertTrue(delivery.acknowledge(recovered['receipt']))

    def test_concurrent_workers_cannot_claim_same_delivery(self):
        delivery.enqueue('workwechat', self.raw(), ['alice'])
        with ThreadPoolExecutor(max_workers=4) as pool:
            claimed = list(pool.map(lambda _: delivery.claim('workwechat', 'corp', '1', 'alice'), range(4)))
        self.assertEqual(sum(item is not None for item in claimed), 1)

    def test_failed_ingestion_releases_without_acknowledging(self):
        adapter = Mock()
        pipeline = Mock()
        pipeline.process_batch.side_effect = OSError('disk full')
        msg = self.message()
        _ingest_message({'pipeline': pipeline, 'adapter': adapter}, msg)
        adapter.acknowledge.assert_not_called()
        adapter.reject.assert_called_once_with(msg)

    def test_adapter_acknowledges_only_after_message_and_jobs_commit(self):
        raw = self.raw()
        delivery.enqueue('workwechat', raw, ['alice'])
        adapter = WorkWechatAdapter({'WORKWECHAT_CORP_ID': 'corp', 'WORKWECHAT_AGENT_ID': '1'}, 'alice')
        adapter.start()
        self.addCleanup(adapter.stop)
        message = next(adapter.iter_messages(timeout=3))
        self.assertIsNone(delivery.claim('workwechat', 'corp', '1', 'alice'))
        pipeline = Pipeline(self.storage, {}, 'workwechat')
        _ingest_message({'pipeline': pipeline, 'adapter': adapter}, message)
        self.assertEqual(self.storage.query_messages('workwechat')['total'], 1)
        self.assertEqual(self.storage.analysis_status()['pending'], 1)
        self.assertEqual(delivery.pending_count('workwechat', 'corp', '1', 'alice'), 0)

    def test_legacy_inbox_fans_out_and_preserves_unmatched_files(self):
        cfg = {'WORKWECHAT_CORP_ID': 'corp', 'WORKWECHAT_AGENT_ID': '1'}
        for user in ['alice', 'bob']:
            accounts.save_user_binding(user, 'workwechat', cfg)
        inbox.push_message('workwechat', self.raw())
        unmatched = {**self.raw('999'), 'msg_id': 'unmatched'}
        inbox.push_message('workwechat', unmatched)
        workwechat_routing.migrate_legacy()
        for user in ['alice', 'bob']:
            self.assertIsNotNone(delivery.claim('workwechat', 'corp', '1', user))
        self.assertEqual(inbox.pending_count('workwechat', 'corp'), 1)
        self.assertEqual(inbox.pop_messages('workwechat', 'corp')[0]['msg_id'], 'unmatched')


class CallbackTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        workwechat._fail_ts.clear()
        self.addCleanup(workwechat._fail_ts.clear)
        self.cfg = {'WORKWECHAT_CORP_ID': 'corp', 'WORKWECHAT_AGENT_ID': '1',
                    'WORKWECHAT_TOKEN': 'test-token', 'WORKWECHAT_AES_KEY': 'a' * 43}
        for user, cfg in [('alice', self.cfg), ('bob', self.cfg),
                          ('claire', {**self.cfg, 'WORKWECHAT_AGENT_ID': '2'}),
                          ('intruder', {**self.cfg, 'WORKWECHAT_TOKEN': 'wrong-token'})]:
            accounts.save_user_binding(user, 'workwechat', cfg)
        crypt = WXBizMsgCrypt('test-token', 'a' * 43, 'corp')
        xml = ('<xml><ToUserName>corp</ToUserName><AgentID>1</AgentID><MsgId>42</MsgId>'
               '<ChatId>group</ChatId><FromUserName>sender</FromUserName><CreateTime>100</CreateTime>'
               '<MsgType>text</MsgType><Content>notice</Content></xml>')
        encrypted = crypt.encrypt(xml)
        self.params = {'timestamp': '100', 'nonce': 'n',
                       'msg_signature': crypt.signature('100', 'n', encrypted)}
        self.body = f'<xml><Encrypt>{encrypted}</Encrypt></xml>'
        self.client = self.stack.enter_context(TestClient(app))

    def receive(self):
        return self.client.post('/api/workwechat/callback', params=self.params, content=self.body)

    def test_callback_fanout_checks_app_and_decryption_credentials(self):
        self.assertEqual(self.receive().status_code, 200)
        for user in ['alice', 'bob']:
            self.assertIsNotNone(delivery.claim('workwechat', 'corp', '1', user))
        self.assertEqual(delivery.pending_count('workwechat', 'corp', '2', 'claire'), 0)
        self.assertEqual(delivery.pending_count('workwechat', 'corp', '1', 'intruder'), 0)

    def test_callback_storage_failure_returns_retryable_response(self):
        with patch.object(delivery, 'enqueue', return_value=False):
            self.assertEqual(self.receive().status_code, 503)
        with patch.object(delivery, 'enqueue', side_effect=OSError('unavailable')):
            self.assertEqual(self.receive().status_code, 503)
        self.assertEqual(self.receive().status_code, 200)


class AnalysisTests(IsolatedTest):
    def test_pause_during_ingestion_still_persists_message_before_ack(self):
        pipeline = self.pipeline()
        pipeline.pause()
        adapter = Mock()
        with patch.object(analyzer, 'confirm_importance', new=AsyncMock()) as confirm:
            _ingest_message({'pipeline': pipeline, 'adapter': adapter}, self.message())
            confirm.assert_not_awaited()
        adapter.acknowledge.assert_called_once()
        self.assertEqual(self.storage.query_messages('qq')['total'], 1)
        self.assertEqual(self.storage.analysis_status()['pending'], 1)

    def test_report_waits_for_analysis_then_recovers_after_restart(self):
        start, _ = day_bounds('2024-01-01')
        pipeline = self.pipeline(AI_API_KEY='test')
        pipeline.process_batch([self.message(ts=start)], analyze=False)
        self.assertIsNone(pipeline.build_daily_report('2024-01-01'))
        self.assertEqual(self.storage.report_task_status('qq')['failed'], 1)
        self.assertEqual(self.storage.query_reports(), [])
        self.storage = Storage(self.storage.db_path)
        pipeline = self.pipeline(AI_API_KEY='test')
        item = ImportantItem('qq', msg_id='m1', content='重要通知', ts=start)
        with patch.object(analyzer, 'confirm_importance', new=AsyncMock(return_value=[item])):
            pipeline.retry_analysis()
        self.storage.reset_failed_reports('qq')
        with patch.object(analyzer, 'generate_summary', new=AsyncMock(return_value='完整总结')) as summary:
            report = pipeline.retry_reports()
            self.assertEqual(report.important_count, 1)
            self.assertEqual(len(summary.await_args.args[3]), 1)
        self.assertEqual(self.storage.report_task_status('qq')['done'], 1)

    def test_report_ai_failure_is_persistent_and_can_be_retried(self):
        pipeline = self.pipeline(AI_API_KEY='test')
        start, _ = day_bounds('2024-01-01')
        self.storage.insert_messages([self.message(ts=start)])
        with patch.object(analyzer, 'generate_summary', new=AsyncMock(side_effect=analyzer.AnalysisError('AI HTTP 503'))):
            self.assertIsNone(pipeline.build_daily_report('2024-01-01'))
            self.assertIsNone(pipeline.retry_reports())
        self.assertEqual(self.storage.report_task_status('qq')['failed'], 1)
        self.storage.reset_failed_reports('qq')
        with patch.object(analyzer, 'generate_summary', new=AsyncMock(return_value='恢复成功')):
            self.assertIsNotNone(self.pipeline(AI_API_KEY='test').retry_reports())

    def test_keyword_rescan_retains_failures_for_retry(self):
        pipeline = self.pipeline()
        pipeline.process_batch([self.message()], analyze=False)
        with patch.object(analyzer, 'confirm_importance', new=AsyncMock(side_effect=analyzer.AnalysisError('AI HTTP 503'))):
            pipeline.retry_analysis()
        self.assertEqual(pipeline.rescan_today(), 1)
        with patch.object(analyzer, 'confirm_importance', new=AsyncMock(return_value=[])):
            pipeline.retry_analysis()
        self.assertEqual(self.storage.analysis_status()['done'], 1)

    def test_failed_analysis_survives_restart_and_duplicate_ingest(self):
        pipeline = self.pipeline()
        with patch.object(analyzer, 'confirm_importance', new=AsyncMock(side_effect=analyzer.AnalysisError('AI HTTP 503'))):
            self.assertEqual(pipeline.process_batch([self.message()]), 1)
        self.assertEqual(self.storage.analysis_status()['failed'], 1)
        self.assertEqual(self.storage.query_alerts()['total'], 0)
        # New storage/pipeline simulate restarting without relying on memory state.
        self.storage = Storage(self.storage.db_path)
        pipeline = self.pipeline()
        pipeline.process_batch([self.message()], analyze=False)
        self.storage.reset_failed_analysis('qq')
        item = ImportantItem('qq', msg_id='m1', content='notice')
        with patch.object(analyzer, 'confirm_importance', new=AsyncMock(return_value=[item])) as confirm:
            self.assertEqual(pipeline.retry_analysis(), 1)
            self.assertEqual(pipeline.retry_analysis(), 0)
            confirm.assert_awaited_once()
        self.assertEqual(self.storage.analysis_status()['done'], 1)
        self.assertEqual(self.storage.query_alerts()['total'], 1)

    def test_negative_judgment_finishes_but_network_failure_does_not(self):
        pipeline = self.pipeline()
        with patch.object(analyzer, 'confirm_importance', new=AsyncMock(return_value=[])):
            pipeline.process_batch([self.message()])
        self.assertEqual(self.storage.analysis_status()['done'], 1)
        self.assertEqual(self.storage.analysis_status()['failed'], 0)

    def test_backoff_prevents_busy_retries(self):
        pipeline = self.pipeline()
        with patch.object(analyzer, 'confirm_importance', new=AsyncMock(side_effect=TimeoutError)) as confirm:
            pipeline.process_batch([self.message()])
            self.assertEqual(pipeline.retry_analysis(), 0)
            confirm.assert_awaited_once()

    def test_expired_analysis_lease_can_be_reclaimed(self):
        self.storage.insert_messages([self.message()], enqueue_analysis=True)
        old = self.storage.claim_analysis('qq', lease_seconds=-1)
        new = Storage(self.storage.db_path).claim_analysis('qq')
        self.storage.finish_analysis(old['receipt'])
        self.assertEqual(self.storage.analysis_status()['running'], 1)
        self.storage.finish_analysis(new['receipt'])
        self.assertEqual(self.storage.analysis_status()['done'], 1)

    def test_media_analysis_retries_existing_file_record(self):
        media_path = config.DATA_DIR / 'media' / 'notice.pdf'
        media_path.parent.mkdir()
        media_path.write_bytes(b'test-document')
        message = self.message(content='', media_urls=['media/notice.pdf'])
        pipeline = self.pipeline()
        with patch.object(analyzer, 'analyze_file', new=AsyncMock(side_effect=analyzer.AnalysisError('AI HTTP 429'))):
            pipeline.process_batch([message])
        self.assertEqual(self.storage.query_files()['total'], 1)
        self.assertEqual(self.storage.analysis_status()['failed'], 1)
        self.storage.reset_failed_analysis('qq')
        info = {'important': True, 'desc': '考试通知', 'category': '通知'}
        with patch.object(analyzer, 'analyze_file', new=AsyncMock(return_value=info)):
            pipeline.retry_analysis()
        self.assertEqual(self.storage.query_files()['total'], 1)
        self.assertEqual(self.storage.query_files()['items'][0]['ai_desc'], '考试通知')
        self.assertEqual(self.storage.query_alerts()['total'], 1)

    def test_message_and_job_creation_roll_back_together(self):
        with patch('core.storage.messages.enqueue_jobs', side_effect=RuntimeError('queue failure')):
            with self.assertRaises(RuntimeError):
                self.pipeline().process_batch([self.message()], analyze=False)
        self.assertEqual(self.storage.query_messages('qq')['total'], 0)

    def test_http_failure_empty_and_invalid_json_are_distinct_from_negative(self):
        message = self.message()
        for content in ['not json', '[]', '[{"index":"0","important":true}]',
                        '[{"index":0,"important":"false"}]']:
            with self.subTest(content=content), patch.object(analyzer, 'chat_completion', new=AsyncMock(return_value=content)):
                with self.assertRaises(analyzer.AnalysisError):
                    asyncio.run(analyzer.confirm_importance({}, [message]))
        with patch.object(analyzer, 'chat_completion', new=AsyncMock(return_value='[{"index":0,"important":false}]')):
            self.assertEqual(asyncio.run(analyzer.confirm_importance({}, [message])), [])
        for response in [httpx.Response(503), httpx.Response(200, json={'choices': [{'message': {'content': ''}}]}),
                         httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': '截断'}}]})]:
            client = AsyncMock()
            client.post.return_value = response
            with patch.object(httpx, 'AsyncClient') as factory:
                factory.return_value.__aenter__.return_value = client
                with self.assertRaises(analyzer.AnalysisError):
                    asyncio.run(analyzer.chat_completion({'AI_API_KEY': 'test'}, []))


class ReportTests(IsolatedTest):
    def test_historical_day_includes_over_500_messages_and_over_100_alerts(self):
        start, end = day_bounds('2024-01-01')
        messages = [self.message(f'old_{i}', f'完整消息{i}', ts=start + i) for i in range(601)]
        # The newest page contains only another day: the old implementation lost the whole target day.
        messages += [self.message(f'new_{i}', ts=end + i) for i in range(650)]
        self.storage.insert_messages(messages)
        for i in range(121):
            self.storage.add_alert(ImportantItem('qq', msg_id=f'old_{i}', content=f'重要{i}', ts=start + i))
        for i in range(110):
            self.storage.add_alert(ImportantItem('qq', msg_id=f'new_{i}', ts=end + i))
        async def summarize(cfg, platform, msgs, alerts):
            self.assertEqual(len(msgs), 601)
            self.assertEqual(len(alerts), 121)
            self.assertEqual(msgs[0].msg_id, 'old_0')
            self.assertEqual(msgs[-1].msg_id, 'old_600')
            return '完整总结'
        with patch.object(analyzer, 'generate_summary', side_effect=summarize):
            report = reporter.generate_report(self.storage, {}, 'qq', '2024-01-01')
        self.assertEqual((report.msg_count, report.important_count), (601, 121))
        html = Path(report.html_path).read_text()
        self.assertIn('完整消息600', html)
        self.assertNotIn('new_0', html)
        doc = Document(report.docx_path)
        self.assertTrue(any('完整消息600' in paragraph.text for paragraph in doc.paragraphs))

    def test_summary_sends_every_message_and_alert_to_bounded_chunks(self):
        messages = [self.message(str(i), f'UNIQUE_{i:04d}_' + 'x' * 250) for i in range(150)]
        alerts = [ImportantItem('qq', content='ALERT_TAIL_MARKER', suggestion='负责人:老师')]
        calls = []
        async def completion(cfg, prompts, **kwargs):
            calls.append(prompts[-1]['content'])
            return '分段汇总'
        with patch.object(analyzer, 'chat_completion', side_effect=completion):
            text = asyncio.run(analyzer.generate_summary({'AI_API_KEY': 'test'}, 'qq', messages, alerts))
        combined = ''.join(calls)
        for i in range(150):
            self.assertIn(f'UNIQUE_{i:04d}_', combined)
        self.assertIn('ALERT_TAIL_MARKER', combined)
        self.assertGreater(len(calls), 2)
        self.assertTrue(all(len(part) <= 6000 for part in calls))
        self.assertIn('150 条消息', text)

    def test_oversized_message_tail_is_not_truncated(self):
        content = 'x' * 20000 + 'LAST_CHARACTER_MARKER'
        chunks = analyzer._summary_chunks([content])
        self.assertEqual(''.join(chunks), content)

    def test_summary_failure_does_not_overwrite_previous_report(self):
        start, _ = day_bounds('2024-01-01')
        self.storage.insert_messages([self.message(ts=start)])
        report = reporter.generate_report(self.storage, {}, 'qq', '2024-01-01')
        before = Path(report.html_path).read_bytes()
        with patch.object(analyzer, 'generate_summary', new=AsyncMock(side_effect=analyzer.AnalysisError('AI HTTP 503'))):
            with self.assertRaises(analyzer.AnalysisError):
                reporter.generate_report(self.storage, {}, 'qq', '2024-01-01')
        self.assertEqual(Path(report.html_path).read_bytes(), before)
        self.assertEqual(len(self.storage.query_reports()), 1)

    def test_day_bounds_obey_timezone_dst_and_exclusive_end(self):
        start, end = day_bounds('2024-03-10', 'America/New_York')
        self.assertEqual(end - start, 23 * 3600_000)
        self.storage.insert_messages([self.message('before', ts=start - 1), self.message('start', ts=start),
                                      self.message('last', ts=end - 1), self.message('end', ts=end)])
        messages, _ = self.storage.report_inputs('qq', start, end)
        self.assertEqual([m['msg_id'] for m in messages], ['start', 'last'])
        with self.assertRaises(ValueError):
            day_bounds('../invalid')

    def test_daily_job_lifecycle_tracks_dynamic_bindings(self):
        scheduler = BackgroundScheduler()
        scheduler.start(paused=True)
        self.addCleanup(lambda: scheduler.shutdown(wait=False))
        def instance(name):
            return {'username': name, 'config': {}, 'pipeline': Mock()}
        alice, bob = instance('alice'), instance('bob')
        _sync_daily_jobs(scheduler, 'qq', [alice])
        _sync_daily_jobs(scheduler, 'qq', [alice, bob])
        self.assertEqual(len(scheduler.get_jobs()), 2)
        replacement = instance('alice')
        _sync_daily_jobs(scheduler, 'qq', [replacement])
        self.assertIsNone(scheduler.get_job('daily_qq_user_bob'))
        self.assertEqual(scheduler.get_job('daily_qq_user_alice').func, replacement['pipeline'].build_daily_report)
        _sync_daily_jobs(scheduler, 'qq', [instance(''), instance('global')])
        self.assertEqual({job.id for job in scheduler.get_jobs()}, {'daily_qq_global', 'daily_qq_user_global'})

    def test_same_corp_global_binding_does_not_hide_user_subscription(self):
        cfg = {'WORKWECHAT_ENABLED': 'true', 'WORKWECHAT_CORP_ID': 'corp', 'WORKWECHAT_AGENT_ID': '1'}
        accounts.save_user_binding('alice', 'workwechat', cfg)
        self.assertEqual({i['username'] for i in _collect_instances('workwechat', cfg)}, {'', 'alice'})


if __name__ == '__main__':
    unittest.main()
