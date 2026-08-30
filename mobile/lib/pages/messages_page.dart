import 'dart:async';

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';

class MessagesPage extends StatefulWidget {
  const MessagesPage({super.key});

  @override
  State<MessagesPage> createState() => _MessagesPageState();
}

class _MessagesPageState extends State<MessagesPage> {
  String _platform = 'qq';
  String _group = '';
  final _search = TextEditingController();
  List<String> _groups = [];

  final List<ChatMessage> _items = [];
  int _total = 0;
  int _page = 1;
  bool _loading = false;
  bool _initialLoading = true;
  String? _error;
  final _scroll = ScrollController();
  Timer? _debounce;
  SseEvent? _lastSeenEvent;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      if (_scroll.position.pixels > _scroll.position.maxScrollExtent - 200) {
        _loadMore();
      }
    });
    _loadGroups();
    _reload();
  }

  @override
  void dispose() {
    _scroll.dispose();
    _search.dispose();
    _debounce?.cancel();
    super.dispose();
  }

  Future<void> _loadGroups() async {
    try {
      final g = await AppState.instance.api.groups(_platform);
      if (mounted) setState(() => _groups = g);
    } catch (_) {}
  }

  Future<void> _reload() async {
    setState(() {
      _initialLoading = true;
      _error = null;
      _page = 1;
    });
    try {
      final r = await AppState.instance.api.messages(_platform,
          group: _group, q: _search.text.trim(), page: 1);
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
      final r = await AppState.instance.api.messages(_platform,
          group: _group, q: _search.text.trim(), page: _page + 1);
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

  /// SSE 新消息 → 增量拉取置顶（since_ts 游标）
  Future<void> _incremental() async {
    if (_items.isEmpty) return _reload();
    try {
      final r = await AppState.instance.api.messages(_platform,
          group: _group, q: _search.text.trim(),
          pageSize: 50, sinceTs: _items.first.ts);
      if (!mounted || r.items.isEmpty) return;
      setState(() {
        final existing = _items.map((m) => m.msgId).toSet();
        _items.insertAll(
            0, r.items.where((m) => !existing.contains(m.msgId)));
        _total += r.items.length;
      });
    } catch (_) {}
  }

  void _onSearchChanged(String _) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 500), _reload);
  }

  @override
  Widget build(BuildContext context) {
    // 监听 SSE：本页平台有新消息时增量刷新
    final app = AppState.instance;
    return ListenableBuilder(
      listenable: app,
      builder: (context, _) {
        final ev = app.lastEvent;
        if (ev != null && ev != _lastSeenEvent) {
          _lastSeenEvent = ev;
          if (ev.event == 'poll' ||
              (ev.event == 'message' && ev.data['platform'] == _platform)) {
            WidgetsBinding.instance
                .addPostFrameCallback((_) => _incremental());
          }
        }
        return Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Row(children: [
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'qq', label: Text('QQ')),
                  ButtonSegment(value: 'dingtalk', label: Text('钉钉')),
                ],
                selected: {_platform},
                onSelectionChanged: (s) {
                  setState(() {
                    _platform = s.first;
                    _group = '';
                  });
                  _loadGroups();
                  _reload();
                },
              ),
              const SizedBox(width: 8),
              Expanded(
                child: DropdownButtonFormField<String>(
                  initialValue: _group.isEmpty ? null : _group,
                  hint: const Text('全部群'),
                  isExpanded: true,
                  decoration: const InputDecoration(
                      isDense: true,
                      border: OutlineInputBorder(),
                      contentPadding:
                          EdgeInsets.symmetric(horizontal: 10, vertical: 8)),
                  items: [
                    const DropdownMenuItem(value: '', child: Text('全部群')),
                    ..._groups.map((g) =>
                        DropdownMenuItem(value: g, child: Text(g, overflow: TextOverflow.ellipsis))),
                  ],
                  onChanged: (v) {
                    setState(() => _group = v ?? '');
                    _reload();
                  },
                ),
              ),
            ]),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              controller: _search,
              onChanged: _onSearchChanged,
              decoration: InputDecoration(
                hintText: '搜索消息内容或发送者',
                prefixIcon: const Icon(Icons.search),
                isDense: true,
                border: const OutlineInputBorder(),
                suffixIcon: _search.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _search.clear();
                          _reload();
                        }),
              ),
            ),
          ),
          Expanded(child: _buildList()),
        ]);
      },
    );
  }

  Widget _buildList() {
    if (_initialLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) return ErrorView(_error!, onRetry: _reload);
    if (_items.isEmpty) return const EmptyView('暂无消息');
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
          return _MessageTile(m: _items[i]);
        },
      ),
    );
  }
}

class _MessageTile extends StatelessWidget {
  final ChatMessage m;
  const _MessageTile({required this.m});

  @override
  Widget build(BuildContext context) {
    final app = AppState.instance;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Text(m.sender,
                style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
            const SizedBox(width: 8),
            Expanded(
              child: Text(m.groupName,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
            ),
            Text(fmtTs(m.ts),
                style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
          ]),
          if (m.content.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(m.content),
            ),
          if (m.mediaUrls.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final u in m.mediaUrls)
                    _MediaThumb(
                        uri: app.api.mediaRawUri(u), headers: app.api.authHeaders),
                ],
              ),
            ),
        ]),
      ),
    );
  }
}

class _MediaThumb extends StatelessWidget {
  final Uri uri;
  final Map<String, String> headers;
  const _MediaThumb({required this.uri, required this.headers});

  @override
  Widget build(BuildContext context) {
    final isImage = RegExp(r'\.(png|jpe?g|gif|webp|bmp)($|\.)', caseSensitive: false)
        .hasMatch(uri.toString());
    if (!isImage) {
      return Chip(
        avatar: const Icon(Icons.attach_file, size: 16),
        label: Text(uri.pathSegments.isEmpty ? '附件' : uri.pathSegments.last,
            style: const TextStyle(fontSize: 12)),
      );
    }
    return GestureDetector(
      onTap: () => showDialog(
        context: context,
        builder: (_) => Dialog(
          child: InteractiveViewer(
            child: Image.network(uri.toString(), headers: headers),
          ),
        ),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: Image.network(
          uri.toString(),
          headers: headers,
          width: 80,
          height: 80,
          fit: BoxFit.cover,
          errorBuilder: (_, _, _) => Container(
            width: 80,
            height: 80,
            color: Colors.grey.shade200,
            child: const Icon(Icons.broken_image_outlined),
          ),
        ),
      ),
    );
  }
}
