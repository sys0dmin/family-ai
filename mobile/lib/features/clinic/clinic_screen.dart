import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'clinic_gateway.dart';
import 'clinic_models.dart';

IconData _patientIcon(String caseId) => switch (caseId) {
  'robot_checkup' => Icons.smart_toy_rounded,
  'fox_after_procedure' => Icons.cruelty_free_rounded,
  _ => Icons.pets_rounded,
};

IconData _vitalIcon(String id) => switch (id) {
  'heart' || 'pulse' => Icons.favorite_rounded,
  'pressure' => Icons.monitor_heart_rounded,
  'temperature' => Icons.device_thermostat_rounded,
  'breathing' => Icons.air_rounded,
  _ => Icons.monitor_heart_rounded,
};

IconData _actionIcon(String id) => switch (id) {
  'listen_heart' => Icons.hearing_rounded,
  'give_water' => Icons.local_drink_rounded,
  'feed' => Icons.restaurant_rounded,
  'rest' => Icons.bedtime_rounded,
  'measure_temperature' => Icons.device_thermostat_rounded,
  'measure_pressure' => Icons.monitor_heart_rounded,
  'give_blanket' => Icons.bed_rounded,
  'call_senior' => Icons.support_agent_rounded,
  'mark_injection' => Icons.task_alt_rounded,
  'mark_iv' => Icons.fact_check_rounded,
  _ => Icons.check_circle_outline_rounded,
};

class ClinicScreen extends StatefulWidget {
  const ClinicScreen({
    required this.gateway,
    required this.conversationId,
    this.onSpeak,
    super.key,
  });

  final ClinicGateway gateway;
  final String conversationId;
  final Future<void> Function(String messageId, String text)? onSpeak;

  @override
  State<ClinicScreen> createState() => _ClinicScreenState();
}

class _ClinicScreenState extends State<ClinicScreen> {
  List<ClinicCaseSummary> _cases = const [];
  ClinicSession? _session;
  String? _message;
  String? _error;
  bool _loading = true;
  bool _busy = false;
  bool _soundEnabled = false;
  Timer? _heartbeat;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _heartbeat?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final results = await Future.wait<Object?>([
        widget.gateway.getClinicCases(),
        widget.gateway.getClinicState(widget.conversationId),
      ]);
      if (!mounted) return;
      setState(() {
        _cases = results[0]! as List<ClinicCaseSummary>;
        _session = results[1] as ClinicSession?;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = 'Кабинет пока не открылся. Попробуй ещё раз.';
        _loading = false;
      });
    }
  }

  Future<void> _run(Future<ClinicTurnResult> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await action();
      if (!mounted) return;
      setState(() {
        _session = result.session;
        _message = result.message;
      });
      await widget.onSpeak?.call(result.messageId, result.message);
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Не получилось. Давай нажмём ещё раз.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _transition(String transition) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final session = await widget.gateway.transitionClinic(
        widget.conversationId,
        transition,
      );
      if (!mounted) return;
      setState(() {
        _session = transition == 'leave' ? null : session;
        _message = null;
      });
    } catch (_) {
      if (mounted) setState(() => _error = 'Не получилось изменить игру.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _toggleSound() {
    setState(() => _soundEnabled = !_soundEnabled);
    _heartbeat?.cancel();
    if (_soundEnabled) {
      SystemSound.play(SystemSoundType.click);
      _heartbeat = Timer.periodic(
        const Duration(milliseconds: 1300),
        (_) => SystemSound.play(SystemSoundType.click),
      );
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: const Color(0xFFF5FCFB),
    appBar: AppBar(
      backgroundColor: const Color(0xFFDDF7F2),
      title: const Text(
        'Доктор Пульс',
        style: TextStyle(fontWeight: FontWeight.w900),
      ),
      actions: [
        IconButton(
          onPressed: _toggleSound,
          tooltip: _soundEnabled ? 'Выключить звук' : 'Включить звук',
          icon: Icon(
            _soundEnabled ? Icons.volume_up_rounded : Icons.volume_off_rounded,
          ),
        ),
      ],
    ),
    body: SafeArea(
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : _session == null
          ? _CasePicker(
              cases: _cases,
              enabled: !_busy,
              error: _error,
              onSelected: (caseId) => _run(
                () => widget.gateway.startClinicCase(
                  widget.conversationId,
                  caseId,
                ),
              ),
            )
          : _ClinicRoom(
              session: _session!,
              message: _message,
              error: _error,
              enabled: !_busy,
              onAction: (actionId) => _run(
                () => widget.gateway.performClinicAction(
                  widget.conversationId,
                  actionId,
                ),
              ),
              onPause: () =>
                  _transition(_session!.isPaused ? 'resume' : 'pause'),
              onLeave: () => _transition('leave'),
            ),
    ),
  );
}

class _CasePicker extends StatelessWidget {
  const _CasePicker({
    required this.cases,
    required this.enabled,
    required this.error,
    required this.onSelected,
  });

  final List<ClinicCaseSummary> cases;
  final bool enabled;
  final String? error;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(18),
    children: [
      const Text(
        'Палата Доктора Пульса',
        textAlign: TextAlign.center,
        style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900),
      ),
      const SizedBox(height: 6),
      const Text(
        'Позаботимся о наших пациентах',
        textAlign: TextAlign.center,
        style: TextStyle(fontSize: 15),
      ),
      if (error != null) ...[
        const SizedBox(height: 12),
        Text(error!, textAlign: TextAlign.center),
      ],
      const SizedBox(height: 18),
      for (final item in cases)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: FilledButton.tonal(
            key: Key('clinic-case-${item.id}'),
            onPressed: enabled ? () => onSelected(item.id) : null,
            style: FilledButton.styleFrom(
              padding: const EdgeInsets.all(18),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(24),
              ),
            ),
            child: Row(
              children: [
                Icon(_patientIcon(item.id), size: 48),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.shortTitle,
                        style: const TextStyle(
                          fontSize: 19,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      Text(item.patientName),
                    ],
                  ),
                ),
                const Icon(Icons.play_arrow_rounded, size: 34),
              ],
            ),
          ),
        ),
    ],
  );
}

