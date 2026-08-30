import 'dart:io';

import 'package:app_settings/app_settings.dart';
import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import '../service/keepalive.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  Map<String, dynamic>? _settings;
  String? _error;
  bool _serviceRunning = false;
  bool _batteryIgnored = false;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      final s = await AppState.instance.api.settings();
      final running = await KeepaliveService.isRunning;
      final ignored = Platform.isAndroid
          ? await FlutterForegroundTask.isIgnoringBatteryOptimizations
          : true;
      if (!mounted) return;
      setState(() {
        _settings = s;
        _error = null;
        _serviceRunning = running;
        _batteryIgnored = ignored;
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) return ErrorView(_error!, onRetry: _reload);
    final s = _settings;
    if (s == null) return const Center(child: CircularProgressIndicator());
    final app = AppState.instance;
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(padding: const EdgeInsets.all(12), children: [
        // ── 账号 ──
        _Section('账号', children: [
          ListTile(
            leading: const Icon(Icons.person_outline),
            title: Text(s['nickname']?.isNotEmpty == true
                ? s['nickname']
                : s['username'] ?? ''),
            subtitle: Text(
                '账号 ${s['username']} · ${s['role'] == 'admin' ? '管理员' : '普通用户'}'),
            trailing: TextButton(
              child: const Text('改昵称'),
              onPressed: () => _editNickname(s['nickname'] ?? ''),
            ),
          ),
          ListTile(
            leading: const Icon(Icons.lock_outline),
            title: const Text('修改密码'),
            onTap: _changePassword,
          ),
          ListTile(
            leading: const Icon(Icons.logout, color: Colors.red),
            title: const Text('退出登录', style: TextStyle(color: Colors.red)),
            onTap: () async {
              await KeepaliveService.stop();
              await app.logout();
            },
          ),
        ]),

        // ── 保活设置 ──
        _Section('后台通知（保活）', children: [
          SwitchListTile(
            secondary: const Icon(Icons.sync),
            title: const Text('后台监控服务'),
            subtitle: Text(_serviceRunning ? '运行中：实时接收提醒' : '已停止'),
            value: _serviceRunning,
            onChanged: (v) async {
              if (v) {
                final ok = await KeepaliveService.start();
                await KeepaliveService.registerPolling();
                if (!context.mounted) return;
                showSnack(context, ok ? '服务已启动' : '启动失败，请检查通知权限',
                    error: !ok);
              } else {
                await KeepaliveService.stop();
              }
              await _reload();
            },
          ),
          if (!_batteryIgnored)
            ListTile(
              leading: const Icon(Icons.battery_saver, color: Colors.orange),
              title: const Text('电池优化未关闭'),
              subtitle: const Text('为保证后台稳定接收，建议关闭本应用的电池优化'),
              trailing: TextButton(
                child: const Text('去设置'),
                onPressed: () async {
                  await FlutterForegroundTask.requestIgnoreBatteryOptimization();
                  await _reload();
                },
              ),
            ),
          ListTile(
            leading: const Icon(Icons.phonelink_setup_outlined),
            title: const Text('自启动 / 后台运行权限'),
            subtitle: const Text('国产 ROM 请在系统设置中允许自启动、锁定后台'),
            trailing: TextButton(
              child: const Text('去设置'),
              onPressed: () => AppSettings.openAppSettings(),
            ),
          ),
          ListTile(
            leading: const Icon(Icons.notifications_outlined),
            title: const Text('通知权限与渠道'),
            trailing: TextButton(
              child: const Text('去设置'),
              onPressed: () =>
                  AppSettings.openAppSettings(type: AppSettingsType.notification),
            ),
          ),
        ]),

        // ── 关键词库 ──
        _Section('关键词库', children: [
          ListTile(
            leading: const Icon(Icons.key_outlined),
            title: Text(
                '${(s['keywords'] as Map? ?? {}).length} 个分类'),
            subtitle: const Text('命中关键词的消息将进入 AI 重要性确认'),
            trailing: TextButton(
              child: const Text('编辑'),
              onPressed: () => _editKeywords(
                  Map<String, dynamic>.from(s['keywords'] as Map? ?? {})),
            ),
          ),
        ]),

        // ── 平台绑定 ──
        _Section('平台绑定', children: [
          for (final p in (s['platforms'] as List? ?? []))
            ListTile(
              leading: Icon(Icons.link,
                  color: platformColor('${(p as Map)['name']}')),
              title: Text(platformLabel('${p['name']}')),
              subtitle: Text(
                  '${p['enabled'] ? '已启用' : '未启用'}${p['running'] ? ' · 运行中' : ''} · 日报 ${p['report_time']}'),
              trailing: TextButton(
                child: const Text('配置'),
                onPressed: () => _editBinding('${p['name']}'),
              ),
            ),
        ]),

        // ── 关于 ──
        _Section('关于', children: [
          ListTile(
            leading: const Icon(Icons.dns_outlined),
            title: const Text('服务器'),
            subtitle: Text(app.baseUrl),
          ),
          ListTile(
            leading: const Icon(Icons.smart_toy_outlined),
            title: const Text('AI 模型'),
            subtitle: Text(
                '${(s['ai'] as Map? ?? {})['model'] ?? '-'}（密钥${(s['ai'] as Map? ?? {})['key_set'] == true ? '已配置' : '未配置'}）'),
          ),
        ]),
        const SizedBox(height: 24),
      ]),
    );
  }

  // ═══════════════ 账号操作 ═══════════════
  Future<void> _editNickname(String current) async {
    final c = TextEditingController(text: current);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('修改昵称'),
        content: TextField(
          controller: c,
          maxLength: 24,
          decoration: const InputDecoration(labelText: '昵称'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('保存')),
        ],
      ),
    );
    if (ok == true) {
      try {
        await AppState.instance.api.updateNickname(c.text.trim());
        if (mounted) showSnack(context, '昵称已更新');
        _reload();
      } catch (e) {
        if (mounted) showSnack(context, '$e', error: true);
      }
    }
  }

  Future<void> _changePassword() async {
    final oldC = TextEditingController();
    final newC = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('修改密码'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
              controller: oldC,
              obscureText: true,
              decoration: const InputDecoration(labelText: '旧密码')),
          const SizedBox(height: 8),
          TextField(
              controller: newC,
              obscureText: true,
              decoration: const InputDecoration(labelText: '新密码（至少 6 位）')),
        ]),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('确认')),
        ],
      ),
    );
    if (ok == true) {
      try {
        await AppState.instance.api.changePassword(oldC.text, newC.text);
        if (mounted) {
          showSnack(context, '密码已修改，请重新登录');
          await KeepaliveService.stop();
          await AppState.instance.logout();
        }
      } catch (e) {
        if (mounted) showSnack(context, '$e', error: true);
      }
    }
  }

  // ═══════════════ 关键词编辑 ═══════════════
  Future<void> _editKeywords(Map<String, dynamic> keywords) async {
    final changed = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => KeywordsEditorPage(keywords: keywords),
    ));
    if (changed == true) _reload();
  }

  // ═══════════════ 平台绑定编辑 ═══════════════
  Future<void> _editBinding(String platform) async {
    final changed = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => PlatformBindingPage(platform: platform),
    ));
    if (changed == true) _reload();
  }
}

