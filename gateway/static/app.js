let mediaRecorder;
let audioChunks = [];
let conversationId = null;
let isRecording = false;
let availableAgents = [];
let selectedAgent = null;

const chatContainer = document.getElementById('chat-container');
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');
const micBtn = document.getElementById('mic-btn');
const statusPill = document.getElementById('status-pill');
const typingIndicator = document.getElementById('typing-indicator');
const quickReplies = document.getElementById('quick-replies');
const agentPicker = document.getElementById('agent-picker');
const agentGrid = document.getElementById('agent-grid');
const closeAgentPicker = document.getElementById('close-agent-picker');
const changeAgentBtn = document.getElementById('change-agent-btn');

const quickPhrasesByAgent = {
    teacher_friend: ['Объясни мне что-нибудь интересное', 'Загадай мне загадку', 'Поиграем в слова', 'Почему небо голубое?'],
    scientist: ['Почему идёт дождь?', 'Как растёт цветок?', 'Расскажи про космос', 'Давай простой опыт'],
    storyteller: ['Придумай сказку про котёнка', 'Сказку про волшебный лес', 'Я выберу героя сказки', 'Продолжим историю вместе'],
    socrates: ['Помоги мне самой найти ответ', 'Задай мне хитрый вопрос', 'Почему важно дружить?', 'Давай рассуждать вместе']
};

function setStatus(text, kind = 'ok') {
    if (!statusPill) return;
    statusPill.textContent = text;
    statusPill.classList.remove('busy', 'error');
    if (kind === 'busy' || kind === 'error') {
        statusPill.classList.add(kind);
    }
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function showTyping(show) {
    if (!typingIndicator) return;
    typingIndicator.classList.toggle('visible', Boolean(show));
    if (show) {
        scrollToBottom();
    }
}

function addMessage(text, role) {
    if (role === 'system') {
        const systemDiv = document.createElement('div');
        systemDiv.className = 'system';
        systemDiv.textContent = text;
        chatContainer.insertBefore(systemDiv, typingIndicator);
        scrollToBottom();
        return;
    }

    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'assistant' ? (selectedAgent?.icon || '✨') : '🧒';

    const bubble = document.createElement('div');
    bubble.className = 'message';
    bubble.textContent = text;

    row.appendChild(avatar);
    row.appendChild(bubble);
    chatContainer.insertBefore(row, typingIndicator);
    scrollToBottom();
}

function renderQuickReplies() {
    if (!quickReplies) return;
    quickReplies.innerHTML = '';

    const phrases = quickPhrasesByAgent[selectedAgent?.id] || quickPhrasesByAgent.teacher_friend;
    phrases.forEach((phrase) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = phrase;
        button.onclick = () => {
            textInput.value = phrase;
            sendText();
        };
        quickReplies.appendChild(button);
    });
}

function setControlsEnabled(enabled) {
    textInput.disabled = !enabled;
    sendBtn.disabled = !enabled;
    micBtn.disabled = !enabled;
}

function renderAgentPicker() {
    agentGrid.replaceChildren();
    availableAgents.forEach((agent) => {
        const card = document.createElement('button');
        card.type = 'button';
        card.className = `agent-card ${['blue', 'green', 'purple', 'orange'].includes(agent.color) ? agent.color : ''}`;
        const icon = document.createElement('span');
        icon.className = 'agent-card-icon';
        icon.textContent = agent.icon;
        const name = document.createElement('span');
        name.className = 'agent-card-name';
        name.textContent = agent.display_name;
        const description = document.createElement('span');
        description.className = 'agent-card-description';
        description.textContent = agent.description;
        card.append(icon, name, description);
        card.onclick = () => chooseAgent(agent);
        agentGrid.append(card);
    });
}

function resetConversationView(agent) {
    conversationId = null;
    chatContainer.querySelectorAll('.message-row, .system').forEach((element) => element.remove());
    document.querySelector('#welcome-card .emoji').textContent = agent.icon;
    document.getElementById('welcome-text').textContent = agent.greeting;
    addMessage(agent.greeting, 'assistant');
}

function chooseAgent(agent) {
    const changed = selectedAgent?.id !== agent.id;
    selectedAgent = agent;
    document.getElementById('agent-logo').textContent = agent.icon;
    document.getElementById('agent-title').textContent = agent.display_name;
    document.getElementById('agent-subtitle').textContent = agent.description;
    if (changed) resetConversationView(agent);
    renderQuickReplies();
    setControlsEnabled(true);
    agentPicker.hidden = true;
    closeAgentPicker.hidden = false;
    setStatus('Готов к разговору');
    textInput.focus();
}

