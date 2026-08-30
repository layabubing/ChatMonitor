import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../widgets/common.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _server = TextEditingController();
  final _user = TextEditingController();
  final _pass = TextEditingController();
  final _invite = TextEditingController();
  bool _registerMode = false;
  bool _busy = false;
  bool _obscure = true;

  @override
  void initState() {
    super.initState();
    _server.text = AppState.instance.baseUrl;
  }

  @override
  void dispose() {
    _server.dispose();
    _user.dispose();
    _pass.dispose();
    _invite.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final server = _server.text.trim();
    final user = _user.text.trim();
    final pass = _pass.text;
    if (server.isEmpty || user.isEmpty || pass.isEmpty) {
      showSnack(context, '请填写服务器地址、用户名和密码', error: true);
      return;
    }
    setState(() => _busy = true);
    try {
      if (_registerMode) {
        await AppState.instance
            .register(server, user, pass, inviteCode: _invite.text.trim());
        if (mounted) showSnack(context, '注册成功，请登录');
        setState(() => _registerMode = false);
      } else {
        await AppState.instance.login(server, user, pass);
      }
    } catch (e) {
      if (mounted) showSnack(context, '$e', error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(28),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(Icons.monitor_heart,
                      size: 64, color: Theme.of(context).colorScheme.primary),
                  const SizedBox(height: 12),
                  Text('ChatMonitor',
                      textAlign: TextAlign.center,
                      style: Theme.of(context)
                          .textTheme
                          .headlineMedium
                          ?.copyWith(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text('群聊监控 · 重要提醒 · 每日报告',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey.shade600)),
                  const SizedBox(height: 32),
                  TextField(
                    controller: _server,
                    keyboardType: TextInputType.url,
                    decoration: const InputDecoration(
                      labelText: '服务器地址',
                      hintText: 'https://your-domain 或 http://192.168.x.x:8001',
                      prefixIcon: Icon(Icons.dns_outlined),
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 14),
                  TextField(
                    controller: _user,
                    decoration: const InputDecoration(
                      labelText: '用户名',
                      prefixIcon: Icon(Icons.person_outline),
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 14),
                  TextField(
                    controller: _pass,
                    obscureText: _obscure,
                    onSubmitted: (_) => _submit(),
                    decoration: InputDecoration(
                      labelText: '密码',
                      prefixIcon: const Icon(Icons.lock_outline),
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        icon: Icon(
                            _obscure ? Icons.visibility_off : Icons.visibility),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                  ),
                  if (_registerMode) ...[
                    const SizedBox(height: 14),
                    TextField(
                      controller: _invite,
                      decoration: const InputDecoration(
                        labelText: '邀请码（如服务器未设置可留空）',
                        prefixIcon: Icon(Icons.card_giftcard),
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ],
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: _busy ? null : _submit,
                    style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 14)),
                    child: _busy
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : Text(_registerMode ? '注册' : '登录'),
                  ),
                  TextButton(
                    onPressed: () =>
                        setState(() => _registerMode = !_registerMode),
                    child: Text(_registerMode ? '已有账号？去登录' : '没有账号？注册'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
