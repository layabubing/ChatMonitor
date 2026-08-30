/// 平台元数据：与后端 PLATFORM_META 对齐。
/// 内置 4 平台默认值兜底，登录后由 /api/platforms/meta 下发覆盖并持久化。
/// 纯 Dart（不依赖 Flutter），App UI 与后台保活 isolate 共用。
library;

import 'dart:convert';

class PlatformMeta {
  final String name;
  String displayName;
  List<String> keys;
  List<String> secretKeys;

  PlatformMeta({
    required this.name,
    required this.displayName,
    this.keys = const [],
    this.secretKeys = const [],
  });

  factory PlatformMeta.fromJson(Map<String, dynamic> j) => PlatformMeta(
        name: j['name'] ?? '',
        displayName: j['display_name'] ?? j['name'] ?? '',
        keys: (j['keys'] as List? ?? []).map((e) => '$e').toList(),
        secretKeys: (j['secret_keys'] as List? ?? []).map((e) => '$e').toList(),
      );

  Map<String, dynamic> toJson() => {
        'name': name,
        'display_name': displayName,
        'keys': keys,
        'secret_keys': secretKeys,
      };

  /// 绑定表单要展示的键（排除 *_ENABLED，启用开关单独处理）
  List<String> get formKeys =>
      keys.where((k) => !k.endsWith('_ENABLED')).toList();

  bool isSecret(String key) => secretKeys.contains(key);
}

/// 平台显示色（服务端不下发颜色，本地约定）
const _platformColors = <String, int>{
  'qq': 0xFF12B7F5,
  'dingtalk': 0xFF1E88E5,
  'feishu': 0xFF3370FF,
  'workwechat': 0xFF07C160,
};

/// 内置默认元数据（服务端 meta 不可用时的兜底，顺序即 UI 顺序）
final List<PlatformMeta> kDefaultPlatformMetas = [
  PlatformMeta(
    name: 'qq',
    displayName: 'QQ',
    keys: ['QQ_APP_ID', 'QQ_APP_SECRET', 'QQ_ENV', 'QQ_GROUP_OPENIDS', 'QQ_ENABLED'],
    secretKeys: ['QQ_APP_SECRET'],
  ),
  PlatformMeta(
    name: 'dingtalk',
    displayName: '钉钉',
    keys: ['DINGTALK_APP_KEY', 'DINGTALK_APP_SECRET', 'DINGTALK_CHAT_IDS', 'DINGTALK_ENABLED'],
    secretKeys: ['DINGTALK_APP_SECRET'],
  ),
  PlatformMeta(
    name: 'feishu',
    displayName: '飞书',
    keys: ['FEISHU_APP_ID', 'FEISHU_APP_SECRET', 'FEISHU_CHAT_IDS', 'FEISHU_ENABLED'],
    secretKeys: ['FEISHU_APP_SECRET'],
  ),
  PlatformMeta(
    name: 'workwechat',
    displayName: '企业微信',
    keys: [
      'WORKWECHAT_CORP_ID', 'WORKWECHAT_AGENT_ID', 'WORKWECHAT_SECRET',
      'WORKWECHAT_TOKEN', 'WORKWECHAT_AES_KEY', 'WORKWECHAT_CHAT_IDS',
      'WORKWECHAT_ENABLED',
    ],
    secretKeys: ['WORKWECHAT_SECRET', 'WORKWECHAT_TOKEN', 'WORKWECHAT_AES_KEY'],
  ),
];

/// 当前生效的元数据（有序）。AppState 登录后更新；后台 isolate 经 loadMetasJson 注入。
List<PlatformMeta> activeMetas = List.of(kDefaultPlatformMetas);

PlatformMeta? metaOf(String name) {
  for (final m in activeMetas) {
    if (m.name == name) return m;
  }
  return null;
}

String platformDisplayName(String p) => metaOf(p)?.displayName ?? p;

int platformColorValue(String p) => _platformColors[p] ?? 0xFF607D8B;

/// 服务端下发合并：显示名/键名以服务端为准，顺序以服务端为准。
void applyServerMetas(List<dynamic> items) {
  final parsed = items
      .whereType<Map>()
      .map((e) => PlatformMeta.fromJson(Map<String, dynamic>.from(e)))
      .where((m) => m.name.isNotEmpty)
      .toList();
  if (parsed.isNotEmpty) activeMetas = parsed;
}

String dumpMetasJson() =>
    jsonEncode(activeMetas.map((m) => m.toJson()).toList());

void loadMetasJson(String? raw) {
  if (raw == null || raw.isEmpty) return;
  try {
    final l = jsonDecode(raw);
    if (l is List) applyServerMetas(l);
  } catch (_) {}
}

// ═══════════════ 绑定表单键名 → 人类可读标签 ═══════════════
const _keyLabels = <String, String>{
  'APP_ID': 'App ID',
  'APP_KEY': 'App Key',
  'APP_SECRET': 'App Secret',
  'CORP_ID': '企业 ID（Corp ID）',
  'AGENT_ID': '应用 ID（Agent ID）',
  'SECRET': '应用 Secret',
  'TOKEN': '回调 Token',
  'AES_KEY': '回调 EncodingAESKey',
  'ENV': '环境（sandbox / prod）',
  'GROUP_OPENIDS': '群 OpenID（多个用逗号分隔）',
  'CHAT_IDS': '群 Chat ID（多个用逗号分隔）',
};

/// 去掉平台前缀后查表，查不到回显原键名。
String bindingKeyLabel(String platform, String key) {
  var suffix = key;
  final prefix = '${platform.toUpperCase()}_';
  if (suffix.startsWith(prefix)) suffix = suffix.substring(prefix.length);
  return _keyLabels[suffix] ?? key;
}
