/// 数据模型：与后端 API 的 JSON 结构一一对应。
library;

class ChatMessage {
  final String msgId;
  final String platform;
  final String groupName;
  final String sender;
  final String content;
  final String msgType;
  final List<String> mediaUrls;
  final int ts;

  ChatMessage.fromJson(Map<String, dynamic> j)
      : msgId = j['msg_id'] ?? '',
        platform = j['platform'] ?? '',
        groupName = j['group_name'] ?? '',
        sender = j['sender'] ?? '',
        content = j['content'] ?? '',
        msgType = j['msg_type'] ?? 'text',
        mediaUrls = (j['media_urls'] as List? ?? []).map((e) => '$e').toList(),
        ts = j['ts'] ?? 0;
}

class AlertItem {
  final int id;
  final String platform;
  final String content;
  final String reason;
  final String suggestion;
  final String priority; // high / medium / low
  final String sender;
  final String groupName;
  final int ts;
  final bool isRead;

  AlertItem.fromJson(Map<String, dynamic> j)
      : id = j['id'] ?? 0,
        platform = j['platform'] ?? '',
        content = j['content'] ?? '',
        reason = j['reason'] ?? '',
        suggestion = j['suggestion'] ?? '',
        priority = j['priority'] ?? 'low',
        sender = j['sender'] ?? '',
        groupName = j['group_name'] ?? '',
        ts = j['ts'] ?? 0,
        isRead = (j['is_read'] ?? 0) == 1;
}

class ReportItem {
  final int id;
  final String platform;
  final String date;
  final String summary;
  final int msgCount;
  final int importantCount;

  ReportItem.fromJson(Map<String, dynamic> j)
      : id = j['id'] ?? 0,
        platform = j['platform'] ?? '',
        date = j['date'] ?? '',
        summary = j['summary'] ?? '',
        msgCount = j['msg_count'] ?? 0,
        importantCount = j['important_count'] ?? 0;
}

class FileItem {
  final int id;
  final String platform;
  final String localPath;
  final String origName;
  final String ftype;
  final String ext;
  final int size;
  final bool important;
  final String aiDesc;
  final String category;
  final int ts;

  FileItem.fromJson(Map<String, dynamic> j)
      : id = j['id'] ?? 0,
        platform = j['platform'] ?? '',
        localPath = j['local_path'] ?? '',
        origName = j['orig_name'] ?? '',
        ftype = j['ftype'] ?? '',
        ext = j['ext'] ?? '',
        size = j['size'] ?? 0,
        important = (j['important'] ?? 0) == 1,
        aiDesc = j['ai_desc'] ?? '',
        category = j['category'] ?? '',
        ts = j['ts'] ?? 0;

  bool get isImage =>
      ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']
          .contains(ext.replaceAll('.', '').toLowerCase()) ||
      ftype == 'image';
}

class PlatformOverview {
  final int msgTotal;
  final int alertTotal;
  final int alertUnread;
  final ReportItem? lastReport;
  final bool running;
  final int todayMessages;

  PlatformOverview.fromJson(Map<String, dynamic> j)
      : msgTotal = j['msg_total'] ?? 0,
        alertTotal = j['alert_total'] ?? 0,
        alertUnread = j['alert_unread'] ?? 0,
        lastReport =
            j['last_report'] != null ? ReportItem.fromJson(j['last_report']) : null,
        running = j['running'] ?? false,
        todayMessages = j['today_messages'] ?? 0;
}

/// 分页响应
class PageResult<T> {
  final int total;
  final int page;
  final List<T> items;
  PageResult(this.total, this.page, this.items);
  bool get hasMore => items.length < total;
}
