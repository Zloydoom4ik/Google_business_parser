# Google_business_parser

Выгружает фотографии точек Google Maps: метаданные в Postgres, файлы владельца на диск.

Работает через внутренние запросы публичных Карт (те, которыми страница точки подгружает карточку и галерею),
не через официальный Business Profile API. Обычные HTTP-запросы из Python: браузер и вход в Google не нужны.

## Запуск

```
docker compose up -d --wait
.venv\Scripts\activate
python main.py sync
python main.py status
```

Нужен Docker. Первая установка окружения:

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

## Что где

| Файл | Что делает |
|---|---|
| `places.json` | Список точек: точное название, адрес, ссылка на Картах |
| `gbp_parser/maps_client.py` | Запросы к Картам: карточка точки и список фото |
| `gbp_parser/parse.py` | Разбор ответа: id, дата, кто загрузил, размер, ссылка |
| `gbp_parser/db.py`, `schema.sql` | Таблицы `places` и `photos` |
| `gbp_parser/download.py` | Скачивание оригиналов в `data/<точка>/photos/` |
| `gbp_parser/__main__.py` | Команды `sync` и `status` |

Повторный `sync` обновляет метаданные и докачивает только новые фото владельца.
В базу попадают все фото и видео галереи с пометкой `owner` / `customer`; файлы качаются только для фото владельца.
