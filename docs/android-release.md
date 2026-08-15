# Android release runbook

## Граница безопасности

Release APK подписывается постоянным проектным ключом. Keystore и
`key.properties` находятся в
`%USERPROFILE%\.family-ai\android-signing` и никогда не копируются в Git.
Пароли не передаются параметрами Gradle и не выводятся в консоль.

Текущий сертификат Family AI Mentor:

```text
SHA-256: 4b6ea599c89e618b92600f04a4d527e0c8d4b2a446ef1bddae38365fc4951d7e
```

Fingerprint публичен и нужен для проверки идентичности релиза; паролем или
секретом он не является.

Инициализация создаёт DPAPI CurrentUser recovery-kit:

```powershell
.\scripts\mobile\Initialize-AndroidSigning.ps1
```

По умолчанию recovery-kit сохраняется в
`.dr\android-signing-kit.dpapi`. Он исключён из Git и расшифровывается только
текущей Windows-учётной записью на этом компьютере. Сам файл следует хранить
вместе с локальным DR-kit. Если Windows-профиль или компьютер будут потеряны,
одного DPAPI-файла недостаточно.

Команда не перезаписывает существующий keystore, properties или recovery-kit.
Повторная генерация нового ключа для существующего приложения запрещена:
Android не примет такой APK как обновление.

## Восстановление signing material

Если внешний каталог signing material удалён, но DPAPI-kit остался:

```powershell
.\scripts\mobile\Restore-AndroidSigning.ps1
```

Восстановление также отказывается перезаписывать существующие файлы. После него
нужно собрать APK и сравнить fingerprint сертификата с предыдущим release
manifest.

## Сборка из точного commit

Сначала commit должен существовать локально:

```powershell
git fetch origin
.\scripts\mobile\Build-AndroidRelease.ps1 -Commit <full-or-short-commit>
```

Скрипт:

1. разрешает commit в полный SHA;
2. экспортирует только отслеживаемые Git-файлы;
3. создаёт одноразовый source tree внутри `.artifacts`;
4. запускает `flutter pub get` и release build;
5. проверяет подпись и package `ru.familyai.mentor`;
6. создаёт APK, `.sha256` и JSON manifest;
7. удаляет временный source tree даже после ошибки.

Во время build скрипт также встраивает version и полный source commit через
compile-time Dart definitions. Release-приложение передаёт эту build-wide
identity Gateway без device ID; последняя замеченная сборка видна в
Admin-паспорте. Подробности — в
[`release-passport.md`](release-passport.md).

Результат находится в `.artifacts\android` и не добавляется в Git. JSON manifest
фиксирует commit, версию, SHA-256 APK и fingerprint сертификата.

Для текущего рабочего commit:

```powershell
.\scripts\mobile\Build-AndroidRelease.ps1 -Commit HEAD
```

## Первая установка вместо debug APK

Debug APK и новый release APK подписаны разными сертификатами. Android
намеренно запрещает установить release поверх debug.

1. Записать текущий адрес Gateway.
2. Удалить debug-версию приложения.
3. Установить release APK.
4. Один раз ввести адрес Gateway и дождаться успешного health-check.

История диалогов находится на Gateway и снова загрузится с сервера. Локальный
аудиокеш debug-приложения удалится.

## Последующие обновления без потери адреса

Проверить устройство и установить новый APK поверх старого:

```powershell
.\.tools\android-sdk\platform-tools\adb.exe devices
.\.tools\android-sdk\platform-tools\adb.exe install -r `
  .\.artifacts\android\family-ai-<version>-<commit>-release.apk
```

`applicationId` и release-ключ остаются одинаковыми, поэтому Android сохраняет
данные приложения, включая ручной адрес Gateway. Перед установкой следует
сравнить `signer_certificate_sha256` нового manifest с предыдущим.

Если `adb` сообщает `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, нельзя удалять
работающий release вслепую. Сначала нужно проверить, что выбран правильный APK
и signing kit.

## Проверка

Минимальный выпускной набор:

```powershell
cd mobile
..\.tools\flutter\bin\flutter.bat analyze
..\.tools\flutter\bin\flutter.bat test
cd ..
.\scripts\docs\Test-MarkdownLinks.ps1
.\scripts\mobile\Build-AndroidRelease.ps1 -Commit HEAD
```

Архитектурное решение:
[`ADR 028`](adr/028-signed-reproducible-android-releases.md).
