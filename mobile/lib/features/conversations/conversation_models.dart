class MessageMedia {
  const MessageMedia({
    required this.mediaType,
    required this.contentUrl,
    required this.title,
    required this.attribution,
  });

  final String mediaType;
  final String contentUrl;
  final String title;
  final String attribution;

  factory MessageMedia.fromJson(Map<String, dynamic> json) {
    return MessageMedia(
      mediaType: json['media_type'] as String,
      contentUrl: json['content_url'] as String,
      title: json['title'] as String,
      attribution: json['attribution'] as String,
    );
  }
}

class ConversationMessage {
  const ConversationMessage({
    required this.id,
    required this.role,
    required this.content,
    this.media = const [],
  });

  final String id;
  final String role;
  final String content;
  final List<MessageMedia> media;

  bool get isChild => role == 'child';

  factory ConversationMessage.fromJson(Map<String, dynamic> json) {
    return ConversationMessage(
      id: json['id'] as String,
      role: json['role'] as String,
      content: json['content'] as String,
      media: (json['media'] as List<dynamic>? ?? const [])
          .map((item) => MessageMedia.fromJson(item as Map<String, dynamic>))
          .toList(growable: false),
    );
  }
}

class ConversationHistory {
  const ConversationHistory({
    required this.conversationId,
    required this.messages,
    required this.isTruncated,
  });

  final String? conversationId;
  final List<ConversationMessage> messages;
  final bool isTruncated;
}
