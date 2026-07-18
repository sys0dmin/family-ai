let mediaRecorder;
let audioChunks = [];
let conversationId = null;
let isRecording = false;

const chatContainer = document.getElementById('chat-container');
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');
const micBtn = document.getElementById('mic-btn');
const statusPill = document.getElementById('status-pill');
const typingIndicator = document.getElementById('typing-indicator');
const quickReplies = document.getElementById('quick-replies');

const quickPhrases = [
    'Придумай сказку про котенка',
    'Загадай мне загадку',
    'Поиграем в слова',
    'Почему небо голубое?',
    'Давай викторину про животных'
];

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
        chatContainer.appendChild(systemDiv);
        scrollToBottom();
        return;
    }

    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'assistant' ? '🤖' : '🧒';

    const bubble = document.createElement('div');
    bubble.className = 'message';
    bubble.textContent = text;

    row.appendChild(avatar);
    row.appendChild(bubble);
    chatContainer.appendChild(row);
    scrollToBottom();
}

function renderQuickReplies() {
    if (!quickReplies) return;
    quickReplies.innerHTML = '';

    quickPhrases.forEach((phrase) => {
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

async function ensureConversation() {
    if (conversationId) {
        return conversationId;
    }

    try {
        const response = await fetch('/v1/conversations', {
            method: 'POST'
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

renderQuickReplies();
setStatus('Готов к чату');
