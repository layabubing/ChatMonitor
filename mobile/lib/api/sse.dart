/// SSE 客户端：基于 Dio 流式响应解析 EventSource 帧，支持自动重连（指数退避）。
library;

import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

class SseEvent {
  final String event;
  final Map<String, dynamic> data;
  SseEvent(this.event, this.data);
}

class SseClient {
  final Dio _dio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: Duration.zero, // 长连接不做接收超时
  ));

  StreamSubscription? _sub;
  CancelToken? _cancel;
  Timer? _reconnectTimer;
  int _retry = 0;
  bool _disposed = false;

  final String url;
  final Map<String, String> headers;
  final void Function(SseEvent) onEvent;
  final void Function(bool connected)? onStateChange;

  SseClient({
    required this.url,
    required this.headers,
    required this.onEvent,
    this.onStateChange,
  });

  bool get isConnected => _sub != null;

  Future<void> connect() async {
    if (_disposed) return;
    _reconnectTimer?.cancel();
    await _closeStream();
    try {
      final cancel = CancelToken();
      final resp = await _dio.get<ResponseBody>(
        url,
        cancelToken: cancel,
        options: Options(
          responseType: ResponseType.stream,
          headers: {...headers, 'Accept': 'text/event-stream', 'Cache-Control': 'no-cache'},
        ),
      );
      _cancel = cancel;
      _retry = 0;
      onStateChange?.call(true);
      String buffer = '';
      String eventName = '';
      final dataLines = <String>[];
      _sub = resp.data!.stream.listen(
        (chunk) {
          buffer += utf8.decode(chunk, allowMalformed: true);
          // SSE 以 \n 分行，空行表示一帧结束
          while (buffer.contains('\n')) {
            final idx = buffer.indexOf('\n');
            final line = buffer.substring(0, idx).trimRight();
            buffer = buffer.substring(idx + 1);
            if (line.isEmpty) {
              if (dataLines.isNotEmpty) {
                _dispatch(eventName.isEmpty ? 'message' : eventName,
                    dataLines.join('\n'));
              }
              eventName = '';
              dataLines.clear();
            } else if (line.startsWith(':')) {
              // 保活注释，忽略
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
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _dispatch(String event, String raw) {
    Map<String, dynamic> data = {};
    try {
      final d = jsonDecode(raw);
      if (d is Map<String, dynamic>) data = d;
    } catch (_) {}
    onEvent(SseEvent(event, data));
  }

  void _scheduleReconnect() {
    if (_disposed) return;
    _closeStream();
    onStateChange?.call(false);
    _retry = (_retry + 1).clamp(1, 6);
    final delay = Duration(seconds: 2 * (1 << (_retry - 1))); // 2,4,8,16,32,64
    _reconnectTimer = Timer(delay, connect);
  }

  Future<void> _closeStream() async {
    await _sub?.cancel();
    _sub = null;
    _cancel?.cancel();
    _cancel = null;
  }

  Future<void> dispose() async {
    _disposed = true;
    _reconnectTimer?.cancel();
    await _closeStream();
  }
}
