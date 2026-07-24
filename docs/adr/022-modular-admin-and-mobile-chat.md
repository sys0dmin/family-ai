# Modular Admin UI and Android chat controllers

## Status

Accepted

## Context

The protected Admin UI grew into one `panel.html` containing more than two
thousand lines of markup, CSS and JavaScript. A change to one screen could
accidentally affect unrelated screens and static behavior could not be tested
independently.

The Flutter chat screen also owned history loading, text turns, voice recording,
network orchestration, audio caching, playback and all widgets. Voice behavior
was represented by unrelated booleans, so adding cancellation or another state
made invalid combinations increasingly likely.

The deployment is a small home system. A JavaScript framework or a new Flutter
state-management dependency would add more lifecycle and build complexity than
the current product needs.

## Decision

Keep both clients dependency-light and split them by responsibility.

Admin:

- `panel.html` contains semantic markup only;
- FastAPI serves a local stylesheet and native ES modules under
  `/admin-assets`;
- API/session, DOM helpers and navigation are independent modules;
- screens with substantial state own small controllers, beginning with Safety
  Policy, history and infrastructure;
- no npm build, CDN or UI framework is introduced.

Android:

- `ConversationGateway` is the stable client-side port used by chat features;
- `ConversationController` owns history, text turns and conversation lifecycle;
- `VoiceChatController` owns recording, voice-turn state, caching, replay and
  cancellation;
- chat widgets are independent from orchestration;
- voice state is one enum: `idle`, `listening`, `understanding`, `thinking`,
  `speaking`, or `error`.

Cancellation increments an operation generation, stops recording or playback
and immediately returns the UI to idle. A response belonging to an older
generation is ignored and cannot update the screen or start playback.

The current one-shot HTTP endpoint cannot cancel STT/LLM/TTS work already
running on the server and cannot report exact intermediate boundaries.
Therefore cancellation is client-side, and the short `understanding` state
represents local audio preparation before the request waits in `thinking`.

## Alternatives

- Add React/Vue and a bundler to Admin: rejected because native modules already
  provide sufficient isolation without a Node toolchain.
- Add Provider, Riverpod or Bloc to Flutter: rejected because two focused
  `ChangeNotifier` controllers cover the current state graph with no new
  dependency.
- Keep booleans in `ChatScreen`: rejected because combinations such as
  recording and playing simultaneously are not valid domain states.
- Close the shared HTTP client to cancel a turn: rejected because it would
  disrupt unrelated requests and make the client unusable.
- Add server-side cancellation now: deferred until the voice API gains a
  request ID, cancellable job lifecycle or streaming transport.

## Consequences

- Admin screen code and Flutter orchestration can be tested independently.
- `panel.html` and `chat_screen.dart` become small composition roots.
- Late cancelled voice responses may still complete and be stored by Gateway,
  but they are not shown or played in the cancelled client session.
- A future streaming voice API can replace generation-based cancellation
  without changing widgets or conversation state.
- Static Admin assets must be deployed together with `panel.html`.
