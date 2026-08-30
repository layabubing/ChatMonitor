/// 全局应用状态：登录态、总览数据、SSE 实时事件分发（ChangeNotifier，无第三方状态库）。
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../api/platforms.dart';
import '../api/sse.dart';

export '../api/platforms.dart';
export '../api/sse.dart' show SseEvent;

class SseState {
  static const connecting = 0;
  static const online = 1;
  static const offline = 2;
}

class AppState extends ChangeNotifier {
  static final AppState instance = AppState._();
  AppState._();

  late final ApiClient api;
  bool ready = false;

  // 登录态
  String baseUrl = '';
  String? token;
  String username = '';
  String role = '';
  String nickname = '';
  bool get loggedIn => token != null && token!.isNotEmpty;

  // 总览
  Map<String, PlatformOverview> overviewData = {};
  int get unreadTotal =>
      overviewData.values.fold(0, (s, o) => s + o.alertUnread);

  // SSE
  SseClient? _sse;
  int sseState = SseState.offline;
  SseEvent? lastEvent; // 最近一次事件（页面监听后自行刷新）
  Timer? _pollTimer;

  // 底部导航
  int currentTab = 0;
  void setTab(int i) {
    currentTab = i;
    notifyListeners();
  }

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    baseUrl = prefs.getString('base_url') ?? '';
    token = prefs.getString('token');
    loadMetasJson(prefs.getString('platform_meta')); // 恢复上次服务端下发的平台元数据
    api = ApiClient(baseUrl: baseUrl, token: token)
      ..onUnauthorized = () => logout(kickToLogin: true);
    if (loggedIn) {
      try {
        final me = await api.me();
        username = me['username'] ?? '';
        role = me['role'] ?? '';
        nickname = me['nickname'] ?? '';
        startRealtime();
        unawaited(refreshOverview());
        unawaited(refreshPlatformMetas());
      } on ApiException catch (e) {
        if (e.isAuth) await logout();
      } catch (_) {}
    }
    ready = true;
    notifyListeners();
  }

  /// 拉取服务端平台元数据并持久化（供 UI 动态渲染与后台 isolate 使用）。
  Future<void> refreshPlatformMetas() async {
    if (!loggedIn) return;
    try {
      final items = await api.platformsMeta();
      applyServerMetas(items);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('platform_meta', dumpMetasJson());
      notifyListeners();
    } catch (_) {}
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('base_url', baseUrl);
    if (token != null) {
      await prefs.setString('token', token!);
    } else {
      await prefs.remove('token');
    }
  }

  Future<void> login(String server, String user, String password) async {
    baseUrl = server.trim().replaceAll(RegExp(r'/+$'), '');
    if (!baseUrl.startsWith('http')) baseUrl = 'http://$baseUrl';
    api.baseUrl = baseUrl;
    await api.login(user, password);
    token = api.token;
    final me = await api.me();
    username = me['username'] ?? '';
    role = me['role'] ?? '';
    nickname = me['nickname'] ?? '';
    await _persist();
    startRealtime();
    unawaited(refreshOverview());
    unawaited(refreshPlatformMetas());
    notifyListeners();
  }

  Future<void> register(String server, String user, String password,
      {String inviteCode = ''}) async {
    baseUrl = server.trim().replaceAll(RegExp(r'/+$'), '');
    if (!baseUrl.startsWith('http')) baseUrl = 'http://$baseUrl';
    api.baseUrl = baseUrl;
    await api.register(user, password, inviteCode: inviteCode);
  }

  Future<void> logout({bool kickToLogin = false}) async {
    if (!kickToLogin) {
      try {
        await api.me(); // 保持语义简单：后端登出仅清 Cookie，移动端直接清本地 token
      } catch (_) {}
    }
    token = null;
    api.token = null;
    username = role = nickname = '';
    overviewData = {};
    currentTab = 0;
    await _stopRealtime();
    await _persist();
    notifyListeners();
  }

  Future<void> refreshOverview() async {
    if (!loggedIn) return;
    try {
      overviewData = await api.overview();
      notifyListeners();
    } catch (_) {}
  }

  // ── 实时（SSE + 断线轮询兜底）──
  void startRealtime() {
    if (!loggedIn) return;
    _sse?.dispose();
    sseState = SseState.connecting;
    _sse = SseClient(
      url: '$baseUrl/api/stream',
      headers: api.authHeaders,
      onEvent: _onSseEvent,
      onStateChange: (connected) {
        sseState = connected ? SseState.online : SseState.offline;
        if (connected) {
          _pollTimer?.cancel();
        } else {
          _startPollingFallback();
        }
        notifyListeners();
      },
    )..connect();
    notifyListeners();
  }

  void _onSseEvent(SseEvent e) {
    lastEvent = e;
    if (e.event == 'alert' || e.event == 'message' || e.event == 'report') {
      unawaited(refreshOverview());
    }
    notifyListeners();
  }

  void _startPollingFallback() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 15), (_) async {
      await refreshOverview();
      // 轮询兜底下也分发一次"伪事件"，让列表页有机会自刷新
      lastEvent = SseEvent('poll', {});
      notifyListeners();
    });
  }

  Future<void> _stopRealtime() async {
    _pollTimer?.cancel();
    await _sse?.dispose();
    _sse = null;
    sseState = SseState.offline;
  }
}
