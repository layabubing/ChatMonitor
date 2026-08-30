import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';

class FilesPage extends StatefulWidget {
  const FilesPage({super.key});

  @override
  State<FilesPage> createState() => _FilesPageState();
}

class _FilesPageState extends State<FilesPage> {
  String _platform = '';
  String _category = '';
  bool _importantOnly = false;
  final _search = TextEditingController();
  List<String> _categories = [];

  final List<FileItem> _items = [];
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
    _loadCategories();
    _reload();
  }

  @override
  void dispose() {
    _scroll.dispose();
    _search.dispose();
    super.dispose();
  }

  Future<void> _loadCategories() async {
    try {
      final c = await AppState.instance.api.fileCategories();
      if (mounted) setState(() => _categories = c);
    } catch (_) {}
  }

  Future<void> _reload() async {
    setState(() {
      _initialLoading = true;
      _error = null;
      _page = 1;
    });
    try {
      final r = await AppState.instance.api.files(
          platform: _platform,
          category: _category,
          important: _importantOnly,
          q: _search.text.trim(),
          page: 1);
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
      final r = await AppState.instance.api.files(
          platform: _platform,
          category: _category,
          important: _importantOnly,
          q: _search.text.trim(),
          page: _page + 1);
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

  Future<void> _toggleImportant(FileItem f) async {
    try {
      await AppState.instance.api.setFileImportant(f.platform, f.id, !f.important);
      setState(() {
        final i = _items.indexWhere((e) => e.id == f.id && e.platform == f.platform);
        if (i >= 0) {
          _items[i] = FileItem.fromJson({
            'id': f.id,
            'platform': f.platform,
            'local_path': f.localPath,
            'orig_name': f.origName,
            'ftype': f.ftype,
            'ext': f.ext,
            'size': f.size,
            'important': f.important ? 0 : 1,
            'ai_desc': f.aiDesc,
            'category': f.category,
            'ts': f.ts,
          });
        }
      });
    } catch (e) {
      if (mounted) showSnack(context, '$e', error: true);
    }
  }

  Future<void> _download(FileItem f) async {
    try {
      showSnack(context, '开始下载…');
      final dir = await getApplicationDocumentsDirectory();
      final name = f.origName.isEmpty ? 'file_${f.id}${f.ext}' : f.origName;
      final path = '${dir.path}/$name';
      await AppState.instance.api
          .download(AppState.instance.api.fileRawUri(f.platform, f.id), path);
      final result = await OpenFilex.open(path);
      if (mounted && result.type != ResultType.done) {
        showSnack(context, '已下载到 $path（打开失败：${result.message}）');
      }
    } catch (e) {
      if (mounted) showSnack(context, '$e', error: true);
    }
  }

  void _previewImage(FileItem f) {
    final api = AppState.instance.api;
    showDialog(
      context: context,
      builder: (_) => Dialog(
        child: InteractiveViewer(
          child: Image.network(api.fileRawUri(f.platform, f.id).toString(),
              headers: api.authHeaders),
        ),
      ),
    );
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
          if (ev.event == 'file' || ev.event == 'poll') {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              _reload();
              _loadCategories();
            });
          }
        }
        return Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Row(children: [
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
            ]),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Row(children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  initialValue: _category.isEmpty ? '' : _category,
                  isExpanded: true,
                  decoration: const InputDecoration(
                      isDense: true,
                      labelText: '分类',
                      border: OutlineInputBorder(),
                      contentPadding:
                          EdgeInsets.symmetric(horizontal: 10, vertical: 8)),
                  items: [
                    const DropdownMenuItem(value: '', child: Text('全部分类')),
                    ..._categories.map((c) => DropdownMenuItem(
                        value: c, child: Text(c, overflow: TextOverflow.ellipsis))),
                  ],
                  onChanged: (v) {
                    setState(() => _category = v ?? '');
                    _reload();
                  },
                ),
              ),
              const SizedBox(width: 8),
              FilterChip(
                label: const Text('仅重要'),
                selected: _importantOnly,
                onSelected: (v) {
                  setState(() => _importantOnly = v);
                  _reload();
                },
              ),
            ]),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              controller: _search,
              onSubmitted: (_) => _reload(),
              decoration: InputDecoration(
                hintText: '搜索文件名或描述，回车确认',
                prefixIcon: const Icon(Icons.search),
                isDense: true,
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
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
    if (_initialLoading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return ErrorView(_error!, onRetry: _reload);
    if (_items.isEmpty) return const EmptyView('暂无文件');
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
          final f = _items[i];
          return _FileTile(
            f: f,
            onToggleImportant: () => _toggleImportant(f),
            onTap: () => f.isImage ? _previewImage(f) : _download(f),
            onDownload: () => _download(f),
          );
        },
      ),
    );
  }
}

class _FileTile extends StatelessWidget {
  final FileItem f;
  final VoidCallback onToggleImportant;
  final VoidCallback onTap;
  final VoidCallback onDownload;

  const _FileTile({
    required this.f,
    required this.onToggleImportant,
    required this.onTap,
    required this.onDownload,
  });

  String get _sizeLabel {
    if (f.size >= 1048576) return '${(f.size / 1048576).toStringAsFixed(1)}MB';
    if (f.size >= 1024) return '${(f.size / 1024).toStringAsFixed(0)}KB';
    return '${f.size}B';
  }

  @override
  Widget build(BuildContext context) {
    final api = AppState.instance.api;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: ListTile(
        onTap: onTap,
        leading: f.isImage
            ? ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: Image.network(
                  api.fileRawUri(f.platform, f.id).toString(),
                  headers: api.authHeaders,
                  width: 44,
                  height: 44,
                  fit: BoxFit.cover,
                  errorBuilder: (_, _, _) =>
                      const Icon(Icons.broken_image_outlined, size: 32),
                ),
              )
            : Icon(_iconFor(f), size: 32, color: Colors.blueGrey),
        title: Text(
          f.origName.isEmpty ? '未命名${f.ext}' : f.origName,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 14),
        ),
        subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(
              '${platformLabel(f.platform)}${f.category.isEmpty ? '' : ' · ${f.category}'} · $_sizeLabel · ${fmtTs(f.ts)}',
              style: const TextStyle(fontSize: 11)),
          if (f.aiDesc.isNotEmpty)
            Text(f.aiDesc,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
        ]),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(
            tooltip: f.important ? '取消重要' : '标为重要',
            icon: Icon(f.important ? Icons.star : Icons.star_border,
                color: f.important ? Colors.amber : null),
            onPressed: onToggleImportant,
          ),
          IconButton(
            tooltip: '下载',
            icon: const Icon(Icons.download_outlined),
            onPressed: onDownload,
          ),
        ]),
      ),
    );
  }

  IconData _iconFor(FileItem f) {
    final e = f.ext.replaceAll('.', '').toLowerCase();
    if (['doc', 'docx'].contains(e)) return Icons.description_outlined;
    if (['xls', 'xlsx', 'csv'].contains(e)) return Icons.table_chart_outlined;
    if (['ppt', 'pptx'].contains(e)) return Icons.slideshow_outlined;
    if (e == 'pdf') return Icons.picture_as_pdf_outlined;
    if (['zip', 'rar', '7z', 'tar', 'gz'].contains(e)) {
      return Icons.folder_zip_outlined;
    }
    if (['mp3', 'wav', 'amr', 'm4a', 'aac'].contains(e)) {
      return Icons.audio_file_outlined;
    }
    if (['mp4', 'mov', 'avi', 'mkv'].contains(e)) {
      return Icons.video_file_outlined;
    }
    return Icons.insert_drive_file_outlined;
  }
}
