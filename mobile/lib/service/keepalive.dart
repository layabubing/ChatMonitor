/// 后台保活：前台服务维持 SSE 长连接，收到提醒弹系统通知；workmanager 15 分钟兜底轮询。
library;

import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:workmanager/workmanager.dart';

// ═══════════════ 本地通知（App 主 isolate 与保活 isolate 共用） ═══════════════
class NotifyHelper {
  static final FlutterLocalNotificationsPlugin plugin =
      FlutterLocalNotificationsPlugin();

  static const channelHigh = 'alerts_high';
  static const channelNormal = 'alerts_normal';

  static Future<void> init(
      {void Function(String? payload)? onTap}) async {
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    await plugin.initialize(
      const InitializationSettings(android: android),
      onDidReceiveNotificationResponse: (resp) => onTap?.call(resp.payload),
    );
    await plugin
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(const AndroidNotificationChannel(
          channelHigh,
          '重要提醒',
          description: '高优先级群聊提醒',
          importance: Importance.max,
        ));
    await plugin
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(const AndroidNotificationChannel(
          channelNormal,
          '普通提醒',
          description: '中/低优先级群聊提醒',
          importance: Importance.defaultImportance,
        ));
  }

  static Future<void> showAlert({
    required int id,
    required String priority,
    required String title,
    required String body,
  }) async {
    final high = priority == 'high';
    await plugin.show(
      id,
      title,
      body,
      NotificationDetails(
        android: AndroidNotificationDetails(
          high ? channelHigh : channelNormal,
          high ? '重要提醒' : '普通提醒',
          importance: high ? Importance.max : Importance.defaultImportance,
          priority: high ? Priority.high : Priority.defaultPriority,
        ),
      ),
      payload: 'alerts',
    );
  }
}

// ═══════════════ 前台服务 TaskHandler（独立 isolate） ═══════════════
@pragma('vm:entry-point')
void monitorStartCallback() {
  FlutterForegroundTask.setTaskHandler(MonitorTaskHandler());
}

class MonitorTaskHandler extends TaskHandler {
  StreamSubscription? _sub;
  Timer? _reconnect;
  Timer? _poll;
  Dio? _dio;
  String _baseUrl = '';
  String _token = '';
  bool _stopped = false;

  Future<void> _loadConfig() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString('base_url') ?? '';
    _token = prefs.getString('token') ?? '';
    _dio = Dio(BaseOptions(
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: Duration.zero,
      headers: {'Authorization': 'Bearer $_token'},
    ));
  }

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    await NotifyHelper.init();
    await _loadConfig();
    if (_baseUrl.isEmpty || _token.isEmpty) return;
    _connectSse();
    // 每 60s 自检：SSE 断了兜底轮询一次
    _poll = Timer.periodic(const Duration(seconds: 60), (_) => _pollAlerts());
  }

  void _connectSse() {
    if (_stopped) return;
    _sub?.cancel();
    _reconnect?.cancel();
    _dio!
        .get<ResponseBody>(
      '$_baseUrl/api/stream',
      options: Options(
          responseType: ResponseType.stream,
          headers: {'Accept': 'text/event-stream', 'Cache-Control': 'no-cache'}),
    )
        .then((resp) {
      String buffer = '', eventName = '';
      final dataLines = <String>[];
      _sub = resp.data!.stream.listen(
        (chunk) {
          buffer += utf8.decode(chunk, allowMalformed: true);
          while (buffer.contains('\n')) {
            final idx = buffer.indexOf('\n');
            final line = buffer.substring(0, idx).trimRight();
            buffer = buffer.substring(idx + 1);
            if (line.isEmpty) {
              if (dataLines.isNotEmpty) {
                _handleEvent(eventName, dataLines.join('\n'));
              }
              eventName = '';
              dataLines.clear();
            } else if (line.startsWith('event:')) {
              eventName = line.substring(6).trim();
            } else if (line.startsWith('data:')) {
              dataLines.add(line.substring(5).trimLeft());
            }
          }
        },
        onError: (_) => _scheduleReconnect(),
        onDone: _scheduleReconnect,
        cancelOnError: true,
      );
    }).catchError((_) => _scheduleReconnect());
  }

  void _scheduleReconnect() {
    if (_stopped) return;
    _sub?.cancel();
    _reconnect = Timer(const Duration(seconds: 30), _connectSse);
  }

  Future<void> _handleEvent(String event, String raw) async {
    if (event != 'alert') return;
    try {
      final d = jsonDecode(raw);
      if (d is! Map) return;
      final preview = '${d['preview'] ?? ''}';
      final group = '${d['group_name'] ?? ''}';
      final platform = '${d['platform'] ?? ''}' == 'qq' ? 'QQ' : '钉钉';
      await NotifyHelper.showAlert(
        id: DateTime.now().millisecondsSinceEpoch ~/ 1000 % 100000,
        priority: '${d['priority'] ?? ''}',
        title: '[$platform] $group 有新提醒',
        body: preview.isEmpty ? '点击查看详情' : preview,
      );
      await _markSeen();
    } catch (_) {}
  }

  /// 兜底轮询：拉未读提醒，与上次最大 id 比对，补发通知。
  Future<void> _pollAlerts() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final lastId = prefs.getInt('last_alert_id') ?? 0;
      final resp = await _dio!.get<Map<String, dynamic>>(
        '$_baseUrl/api/alerts',
        queryParameters: {'unread': true, 'page': 1, 'page_size': 10},
      );
      final items = (resp.data?['items'] as List? ?? []);
      var maxId = lastId;
      for (final it in items.reversed) {
        final m = it as Map;
        final id = (m['id'] ?? 0) as int;
        final platform = '${m['platform'] ?? ''}';
        // 跨平台 id 可能重复/乱序，用 "platform:id" 判重更稳
        final seenKey = 'seen_alert_$platform:$id';
        if (prefs.getBool(seenKey) == true) continue;
        if (id > maxId) maxId = id;
        if (lastId > 0 && id <= lastId) continue; // 首次运行不轰炸
        await prefs.setBool(seenKey, true);
        await NotifyHelper.showAlert(
          id: id % 100000,
          priority: '${m['priority'] ?? ''}',
          title:
              '[${platform == 'qq' ? 'QQ' : '钉钉'}] ${m['group_name'] ?? ''} 有新提醒',
          body: ('${m['content'] ?? ''}').isEmpty
              ? '点击查看详情'
              : '${m['content']}'.substring(
                  0, '${m['content']}'.length.clamp(0, 50)),
        );
      }
      if (maxId > lastId) await prefs.setInt('last_alert_id', maxId);
    } catch (_) {}
  }

  Future<void> _markSeen() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final resp = await _dio!.get<Map<String, dynamic>>(
        '$_baseUrl/api/alerts',
        queryParameters: {'page': 1, 'page_size': 1},
      );
      final items = (resp.data?['items'] as List? ?? []);
      if (items.isNotEmpty) {
        final m = items.first as Map;
        await prefs.setInt('last_alert_id', (m['id'] ?? 0) as int);
      }
    } catch (_) {}
  }

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  Future<void> onDestroy(DateTime timestamp) async {
    _stopped = true;
    _reconnect?.cancel();
    _poll?.cancel();
    await _sub?.cancel();
  }
}

