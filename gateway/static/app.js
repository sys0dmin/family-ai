let mediaRecorder = null;
let mediaStream = null;
let audioChunks = [];
let currentAudio = null;
let currentAudioUrl = null;
let conversationId = null;
let isRecording = false;
let turnInProgress = false;
let availableAgents = [];
let selectedAgent = null;
let agentSelectionVersion = 0;
let newConversationConfirmationTimer = null;
let browserSpeechEnabled = loadBrowserSpeechPreference();

const chooser = document.getElementById('chooser');
const conversation = document.getElementById('conversation');
const agentGrid = document.getElementById('agent-grid');
const chatContainer = document.getElementById('chat-container');
const typingIndicator = document.getElementById('typing-indicator');
const quickReplies = document.getElementById('quick-replies');
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');
const micBtn = document.getElementById('mic-btn');
const keyboardToggle = document.getElementById('keyboard-toggle');
const textComposer = document.getElementById('text-composer');
const voiceControls = document.getElementById('voice-controls');
const photoBtn = document.getElementById('photo-btn');
const photoInput = document.getElementById('photo-input');

const agentPresentation = {
    teacher_friend: {
        image: '/static/assets/characters/teacher-friend.webp',
        color: '#356fc0',
        soft: '#e7f0fd',
        deep: '#214d8a'
    },
    scientist: {
        image: '/static/assets/characters/scientist.webp',
        color: '#138b78',
        soft: '#e0f5ef',
        deep: '#176557'
    },
    storyteller: {
        image: '/static/assets/characters/storyteller.webp',
        color: '#6654ad',
        soft: '#ece9f8',
        deep: '#46377f'
    },
    socrates: {
        image: '/static/assets/characters/socrates.webp',
        color: '#d87831',
        soft: '#fbeddf',
        deep: '#9b4f1f'
    },
    musician: {
        image: '/static/assets/characters/musician.webp',
        color: '#159c9a',
        soft: '#dff7f4',
        deep: '#116b72'
    },
    outdoor_guide: {
        image: '/static/assets/characters/murka.webp',
        color: '#5f8f42',
        soft: '#edf5df',
        deep: '#385e32'
    },
    tech_guide: {
        image: '/static/assets/characters/baytik.webp',
        color: '#176b91',
        soft: '#e2f3f8',
        deep: '#173f64'
    },
    space_guide: {
        image: '/static/assets/characters/alice-selezneva.webp',
        color: '#7a4fc7',
        soft: '#eee8fb',
        deep: '#49317d'
    }
};

