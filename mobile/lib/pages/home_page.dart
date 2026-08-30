import 'package:flutter/material.dart';

import '../state/app_state.dart';
import 'alerts_page.dart';
import 'files_page.dart';
import 'messages_page.dart';
import 'overview_page.dart';
import 'reports_page.dart';
import 'settings_page.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  static const _titles = ['总览', '消息', '提醒', '报告', '文件库', '设置'];
  static const _pages = [
    OverviewPage(),
    MessagesPage(),
    AlertsPage(),
    ReportsPage(),
    FilesPage(),
    SettingsPage(),
  ];

  @override
  Widget build(BuildContext context) {
    final app = AppState.instance;
    return ListenableBuilder(
      listenable: app,
      builder: (context, _) {
        final tab = app.currentTab;
        final sseLabel = switch (app.sseState) {
          SseState.online => '实时连接中',
          SseState.connecting => '连接中…',
          _ => '轮询模式',
        };
        return Scaffold(
          appBar: AppBar(
            title: Text(_titles[tab]),
            actions: [
              Padding(
                padding: const EdgeInsets.only(right: 16),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(Icons.circle,
                      size: 8,
                      color: app.sseState == SseState.online
                          ? Colors.green
                          : Colors.orange),
                  const SizedBox(width: 4),
                  Text(sseLabel, style: const TextStyle(fontSize: 12)),
                ]),
              ),
            ],
          ),
          body: IndexedStack(index: tab, children: _pages),
          bottomNavigationBar: NavigationBar(
            selectedIndex: tab,
            onDestinationSelected: app.setTab,
            labelBehavior: NavigationDestinationLabelBehavior.onlyShowSelected,
            destinations: [
              const NavigationDestination(
                  icon: Icon(Icons.dashboard_outlined),
                  selectedIcon: Icon(Icons.dashboard),
                  label: '总览'),
              const NavigationDestination(
                  icon: Icon(Icons.chat_bubble_outline),
                  selectedIcon: Icon(Icons.chat_bubble),
                  label: '消息'),
              NavigationDestination(
                  icon: Badge(
                    isLabelVisible: app.unreadTotal > 0,
                    label: Text('${app.unreadTotal}'),
                    child: const Icon(Icons.notifications_outlined),
                  ),
                  selectedIcon: Badge(
                    isLabelVisible: app.unreadTotal > 0,
                    label: Text('${app.unreadTotal}'),
                    child: const Icon(Icons.notifications),
                  ),
                  label: '提醒'),
              const NavigationDestination(
                  icon: Icon(Icons.description_outlined),
                  selectedIcon: Icon(Icons.description),
                  label: '报告'),
              const NavigationDestination(
                  icon: Icon(Icons.folder_outlined),
                  selectedIcon: Icon(Icons.folder),
                  label: '文件库'),
              const NavigationDestination(
                  icon: Icon(Icons.settings_outlined),
                  selectedIcon: Icon(Icons.settings),
                  label: '设置'),
            ],
          ),
        );
      },
    );
  }
}
