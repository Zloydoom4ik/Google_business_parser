# Google_business_parser

Выгружает фотографии точек Google Maps: метаданные в Postgres, файлы владельца на диск.

Работает через внутренние запросы публичных Карт (те, которыми страница точки подгружает карточку и галерею),
не через официальный Business Profile API. Обычные HTTP-запросы из Python: браузер и вход в Google не нужны.

## Запуск

```
docker compose up -d --wait
.venv\Scripts\activate
python main.py sync
python main.py sync_posts
python main.py status
```

`sync` — фотографии галереи, `sync_posts` — посты (отдельная команда, отдельная таблица `posts`, картинки в `data\<точка>\posts\`).
Карты отдают только 10 последних постов точки. Пост, выпавший из этой десятки, из базы не удаляется.

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
| `gbp_parser/maps_client.py` | Запросы к Картам: карточка точки, список фото, список постов |
| `gbp_parser/parse.py` | Разбор ответа: id, дата, кто загрузил, размер, ссылка |
| `gbp_parser/db.py`, `schema.sql` | Таблицы `places`, `photos` и `posts` |
| `gbp_parser/download.py` | Скачивание оригиналов в `data/<точка>/photos/` и `data/<точка>/posts/` |
| `gbp_parser/places.py` | Чтение `places.json` и сверка названия и адреса точки |
| `gbp_parser/posts.py` | Посты: разбор ответа и команда `sync_posts` |
| `gbp_parser/__main__.py` | Команды `sync`, `sync_posts` и `status` |

Повторный `sync` обновляет метаданные и докачивает только новые фото владельца.
Если объект пропал из списка Google, его строка удаляется из базы, а файл — с диска.
В базу попадает всё, что Google отдал списком: фото и видео с пометкой `owner` / `customer` и панорамы Street View (`google`).
Файлы качаются только для фото владельца.

## Сколько объектов выгружается: `PAGE_SIZE`

У одной и той же точки Google называет три разных количества. Пример — Fusion Repair, 20 W 30th St (`places.id = 3`):

| Что | Сколько | Где это видно |
|---|---|---|
| Счётчик Google | 127 | `places.google_claims`. Просто цифра из ответа Google, от настроек не зависит |
| Отдаётся порциями по 100 | 114 | — |
| Отдаётся порциями по 20 — столько видит человек на Картах | 100 | `places.google_listed` и число строк точки в `photos` |

- **100** — это 98 фото (95 владельца + 3 клиентских), 1 видео и 1 панорама. Файлов на диске 95.
- **Ещё 14** (до 114) — фото владельца, которые Google отдаёт только при больших порциях. На сайте Карт их не видно.
- **Ещё 13** (до 127) — не отдаются ни при каких настройках. По ним нет ни данных, ни файлов, известна только сама цифра счётчика.

Размер порции задаётся в `gbp_parser/maps_client.py`, константа `PAGE_SIZE`:

| `PAGE_SIZE` | Что выгружается |
|---|---|
| `20` (сейчас) | То же, что видит посетитель Карт: сайт сам просит по 20 |
| `100` | Всё, что Google готов отдать, включая фото, скрытые с сайта. Значения больше 100 ничего не добавляют |

После смены значения нужно запустить `python main.py sync`. При переходе с 20 на 100 недостающие фото докачаются;
при переходе обратно на 20 они удалятся из базы и с диска (правило «нет в списке — удаляем»).

Google нигде не помечает дубликаты. Точные копии находятся по совпадению `photos.file_sha256` — отпечатка скачанного файла.

## Запросы к Google и его ответы

Всё ниже — настоящие запросы и ответы при выгрузке фото точки Fusion Repair, 20 W 30th St (`places.id = 3`).
Длинные служебные куски заменены на `…`. Запросы A и B делаются один раз за запуск, C–E — на каждую точку, F — на каждый новый файл.

### A. Начать сессию

```
GET https://www.google.com/maps?hl=en
```

Ответ: `200`, HTML. Google перенаправляет на страницу согласия с куки:
`https://consent.google.com/m?continue=https://www.google.com/maps?hl=en&gl=NL&…`

### B. Ответить «Отклонить все» на форму согласия

```
POST https://consent.google.com/save
gl=NL  hl=en  continue=https://www.google.com/maps?hl=en  set_eom=true
+ служебные поля со страницы согласия: bl, escs, x, m, app, pc, src, uxe, cm
```

Ответ: `200`, возврат на `https://www.google.com/maps?hl=en`. В сессии появляются куки
`SOCS`, `__Secure-ENID`, `__Secure-BUCKET`, `SEARCH_SAMESITE`.
Без этого шага запрос E возвращает вместо галереи одну панораму.

### C. Страница точки

```
GET https://www.google.com/maps/place/Fusion+Repair/data=!4m6!3m5!1s0x89c25929d8effddf:0x36ef76158161a142!8m2!3d40.7461213!4d-73.9877555!16s%2Fg%2F11x0ds1nny?hl=en
```

Ответ: `200`, HTML около 207 КБ. Из него берётся только одна ссылка — адрес карточки точки:
`/maps/preview/place?authuser=0&hl=en&gl=nl&q=Fusion+Repair&pb=!1m21!1s0x89c25929d8effddf:0x36ef76158161a142!2sFusion+Repair!…`

### D. Карточка точки

```
GET https://www.google.com/maps/preview/place?authuser=0&hl=en&gl=nl&q=Fusion+Repair&pb=…
```

Ответ: `200`, JSON около 108 КБ, первой строкой идёт защитная приставка `)]}'`. Используются два значения:

```
[6][11] = "Fusion Repair"
[6][39] = "20 W 30th St, New York, NY 10001, United States"
```

Они сверяются с `name` и `address` из `places.json`. Не совпало — точка пропускается.

### E. Список галереи

```
POST https://www.google.com/maps/_/MapsWizUi/data/batchexecute?rpcids=hspqX&hl=en&rt=c
Content-Type: application/x-www-form-urlencoded;charset=UTF-8

f.req=[[["hspqX","<аргументы строкой>",null,"generic"]]]
```

Аргументы первого запроса:

```
[2,null,
 ["0x89c25929d8effddf:0x36ef76158161a142",null,null,null,null,null,null,null,0,null,null,null,null,null,
  [[null,null,null,"/g/11x0ds1nny"]]],
 null,
 [null,[203,100],[null,20,null,null,1],null,null,null,
  [[[1,0,3],[2,1,2],[2,0,3],[8,0,3],[10,0,3],[10,1,2],[10,0,4],[9,1,2]],1],
  null,0,null,null,null,null,null,[[[[[[2]]],[195,195],20]]]],
 null,null,null,null,null,null,null,null,null,null,
 [null,1,null,1]]
```

От запроса к запросу меняются три вещи: номер точки (`0x89c2…a142`), её второй номер (`/g/11x0ds1nny`) и блок
`[null,20,null,null,1]` — в нём `20` это `PAGE_SIZE`, а третье место — метка следующей страницы (в первом запросе `null`).
Остальное скопировано из запроса, который шлёт сама страница Карт.

Ответ — `200`, около 27 КБ на страницу, в обёртке:

```
)]}'

26846
[["wrb.fr","hspqX","[[[\"CIABIhAA3jU3tjjpRWe16FIACuEc\",10,12,null,null,null,[\"https://lh3.googleuserconten…
```

После распаковки это список: `[объекты, счётчик, …, метка следующей страницы (место 5), …]`.
Для этой точки понадобилось 6 запросов:

| Запрос | Метка страницы | Объектов в ответе | Счётчик Google |
|---|---|---|---|
| 1 | нет | 20 | 128 |
| 2–5 | из предыдущего ответа | по 20 | 127 |
| 6 | из предыдущего ответа | 0 — конец списка | 127 |

Итого 100 объектов. Счётчик между запросами может плавать на единицу.

Один объект из ответа, как его присылает Google:

```
["CIABIhAA3jU3tjjpRWe16FIACuEc",                    номер фото
 10, 12, null, null, null,                          10 = фото или видео; у панорамы на этом месте 0
 ["https://lh3.googleusercontent.com/gps-cs-s/AHRPTWlclwQc…D6PS24jq=w203-h135-k-no",   ссылка на файл (здесь превью)
  "", [6045, 4030], [203, 100]],                    исходный размер 6045×4030
 null,
 [[3, -73.9875732, 40.7464216], [0, 90], [6045, 4030], 75],                            координаты
 "fkzFavL5Gt-u7_UPxeudmA8", "0ahUKEwjysNHT…", null, null, null, null,
 [[["0x89c25929d8effddf:0x36ef76158161a142", …, [[null, null, null, "/g/11x0ds1nny"]]]]],
 null, null, null, null, null,
 [null, [10, "CIABIhAA3jU3tjjpRWe16FIACuEc"], [10, 3, [4030, 6045]], null, null, […],
  [1,                                               кто добавил: 1 владелец, 2 клиент, 3 Google
   null, null, [7, 5], null,
   [null, null, "bizbuilder:gmb_on_local_universal_desktop", [6, 7, 4, 1, 3]],          через что загружено
   null, null,
   [2025, 2, 19, 14]]],                             дата загрузки: год, месяц, день, час
 1, null, null, null, null, null, null,
 ["-8520149508763419169", "3958512432219005250"], null, "wlMZ6ECJHUg"]
```

Из него в таблицу `photos` идут: номер, тип, кто добавил, канал загрузки, дата, размер, координаты, ссылка без хвоста после `=`.
Весь объект целиком сохраняется в колонку `raw`.

### F. Файл фото

```
GET https://lh3.googleusercontent.com/gps-cs-s/AHRPTWlclwQc…D6PS24jq=s0
```

Ссылка та же, что в ответе E, только хвост `=w203-h135-k-no` заменён на `=s0` — «исходный размер».
Ответ: `200`, `image/jpeg`, 3 625 351 байт — сам файл 6045×4030. Запрос делается только для фото владельца, у которых файла ещё нет.

Команда `python show_request.py` сохраняет настоящий запрос E и ответ на него в папку `request_example\`.
