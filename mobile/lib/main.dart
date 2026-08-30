import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import 'pages/home_page.dart';
import 'pages/login_page.dart';
import 'service/keepalive.dart';
import 'state/app_state.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // 前台服务 UI↔Task 通信端口
  FlutterForegroundTask.initCommunicationPort();
  KeepaliveService.init();
  await NotifyHelper.init(onTap: (payload) {
    if (payload == 'alerts') AppState.instance.setTab(2);
  });
  await AppState.instance.init();
  // 已登录：确保保活服务与兜底轮询在运行
  if (AppState.instance.loggedIn) {
    await KeepaliveService.start();
    await KeepaliveService.registerPolling();
  }
  runApp(const ChatMonitorApp());
}

class ChatMonitorApp extends StatelessWidget {
  const ChatMonitorApp({super.key});

  @override
  Widget build(BuildContext context) {
    const seed = Color(0xFF1E88E5);
    return MaterialApp(
      title: 'ChatMonitor',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: seed),
        useMaterial3: true,
      ),
      darkTheme: ThemeData(
        colorScheme:
            ColorScheme.fromSeed(seedColor: seed, brightness: Brightness.dark),
        useMaterial3: true,
      ),
      home: ListenableBuilder(
        listenable: AppState.instance,
        builder: (context, _) {
          if (!AppState.instance.ready) {
            return const Scaffold(
                body: Center(child: CircularProgressIndicator()));
          }
          final child = AppState.instance.loggedIn
              ? const HomePage()
              : const LoginPage();
          // 服务运行时按返回键最小化而不是退出
          return WithForegroundTask(child: child);
        },
      ),
    );
  }
}