class _Section extends StatelessWidget {
  final String title;
  final List<Widget> children;
  const _Section(this.title, {required this.children});

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(8, 16, 8, 6),
        child: Text(title,
            style: TextStyle(
                color: Theme.of(context).colorScheme.primary,
                fontWeight: FontWeight.bold)),
      ),
      Card(margin: EdgeInsets.zero, child: Column(children: children)),
    ]);
  }
}

// ═══════════════ 关键词编辑页 ═══════════════
class KeywordsEditorPage extends StatefulWidget {
  final Map<String, dynamic> keywords;
  const KeywordsEditorPage({super.key, required this.keywords});

  @override
  State<KeywordsEditorPage> createState() => _KeywordsEditorPageState();
}

class _KeywordsEditorPageState extends State<KeywordsEditorPage> {
  late final Map<String, TextEditingController> _controllers = {
    for (final e in widget.keywords.entries)
      e.key: TextEditingController(
          text: (e.value as List? ?? []).join('，')),
  };
  bool _saving = false;

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final cats = <String, dynamic>{
        for (final e in _controllers.entries)
          e.key: e.value.text
              .split(RegExp(r'[,，;；\n]'))
              .map((w) => w.trim())
              .where((w) => w.isNotEmpty)
              .toList(),
      };
      await AppState.instance.api.saveKeywords(cats);
      if (mounted) {
        showSnack(context, '关键词已保存并下发重载');
        Navigator.pop(context, true);
      }
    } catch (e) {
      if (mounted) showSnack(context, '$e', error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _addCategory() async {
    final c = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('新增分类'),
        content: TextField(
            controller: c, decoration: const InputDecoration(labelText: '分类名')),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('添加')),
        ],
      ),
    );
    if (ok == true && c.text.trim().isNotEmpty) {
      setState(() =>
          _controllers[c.text.trim()] = TextEditingController());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('编辑关键词库'), actions: [
        IconButton(
            icon: const Icon(Icons.add),
            tooltip: '新增分类',
            onPressed: _addCategory),
      ]),
      body: ListView(padding: const EdgeInsets.all(12), children: [
        const Padding(
          padding: EdgeInsets.only(bottom: 8),
          child: Text('每个分类一组关键词，用逗号/分号/换行分隔；保存后自动通知监控端重载。',
              style: TextStyle(fontSize: 12, color: Colors.grey)),
        ),
        for (final e in _controllers.entries)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Expanded(
                          child: Text(e.key,
                              style: const TextStyle(
                                  fontWeight: FontWeight.bold))),
                      IconButton(
                        icon: const Icon(Icons.delete_outline, size: 20),
                        onPressed: () =>
                            setState(() => _controllers.remove(e.key)),
                      ),
                    ]),
                    TextField(
                      controller: e.value,
                      maxLines: null,
                      decoration: const InputDecoration(
                          hintText: '关键词1，关键词2，…', border: InputBorder.none),
                    ),
                  ]),
            ),
          ),
        const SizedBox(height: 72),
      ]),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _saving ? null : _save,
        icon: _saving
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2))
            : const Icon(Icons.save),
        label: const Text('保存'),
      ),
    );
  }
}