const promptsByAgent = {
    teacher_friend: [
        { icon: '☁', label: 'Почему небо?', phrase: 'Почему небо голубое?' },
        { icon: '🦁', label: 'Животные', phrase: 'Давай викторину про животных' },
        { icon: '🔤', label: 'Игра в слова', phrase: 'Поиграем в слова' },
        { icon: '❓', label: 'Загадка', phrase: 'Загадай мне загадку' }
    ],
    scientist: [
        { icon: '🌧', label: 'Дождь', phrase: 'Почему идёт дождь?' },
        { icon: '🌱', label: 'Растения', phrase: 'Как растёт цветок?' },
        { icon: '🪐', label: 'Космос', phrase: 'Расскажи мне про космос' },
        { icon: '🔎', label: 'Опыт', phrase: 'Давай проведём простой безопасный опыт' }
    ],
    storyteller: [
        { icon: '🐈', label: 'Котёнок', phrase: 'Придумай сказку про котёнка' },
        { icon: '🌲', label: 'Лес', phrase: 'Расскажи сказку про волшебный лес' },
        { icon: '🏰', label: 'Замок', phrase: 'Давай придумаем сказку про добрый замок' },
        { icon: '⭐', label: 'Продолжить', phrase: 'Начни сказку, а я буду выбирать продолжение' }
    ],
    socrates: [
        { icon: '🤝', label: 'Дружба', phrase: 'Почему важно дружить?' },
        { icon: '💭', label: 'Подумать', phrase: 'Помоги мне самой найти ответ' },
        { icon: '🧩', label: 'Задача', phrase: 'Задай мне интересную задачку' },
        { icon: '⚖', label: 'Выбор', phrase: 'Давай рассуждать вместе' }
    ],
    musician: [
        { icon: '🎧', label: 'Угадай', phrase: 'Я напою мелодию, а ты попробуй угадать песню' },
        { icon: '🎵', label: 'Новая песня', phrase: 'Давай вместе сочиним новую песню' },
        { icon: '🎤', label: 'Припев', phrase: 'Придумаем весёлый припев по одной строчке' },
        { icon: '🥁', label: 'Ритм', phrase: 'Давай придумаем ритм и хлопать в ладоши' }
    ],
    outdoor_guide: [
        { icon: '⛺', label: 'Палатка', phrase: 'Мурка, расскажи, как вместе с родителями поставить палатку' },
        { icon: '🔥', label: 'Костёр', phrase: 'Как безопасно развести костёр вместе с родителями?' },
        { icon: '🎣', label: 'Рыбалка', phrase: 'Как мы можем безопасно порыбачить с родителями?' },
        { icon: '🐾', label: 'Следы', phrase: 'Расскажи добрую историю о следах животных в лесу' }
    ],
    tech_guide: [
        { icon: '🗄️', label: 'Сервер', phrase: 'Байтик, что такое сервер и зачем он нужен?' },
        { icon: '☁️', label: 'Облако', phrase: 'Почему компьютерное облако называется облаком?' },
        { icon: '🤖', label: 'ИИ', phrase: 'Как работает искусственный интеллект?' },
        { icon: '👨‍💻', label: 'Папина работа', phrase: 'Расскажи, чем папа-админ занимается на работе' }
    ],
    space_guide: [
        { icon: '🌙', label: 'Луна', phrase: 'Алиса, почему Луна меняет форму?' },
        { icon: '🪐', label: 'Планеты', phrase: 'Алиса, какая планета самая необычная?' },
        { icon: '✨', label: 'Звёзды', phrase: 'Алиса, почему звёзды мерцают?' },
        { icon: '🚀', label: 'Полетели!', phrase: 'Давай представим наше путешествие на новую планету' }
    ]
};

function presentationFor(agent) {
    return agentPresentation[agent.id] || agentPresentation.teacher_friend;
}

function setTheme(agent) {
    const presentation = presentationFor(agent);
    conversation.style.setProperty('--theme', presentation.color);
    conversation.style.setProperty('--theme-soft', presentation.soft);
    conversation.style.setProperty('--theme-deep', presentation.deep);
}

function loadBrowserSpeechPreference() {
    try {
        return window.localStorage.getItem('family-ai-browser-speech') !== 'off';
    } catch (error) {
        console.warn('Browser speech preference is unavailable:', error);
        return true;
    }
}

function saveBrowserSpeechPreference() {
    try {
        window.localStorage.setItem(
            'family-ai-browser-speech',
            browserSpeechEnabled ? 'on' : 'off'
        );
    } catch (error) {
        console.warn('Browser speech preference could not be saved:', error);
    }
}

function renderBrowserSpeechToggles() {
    document.querySelectorAll('.browser-speech-toggle').forEach((button) => {
        button.textContent = browserSpeechEnabled ? '🔊' : '🔇';
        button.classList.toggle('is-off', !browserSpeechEnabled);
        const action = browserSpeechEnabled
            ? 'Выключить автоозвучку'
            : 'Включить автоозвучку';
        button.setAttribute('aria-label', action);
        button.title = action;
        button.setAttribute('aria-pressed', String(browserSpeechEnabled));
    });
}

