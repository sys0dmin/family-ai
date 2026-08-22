import 'conversation_models.dart';

class ActivitySummary {
  const ActivitySummary({
    required this.id,
    required this.title,
    required this.shortTitle,
    required this.description,
    required this.icon,
    required this.color,
    required this.totalSteps,
  });

  final String id;
  final String title;
  final String shortTitle;
  final String description;
  final String icon;
  final String color;
  final int totalSteps;

  factory ActivitySummary.fromJson(Map<String, dynamic> json) {
    return ActivitySummary(
      id: json['id'] as String,
      title: json['title'] as String,
      shortTitle: json['short_title'] as String,
      description: json['description'] as String,
      icon: json['icon'] as String,
      color: json['color'] as String,
      totalSteps: json['total_steps'] as int,
    );
  }
}

class ActivitySession {
  const ActivitySession({
    required this.id,
    required this.activityId,
    required this.title,
    required this.icon,
    required this.color,
    required this.status,
    required this.currentStep,
    required this.totalSteps,
    this.currentStepTitle,
    this.currentStepIcon,
    this.completionSummary,
  });

  final String id;
  final String activityId;
  final String title;
  final String icon;
  final String color;
  final String status;
  final int currentStep;
  final int totalSteps;
  final String? currentStepTitle;
  final String? currentStepIcon;
  final String? completionSummary;

  bool get isActive => status == 'active';
  bool get isPaused => status == 'paused';
  bool get isInProgress => isActive || isPaused;

  factory ActivitySession.fromJson(Map<String, dynamic> json) {
    return ActivitySession(
      id: json['id'] as String,
      activityId: json['activity_id'] as String,
      title: json['title'] as String,
      icon: json['icon'] as String,
      color: json['color'] as String,
      status: json['status'] as String,
      currentStep: json['current_step'] as int,
      totalSteps: json['total_steps'] as int,
      currentStepTitle: json['current_step_title'] as String?,
      currentStepIcon: json['current_step_icon'] as String?,
      completionSummary: json['completion_summary'] as String?,
    );
  }
}

class ActivityActionResult {
  const ActivityActionResult({required this.session, required this.message});

  final ActivitySession session;
  final ConversationMessage message;
}
