class CalibrationPrompt {
  const CalibrationPrompt({
    required this.id,
    required this.kind,
    required this.phrase,
    required this.icon,
  });

  factory CalibrationPrompt.fromJson(Map<String, dynamic> json) {
    return CalibrationPrompt(
      id: json['id'] as String,
      kind: json['kind'] as String,
      phrase: json['phrase'] as String? ?? '',
      icon: json['icon'] as String? ?? '🎙️',
    );
  }

  final String id;
  final String kind;
  final String phrase;
  final String icon;

  bool get isSilence => kind == 'silence';
}

class ActiveCalibration {
  const ActiveCalibration({
    required this.active,
    required this.sessionId,
    required this.prompts,
    required this.collectedPromptIds,
  });

  factory ActiveCalibration.fromJson(Map<String, dynamic> json) {
    final rawPrompts = json['prompts'] as List<dynamic>? ?? const [];
    final rawCollected =
        json['collected_prompt_ids'] as List<dynamic>? ?? const [];
    return ActiveCalibration(
      active: json['active'] as bool? ?? false,
      sessionId: json['session_id'] as String?,
      prompts: rawPrompts
          .map(
            (item) => CalibrationPrompt.fromJson(item as Map<String, dynamic>),
          )
          .toList(growable: false),
      collectedPromptIds: rawCollected.cast<String>().toSet(),
    );
  }

  const ActiveCalibration.inactive()
    : active = false,
      sessionId = null,
      prompts = const [],
      collectedPromptIds = const {};

  final bool active;
  final String? sessionId;
  final List<CalibrationPrompt> prompts;
  final Set<String> collectedPromptIds;
}