// ═══════════════ 平台绑定配置页 ═══════════════
class PlatformBindingPage extends StatefulWidget {
  final String platform;
  const PlatformBindingPage({super.key, required this.platform});

  @override
  State<PlatformBindingPage> createState() => _PlatformBindingPageState();
}

class _PlatformBindingPageState extends State<PlatformBindingPage> {
  PlatformMeta? get _meta => metaOf(widget.platform);

  final _controllers = <String, TextEditingController>{};
  final _secretKeys = <String>{};
  final _secretSet = <String, bool>{};
  bool _enabled = true;
  bool _loading = true;
  bool _busy = false;
  String? _testResult;
  bool? _testOk;

  /// 表单键由平台元数据驱动（排除 *_ENABLED，启用走开关）
  List<String> get _keys =>
      _meta?.formKeys ?? [for (final k in _controllers.keys) k];

  String _labelOf(String k) => bindingKeyLabel(widget.platform, k);

  bool _isSecret(String k) =>
      _secretKeys.contains(k) || (_meta?.isSecret(k) ?? k.endsWith('SECRET'));

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d =
          await AppState.instance.api.getPlatformBinding(widget.platform);
      final cfg = Map<String, dynamic>.from(d['config'] as Map? ?? {});
      // 元数据未知的平台：从返回的配置键推导表单（排除 enabled 与 *_SET 标记）
      final ks = _keys.isNotEmpty
          ? _keys
          : cfg.keys
              .where((k) =>
                  k != 'enabled' && !k.endsWith('_SET') && !k.endsWith('_ENABLED'))
              .toList();
      setState(() {
        _enabled = cfg['enabled'] == true;
        for (final k in ks) {
          // 元数据 secret_keys 或后端 *_SET 标记任一为真即按密钥处理
          final secret = _isSecret(k) || cfg.containsKey('${k}_SET');
          if (secret) {
            _secretKeys.add(k);
            _secretSet[k] = cfg['${k}_SET'] == true;
          }
          _controllers[k] = TextEditingController(
              text: secret ? '' : '${cfg[k] ?? ''}');
        }
        _loading = false;
      });
    } catch (e) {
      if (mounted) {
        showSnack(context, '$e', error: true);
        setState(() => _loading = false);
      }
    }
  }

  Map<String, dynamic> _buildBody() {
    final body = <String, dynamic>{'enabled': _enabled};
    for (final e in _controllers.entries) {
      if (_isSecret(e.key) && e.value.text.trim().isEmpty) continue; // 留空=不变
      body[e.key] = e.value.text.trim();
    }
    return body;
  }

  Future<void> _save() async {
    setState(() => _busy = true);
    try {
      await AppState.instance.api.savePlatformBinding(widget.platform, _buildBody());
      if (mounted) {
        showSnack(context, '已保存，监控端将在 15 秒内自动接入');
        Navigator.pop(context, true);
      }
    } catch (e) {
      if (mounted) showSnack(context, '$e', error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _test() async {
    setState(() {
      _busy = true;
      _testResult = null;
    });
    try {
      final r = await AppState.instance.api
          .testPlatformBinding(widget.platform, _buildBody());
      setState(() {
        _testOk = r['ok'] == true;
        _testResult = '${r['detail'] ?? ''}';
      });
    } catch (e) {
      setState(() {
        _testOk = false;
        _testResult = '$e';
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('${platformLabel(widget.platform)}绑定配置')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(padding: const EdgeInsets.all(16), children: [
              SwitchListTile(
                title: const Text('启用该平台的监控'),
                value: _enabled,
                onChanged: (v) => setState(() => _enabled = v),
              ),
              const SizedBox(height: 8),
              for (final k in _keys)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: TextField(
                    controller: _controllers[k],
                    obscureText: _isSecret(k),
                    decoration: InputDecoration(
                      labelText: _labelOf(k),
                      hintText: _isSecret(k)
                          ? (_secretSet[k] == true
                              ? '已保存，留空表示不修改'
                              : '留空表示不修改已保存的密钥')
                          : null,
                      border: const OutlineInputBorder(),
                    ),
                  ),
                ),
              if (_testResult != null)
                Container(
                  padding: const EdgeInsets.all(12),
                  margin: const EdgeInsets.only(bottom: 12),
                  decoration: BoxDecoration(
                    color: (_testOk == true ? Colors.green : Colors.red)
                        .withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(children: [
                    Icon(
                        _testOk == true
                            ? Icons.check_circle_outline
                            : Icons.error_outline,
                        color: _testOk == true ? Colors.green : Colors.red,
                        size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                        child: Text(_testResult!,
                            style: const TextStyle(fontSize: 13))),
                  ]),
                ),
              Row(children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _busy ? null : _test,
                    icon: const Icon(Icons.wifi_tethering),
                    label: const Text('测试凭证'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: _busy ? null : _save,
                    icon: const Icon(Icons.save),
                    label: const Text('保存'),
                  ),
                ),
              ]),
            ]),
    );
  }
}
