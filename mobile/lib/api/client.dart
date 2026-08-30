/// API 客户端：Dio 封装（Bearer 认证、统一错误、全部业务端点）。
library;

import 'package:dio/dio.dart';

import 'models.dart';

class ApiException implements Exception {
  final String message;
  final int? statusCode;
  ApiException(this.message, {this.statusCode});

  /// true 表示认证失效（401），调用方应跳转登录页。
  bool get isAuth => statusCode == 401;

  @override
  String toString() => message;
}

class ApiClient {
  String baseUrl;
  String? token;
  void Function()? onUnauthorized;

  late final Dio _dio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 20),
  ))
    ..interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
    ));

  ApiClient({this.baseUrl = '', this.token});

  Uri _u(String path, [Map<String, dynamic>? query]) =>
      Uri.parse('$baseUrl$path').replace(queryParameters: query);

  Map<String, String> get authHeaders =>
      token != null ? {'Authorization': 'Bearer $token'} : {};

  /// 媒体/文件等需要拼完整 URL 的场景（WebView / 图片加载）。
  Uri fullUri(String path, [Map<String, dynamic>? query]) => _u(path, query);

  Future<dynamic> _req(String method, String path,
      {Map<String, dynamic>? query, dynamic data, bool raw = false}) async {
    try {
      final resp = await _dio.request<dynamic>(
        '$baseUrl$path',
        queryParameters: query,
        data: data,
        options: Options(
            method: method,
            responseType: raw ? ResponseType.bytes : ResponseType.json),
      );
      return resp.data;
    } on DioException catch (e) {
      final code = e.response?.statusCode;
      if (code == 401) onUnauthorized?.call();
      String msg = '网络错误，请检查服务器地址与网络';
      final d = e.response?.data;
      if (d is Map && d['error'] != null) {
        msg = '${d['error']}';
      } else if (e.type == DioExceptionType.connectionTimeout ||
          e.type == DioExceptionType.receiveTimeout) {
        msg = '连接超时，请稍后重试';
      }
      throw ApiException(msg, statusCode: code);
    }
  }

  // ── 认证 ──
  /// 登录：从 Set-Cookie 提取 JWT（后端仅 HttpOnly Cookie 下发，移动端走 Bearer）。
  Future<void> login(String username, String password) async {
    try {
      final resp = await _dio.post<Map<String, dynamic>>('$baseUrl/api/login',
          data: {'username': username, 'password': password});
      final cookies = resp.headers['set-cookie'] ?? [];
      for (final c in cookies) {
        final m = RegExp(r'chat_monitor_token=([^;]+)').firstMatch(c);
        if (m != null) {
          token = m.group(1);
          return;
        }
      }
      throw ApiException('登录响应异常：未获取到凭证');
    } on DioException catch (e) {
      final code = e.response?.statusCode;
      String msg = '网络错误，请检查服务器地址与网络';
      final d = e.response?.data;
      if (d is Map && d['error'] != null) msg = '${d['error']}';
      throw ApiException(msg, statusCode: code);
    }
  }

  Future<void> register(String username, String password,
          {String inviteCode = ''}) =>
      _req('POST', '/api/register', data: {
        'username': username,
        'password': password,
        'invite_code': inviteCode,
      });

  Future<Map<String, dynamic>> me() async =>
      Map<String, dynamic>.from(await _req('GET', '/api/me'));

  // ── 总览 ──
  Future<Map<String, PlatformOverview>> overview() async {
    final d = Map<String, dynamic>.from(await _req('GET', '/api/overview'));
    return d.map((k, v) => MapEntry(k, PlatformOverview.fromJson(v)));
  }

  // ── 消息 ──
  Future<List<String>> groups(String platform) async {
    final d = await _req('GET', '/api/groups', query: {'platform': platform});
    return (d['items'] as List).map((e) => '$e').toList();
  }

  Future<PageResult<ChatMessage>> messages(String platform,
      {String group = '', String q = '', int page = 1, int pageSize = 50, int sinceTs = 0}) async {
    final d = await _req('GET', '/api/messages', query: {
      'platform': platform,
      'group': group,
      'q': q,
      'page': page,
      'page_size': pageSize,
      if (sinceTs > 0) 'since_ts': sinceTs,
    });
    return PageResult(d['total'] ?? 0, d['page'] ?? 1,
        (d['items'] as List).map((e) => ChatMessage.fromJson(e)).toList());
  }

  // ── 提醒 ──
  Future<PageResult<AlertItem>> alerts(
      {String platform = '', bool unread = false, int page = 1, int pageSize = 50}) async {
    final d = await _req('GET', '/api/alerts', query: {
      if (platform.isNotEmpty) 'platform': platform,
      'unread': unread,
      'page': page,
      'page_size': pageSize,
    });
    return PageResult(d['total'] ?? 0, d['page'] ?? 1,
        (d['items'] as List).map((e) => AlertItem.fromJson(e)).toList());
  }

  Future<void> markAlertsRead({List<int>? ids, String platform = ''}) =>
      _req('POST', '/api/alerts/read',
          data: {'ids': ?ids, 'platform': platform});

  // ── 报告 ──
  Future<List<ReportItem>> reports({String platform = ''}) async {
    final d = await _req('GET', '/api/reports',
        query: {if (platform.isNotEmpty) 'platform': platform});
    return (d['items'] as List).map((e) => ReportItem.fromJson(e)).toList();
  }

  Uri reportHtmlUri(String platform, String date) =>
      _u('/api/reports/$platform/$date/html');

  Uri reportDocxUri(String platform, String date) =>
      _u('/api/reports/$platform/$date/docx');

  // ── 文件库 ──
  Future<PageResult<FileItem>> files(
      {String platform = '', String category = '', bool important = false,
       String q = '', int page = 1, int pageSize = 50}) async {
    final d = await _req('GET', '/api/files', query: {
      if (platform.isNotEmpty) 'platform': platform,
      if (category.isNotEmpty) 'category': category,
      if (important) 'important': '1',
      'q': q,
      'page': page,
      'page_size': pageSize,
    });
    return PageResult(d['total'] ?? 0, d['page'] ?? 1,
        (d['items'] as List).map((e) => FileItem.fromJson(e)).toList());
  }

  Future<List<String>> fileCategories() async {
    final d = await _req('GET', '/api/files/categories');
    return (d['items'] as List).map((e) => '$e').toList();
  }

  Uri fileRawUri(String platform, int fid) => _u('/api/files/$platform/$fid/raw');

  Uri mediaRawUri(String relPath) => _u('/api/media/raw', {'path': relPath});

  Future<void> setFileImportant(String platform, int fid, bool important) =>
      _req('POST', '/api/files/$platform/$fid/important',
          data: {'important': important});

  /// 下载到本地路径（docx/文件），返回保存路径。
  Future<String> download(Uri uri, String savePath) async {
    try {
      await _dio.downloadUri(uri, savePath);
      return savePath;
    } on DioException catch (e) {
      final code = e.response?.statusCode;
      if (code == 401) onUnauthorized?.call();
      throw ApiException('下载失败（${code ?? e.type.name}）', statusCode: code);
    }
  }

  // ── 平台控制 ──
  Future<void> platformCommand(String name, String cmd) =>
      _req('POST', '/api/platforms/$name/command', data: {'cmd': cmd});

  // ── 设置 ──
  Future<Map<String, dynamic>> settings() async =>
      Map<String, dynamic>.from(await _req('GET', '/api/settings'));

  Future<void> saveKeywords(Map<String, dynamic> categories) =>
      _req('POST', '/api/settings/keywords', data: {'categories': categories});

  Future<Map<String, dynamic>> getPlatformBinding(String name) async =>
      Map<String, dynamic>.from(
          await _req('GET', '/api/settings/platforms/$name'));

  Future<void> savePlatformBinding(String name, Map<String, dynamic> body) =>
      _req('POST', '/api/settings/platforms/$name', data: body);

  Future<Map<String, dynamic>> testPlatformBinding(
          String name, Map<String, dynamic> body) async =>
      Map<String, dynamic>.from(
          await _req('POST', '/api/settings/platforms/$name/test', data: body));

  Future<void> updateNickname(String nickname) =>
      _req('POST', '/api/me/nickname', data: {'nickname': nickname});

  Future<void> changePassword(String oldPassword, String newPassword) =>
      _req('POST', '/api/settings/password',
          data: {'old_password': oldPassword, 'password': newPassword});
}
