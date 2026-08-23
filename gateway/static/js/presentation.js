const AGENT_PRESENTATION = {
  teacher_friend: { image: '/static/assets/characters/teacher-friend.webp', color: '#356fc0', soft: '#e7f0fd', deep: '#214d8a' },
  scientist: { image: '/static/assets/characters/scientist.webp', color: '#138b78', soft: '#e0f5ef', deep: '#176557' },
  storyteller: { image: '/static/assets/characters/storyteller.webp', color: '#6654ad', soft: '#ece9f8', deep: '#46377f' },
  socrates: { image: '/static/assets/characters/socrates.webp', color: '#d87831', soft: '#fbeddf', deep: '#9b4f1f' },
  musician: { image: '/static/assets/characters/musician.webp', color: '#159c9a', soft: '#dff7f4', deep: '#116b72' },
  outdoor_guide: { image: '/static/assets/characters/murka.webp', color: '#5f8f42', soft: '#edf5df', deep: '#385e32' },
  tech_guide: { image: '/static/assets/characters/baytik.webp', color: '#176b91', soft: '#e2f3f8', deep: '#173f64' },
  space_guide: { image: '/static/assets/characters/alice-selezneva.webp', color: '#7a4fc7', soft: '#eee8fb', deep: '#49317d' }
};

export const PROMPTS_BY_AGENT = {
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

export function presentationFor(agent) {
  return AGENT_PRESENTATION[agent.id] || AGENT_PRESENTATION.teacher_friend;
}