function toggleBrowserSpeech() {
    browserSpeechEnabled = !browserSpeechEnabled;
    saveBrowserSpeechPreference();
    if (!browserSpeechEnabled) {
        window.speechSynthesis?.cancel();
        if (!conversation.hidden && !turnInProgress) {
            setState('ready', 'Готов слушать');
        }
    } else if (selectedAgent && !conversation.hidden && !turnInProgress) {
        speakText(selectedAgent.greeting);
    }
    renderBrowserSpeechToggles();
}

function setState(state, text) {
    conversation.dataset.state = state;
    document.querySelectorAll('.visual-status').forEach((element) => {
        element.className = `visual-status ${state}`;
        const label = element.querySelector('.status-text');
        if (label) label.textContent = text;
    });
}

function showTyping(show) {
    typingIndicator.classList.toggle('visible', Boolean(show));
    if (show) scrollToBottom();
}

function showSilentResponse() {
    setState('responded', 'Ответ готов');
    window.setTimeout(() => {
        if (conversation.dataset.state === 'responded') {
            setState('ready', 'Готов слушать');
        }
    }, 1100);
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function speakText(text) {
    if (!browserSpeechEnabled || !('speechSynthesis' in window) || !text) return false;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ru-RU';
    utterance.rate = 0.92;
    utterance.pitch = 1.03;
    const russianVoice = window.speechSynthesis.getVoices()
        .find((voice) => voice.lang.toLowerCase().startsWith('ru'));
    if (russianVoice) utterance.voice = russianVoice;
    utterance.onstart = () => setState('speaking', 'Говорю');
    utterance.onend = () => setState('ready', 'Готов слушать');
    utterance.onerror = () => setState('ready', 'Готов слушать');
    window.speechSynthesis.speak(utterance);
    return true;
}

function renderAgentCards() {
    agentGrid.replaceChildren();
    for (const agent of availableAgents) {
        const presentation = presentationFor(agent);
        const card = document.createElement('button');
        card.type = 'button';
        card.className = 'agent-card';
        card.setAttribute('aria-label', `${agent.display_name}. ${agent.description}`);
        card.style.setProperty('--agent-color', presentation.color);
        card.style.setProperty('--agent-soft', presentation.soft);

        const art = document.createElement('img');
        art.className = 'agent-card-art';
        art.src = presentation.image;
        art.alt = '';

        const sound = document.createElement('span');
        sound.className = 'agent-card-sound';
        sound.setAttribute('aria-hidden', 'true');
        sound.textContent = '♪';

        const copy = document.createElement('span');
        copy.className = 'agent-card-copy';
        const name = document.createElement('span');
        name.className = 'agent-card-name';
        name.textContent = agent.display_name;
        const hint = document.createElement('span');
        hint.className = 'agent-card-hint';
        hint.textContent = agent.description;
        copy.append(name, hint);

        card.append(art, sound, copy);
        card.onclick = () => chooseAgent(agent);
        agentGrid.append(card);
    }
}

function renderQuickReplies() {
    quickReplies.replaceChildren();
    const prompts = promptsByAgent[selectedAgent?.id] || promptsByAgent.teacher_friend;
    for (const prompt of prompts) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'prompt-button';
        button.setAttribute('aria-label', prompt.phrase);
        const icon = document.createElement('span');
        icon.className = 'prompt-icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = prompt.icon;
        const label = document.createElement('span');
        label.className = 'prompt-label';
        label.textContent = prompt.label;
        button.append(icon, label);
        button.onclick = () => sendText(prompt.phrase);
        quickReplies.append(button);
    }
}