// ═══════════════ workmanager 兜底任务 ═══════════════
const kPollTaskName = 'chat_monitor_poll';

@pragma('vm:entry-point')
void callbackDispatcher() {
  Workmanager().executeTask((task, inputData) async {
    try {
      await NotifyHelper.init();
      final prefs = await SharedPreferences.getInstance();
      final baseUrl = prefs.getString('base_url') ?? '';
      final token = prefs.getString('token') ?? '';
      if (baseUrl.isEmpty || token.isEmpty) return true;
      final dio = Dio(BaseOptions(
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 15),
        headers: {'Authorization': 'Bearer $token'},
      ));
      final lastId = prefs.getInt('last_alert_id') ?? 0;
      final resp = await dio.get<Map<String, dynamic>>(
        '$baseUrl/api/alerts',
        queryParameters: {'unread': true, 'page': 1, 'page_size': 10},
      );
      final items = (resp.data?['items'] as List? ?? []);
      var maxId = lastId;
      for (final it in items) {
        final m = it as Map;
        final id = (m['id'] ?? 0) as int;
        if (id > maxId) maxId = id;
        final platform = '${m['platform'] ?? ''}';
        final seenKey = 'seen_alert_$platform:$id';
        if (prefs.getBool(seenKey) == true) continue;
        if (lastId > 0 && id <= lastId) continue;
        await prefs.setBool(seenKey, true);
        final content = '${m['content'] ?? ''}';
        await NotifyHelper.showAlert(
          id: id % 100000,
          priority: '${m['priority'] ?? ''}',
          title:
              '[${platform == 'qq' ? 'QQ' : '钉钉'}] ${m['group_name'] ?? ''} 有新提醒',
          body: content.isEmpty
              ? '点击查看详情'
              : content.substring(0, content.length.clamp(0, 50)),
        );
      }
      if (maxId > lastId) await prefs.setInt('last_alert_id', maxId);
      return true;
    } catch (_) {
      return true; // 失败也标记完成，交给下一周期
    }
  });
}

// ═══════════════ UI 侧控制 ═══════════════
class KeepaliveService {
  static void init() {
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'monitor_service',
        channelName: '监控服务',
        channelDescription: '保持与服务器连接以接收实时提醒',
        onlyAlertOnce: true,
        channelImportance: NotificationChannelImportance.LOW,
        priority: NotificationPriority.LOW,
      ),
      iosNotificationOptions:
          const IOSNotificationOptions(showNotification: false, playSound: false),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.repeat(60000),
        autoRunOnBoot: true,
        autoRunOnMyPackageReplaced: true,
        allowWakeLock: true,
        allowWifiLock: true,
      ),
    );
  }

  static Future<void> requestPermissions() async {
    final p = await FlutterForegroundTask.checkNotificationPermission();
    if (p != NotificationPermission.granted) {
      await FlutterForegroundTask.requestNotificationPermission();
    }
  }

  static Future<bool> start() async {
    await requestPermissions();
    if (await FlutterForegroundTask.isRunningService) {
      final r = await FlutterForegroundTask.restartService();
      return r is ServiceRequestSuccess;
    }
    final r = await FlutterForegroundTask.startService(
      serviceId: 256,
      notificationTitle: 'ChatMonitor 运行中',
      notificationText: '正在实时接收群聊提醒',
      callback: monitorStartCallback,
    );
    return r is ServiceRequestSuccess;
  }

  static Future<void> stop() async {
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
  }

  static Future<bool> get isRunning => FlutterForegroundTask.isRunningService;

  static Future<void> registerPolling() async {
    await Workmanager().initialize(callbackDispatcher);
    await Workmanager().registerPeriodicTask(
      kPollTaskName,
      kPollTaskName,
      frequency: const Duration(minutes: 15),
      constraints: Constraints(networkType: NetworkType.connected),
    );
  }
}