async function loadAgents() {
    setControlsEnabled(false);
    setStatus('Загружаю друзей...', 'busy');
    try {
        const response = await fetch('/v1/agents');
        if (!response.ok) throw new Error('Не удалось загрузить агентов');
        const data = await response.json();
        availableAgents = data.items;
        renderAgentPicker();
        if (!availableAgents.length) throw new Error('Нет доступных агентов');
        setStatus('Выбери помощника');
    } catch (err) {
        console.error('Agent loading failed:', err);
        agentGrid.textContent = 'Не получилось позвать друзей. Обнови страницу чуть позже.';
        setStatus('Нет связи с помощниками', 'error');
    }
}

async function ensureConversation() {
    if (conversationId) {
        return conversationId;
    }

    try {
        if (!selectedAgent) {
            throw new Error('Сначала выбери помощника');
        }
        const response = await fetch('/v1/conversations/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: selectedAgent.id })
        });

        if (!response.ok) {
            throw new Error('Не удалось создать диалог');
        }

        const data = await response.json();
        conversationId = data.conversation_id;
        return conversationId;
    } catch (err) {
        console.error('Conversation creation failed:', err);
        addMessage('Не удалось подготовить диалог. Повтори чуть позже.', 'system');
        throw err;
    }
}

async function sendText() {
    const text = textInput.value.trim();
    if (!text) return;

    textInput.value = '';
    addMessage(text, 'child');
    setStatus('Думаю над ответом...', 'busy');
    showTyping(true);

    try {
        await ensureConversation();

        const response = await fetch(`/v1/conversations/${conversationId}/turn`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: 'child', content: text })
        });

        if (!response.ok) {
            throw new Error('Сервер не принял сообщение');
        }

        const data = await response.json();
        addMessage(data.content, 'assistant');
        setStatus('Готов к чату');
    } catch (err) {
        console.error('Text send failed:', err);
        addMessage('Ой, что-то сломалось. Попробуй еще раз!', 'system');
        setStatus('Есть ошибка соединения', 'error');
    } finally {
        showTyping(false);
    }
}

async function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('Браузер блокирует микрофон на HTTP.\n\nВключите флаг: chrome://flags/#unsafely-treat-insecure-origin-as-secure и добавьте http://192.168.31.173:8000');
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            await sendVoice(audioBlob);
            stream.getTracks().forEach((track) => track.stop());
        };

        mediaRecorder.start();
        isRecording = true;
        micBtn.classList.add('recording');
        micBtn.textContent = '🛑';
        setStatus('Слушаю тебя...', 'busy');
    } catch (err) {
        console.error('Error accessing mic:', err);
        alert('Ошибка доступа к микрофону: ' + err.message);
        setStatus('Микрофон недоступен', 'error');
    }
}

async function sendVoice(audioBlob) {
    addMessage('🎤 Голосовое сообщение отправлено...', 'child');
    setStatus('Обрабатываю голос...', 'busy');
    showTyping(true);

    try {
        await ensureConversation();

        const formData = new FormData();
        formData.append('file', audioBlob, 'recording.wav');

        const response = await fetch(`/v1/voice/${conversationId}/turn`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('Сервер не смог обработать голос');
        }

        const audioResponse = await response.blob();
        const audioUrl = URL.createObjectURL(audioResponse);
        const audio = new Audio(audioUrl);
        audio.play();
        addMessage('🔊 Включаю голосовой ответ', 'assistant');
        setStatus('Готов к чату');
    } catch (err) {
        console.error('Voice send failed:', err);
        addMessage('Не удалось отправить голос :(', 'system');
        setStatus('Ошибка голоса', 'error');
    } finally {
        showTyping(false);
    }
}

micBtn.onclick = () => {
    if (isRecording && mediaRecorder) {
        mediaRecorder.stop();
        micBtn.classList.remove('recording');
        micBtn.textContent = '🎤';
        isRecording = false;
    } else {
        startRecording();
    }
};

sendBtn.onclick = sendText;
textInput.onkeypress = (e) => {
    if (e.key === 'Enter') {
        sendText();
    }
};

changeAgentBtn.onclick = () => {
    agentPicker.hidden = false;
    closeAgentPicker.hidden = !selectedAgent;
};
closeAgentPicker.onclick = () => {
    if (selectedAgent) agentPicker.hidden = true;
};

loadAgents();