function addMessage(text, role, media = []) {
    if (role === 'system') {
        const message = document.createElement('div');
        message.className = 'system-message';
        message.textContent = text;
        chatContainer.insertBefore(message, typingIndicator);
        scrollToBottom();
        return;
    }

    const row = document.createElement('div');
    row.className = `message-row ${role}`;
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    if (role === 'assistant') {
        const image = document.createElement('img');
        image.src = presentationFor(selectedAgent).image;
        image.alt = '';
        avatar.append(image);
    } else {
        avatar.textContent = '●';
        avatar.setAttribute('aria-hidden', 'true');
    }
    const bubble = document.createElement('div');
    bubble.className = 'message';
    const messageText = document.createElement('div');
    messageText.textContent = text;
    bubble.append(messageText);
    if (role === 'assistant') {
        for (const item of media) {
            if (item.media_type !== 'image') continue;
            const figure = document.createElement('figure');
            figure.className = 'message-media';
            const image = document.createElement('img');
            image.src = item.content_url;
            image.alt = item.title || 'Картинка к ответу';
            image.loading = 'lazy';
            const caption = document.createElement('figcaption');
            const source = document.createElement('a');
            source.href = item.source_url;
            source.target = '_blank';
            source.rel = 'noopener noreferrer';
            source.textContent = item.attribution
                ? `Фото: ${item.attribution}`
                : 'Источник изображения';
            caption.append(source);
            figure.append(image, caption);
            bubble.append(figure);
        }
    }
    row.append(avatar, bubble);
    chatContainer.insertBefore(row, typingIndicator);
    scrollToBottom();
}

function clearConversationView() {
    conversationId = null;
    chatContainer.querySelectorAll('.message-row, .system-message').forEach((item) => item.remove());
    document.getElementById('welcome-card').hidden = false;
}

function resetNewConversationConfirmation() {
    if (newConversationConfirmationTimer) {
        window.clearTimeout(newConversationConfirmationTimer);
        newConversationConfirmationTimer = null;
    }
    document.querySelectorAll('.new-conversation').forEach((button) => {
        button.classList.remove('confirming');
        button.setAttribute('aria-label', 'Начать новый разговор');
        button.title = 'Начать новый разговор';
        button.querySelector('.new-conversation-symbol').textContent = '↻';
    });
}

async function chooseAgent(agent, announce = true) {
    const selectionVersion = ++agentSelectionVersion;
    selectedAgent = agent;
    const presentation = presentationFor(agent);
    resetNewConversationConfirmation();
    cancelActiveMedia();
    setTheme(agent);
    clearConversationView();
    document.getElementById('companion-art').src = presentation.image;
    document.getElementById('companion-art').alt = agent.display_name;
    document.getElementById('companion-name').textContent = agent.display_name;
    document.getElementById('mobile-agent-name').textContent = agent.display_name;
    document.getElementById('companion-description').textContent = agent.description;
    document.getElementById('welcome-text').textContent = agent.greeting;
    const supportsPhoto = Boolean(agent.supports_image_upload);
    photoBtn.hidden = !supportsPhoto;
    voiceControls.classList.toggle('has-photo', supportsPhoto);
    renderQuickReplies();
    chooser.hidden = true;
    conversation.hidden = false;
    setControlsEnabled(false);
    setState('busy', 'Вспоминаю');

    try {
        const response = await fetch(
            `/v1/conversations/latest?agent_id=${encodeURIComponent(agent.id)}`
        );
        if (!response.ok) throw new Error('Conversation history unavailable');
        const data = await response.json();
        if (selectionVersion !== agentSelectionVersion) return;

        conversationId = data.conversation_id;
        for (const message of data.messages) {
            addMessage(message.content, message.role, message.media || []);
        }
        const hasMessages = data.messages.length > 0;
        document.getElementById('welcome-card').hidden = hasMessages;
        setState('ready', 'Готов слушать');
        if (announce && !hasMessages) speakText(agent.greeting);
    } catch (error) {
        if (selectionVersion !== agentSelectionVersion) return;
        console.error('Conversation history loading failed:', error);
        conversationId = null;
        setState('error', 'Не вспомнил');
        if (announce) speakText(agent.greeting);
    } finally {
        if (selectionVersion === agentSelectionVersion) setControlsEnabled(true);
    }
}

