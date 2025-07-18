# ATP - TikTok Архиватор

ATP - это архиватор TikTok видео, который автоматически скачивает ваши лайкнутые видео.

А потом регулярно проверяет их доступность и публикует видео в телеграм канал/чат при удалении их из TikTok.

**Теперь вам больше никогда не придётся грустить об утрате ваших любимых видео!**

Или гадать, что это было за видео такое, которое вы сохранили, а TikTok так **бессовестно** удалил?!

## Функциональность

- Импорт видео из JSON-файла экспорта TikTok
- Автоматический импорт лайкнутых видео пользователя 
- Скачивание видео с TikTok (в т.ч. слайдшоу)
- Периодическая проверка доступности видео
- Отправка видео в Telegram при удалении их из TikTok

## Первый запуск

#### Импортируем и качаем видео из JSON выгрузки

1. Скачайте свои данные из [TikTok](https://support.tiktok.com/ru/account-and-privacy/personalized-ads-and-data/requesting-your-data#1) в формате JSON и поместите `user_data_tiktok.json` в корень проекта
2. Скопируйте `.env` файл `cp example.env .env` и измените `Настройки импорта видео` если нужно
3. Создайте пустую базу данных `touch tiktok_videos.db`
4. Убедитесь, что TikTok доступен без ограничений из вашей страны или воспользуйтесь VPN

**Видео будут скачаны в downloads/ (можно изменить `volume` в обоих compose файлах или `DOWNLOADS_DIR` в `.env`)**

### Docker
```bash
docker compose up atp-from-file -d
docker compose logs atp-from-file -f
```

### Без docker

- Установите python зависимости
- Установите `ffmpeg`
- Запустите импорт
```bash
python -m atp.import_from_file
```

##### Загрузка видео может занять много часов! (~1 час на 1000 видео) И потребует ~4GB пространства на 1000 видео

Если после окончания загрузки вы видите сообщение:
```bash
X videos with status `new` remaining
```
Можно запустить скрипт повторно и докачать _зависшие_ видео.

## Запуск проекта

1. Заполните параметры в `.env`:
   - `TIKTOK_USER` - ваш username в TikTok
   - `TELEGRAM_BOT_TOKEN` - токен вашего бота (получите у @BotFather)
   - `TELEGRAM_CHAT_ID` - ID чата/канала для отправки уведомлений
   - `TZ` - ваш часовой пояс (например, Europe/Moscow)

2. Убедитесь что ваши лайкнутые видео видно всем (в настройках приватности)

#### Вы можете поставить `DOWNLOAD_FROM_TIKTOK=false` в `.env`.
#### Тогда видео всё ещё будут проверяться на доступность, но не будут автоматически импортироваться из TikTok

### Docker (рекомендуется)

```bash
docker compose up -d
```

### Запуск без Docker

Как-то запустите browserless/chromium. Можно в докере, только его:

1. Раскомментируйте ports в compose.yaml
2. ```docker compose up -d browserless```
3. Запустите проект

```bash
python entrypoint.py
```

## Готово!
- Теперь в 00 минут каждого часа видео будут проверяться на доступность и при их удалении из TikTok, публиковаться в Telegram

(проверяется `всего_видео / 7 / 24` видео каждый час, а значит все видео будут проверяться за неделю)

- И в 30 минут каждого часа с аккаунта `TIKTOK_USER` будут импортироваться и скачиваться новые лайкнутые видео


## Устранение неполадок

### Проблемы с доступом к TikTok
Если видео не скачиваются:

0. Удалите БД если только что создали её, что бы в ней не было failed видео
1. Проверьте доступность TikTok из вашей сети
2. При необходимости настройте VPN
3. Убедитесь что ваши лайкнутые видео видно всем (в настройках приватности)

### Проблемы с Telegram
Если уведомления не отправляются:
1. Проверьте правильность `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`
2. Убедитесь, что бот добавлен в чат/канал
3. Проверьте права бота в чате/канале

## Поддержка

Если у вас возникли проблемы или есть предложения по улучшению:
- Создайте issue в репозитории
- Напишите мне в Telegram @skrepkaq
