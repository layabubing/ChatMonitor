/// 公共组件与工具：时间格式化、平台/优先级展示、空态/加载态。
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

String fmtTs(int ms, {String pattern = 'MM-dd HH:mm'}) {
  if (ms <= 0) return '';
  return DateFormat(pattern).format(DateTime.fromMillisecondsSinceEpoch(ms));
}

String platformLabel(String p) => p == 'qq' ? 'QQ' : '钉钉';

Color platformColor(String p) =>
    p == 'qq' ? const Color(0xFF12B7F5) : const Color(0xFF1E88E5);

Color priorityColor(String p) => switch (p) {
      'high' => const Color(0xFFE53935),
      'medium' => const Color(0xFFFB8C00),
      _ => const Color(0xFF43A047),
    };

String priorityLabel(String p) => switch (p) {
      'high' => '高',
      'medium' => '中',
      _ => '低',
    };

class PlatformBadge extends StatelessWidget {
  final String platform;
  const PlatformBadge(this.platform, {super.key});

  @override
  Widget build(BuildContext context) {
    final c = platformColor(platform);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: c.withValues(alpha: 0.4)),
      ),
      child: Text(platformLabel(platform),
          style: TextStyle(color: c, fontSize: 11, fontWeight: FontWeight.w600)),
    );
  }
}

class PriorityBadge extends StatelessWidget {
  final String priority;
  const PriorityBadge(this.priority, {super.key});

  @override
  Widget build(BuildContext context) {
    final c = priorityColor(priority);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(4)),
      child: Text(priorityLabel(priority),
          style: const TextStyle(
              color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600)),
    );
  }
}

class EmptyView extends StatelessWidget {
  final String text;
  final IconData icon;
  const EmptyView(this.text, {super.key, this.icon = Icons.inbox_outlined});

  @override
  Widget build(BuildContext context) => Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 56, color: Colors.grey.shade400),
          const SizedBox(height: 12),
          Text(text, style: TextStyle(color: Colors.grey.shade500)),
        ]),
      );
}

class ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const ErrorView(this.message, {super.key, required this.onRetry});

  @override
  Widget build(BuildContext context) => Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.cloud_off, size: 56, color: Colors.grey.shade400),
          const SizedBox(height: 12),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Text(message,
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey.shade600)),
          ),
          const SizedBox(height: 12),
          FilledButton.tonal(onPressed: onRetry, child: const Text('重试')),
        ]),
      );
}

/// 加载更多列表底部指示器
class LoadMoreFooter extends StatelessWidget {
  final bool loading;
  final bool hasMore;
  const LoadMoreFooter({super.key, required this.loading, required this.hasMore});

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: SizedBox(
            width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))),
      );
    }
    if (!hasMore) {
      return Padding(
        padding: const EdgeInsets.all(16),
        child: Center(
            child: Text('— 没有更多了 —',
                style: TextStyle(color: Colors.grey.shade400, fontSize: 12))),
      );
    }
    return const SizedBox.shrink();
  }
}

void showSnack(BuildContext context, String msg, {bool error = false}) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    content: Text(msg),
    backgroundColor: error ? Colors.red.shade400 : null,
    behavior: SnackBarBehavior.floating,
  ));
}