function showChooser() {
    if (turnInProgress) return;
    agentSelectionVersion += 1;
    resetNewConversationConfirmation();
    cancelActiveMedia();
    conversation.hidden = true;
    chooser.hidden = false;
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setControlsEnabled(enabled) {
    textInput.disabled = !enabled;
    sendBtn.disabled = !enabled;
    micBtn.disabled = !enabled;
    keyboardToggle.disabled = !enabled;
    photoBtn.disabled = !enabled;
    quickReplies.querySelectorAll('button').forEach((button) => {
        button.disabled = !enabled;
    });
    document.querySelectorAll('.new-conversation').forEach((button) => {
        button.disabled = !enabled;
    });
}

function setTurnControlsDisabled(disabled) {
    turnInProgress = disabled;
    quickReplies.querySelectorAll('button').forEach((button) => {
        button.disabled = disabled;
    });
    sendBtn.disabled = disabled;
    keyboardToggle.disabled = disabled;
    photoBtn.disabled = disabled;
    document.querySelectorAll('.browser-speech-toggle').forEach((button) => {
        button.disabled = disabled;
    });
    document.querySelectorAll('.new-conversation').forEach((button) => {
        button.disabled = disabled;
    });
    if (!isRecording) micBtn.disabled = disabled;
}

async function loadAgents() {
    setControlsEnabled(false);
    try {
        const response = await fetch('/v1/agents');
        if (!response.ok) throw new Error('Agent API unavailable');
        const data = await response.json();
        availableAgents = data.items;
        if (!availableAgents.length) throw new Error('No enabled agents');
        renderAgentCards();
        const requestedAgentId = new URLSearchParams(window.location.search).get('agent');
        const requestedAgent = availableAgents.find((agent) => agent.id === requestedAgentId);
        if (requestedAgent) chooseAgent(requestedAgent, false);
    } catch (error) {
        console.error('Agent loading failed:', error);
        agentGrid.textContent = 'Друзья скоро вернутся. Обнови страницу чуть позже.';
        speakText('Друзья сейчас заняты. Попробуй ещё раз чуть позже.');
    }
}

async function ensureConversation() {
    if (conversationId) return conversationId;
    if (!selectedAgent) throw new Error('Agent is not selected');

    const response = await fetch('/v1/conversations/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: selectedAgent.id })
    });
    if (!response.ok) throw new Error('Conversation creation failed');
    const data = await response.json();
    conversationId = data.conversation_id;
    return conversationId;
}

function requestNewConversation() {
    if (turnInProgress || !selectedAgent) return;
    const isConfirmed = document.querySelector('.new-conversation')
        ?.classList.contains('confirming');
    if (!isConfirmed) {
        document.querySelectorAll('.new-conversation').forEach((button) => {
            button.classList.add('confirming');
            button.setAttribute('aria-label', 'Подтвердить новый разговор');
            button.title = 'Нажать ещё раз для подтверждения';
            button.querySelector('.new-conversation-symbol').textContent = '✓';
        });
        speakText('Нажми ещё раз, чтобы начать новый разговор.');
        newConversationConfirmationTimer = window.setTimeout(
            resetNewConversationConfirmation,
            3500
        );
        return;
    }
    resetNewConversationConfirmation();
    void startNewConversation();
}

async function startNewConversation() {
    const agent = selectedAgent;
    const selectionVersion = ++agentSelectionVersion;
    cancelActiveMedia();
    clearConversationView();
    setTurnControlsDisabled(true);
    setState('busy', 'Начинаю');
    try {
        const response = await fetch('/v1/conversations/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: agent.id })
        });
        if (!response.ok) throw new Error('Conversation creation failed');
        const data = await response.json();
        if (selectionVersion !== agentSelectionVersion) return;
        conversationId = data.conversation_id;
        setState('ready', 'Готов слушать');
        speakText(agent.greeting);
    } catch (error) {
        if (selectionVersion !== agentSelectionVersion) return;
        console.error('New conversation creation failed:', error);
        addMessage('Ой, новый разговор пока не начался. Попробуем ещё раз.', 'system');
        setState('error', 'Нет связи');
    } finally {
        if (selectionVersion === agentSelectionVersion) setTurnControlsDisabled(false);
    }
}