class _ClinicRoom extends StatelessWidget {
  const _ClinicRoom({
    required this.session,
    required this.message,
    required this.error,
    required this.enabled,
    required this.onAction,
    required this.onPause,
    required this.onLeave,
  });

  final ClinicSession session;
  final String? message;
  final String? error;
  final bool enabled;
  final ValueChanged<String> onAction;
  final VoidCallback onPause;
  final VoidCallback onLeave;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(14),
    children: [
      Card(
        color: const Color(0xFF10282C),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            children: [
              Row(
                children: [
                  Icon(
                    _patientIcon(session.caseId),
                    size: 54,
                    color: const Color(0xFF59F0B5),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          session.patientName,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 23,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        Text(
                          session.isCompleted ? 'Всё готово!' : session.title,
                          style: const TextStyle(color: Color(0xFFA8D8D2)),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: enabled ? onPause : null,
                    color: Colors.white,
                    tooltip: session.isPaused ? 'Продолжить' : 'Пауза',
                    icon: Icon(
                      session.isPaused
                          ? Icons.play_arrow_rounded
                          : Icons.pause_rounded,
                    ),
                  ),
                  IconButton(
                    onPressed: enabled ? onLeave : null,
                    color: Colors.white,
                    tooltip: 'Закрыть карточку',
                    icon: const Icon(Icons.close_rounded),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              const _PulseLine(),
              const SizedBox(height: 10),
              GridView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  childAspectRatio: 2.25,
                  crossAxisSpacing: 8,
                  mainAxisSpacing: 8,
                ),
                itemCount: session.vitals.length,
                itemBuilder: (context, index) {
                  final vital = session.vitals[index];
                  return DecoratedBox(
                    decoration: BoxDecoration(
                      color: const Color(0xFF19393D),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 10),
                      child: Row(
                        children: [
                          Icon(
                            _vitalIcon(vital.id),
                            size: 24,
                            color: const Color(0xFF59F0B5),
                          ),
                          const SizedBox(width: 7),
                          Expanded(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  vital.label,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    color: Color(0xFFA8D8D2),
                                    fontSize: 11,
                                  ),
                                ),
                                Text(
                                  '${vital.value} ${vital.unit}',
                                  maxLines: 1,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w900,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ],
          ),
        ),
      ),
      if (message != null) ...[
        const SizedBox(height: 10),
        Card(
          color: const Color(0xFFE2F7F2),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Text(message!, style: const TextStyle(fontSize: 16)),
          ),
        ),
      ],
      if (error != null) Text(error!, textAlign: TextAlign.center),
      const SizedBox(height: 10),
      GridView.builder(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
          maxCrossAxisExtent: 210,
          mainAxisExtent: 112,
          crossAxisSpacing: 10,
          mainAxisSpacing: 10,
        ),
        itemCount: session.actions.length,
        itemBuilder: (context, index) {
          final action = session.actions[index];
          return FilledButton.tonal(
            key: Key('clinic-action-${action.id}'),
            onPressed:
                enabled &&
                    !session.isPaused &&
                    !session.isCompleted &&
                    !action.completed
                ? () => onAction(action.id)
                : null,
            style: FilledButton.styleFrom(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(22),
              ),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  action.completed
                      ? Icons.check_circle_rounded
                      : _actionIcon(action.id),
                  size: 34,
                  color: action.completed ? const Color(0xFF168675) : null,
                ),
                const SizedBox(height: 5),
                Text(
                  action.label,
                  maxLines: 2,
                  textAlign: TextAlign.center,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
              ],
            ),
          );
        },
      ),
      const SizedBox(height: 14),
      const Text(
        'Отмечай заботу в карточке пациента',
        textAlign: TextAlign.center,
        style: TextStyle(fontWeight: FontWeight.w700),
      ),
    ],
  );
}

class _PulseLine extends StatefulWidget {
  const _PulseLine();

  @override
  State<_PulseLine> createState() => _PulseLineState();
}

class _PulseLineState extends State<_PulseLine>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1300),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 42,
    width: double.infinity,
    child: AnimatedBuilder(
      animation: _controller,
      builder: (context, child) =>
          CustomPaint(painter: _PulsePainter(progress: _controller.value)),
    ),
  );
}

class _PulsePainter extends CustomPainter {
  const _PulsePainter({required this.progress});

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final grid = Paint()
      ..color = const Color(0xFF21494D)
      ..strokeWidth = 1;
    for (var x = 0.0; x < size.width; x += 18) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), grid);
    }
    final path = Path()..moveTo(0, size.height * 0.62);
    final shift = progress * 90;
    for (var x = 0.0; x <= size.width; x += 3) {
      final phase = (x + shift) % 90;
      var y = size.height * 0.62;
      if (phase > 35 && phase <= 43) y -= (phase - 35) * 2.2;
      if (phase > 43 && phase <= 51) y += (phase - 43) * 3.4 - 17.6;
      if (phase > 51 && phase <= 59) y -= (phase - 51) * 1.2 - 9.6;
      path.lineTo(x, y);
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = const Color(0xFF59F0B5)
        ..strokeWidth = 3
        ..style = PaintingStyle.stroke,
    );
  }

  @override
  bool shouldRepaint(_PulsePainter oldDelegate) =>
      progress != oldDelegate.progress;
}
