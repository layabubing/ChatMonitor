import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';

class ReportsPage extends StatefulWidget {
  const ReportsPage({super.key});

  @override
  State<ReportsPage> createState() => _ReportsPageState();
}

class _ReportsPageState extends State<ReportsPage> {
  String _platform = '';
  List<ReportItem> _items = [];
  bool _loading = true;
  String? _error;
  SseEvent? _lastSeenEvent;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items = await AppState.instance.api.reports(platform: _platform);
      if (!mounted) return;
      setState(() {
        _items = items;
        _loading = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = '$e';
          _loading = false;
        });
      }
    }
  }

  Future<void> _downloadDocx(ReportItem r) async {
    try {
      showSnack(context, '开始下载…');
      final dir = await getApplicationDocumentsDirectory();
      final path =
          '${dir.path}/${r.platform}-${r.date}-日报.docx';
      await AppState.instance.api
          .download(AppState.instance.api.reportDocxUri(r.platform, r.date), path);
      final result = await OpenFilex.open(path);
      if (mounted && result.type != ResultType.done) {
        showSnack(context, '已下载到 $path（打开失败：${result.message}）');
      }
    } catch (e) {
      if (mounted) showSnack(context, '$e', error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppState.instance;
    return ListenableBuilder(
      listenable: app,
      builder: (context, _) {
        final ev = app.lastEvent;
        if (ev != null && ev != _lastSeenEvent) {
          _lastSeenEvent = ev;
          if (ev.event == 'report' || ev.event == 'poll') {
            WidgetsBinding.instance.addPostFrameCallback((_) => _reload());
          }
        }
        return Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(children: [
                ChoiceChip(
                  label: const Text('全部平台'),
                  selected: _platform.isEmpty,
                  onSelected: (_) {
                    setState(() => _platform = '');
                    _reload();
                  },
                ),
                for (final m in activeMetas) ...[
                  const SizedBox(width: 8),
                  ChoiceChip(
                    label: Text(m.displayName),
                    selected: _platform == m.name,
                    onSelected: (_) {
                      setState(() => _platform = m.name);
                      _reload();
                    },
                  ),
                ],
              ]),
            ),
          ),
          Expanded(child: _buildList()),
        ]);
      },
    );
  }

  Widget _buildList() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return ErrorView(_error!, onRetry: _reload);
    if (_items.isEmpty) return const EmptyView('暂无日报');
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView.builder(
        itemCount: _items.length,
        itemBuilder: (context, i) {
          final r = _items[i];
          return Card(
            margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            child: ListTile(
              leading: CircleAvatar(
                backgroundColor: platformColor(r.platform).withValues(alpha: 0.15),
                child: Icon(Icons.description,
                    color: platformColor(r.platform), size: 20),
              ),
              title: Text('${r.date} 日报',
                  style: const TextStyle(fontWeight: FontWeight.w600)),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                      '${platformLabel(r.platform)} · 消息 ${r.msgCount} · 重要 ${r.importantCount}',
                      style: const TextStyle(fontSize: 12)),
                  if (r.summary.isNotEmpty)
                    Text(r.summary,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style:
                            TextStyle(fontSize: 12, color: Colors.grey.shade600)),
                ],
              ),
              trailing: IconButton(
                tooltip: '下载 docx',
                icon: const Icon(Icons.download_outlined),
                onPressed: () => _downloadDocx(r),
              ),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => ReportPreviewPage(report: r),
              )),
            ),
          );
        },
      ),
    );
  }
}

/// 日报 HTML 预览（WebView 带 Bearer 头）
class ReportPreviewPage extends StatefulWidget {
  final ReportItem report;
  const ReportPreviewPage({super.key, required this.report});

  @override
  State<ReportPreviewPage> createState() => _ReportPreviewPageState();
}

class _ReportPreviewPageState extends State<ReportPreviewPage> {
  late final WebViewController _controller;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    final api = AppState.instance.api;
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.disabled)
      ..setNavigationDelegate(NavigationDelegate(
        onPageFinished: (_) {
          if (mounted) setState(() => _loading = false);
        },
      ))
      ..loadRequest(api.reportHtmlUri(widget.report.platform, widget.report.date),
          headers: api.authHeaders);
  }

  @override
  Widget build(BuildContext context) {
    final r = widget.report;
    return Scaffold(
      appBar: AppBar(
        title: Text('${r.date} ${platformLabel(r.platform)}日报'),
        actions: [
          IconButton(
            tooltip: '下载 docx',
            icon: const Icon(Icons.download_outlined),
            onPressed: () async {
              try {
                final dir = await getApplicationDocumentsDirectory();
                final path = '${dir.path}/${r.platform}-${r.date}-日报.docx';
                await AppState.instance.api
                    .download(AppState.instance.api.reportDocxUri(r.platform, r.date), path);
                if (context.mounted) showSnack(context, '已下载到 $path');
              } catch (e) {
                if (context.mounted) showSnack(context, '$e', error: true);
              }
            },
          ),
        ],
      ),
      body: Stack(children: [
        WebViewWidget(controller: _controller),
        if (_loading) const Center(child: CircularProgressIndicator()),
      ]),
    );
  }
}