async function sendText(forcedText = null) {
    const text = (forcedText || textInput.value).trim();
    if (!text || !selectedAgent || turnInProgress) return;
    setTurnControlsDisabled(true);
    textInput.value = '';
    document.getElementById('welcome-card').hidden = true;
    addMessage(text, 'child');
    setState('busy', 'Думаю');
    showTyping(true);

    try {
        await ensureConversation();
        const response = await fetch(`/v1/conversations/${conversationId}/turn`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: 'child', content: text })
        });
        if (!response.ok) throw new Error('Message was rejected');
        const data = await response.json();
        addMessage(data.content, 'assistant', data.media);
        showTyping(false);
        if (browserSpeechEnabled) {
            try {
                await speakAssistantReply(data.content);
            } catch (voiceError) {
                console.warn('Agent TTS playback failed, using browser voice:', voiceError);
                if (!speakText(data.content)) setState('ready', 'Готов слушать');
            }
        } else {
            showSilentResponse();
        }
    } catch (error) {
        console.error('Text turn failed:', error);
        addMessage('Ой, связь потерялась. Попробуем ещё раз.', 'system');
        setState('error', 'Нет связи');
        speakText('Ой, связь потерялась. Попробуем ещё раз.');
    } finally {
        showTyping(false);
        setTurnControlsDisabled(false);
    }
}

const DEFAULT_IMAGE_UPLOAD_MAX_BYTES = 10 * 1024 * 1024;

function canvasToBlob(canvas, quality) {
    return new Promise((resolve, reject) => {
        canvas.toBlob(
            (blob) => blob
                ? resolve(blob)
                : reject(new Error('IMAGE_PREPARATION_FAILED')),
            'image/jpeg',
            quality
        );
    });
}

async function preparePhotoForUpload(file, maxBytes) {
    if (file.size <= maxBytes) return file;
    if (typeof createImageBitmap !== 'function') {
        throw new Error('IMAGE_TOO_LARGE');
    }

    const bitmap = await createImageBitmap(file);
    try {
        let scale = Math.min(1, Math.sqrt((maxBytes * 0.82) / file.size));
        let quality = 0.9;
        for (let attempt = 0; attempt < 6; attempt += 1) {
            const canvas = document.createElement('canvas');
            canvas.width = Math.max(1, Math.round(bitmap.width * scale));
            canvas.height = Math.max(1, Math.round(bitmap.height * scale));
            const context = canvas.getContext('2d');
            if (!context) throw new Error('IMAGE_PREPARATION_FAILED');
            context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
            const blob = await canvasToBlob(canvas, quality);
            canvas.width = 1;
            canvas.height = 1;
            if (blob.size <= maxBytes) {
                const stem = (file.name || 'photo').replace(/\.[^.]+$/, '');
                return new File([blob], `${stem}.jpg`, { type: 'image/jpeg' });
            }
            scale *= 0.82;
            quality = Math.max(0.68, quality - 0.05);
        }
    } finally {
        bitmap.close();
    }
    throw new Error('IMAGE_TOO_LARGE');
}

function photoErrorMessage(error, maxBytes) {
    const limitMiB = Math.max(1, Math.floor(maxBytes / 1048576));
    if (error?.message === 'IMAGE_TOO_LARGE') {
        return `Фотография больше ${limitMiB} МиБ, и уменьшить её не получилось.`;
    }
    if (error?.message === 'IMAGE_UNSUPPORTED') {
        return 'Подойдут фотографии JPEG, PNG или WebP.';
    }
    if (error?.message === 'IMAGE_INVALID') {
        return 'Файл не удалось прочитать как фотографию.';
    }
    return 'Не получилось рассмотреть фотографию. Давай попробуем ещё раз.';
}

