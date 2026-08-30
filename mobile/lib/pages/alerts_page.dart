import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';

class AlertsPage extends StatefulWidget {
  const AlertsPage({super.key});

  @override
  State<AlertsPage> createState() => _AlertsPageState();
}

class _AlertsPageState extends State<AlertsPage> {
  String _platform = '';
  bool _unreadOnly = false;
  final List<AlertItem> _items = [];
  int _total = 0;
  int _page = 1;
  bool _loading = false;
  bool _initialLoading = true;
  String? _error;
  final _scroll = ScrollController();
  SseEvent? _lastSeenEvent;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      if (_scroll.position.pixels > _scroll.position.maxScrollExtent - 200) {
        _loadMore();
      }
    });
    _reload();
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    setState(() {
      _initialLoading = true;
      _error = null;
      _page = 1;
    });
    try {
      final r = await AppState.instance.api
          .alerts(platform: _platform, unread: _unreadOnly, page: 1);
      if (!mounted) return;
      setState(() {
        _items
          ..clear()
          ..addAll(r.items);
        _total = r.total;
        _initialLoading = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = '$e';
          _initialLoading = false;
        });
      }
    }
  }

  Future<void> _loadMore() async {
    if (_loading || _items.length >= _total) return;
    setState(() => _loading = true);
    try {
      final r = await AppState.instance.api
          .alerts(platform: _platform, unread: _unreadOnly, page: _page + 1);
      if (!mounted) return;
      setState(() {
        _page = r.page;
        _items.addAll(r.items);
        _total = r.total;
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _markRead(AlertItem a) async {
    if (a.isRead) return;
    try {
      await AppState.instance.api
          .markAlertsRead(ids: [a.id], platform: a.platform);
      setState(() {
        final i = _items.indexWhere((e) => e.id == a.id && e.platform == a.platform);
        if (i >= 0) {
          final old = _items[i];
          _items[i] = AlertItem.fromJson({
            'id': old.id,
            'platform': old.platform,
            'content': old.content,
            'reason': old.reason,
            'suggestion': old.suggestion,
            'priority': old.priority,
            'sender': old.sender,
            'group_name': old.groupName,
            'ts': old.ts,
            'is_read': 1,
          });
        }
      });
      await AppState.instance.refreshOverview();
    } catch (e) {
      if (mounted) showSnack(context, '$e', error: true);
    }
  }

  Future<void> _markAllRead() async {
    try {
      await AppState.instance.api.markAlertsRead(platform: _platform);
      if (!mounted) return;
      showSnack(context, '已全部标记为已读');
      await _reload();
      await AppState.instance.refreshOverview();
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
          if (ev.event == 'alert' || ev.event == 'poll') {
            WidgetsBinding.instance.addPostFrameCallback((_) => _reload());
          }
        }
        return Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
            child: Row(children: [
              FilterChip(
                label: const Text('仅未读'),
                selected: _unreadOnly,
                onSelected: (v) {
                  setState(() => _unreadOnly = v);
                  _reload();
                },
              ),
              const SizedBox(width: 8),
              ChoiceChip(
                label: const Text('全部平台'),
                selected: _platform.isEmpty,
                onSelected: (_) {
                  setState(() => _platform = '');
                  _reload();
                },
              ),
              const SizedBox(width: 8),
              ChoiceChip(
                label: const Text('QQ'),
                selected: _platform == 'qq',
                onSelected: (_) {
                  setState(() => _platform = 'qq');
                  _reload();
                },
              ),
              const SizedBox(width: 8),
              ChoiceChip(
                label: const Text('钉钉'),
                selected: _platform == 'dingtalk',
                onSelected: (_) {
                  setState(() => _platform = 'dingtalk');
                  _reload();
                },
              ),
              const Spacer(),
              IconButton(
                tooltip: '全部已读',
                icon: const Icon(Icons.done_all),
                onPressed: _markAllRead,
              ),
            ]),
          ),
          Expanded(child: _buildList()),
        ]);
      },
    );
  }

  Widget _buildList() {
    if (_initialLoading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return ErrorView(_error!, onRetry: _reload);
    if (_items.isEmpty) return const EmptyView('暂无提醒');
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView.builder(
        controller: _scroll,
        itemCount: _items.length + 1,
        itemBuilder: (context, i) {
          if (i == _items.length) {
            return LoadMoreFooter(
                loading: _loading, hasMore: _items.length < _total);
          }
          final a = _items[i];
          return _AlertTile(a: a, onTap: () => _showDetail(a));
        },
      ),
    );
  }

  void _showDetail(AlertItem a) {
    _markRead(a);
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          bottom: MediaQuery.of(context).viewInsets.bottom + 24,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              PlatformBadge(a.platform),
              const SizedBox(width: 8),
              PriorityBadge(a.priority),
              const Spacer(),
              Text(fmtTs(a.ts, pattern: 'yyyy-MM-dd HH:mm'),
                  style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
            ]),
            const SizedBox(height: 12),
            Text(a.groupName,
                style: const TextStyle(fontWeight: FontWeight.bold)),
            Text('发送者：${a.sender}',
                style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
            const Divider(height: 24),
            Text('内容', style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
            const SizedBox(height: 4),
            SelectableText(a.content),
            const SizedBox(height: 12),
            Text('命中原因',
                style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
            const SizedBox(height: 4),
            SelectableText(a.reason.isEmpty ? '-' : a.reason),
            const SizedBox(height: 12),
            Text('建议', style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
            const SizedBox(height: 4),
            SelectableText(a.suggestion.isEmpty ? '-' : a.suggestion),
          ],
        ),
      ),
    );
  }
}

class _AlertTile extends StatelessWidget {
  final AlertItem a;
  final VoidCallback onTap;
  const _AlertTile({required this.a, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: ListTile(
        onTap: onTap,
        leading: Container(
          width: 4,
          height: 40,
          decoration: BoxDecoration(
            color: priorityColor(a.priority),
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        title: Row(children: [
          PlatformBadge(a.platform),
          const SizedBox(width: 6),
          Expanded(
            child: Text(a.groupName,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                    fontSize: 14,
                    fontWeight: a.isRead ? FontWeight.normal : FontWeight.bold)),
          ),
          if (!a.isRead)
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                  color: Colors.red, shape: BoxShape.circle),
            ),
        ]),
        subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SizedBox(height: 2),
          Text(a.content, maxLines: 2, overflow: TextOverflow.ellipsis),
          const SizedBox(height: 2),
          Text('${a.sender} · ${fmtTs(a.ts)}',
              style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
        ]),
      ),
    );
  }
}
