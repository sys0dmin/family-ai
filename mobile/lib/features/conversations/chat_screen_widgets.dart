part of 'chat_screen.dart';

class _ActivityLaunchButton extends StatelessWidget {
  const _ActivityLaunchButton({required this.enabled, required this.onPressed});

  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(14, 10, 14, 0),
    child: Semantics(
      button: true,
      label: 'Выбрать приключение или занятие',
      child: FilledButton.tonalIcon(
        key: const Key('activity-launch'),
        onPressed: enabled ? onPressed : null,
        icon: const Text('✨', style: TextStyle(fontSize: 28)),
        label: const Text(
          'Приключение',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
        ),
        style: FilledButton.styleFrom(
          minimumSize: const Size(double.infinity, 58),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
          ),
        ),
      ),
    ),
  );
}

class _ActiveActivityCard extends StatelessWidget {
  const _ActiveActivityCard({
    required this.session,
    required this.enabled,
    required this.onStop,
    required this.onLeave,
    required this.onResume,
  });

  final ActivitySession session;
  final bool enabled;
  final VoidCallback onStop;
  final VoidCallback onLeave;
  final VoidCallback onResume;

  @override
  Widget build(BuildContext context) {
    final progress = session.totalSteps == 0
        ? 0.0
        : session.currentStep / session.totalSteps;
    return Container(
      key: const Key('active-activity'),
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF3D2),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        children: [
          Text(
            session.currentStepIcon ?? session.icon,
            style: const TextStyle(fontSize: 34),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  session.currentStepTitle ?? session.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 6),
                LinearProgressIndicator(
                  value: progress.clamp(0, 1),
                  borderRadius: BorderRadius.circular(8),
                ),
              ],
            ),
          ),
          IconButton.filledTonal(
            onPressed: enabled ? onLeave : null,
            tooltip: 'Просто поговорить',
            icon: const Icon(Icons.chat_bubble_outline_rounded),
          ),
          if (session.isPaused)
            IconButton.filled(
              key: const Key('activity-resume'),
              onPressed: enabled ? onResume : null,
              tooltip: 'Продолжить приключение',
              icon: const Icon(Icons.play_arrow_rounded),
            )
          else
            IconButton.filledTonal(
              onPressed: enabled ? onStop : null,
              tooltip: 'Остановить приключение',
              icon: const Icon(Icons.stop_rounded),
            ),
        ],
      ),
    );
  }
}

class _ActivityPicker extends StatelessWidget {
  const _ActivityPicker({required this.activities});

  final List<ActivitySummary> activities;

  @override
  Widget build(BuildContext context) => SafeArea(
    child: Padding(
      padding: const EdgeInsets.fromLTRB(18, 4, 18, 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'Куда отправимся?',
            style: Theme.of(
              context,
            ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 14),
          ConstrainedBox(
            constraints: BoxConstraints(
              maxHeight: MediaQuery.sizeOf(context).height * 0.65,
            ),
            child: GridView.builder(
              shrinkWrap: true,
              gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                maxCrossAxisExtent: 220,
                mainAxisExtent: 190,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
              ),
              itemCount: activities.length,
              itemBuilder: (context, index) {
                final activity = activities[index];
                return Semantics(
                  button: true,
                  label: activity.title,
                  child: InkWell(
                    key: Key('activity-${activity.id}'),
                    onTap: () => Navigator.pop(context, activity),
                    borderRadius: BorderRadius.circular(24),
                    child: Ink(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF3F0FF),
                        borderRadius: BorderRadius.circular(24),
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            activity.icon,
                            style: const TextStyle(fontSize: 62),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            activity.shortTitle,
                            maxLines: 2,
                            textAlign: TextAlign.center,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    ),
  );
}

class _PendingPhotoPreview extends StatelessWidget {
  const _PendingPhotoPreview({required this.bytes});

  final Uint8List bytes;

  @override
  Widget build(BuildContext context) => Container(
    key: const Key('pending-photo-preview'),
    height: 112,
    width: double.infinity,
    padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
    color: const Color(0xFFFFFDF8),
    child: ClipRRect(
      borderRadius: BorderRadius.circular(18),
      child: Image.memory(bytes, fit: BoxFit.cover),
    ),
  );
}

class _PhotoSourceSheet extends StatelessWidget {
  const _PhotoSourceSheet();

  @override
  Widget build(BuildContext context) => SafeArea(
    child: Padding(
      padding: const EdgeInsets.fromLTRB(20, 6, 20, 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'Что покажем?',
            style: Theme.of(
              context,
            ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              Expanded(
                child: _PhotoSourceButton(
                  key: const Key('photo-source-camera'),
                  icon: Icons.photo_camera_rounded,
                  label: 'Камера',
                  color: const Color(0xFF327BB5),
                  onTap: () => Navigator.pop(context, PhotoSource.camera),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: _PhotoSourceButton(
                  key: const Key('photo-source-gallery'),
                  icon: Icons.photo_library_rounded,
                  label: 'Галерея',
                  color: const Color(0xFF5A8F62),
                  onTap: () => Navigator.pop(context, PhotoSource.gallery),
                ),
              ),
            ],
          ),
        ],
      ),
    ),
  );
}

class _PhotoSourceButton extends StatelessWidget {
  const _PhotoSourceButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
    super.key,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: label,
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(24),
      child: Ink(
        height: 138,
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.14),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: color.withValues(alpha: 0.35), width: 2),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 64, color: color),
            const SizedBox(height: 8),
            Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: 18,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
      ),
    ),
  );
}