async function sendPhoto(file) {
    if (!file || !selectedAgent?.supports_image_upload || turnInProgress) return;
    const maxBytes = Number(selectedAgent.image_upload_max_bytes)
        || DEFAULT_IMAGE_UPLOAD_MAX_BYTES;
    const question = textInput.value.trim()
        || 'Алиса, расскажи, что интересного видно на этой фотографии?';
    setTurnControlsDisabled(true);
    textInput.value = '';
    document.getElementById('welcome-card').hidden = true;
    addMessage(`📷 ${question}`, 'child');
    setState('busy', 'Рассматриваю');
    showTyping(true);

    try {
        const preparedFile = await preparePhotoForUpload(file, maxBytes);
        console.info('Photo prepared for Vision', {
            originalBytes: file.size,
            uploadedBytes: preparedFile.size,
            contentType: preparedFile.type
        });
        await ensureConversation();
        const formData = new FormData();
        formData.append('file', preparedFile, preparedFile.name || 'photo.jpg');
        formData.append('question', question);
        const response = await fetch(`/v1/vision/${conversationId}/turn`, {
            method: 'POST',
            body: formData
        });
        if (response.status === 413) throw new Error('IMAGE_TOO_LARGE');
        if (response.status === 415) throw new Error('IMAGE_UNSUPPORTED');
        if (response.status === 422) throw new Error('IMAGE_INVALID');
        if (!response.ok) throw new Error(`Image turn failed: ${response.status}`);
        const data = await response.json();
        addMessage(data.content, 'assistant', data.media || []);
        showTyping(false);
        if (browserSpeechEnabled) {
            try {
                await speakAssistantReply(data.content);
            } catch (voiceError) {
                console.warn('Agent image reply playback failed:', voiceError);
                if (!speakText(data.content)) showSilentResponse();
            }
        } else {
            showSilentResponse();
        }
    } catch (error) {
        console.error('Image turn failed:', error);
        addMessage(photoErrorMessage(error, maxBytes), 'system');
        setState('error', 'Не вижу фото');
    } finally {
        photoInput.value = '';
        showTyping(false);
        setTurnControlsDisabled(false);
    }
}

