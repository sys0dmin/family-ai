# Визуальные регрессии Admin UI и Android

## Назначение

Visual suite обнаруживает смещение сетки, горизонтальный overflow, перекрытие
кнопок, исчезновение критических элементов и непреднамеренное изменение внешнего
вида до публикации UI-релиза.

Эталоны не содержат production-данных. Admin UI использует отдельный
синтетический DOM fixture, Android — mock Gateway и in-memory реализации
аппаратного аудиослоя.

## Поддерживаемые состояния

Admin UI:

| Экран | Viewport |
|---|---:|
| Настройки | 1440 × 1000 |
| Агенты | 1440 × 1000 |
| Тест-студия | 1440 × 1000 |
| Инфраструктура и предупреждения | 1440 × 1000 |
| Настройки | 390 × 844 |
| Тест-студия | 390 × 844 |
| Инфраструктура и предупреждения | 390 × 844 |

Android:

- выбор агента — `430 × 900`;
- чат — `430 × 900`;
- чат с клавиатурой — `430 × 900`, нижний inset `400`;
- чат в landscape — `844 × 390`;
- landscape с клавиатурой — `844 × 390`, нижний inset `260`.

Эти размеры являются тестовым контрактом, а не списком единственных разрешённых
телефонов. Адаптивная раскладка обязана работать и между контрольными точками.

## Обычная проверка

Из корня репозитория:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\visual\Test-VisualRegression.ps1
```

Admin-тест автоматически ищет Chrome, затем Edge. Он собирает временный HTML из
настоящих `panel.html` и `admin.css`, отключает анимации, подставляет
синтетические данные и проверяет отсутствие горизонтального overflow. PNG
сравниваются с небольшим допуском на браузерный anti-aliasing. При расхождении
рядом с baseline сохраняется `*.actual.png`.

Flutter использует настоящий `ChatScreen`, assets персонажа и штатный golden
comparator. Стабильный Roboto берётся из того Flutter SDK, которым запущен тест;
шрифт не добавляется в runtime-приложение.

Release-сборка Android автоматически выполняет mobile visual suite из того же
точного Git commit до сборки APK. Admin visual suite запускается на Windows
рабочей станции до команды Gateway deploy: production-хосту браузер и fixture
не требуются.

## Осознанное обновление эталонов

После намеренного изменения интерфейса:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\visual\Test-VisualRegression.ps1 -UpdateBaselines
```

После команды обязательно:

1. открыть каждый изменённый PNG;
2. проверить desktop/mobile, клавиатуру и landscape;
3. убедиться, что в кадре нет полос Flutter overflow и обрезанных действий;
4. проверить `git diff --stat` и отсутствие `*.actual.png`;
5. только после просмотра включать новые baseline в commit.

Флаг нельзя использовать как способ «починить» упавший тест без анализа
изменения.

## Где лежат файлы

- Admin baselines: `gateway/tests/visual/admin/`;
- Android goldens: `mobile/test/visual/goldens/`;
- Admin fixture: `scripts/visual/admin-fixture.js`;
- PNG comparator: `scripts/visual/compare_png.py`;
- общий runner: `scripts/visual/Test-VisualRegression.ps1`.

Архитектурные границы и причины выбора описаны в
[`ADR 035`](adr/035-visual-regression-baselines.md).
