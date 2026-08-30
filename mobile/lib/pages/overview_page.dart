import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';

class OverviewPage extends StatefulWidget {
  const OverviewPage({super.key});

  @override
  State<OverviewPage> createState() => _OverviewPageState();
}

class _OverviewPageState extends State<OverviewPage> {
  bool _cmdBusy = false;

  Future<void> _command(String platform, String cmd, String label) async {
    setState(() => _cmdBusy = true);
    try {
      await AppState.instance.api.platformCommand(platform, cmd);
      if (mounted) showSnack(context, '$label 命令已下发');
      await Future.delayed(const Duration(seconds: 2));
      await AppState.instance.refreshOverview();
    } catch (e) {
      if (mounted) showSnack(context, '$e', error: true);
    } finally {
      if (mounted) setState(() => _cmdBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppState.instance;
    return ListenableBuilder(
      listenable: app,
      builder: (context, _) {
        final data = app.overviewData;
        return RefreshIndicator(
          onRefresh: app.refreshOverview,
          child: ListView(
            padding: const EdgeInsets.all(12),
            children: [
              for (final p in ['qq', 'dingtalk'])
                _PlatformCard(
                  platform: p,
                  ov: data[p],
                  cmdBusy: _cmdBusy,
                  onCommand: _command,
                ),
              const SizedBox(height: 8),
              Card(
                child: ListTile(
                  leading: const Icon(Icons.info_outline),
                  title: const Text('数据说明'),
                  subtitle: const Text(
                      '统计为当前账号绑定实例的数据；下拉可刷新。后台通知需在「设置 → 保活设置」中开启。'),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _PlatformCard extends StatelessWidget {
  final String platform;
  final PlatformOverview? ov;
  final bool cmdBusy;
  final Future<void> Function(String platform, String cmd, String label) onCommand;

  const _PlatformCard({
    required this.platform,
    required this.ov,
    required this.cmdBusy,
    required this.onCommand,
  });

  @override
  Widget build(BuildContext context) {
    final running = ov?.running ?? false;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            PlatformBadge(platform),
            const SizedBox(width: 8),
            Text('${platformLabel(platform)}监控',
                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const Spacer(),
            Icon(Icons.circle,
                size: 10, color: running ? Colors.green : Colors.grey),
            const SizedBox(width: 4),
            Text(running ? '运行中' : '未运行',
                style: TextStyle(
                    color: running ? Colors.green : Colors.grey, fontSize: 12)),
          ]),
          const SizedBox(height: 12),
          Row(children: [
            _Stat('今日消息', '${ov?.todayMessages ?? '-'}'),
            _Stat('消息总数', '${ov?.msgTotal ?? '-'}'),
            _Stat('提醒', '${ov?.alertTotal ?? '-'}'),
            _Stat('未读', '${ov?.alertUnread ?? '-'}',
                highlight: (ov?.alertUnread ?? 0) > 0),
          ]),
          if (ov?.lastReport != null) ...[
            const Divider(height: 20),
            Row(children: [
              const Icon(Icons.description_outlined, size: 16),
              const SizedBox(width: 6),
              Text('最近日报 ${ov!.lastReport!.date}',
                  style: const TextStyle(fontSize: 13)),
            ]),
            if (ov!.lastReport!.summary.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(ov!.lastReport!.summary,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
              ),
          ],
          const Divider(height: 20),
          Wrap(spacing: 8, runSpacing: 4, children: [
            FilledButton.tonalIcon(
              icon: const Icon(Icons.summarize_outlined, size: 18),
              label: const Text('生成报告'),
              onPressed:
                  cmdBusy ? null : () => onCommand(platform, 'generate_report', '生成报告'),
            ),
            OutlinedButton.icon(
              icon: Icon(running ? Icons.pause : Icons.play_arrow, size: 18),
              label: Text(running ? '暂停' : '恢复'),
              onPressed: cmdBusy
                  ? null
                  : () => onCommand(platform, running ? 'pause' : 'resume',
                      running ? '暂停' : '恢复'),
            ),
            OutlinedButton.icon(
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('重载关键词'),
              onPressed: cmdBusy
                  ? null
                  : () => onCommand(platform, 'reload_keywords', '重载关键词'),
            ),
          ]),
        ]),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  final String label;
  final String value;
  final bool highlight;
  const _Stat(this.label, this.value, {this.highlight = false});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(children: [
        Text(value,
            style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: highlight ? Colors.red : null)),
        const SizedBox(height: 2),
        Text(label, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
      ]),
    );
  }
}