async function speakAssistantReply(text) {
    const response = await fetch(`/v1/voice/${conversationId}/synthesize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
    });
    if (!response.ok) throw new Error('Agent speech synthesis failed');
    await playAudioBlob(await response.blob());
}

function playAudioBlob(blob) {
    return new Promise((resolve, reject) => {
        currentAudioUrl = URL.createObjectURL(blob);
        currentAudio = new Audio(currentAudioUrl);
        const cleanup = () => {
            if (currentAudioUrl) URL.revokeObjectURL(currentAudioUrl);
            currentAudioUrl = null;
            currentAudio = null;
        };
        currentAudio.onplay = () => setState('speaking', 'Говорю');
        currentAudio.onended = () => {
            cleanup();
            setState('ready', 'Готов слушать');
            resolve();
        };
        currentAudio.onerror = () => {
            cleanup();
            setState('error', 'Не получилось ответить');
            reject(new Error('Audio playback failed'));
        };
        currentAudio.play().catch((error) => {
            cleanup();
            reject(error);
        });
    });
}

function cancelActiveMedia() {
    window.speechSynthesis?.cancel();
    if (currentAudio) {
        currentAudio.pause();
        currentAudio = null;
    }
    if (currentAudioUrl) {
        URL.revokeObjectURL(currentAudioUrl);
        currentAudioUrl = null;
    }
    if (isRecording && mediaRecorder) {
        mediaRecorder.onstop = null;
        mediaRecorder.stop();
    }
    mediaStream?.getTracks().forEach((track) => track.stop());
    mediaStream = null;
    isRecording = false;
    micBtn.classList.remove('recording');
}

async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia) {
        speakText('Микрофон пока недоступен. Можно выбрать картинку сверху.');
        setState('error', 'Микрофон недоступен');
        return;
    }

    try {
        window.speechSynthesis?.cancel();
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(mediaStream);
        audioChunks = [];
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size) audioChunks.push(event.data);
        };
        mediaRecorder.onstop = async () => {
            const mimeType = mediaRecorder.mimeType || 'audio/webm';
            const audioBlob = new Blob(audioChunks, { type: mimeType });
            mediaStream?.getTracks().forEach((track) => track.stop());
            mediaStream = null;
            await sendVoice(audioBlob, mimeType);
        };
        mediaRecorder.start();
        isRecording = true;
        micBtn.classList.add('recording');
        micBtn.setAttribute('aria-label', 'Закончить голосовое сообщение');
        setState('listening', 'Слушаю');
    } catch (error) {
        console.error('Microphone access failed:', error);
        setState('error', 'Микрофон недоступен');
        speakText('Не получилось включить микрофон. Можно выбрать картинку сверху.');
    }
}

function stopRecording() {
    if (!isRecording || !mediaRecorder) return;
    mediaRecorder.stop();
    isRecording = false;
    micBtn.classList.remove('recording');
    micBtn.setAttribute('aria-label', 'Начать голосовое сообщение');
    setState('busy', 'Думаю');
}

async function sendVoice(audioBlob, mimeType) {
    if (turnInProgress) return;
    setTurnControlsDisabled(true);
    document.getElementById('welcome-card').hidden = true;
    addMessage('🎙', 'child');
    showTyping(true);
    try {
        await ensureConversation();
        const extension = mimeType.includes('wav') ? 'wav' : 'webm';
        const formData = new FormData();
        formData.append('file', audioBlob, `recording.${extension}`);
        const response = await fetch(`/v1/voice/${conversationId}/turn`, {
            method: 'POST',
            body: formData
        });
        if (!response.ok) throw new Error('Voice turn failed');
        let messageMedia = [];
        const messageId = response.headers.get('X-Family-AI-Message-Id');
        if (messageId) {
            try {
                const messageResponse = await fetch(
                    `/v1/conversations/${conversationId}/messages/${messageId}`
                );
                if (messageResponse.ok) {
                    messageMedia = (await messageResponse.json()).media || [];
                }
            } catch (mediaError) {
                console.warn('Voice reply image could not be loaded:', mediaError);
            }
        }
        addMessage('🔊', 'assistant', messageMedia);
        showTyping(false);
        await playAudioBlob(await response.blob());
    } catch (error) {
        console.error('Voice turn failed:', error);
        addMessage('Ой, я не расслышал. Попробуем ещё раз.', 'system');
        setState('error', 'Не расслышал');
        speakText('Ой, я не расслышал. Попробуем ещё раз.');
    } finally {
        showTyping(false);
        setTurnControlsDisabled(false);
    }
}

document.querySelectorAll('.change-agent').forEach((button) => {
    button.onclick = showChooser;
});

document.querySelectorAll('.new-conversation').forEach((button) => {
    button.onclick = requestNewConversation;
});

document.querySelectorAll('.browser-speech-toggle').forEach((button) => {
    button.onclick = toggleBrowserSpeech;
});

keyboardToggle.onclick = () => {
    const show = textComposer.hidden;
    textComposer.hidden = !show;
    keyboardToggle.setAttribute('aria-expanded', String(show));
    if (show) textInput.focus();
};

micBtn.onclick = () => {
    if (isRecording) stopRecording();
    else startRecording();
};

photoBtn.onclick = () => photoInput.click();
photoInput.onchange = () => sendPhoto(photoInput.files?.[0]);

sendBtn.onclick = () => sendText();
textInput.onkeydown = (event) => {
    if (event.key === 'Enter') sendText();
};

window.addEventListener('beforeunload', cancelActiveMedia);
renderBrowserSpeechToggles();
loadAgents();
