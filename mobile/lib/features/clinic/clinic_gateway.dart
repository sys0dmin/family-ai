import 'clinic_models.dart';

abstract interface class ClinicGateway {
  Future<List<ClinicCaseSummary>> getClinicCases();

  Future<ClinicSession?> getClinicState(String conversationId);

  Future<ClinicTurnResult> startClinicCase(
    String conversationId,
    String caseId,
  );

  Future<ClinicTurnResult> performClinicAction(
    String conversationId,
    String actionId,
  );

  Future<ClinicSession> transitionClinic(
    String conversationId,
    String transition,
  );
}
