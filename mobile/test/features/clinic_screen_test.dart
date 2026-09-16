import 'package:family_ai_mobile/features/clinic/clinic_gateway.dart';
import 'package:family_ai_mobile/features/clinic/clinic_models.dart';
import 'package:family_ai_mobile/features/clinic/clinic_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('clinic is usable through visual patient and action buttons', (
    tester,
  ) async {
    final gateway = _ClinicGatewayFake();
    await tester.pumpWidget(
      MaterialApp(
        home: ClinicScreen(gateway: gateway, conversationId: 'conversation-1'),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Палата Доктора Пульса'), findsOneWidget);
    await tester.tap(find.byKey(const Key('clinic-case-teddy_after_walk')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Мишка Топа'), findsOneWidget);
    expect(find.text('88 уд/мин'), findsOneWidget);
    expect(tester.takeException(), isNull);

    final waterAction = find.byKey(const Key('clinic-action-give_water'));
    await tester.drag(find.byType(ListView), const Offset(0, -260));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(waterAction);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Мишка попил воды.'), findsOneWidget);
  });
}

class _ClinicGatewayFake implements ClinicGateway {
  ClinicSession? state;

  @override
  Future<List<ClinicCaseSummary>> getClinicCases() async => const [
    ClinicCaseSummary(
      id: 'teddy_after_walk',
      title: 'Осмотр после прогулки',
      shortTitle: 'Мишка устал',
      description: 'Поможем мишке',
      patientName: 'Мишка Топа',
      patientIcon: '🧸',
      color: '#45B7A8',
    ),
  ];

  @override
  Future<ClinicSession?> getClinicState(String conversationId) async => state;

  @override
  Future<ClinicTurnResult> startClinicCase(
    String conversationId,
    String caseId,
  ) async {
    state = _session(completed: false);
    return ClinicTurnResult(
      session: state!,
      messageId: 'message-1',
      message: 'Послушаем мишку.',
    );
  }

  @override
  Future<ClinicTurnResult> performClinicAction(
    String conversationId,
    String actionId,
  ) async {
    state = _session(completed: true);
    return ClinicTurnResult(
      session: state!,
      messageId: 'message-2',
      message: 'Мишка попил воды.',
    );
  }

  @override
  Future<ClinicSession> transitionClinic(
    String conversationId,
    String transition,
  ) async => state!;
}

ClinicSession _session({required bool completed}) => ClinicSession(
  id: 'session-1',
  caseId: 'teddy_after_walk',
  title: 'Осмотр после прогулки',
  patientName: 'Мишка Топа',
  patientIcon: '🧸',
  color: '#45B7A8',
  status: completed ? 'completed' : 'active',
  vitals: const [
    ClinicVital(
      id: 'heart',
      icon: '💚',
      label: 'Сердце',
      value: '88',
      unit: 'уд/мин',
      state: 'calm',
    ),
  ],
  actions: [
    ClinicAction(
      id: 'give_water',
      icon: '🥤',
      label: 'Дать воду',
      completed: completed,
    ),
  ],
);
