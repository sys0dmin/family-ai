class Agent {
  const Agent({
    required this.id,
    required this.displayName,
    required this.description,
    required this.icon,
    required this.color,
    required this.greeting,
    this.supportsImageUpload = false,
  });

  final String id;
  final String displayName;
  final String description;
  final String icon;
  final String color;
  final String greeting;
  final bool supportsImageUpload;

  factory Agent.fromJson(Map<String, dynamic> json) {
    return Agent(
      id: json['id'] as String,
      displayName: json['display_name'] as String,
      description: json['description'] as String,
      icon: json['icon'] as String,
      color: json['color'] as String,
      greeting: json['greeting'] as String,
      supportsImageUpload: json['supports_image_upload'] as bool? ?? false,
    );
  }
}
