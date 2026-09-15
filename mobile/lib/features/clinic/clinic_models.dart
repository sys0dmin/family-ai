class ClinicCaseSummary {
  const ClinicCaseSummary({
    required this.id,
    required this.title,
    required this.shortTitle,
    required this.description,
    required this.patientName,
    required this.patientIcon,
    required this.color,
    this.mood = 'спокойное',
    this.complaint = 'Хочет, чтобы о нём позаботились.',
  });

  factory ClinicCaseSummary.fromJson(Map<String, dynamic> json) =>
      ClinicCaseSummary(
        id: json['id'] as String,
        title: json['title'] as String,
        shortTitle: json['short_title'] as String,
        description: json['description'] as String,
        patientName: json['patient_name'] as String,
        patientIcon: json['patient_icon'] as String,
        color: json['color'] as String,
        mood: json['mood'] as String? ?? 'спокойное',
        complaint: json['complaint'] as String? ?? 'Хочет, чтобы о нём позаботились.',
      );

  final String id;
  final String title;
  final String shortTitle;
  final String description;
  final String patientName;
  final String patientIcon;
  final String color;
  final String mood;
  final String complaint;
}

class ClinicVital {
  const ClinicVital({
    required this.id,
    required this.icon,
    required this.label,
    required this.value,
    required this.unit,
    required this.state,
  });

  factory ClinicVital.fromJson(Map<String, dynamic> json) => ClinicVital(
    id: json['id'] as String,
    icon: json['icon'] as String,
    label: json['label'] as String,
    value: json['value'] as String,
    unit: json['unit'] as String,
    state: json['state'] as String,
  );

  final String id;
  final String icon;
  final String label;
  final String value;
  final String unit;
  final String state;
}

class ClinicAction {
  const ClinicAction({
    required this.id,
    required this.icon,
    required this.label,
    required this.completed,
  });

  factory ClinicAction.fromJson(Map<String, dynamic> json) => ClinicAction(
    id: json['id'] as String,
    icon: json['icon'] as String,
    label: json['label'] as String,
    completed: json['completed'] as bool,
  );

  final String id;
  final String icon;
  final String label;
  final bool completed;
}

class ClinicSession {
  const ClinicSession({
    required this.id,
    required this.caseId,
    required this.title,
    required this.patientName,
    required this.patientIcon,
    required this.color,
    this.mood = 'спокойное',
    this.complaint = 'Хочет, чтобы о нём позаботились.',
    required this.status,
    required this.vitals,
    required this.actions,
  });

  factory ClinicSession.fromJson(Map<String, dynamic> json) => ClinicSession(
    id: json['id'] as String,
    caseId: json['case_id'] as String,
    title: json['title'] as String,
    patientName: json['patient_name'] as String,
    patientIcon: json['patient_icon'] as String,
    color: json['color'] as String,
    mood: json['mood'] as String? ?? 'спокойное',
    complaint: json['complaint'] as String? ?? 'Хочет, чтобы о нём позаботились.',
    status: json['status'] as String,
    vitals: (json['vitals'] as List<dynamic>)
        .map((item) => ClinicVital.fromJson(item as Map<String, dynamic>))
        .toList(growable: false),
    actions: (json['actions'] as List<dynamic>)
        .map((item) => ClinicAction.fromJson(item as Map<String, dynamic>))
        .toList(growable: false),
  );

  final String id;
  final String caseId;
  final String title;
  final String patientName;
  final String patientIcon;
  final String color;
  final String mood;
  final String complaint;
  final String status;
  final List<ClinicVital> vitals;
  final List<ClinicAction> actions;

  bool get isPaused => status == 'paused';
  bool get isCompleted => status == 'completed';
}

class ClinicTurnResult {
  const ClinicTurnResult({
    required this.session,
    required this.messageId,
    required this.message,
  });

  final ClinicSession session;
  final String messageId;
  final String message;
}
